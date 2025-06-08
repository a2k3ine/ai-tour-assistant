import streamlit as st
st.set_page_config(page_title="Tadami Route Chat", layout="wide")

# --- パス設定ここだけ修正 ---------------------------------
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
# -----------------------------------------------------------

"""
Streamlit UI
"""

# ここでimport
from src.backend.db_ai import sql_answer

st.title("只見町観光チャットデモ")

txt = st.text_area("行きたい場所・条件を日本語で入力してください")
if st.button("検索") and txt.strip():
    with st.spinner("LLM がルートを検索中..."):
        answer = sql_answer(txt)
    if answer.get("status") == "ok":
        st.write("生成SQL:")
        st.code(answer.get("sql", ""), language="sql")
        st.write("検索結果:")
        st.markdown(answer.get("result_md", ""), unsafe_allow_html=True)
        st.write("ルート提案:")
        st.markdown(answer.get("route_md", ""), unsafe_allow_html=True)
    else:
        st.write("生成SQL:")
        st.code(answer.get("sql", ""), language="sql")
        st.error(answer.get("error", "エラーが発生しました。"))