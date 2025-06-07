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
from . import settings

# -- OpenAI 初期化 -------------------------------------------------
openai.api_type  = "azure"
openai.api_key   = settings.AOAI_KEY
openai.api_base  = settings.AOAI_ENDPOINT
openai.api_version = "2023-12-01-preview"

# -- SQL 接続を 1 回だけ確立 --------------------------------------
_CN = pyodbc.connect(settings.SQL_CONN)
_CUR = _CN.cursor()

def nl2sql(prompt: str) -> str:
    """LLM に NL→SQL を丸投げ。スキーマを System メッセージで渡す簡易版"""
    system_msg = """
あなたは SQL 生成アシスタントです。
tourdb には以下のテーブルがあります:
- spots(spot_id,name,primary_category,lat,lon)
- stops(stop_id,route_id,stop_name,lat,lon)
- transport_routes(route_id,route_name,transport_type)
- timetables(route_id,departure_time,stop_id)
- stop_to_spot(stop_id,spot_id,walk_minutes)
生成する SQL は必ず SELECT 文のみ、改行付きで返してください。
"""
    resp = openai.ChatCompletion.create(
        deployment_id=settings.AOAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.0
    )
    return resp.choices[0].message.content.strip()

def run_sql(sql: str) -> pd.DataFrame:
    """SQL を実行して DataFrame を返す。SELECT 以外は弾く"""
    if not sql.lower().lstrip().startswith("select"):
        raise ValueError("Only SELECT is allowed")
    df = pd.read_sql(sql, _CN)
    return df

def sql_answer(question: str) -> str:
    """自然文の質問 → SQL → 実行 → テキスト整形"""
    sql = nl2sql(question)
    df  = run_sql(sql)
    # 上位5件をマークダウンに
    buf = StringIO()
    buf.write(f"**生成 SQL**\n```sql\n{sql}\n```\n")
    buf.write("**結果 (上位 5 件)**\n\n")
    buf.write(df.head().to_markdown(index=False))
    return buf.getvalue()
