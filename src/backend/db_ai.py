"""
db_ai.py
・自然言語 → SQL                                            (nl2sql)
・SQL 実行して pandas.DataFrame で返す                      (run_sql)
・RAG 用：SQL 結果を整形してチャット向けテキストを作成       (sql_answer)
"""
from __future__ import annotations
import openai
import pandas as pd
import pyodbc
from io import StringIO
from sqlalchemy import create_engine  # 追加
from urllib.parse import quote_plus  # 追加
from ..config import settings

# -- OpenAI 初期化 -------------------------------------------------
openai.azure_endpoint = settings.AOAI_ENDPOINT
openai.api_key = settings.AOAI_KEY
openai.api_version = "2023-12-01-preview"

# -- SQLAlchemyエンジン作成 --------------------------------------
# settings.SQL_CONNはODBC接続文字列なので、SQLAlchemy用に変換
quoted = quote_plus(settings.SQL_CONN)
sqlalchemy_url = f"mssql+pyodbc:///?odbc_connect={quoted}"
_ENGINE = create_engine(sqlalchemy_url)

# -- SQL 接続を 1 回だけ確立（pyodbcは非推奨のためコメントアウト）
# _CN = pyodbc.connect(settings.SQL_CONN)
# _CUR = _CN.cursor()

def nl2sql(prompt: str) -> str:
    """LLM に NL→SQL を丸投げ。スキーマを System メッセージで渡す簡易版"""
    import sys
    system_msg = """
あなたは SQL 生成アシスタントです。
tourdb には以下のテーブルがあります:
- spots(spot_id,name,primary_category,lat,lon)
- stops(stop_id,route_id,stop_name,lat,lon)
- transport_routes(route_id,route_name,transport_type)
- timetables(route_id,departure_time,stop_id)
- stop_to_spot(stop_id,spot_id,walk_minutes)
【重要】
- 生成するSQLは必ず SELECT 文のみとし、他のSQL（INSERT, UPDATE, DELETE, DROP, CREATE, ALTER など）は絶対に生成しないでください。
- SQL文は必ず "SELECT" で始めてください。
- カラム名やテーブル名は上記スキーマから正確に選んでください。
- 例えばwalk_minutesで並べたい場合は、stop_to_spotテーブルとJOINしてください。
- 不明な場合は、存在しないカラムやテーブルを使わず、spot_id, name, primary_category, lat, lonなど基本的なカラムのみを使ってください。
- 改行付きで返してください。
"""
    response = openai.chat.completions.create(
        model=settings.AOAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.0
    )
    sql = response.choices[0].message.content.strip()
    if settings.DEBUG:
        print(f"[DEBUG] 生成SQL: {repr(sql)}", file=sys.stderr)
    return sql

def run_sql(sql: str) -> pd.DataFrame:
    """SQL を実行して DataFrame を返す。SELECT 以外や無効なSQLは弾かない（事前にチェック済み前提）"""
    # SQLAlchemyエンジン経由で実行
    df = pd.read_sql(sql, _ENGINE)
    return df

def extract_time_constraints(text: str) -> dict:
    """
    ユーザー入力から時間制約（例: 3時間, 半日, 一日, 何時から）を抽出し、
    {'max_minutes': int, 'start_time': 'HH:MM'} のdictで返す。
    """
    import re
    result = {}
    # 何時から
    m = re.search(r'(\d{1,2})時(\d{1,2})分?から', text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        result['start_time'] = f"{h:02d}:{mi:02d}"
    else:
        m = re.search(r'(\d{1,2})時から', text)
        if m:
            h = int(m.group(1))
            result['start_time'] = f"{h:02d}:00"
    # ●時間
    m = re.search(r'(\d{1,2})時間', text)
    if m:
        result['max_minutes'] = int(m.group(1)) * 60
    # 半日
    if '半日' in text:
        result['max_minutes'] = 240  # 4時間
    # 一日
    if '一日' in text:
        result['max_minutes'] = 480  # 8時間
    return result

def sql_answer(question: str) -> dict:
    """
    指定された要件に基づき、観光ルートを提案する。
    ・「只見線に乗る」「只見線に乗りたい」→只見線の駅間移動を含む
    ・スポット名がなければカテゴリ、なければtags/descriptionで候補抽出
    ・候補スポットから歩ける範囲の停留所/駅をstop_to_spotで探索
    ・移動手段(route_id)を使い、できるだけ多くの候補スポットを回るルートを探索
    ・各スポットの滞在時間を考慮し、日程表形式で出発時刻も含めて提案
    ・「半日」「3時間」「一日」などの時間指定があれば、その範囲内で回れるルートを提案
    ・「何時から」などの時間指定があれば、その時間を起点にルートを提案
    """
    import re
    time_constraints = extract_time_constraints(question)
    sql = nl2sql(question)
    # SQLが空や不正な場合はエラー内容をそのまま返す
    if not sql or not sql.lower().lstrip().startswith("select") or len(sql.strip()) < 10:
        return {
            "status": "error",
            "sql": sql,
            "error": "AIが有効なSQLを生成できませんでした。入力内容や条件を変えて再度お試しください。"
        }
    try:
        df = run_sql(sql)
    except Exception as e:
        return {
            "status": "error",
            "sql": sql,
            "error": f"SQL実行時にエラーが発生しました: {e}"
        }
    buf = StringIO()
    buf.write(df.head().to_markdown(index=False))
    result_md = buf.getvalue()

    # --- 時間指定の抽出 ---
    time_limit = None
    start_time = None
    # 半日/一日/3時間など
    if re.search(r'半日', question):
        time_limit = 4 * 60  # 4時間
    elif re.search(r'一日', question):
        time_limit = 8 * 60  # 8時間
    m = re.search(r'(\d+)\s*時間', question)
    if m:
        time_limit = int(m.group(1)) * 60
    # 何時から
    m2 = re.search(r'(\d{1,2})時(から|より|に)?', question)
    if m2:
        start_time = int(m2.group(1))
    # --- ルート日本語提案 ---
    route_md = ""
    # 只見線に乗る/乗りたいが含まれる場合は只見線移動を優先
    if re.search(r"只見線に乗(る|りたい)", question):
        sql_tadami = '''
        SELECT s.name, s.primary_category, st.stop_name, tr.route_name, t.departure_time, sts.walk_minutes, s.min_stay_minutes, s.base_stay_minutes
        FROM spots s
        JOIN stop_to_spot sts ON s.spot_id = sts.spot_id
        JOIN stops st ON sts.stop_id = st.stop_id
        JOIN transport_routes tr ON st.route_id = tr.route_id
        LEFT JOIN timetables t ON st.route_id = t.route_id AND st.stop_id = t.stop_id
        WHERE tr.route_name = '只見線'
        ORDER BY t.departure_time
        '''
        try:
            df_tadami = run_sql(sql_tadami)
            if not df_tadami.empty:
                # 時間制約があればフィルタ
                filtered = []
                total_minutes = 0
                prev_dep = None
                for i, row in df_tadami.iterrows():
                    stay = row.get('base_stay_minutes') or row.get('min_stay_minutes') or 30
                    walk = row.get('walk_minutes') or 0
                    dep = row.get('departure_time')
                    # 出発時刻フィルタ
                    if 'start_time' in time_constraints and dep:
                        if dep < time_constraints['start_time']:
                            continue
                    filtered.append((row, stay, walk, dep))
                # 合計所要時間計算
                for i, (row, stay, walk, dep) in enumerate(filtered):
                    total_minutes += int(stay) + int(walk)
                # 制約超過ならカット
                if 'max_minutes' in time_constraints and total_minutes > time_constraints['max_minutes']:
                    route_md += f"指定時間({time_constraints['max_minutes']//60}時間)内で回れる只見線ルートがありませんでした。\n"
                elif filtered:
                    route_md += "只見線で移動できるスポット日程例:\n"
                    for i, (row, stay, walk, dep) in enumerate(filtered):
                        spot = row.get('name', '')
                        stop = row.get('stop_name', '')
                        route_md += f"{i+1}. {spot}（最寄り: {stop}） 出発:{dep} 徒歩:{walk}分 滞在:{stay}分\n"
                    route_md += f"\nこの順に巡ることをおすすめします。合計所要時間: {total_minutes}分\n"
        except Exception:
            pass
    # スポット名/カテゴリ/タグ/説明で候補抽出
    else:
        keywords = extract_keywords(question)
        # 1. スポット名
        like_clauses = [f"name LIKE '%{kw}%' OR alt_names LIKE '%{kw}%" for kw in keywords]
        sql_spot = f"SELECT * FROM spots WHERE {' OR '.join(like_clauses)};" if like_clauses else ""
        spot_candidates = []
        if sql_spot:
            try:
                df_spot = run_sql(sql_spot)
                if not df_spot.empty:
                    spot_candidates = df_spot['spot_id'].tolist()
            except Exception:
                pass
        # 2. カテゴリ
        if not spot_candidates and keywords:
            like_cat = [f"primary_category LIKE '%{kw}%" for kw in keywords]
            sql_cat = f"SELECT spot_id FROM spots WHERE {' OR '.join(like_cat)};"
            try:
                df_cat = run_sql(sql_cat)
                if not df_cat.empty:
                    spot_candidates = df_cat['spot_id'].tolist()
            except Exception:
                pass
        # 3. tags
        if not spot_candidates and keywords:
            like_tags = [f"tags LIKE '%{kw}%" for kw in keywords]
            sql_tags = f"SELECT spot_id FROM spots WHERE {' OR '.join(like_tags)};"
            try:
                df_tags = run_sql(sql_tags)
                if not df_tags.empty:
                    spot_candidates = df_tags['spot_id'].tolist()
            except Exception:
                pass
        # 4. description
        if not spot_candidates and keywords:
            like_desc = [f"description LIKE '%{kw}%" for kw in keywords]
            sql_desc = f"SELECT spot_id FROM spots WHERE {' OR '.join(like_desc)};"
            try:
                df_desc = run_sql(sql_desc)
                if not df_desc.empty:
                    spot_candidates = df_desc['spot_id'].tolist()
            except Exception:
                pass
        # 候補スポットから歩ける範囲の停留所/駅を探索
        if spot_candidates:
            sql_stops = f"SELECT * FROM stop_to_spot WHERE spot_id IN ({', '.join([repr(s) for s in spot_candidates])});"
            try:
                df_stops = run_sql(sql_stops)
                if not df_stops.empty:
                    route_md += "スポット候補と最寄り停留所:\n"
                    for i, row in df_stops.iterrows():
                        route_md += f"- spot_id:{row['spot_id']} stop_id:{row['stop_id']} 徒歩:{row['walk_minutes']}分\n"
            except Exception:
                pass
        # ルート探索・日程表形式（簡易例）
        if spot_candidates:
            sql_routes = f'''
            SELECT s.name, st.stop_name, tr.route_name, t.departure_time, s.base_stay_minutes, s.min_stay_minutes
            FROM spots s
            JOIN stop_to_spot sts ON s.spot_id = sts.spot_id
            JOIN stops st ON sts.stop_id = st.stop_id
            JOIN transport_routes tr ON st.route_id = tr.route_id
            LEFT JOIN timetables t ON st.route_id = t.route_id AND st.stop_id = t.stop_id
            WHERE s.spot_id IN ({', '.join([repr(s) for s in spot_candidates])})
            ORDER BY t.departure_time
            '''
            try:
                df_routes = run_sql(sql_routes)
                if not df_routes.empty:
                    filtered = []
                    total_minutes = 0
                    for i, row in df_routes.iterrows():
                        stay = row.get('base_stay_minutes') or row.get('min_stay_minutes') or 30
                        dep = row.get('departure_time')
                        # 出発時刻フィルタ
                        if 'start_time' in time_constraints and dep:
                            if dep < time_constraints['start_time']:
                                continue
                        filtered.append((row, stay, dep))
                    for i, (row, stay, dep) in enumerate(filtered):
                        total_minutes += int(stay)
                    # 制約超過ならカット
                    if 'max_minutes' in time_constraints and total_minutes > time_constraints['max_minutes']:
                        route_md += f"指定時間({time_constraints['max_minutes']//60}時間)内で回れるルートがありませんでした。\n"
                    elif filtered:
                        route_md += "\n日程表例:\n"
                        for i, (row, stay, dep) in enumerate(filtered):
                            spot = row.get('name', '')
                            stop = row.get('stop_name', '')
                            route = row.get('route_name', '')
                            route_md += f"{i+1}. {spot}（{stop}）{route} 出発:{dep} 滞在:{stay}分\n"
                        route_md += f"\nこの順に巡ることをおすすめします。合計所要時間: {total_minutes}分\n"
            except Exception:
                pass
        if not route_md:
            route_md = "条件に合うルートが見つかりませんでした。条件を変えて再度お試しください。"
    return {
        "status": "ok",
        "sql": sql,
        "result_md": result_md,
        "route_md": route_md
    }

def extract_keywords(text: str) -> list[str]:
    """簡易的に日本語のキーワード（名詞）を抽出する。MeCab等がなければ空白・記号で分割。
    ひらがな・カタカナ・漢字・英数字を含む単語を抽出
    """
    import re
    # ひらがな・カタカナ・漢字・英数字を含む単語を抽出
    words = re.findall(r'[\w\u3040-\u30ff\u3400-\u9fff]+', text)
    # 2文字以上のみ返す
    return [w for w in words if len(w) > 1]
