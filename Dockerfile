FROM python:3.11-slim

# 必要なシステムパッケージをインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        unixodbc-dev \
        freetds-dev \
        && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリを作成
WORKDIR /app

# Pythonパッケージのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリのソースコードをコピー
COPY . .

# ポート指定（Streamlitのデフォルト）
EXPOSE 8501

# Streamlitアプリの起動コマンド
CMD ["streamlit", "run", "src/frontend/app.py", "--server.port=8501", "--server.address=0.0.0.0"]