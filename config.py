# ============================================================
# config.py - 接続情報・APIキーの一括管理
#
# ローカル実行時: このファイルに直接値を書く
# GitHub Actions:  Secrets → 環境変数 → os.getenv() で読む
# ============================================================

import os

# --- PostgreSQL 接続設定 (Supabase 等) ---
DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME",     "suumo_db")
DB_USER     = os.getenv("DB_USER",     "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# --- Google Maps Platform API Key ---
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "YOUR_GOOGLE_MAPS_API_KEY")

# --- Gmail 送信設定 ---
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS",  "")   # 送信元 Gmail アドレス
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")  # Gmail アプリパスワード
