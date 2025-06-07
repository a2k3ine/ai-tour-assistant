# --- app.py (最上部) -----------
import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
# ↑ これでリポジトリルートがパスに入る
# --------------------------------

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
