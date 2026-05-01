"""
dao/db_connection.py
共通DB接続管理とテーブル初期化を担当するモジュール。
賃貸(property_chintai) と 中古マンション(property_chuko) の両テーブルを管理する。
"""

import psycopg2
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


def get_connection():
    """PostgreSQL への接続を返す"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def initialize_tables(conn):
    """
    必要なテーブルとインデックスを初期化する（存在しない場合のみ作成）。
    スクリプト起動時に一度だけ呼び出す。
    """
    with conn.cursor() as cur:

        # 1. 住所・座標キャッシュテーブル（両物件種別で共有）
        cur.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                address    VARCHAR(255) PRIMARY KEY,
                latitude   NUMERIC(10, 7),
                longitude  NUMERIC(10, 7),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. 賃貸物件テーブル
        cur.execute("""
            CREATE TABLE IF NOT EXISTS property_chintai (
                room_code      VARCHAR(50)  PRIMARY KEY,
                status         VARCHAR(20)  DEFAULT 'valid',
                category       VARCHAR(50),
                building_name  VARCHAR(255),
                address        VARCHAR(255),
                station1_access VARCHAR(100),
                station1_min    NUMERIC(8, 2),
                station2_access VARCHAR(100),
                station2_min    NUMERIC(8, 2),
                station3_access VARCHAR(100),
                station3_min    NUMERIC(8, 2),
                age_str        VARCHAR(50),
                age_years      INTEGER,
                floors_str     VARCHAR(50),
                room_floor     VARCHAR(50),
                rent_man       NUMERIC(8, 2),
                admin_fee_man  NUMERIC(8, 2),
                deposit_month  NUMERIC(8, 2),
                gratuity_month NUMERIC(8, 2),
                floor_plan     VARCHAR(50),
                area_m2        NUMERIC(8, 2),
                room_url       TEXT,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_property_chintai_address
                    FOREIGN KEY (address)
                    REFERENCES locations(address)
                    ON DELETE SET NULL
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chintai_status  ON property_chintai(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chintai_address ON property_chintai(address);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chintai_rent    ON property_chintai(rent_man);")

        # 3. 中古マンション物件テーブル
        cur.execute("""
            CREATE TABLE IF NOT EXISTS property_chuko (
                property_code    VARCHAR(50)  PRIMARY KEY,
                status           VARCHAR(20)  DEFAULT 'valid',
                building_name    VARCHAR(255),
                address          VARCHAR(255),
                price_man        NUMERIC(10, 2),
                area_m2          NUMERIC(8, 2),
                balcony_m2       NUMERIC(8, 2),
                floor_plan       VARCHAR(50),
                station1_access  VARCHAR(100),
                station1_min     NUMERIC(8, 2),
                built_year_month VARCHAR(50),
                age_years        INTEGER,
                room_floor       VARCHAR(50),
                floor_num        INTEGER,
                room_url         TEXT,
                updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_property_chuko_address
                    FOREIGN KEY (address)
                    REFERENCES locations(address)
                    ON DELETE SET NULL
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chuko_status  ON property_chuko(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chuko_address ON property_chuko(address);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chuko_price   ON property_chuko(price_man);")

    conn.commit()
    print("  - DBテーブルの初期化完了（locations / property_chintai / property_chuko）")
