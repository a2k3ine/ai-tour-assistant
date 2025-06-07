# --- パス設定ここだけ修正 ---------------------------------
import sys, pathlib
# app.py → frontend → src → プロジェクトルート と 3 階層上がる
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
# -----------------------------------------------------------

"""
Streamlit UI
"""
import streamlit as st
from src.backend.db_ai import sql_answer

st.set_page_config(page_title="Tadami Route Chat", layout="wide")

st.title("只見町観光チャットデモ")

txt = st.text_area("行きたい場所・条件を日本語で入力してください")
if st.button("検索") and txt.strip():
    with st.spinner("LLM がルートを検索中..."):
        answer = sql_answer(txt)
    st.markdown(answer, unsafe_allow_html=True)
