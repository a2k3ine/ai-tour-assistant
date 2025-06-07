"""
settings.py
.env を読み込み、全モジュールで共通に使う定数を公開
"""
from pathlib import Path
import os
from dotenv import load_dotenv

# ルート (2025hackathon/) の .env をロード
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

# ------------ Azure OpenAI ------------
AOAI_ENDPOINT  : str = os.getenv("AOAI_ENDPOINT", "")
AOAI_KEY       : str = os.getenv("AOAI_KEY", "")
AOAI_DEPLOYMENT: str = os.getenv("AOAI_DEPLOYMENT", "gpt-35-turbo")

# ------------ Azure SQL ---------------
SQL_CONN       : str = os.getenv("SQL_CONN", "")

# 汎用：開発モード判定など
DEBUG: bool = os.getenv("DEBUG", "0") == "1"
