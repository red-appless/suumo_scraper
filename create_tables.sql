-- ============================================================
-- create_tables.sql
-- SUUMO スクレイパー用テーブル初期化スクリプト
--
-- 実行順序:
--   1. locations          （住所・座標キャッシュ）
--   2. property_chintai   （賃貸物件）
--   3. property_chuko     （中古マンション）
--   ※ property_chintai / property_chuko は locations に対して
--      外部キーを持つため、locations を先に作成すること。
-- ============================================================


-- ------------------------------------------------------------
-- 1. locations（住所・座標キャッシュ）
--    賃貸・中古マンション両方で共有するジオコーディング結果テーブル。
--    address を PRIMARY KEY にすることで重複登録を防ぐ。
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    address    VARCHAR(255) PRIMARY KEY,
    latitude   NUMERIC(10, 7),
    longitude  NUMERIC(10, 7),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ------------------------------------------------------------
-- 2. property_chintai（賃貸物件）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS property_chintai (
    room_code       VARCHAR(50)  PRIMARY KEY,
    status          VARCHAR(20)  DEFAULT 'valid',   -- 'valid' | 'old'
    category        VARCHAR(50),
    building_name   VARCHAR(255),
    address         VARCHAR(255),

    -- 最寄駅（最大3路線）
    station1_access VARCHAR(100),
    station1_min    NUMERIC(8, 2),
    station2_access VARCHAR(100),
    station2_min    NUMERIC(8, 2),
    station3_access VARCHAR(100),
    station3_min    NUMERIC(8, 2),

    -- 築年数・階数
    age_str         VARCHAR(50),
    age_years       INTEGER,
    floors_str      VARCHAR(50),
    room_floor      VARCHAR(50),

    -- 賃料
    rent_man        NUMERIC(8, 2),
    admin_fee_man   NUMERIC(8, 2),
    deposit_month   NUMERIC(8, 2),
    gratuity_month  NUMERIC(8, 2),

    -- 部屋情報
    floor_plan      VARCHAR(50),
    area_m2         NUMERIC(8, 2),
    room_url        TEXT,

    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_property_chintai_address
        FOREIGN KEY (address)
        REFERENCES locations(address)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chintai_status  ON property_chintai(status);
CREATE INDEX IF NOT EXISTS idx_chintai_address ON property_chintai(address);
CREATE INDEX IF NOT EXISTS idx_chintai_rent    ON property_chintai(rent_man);


-- ------------------------------------------------------------
-- 3. property_chuko（中古マンション）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS property_chuko (
    property_code    VARCHAR(50)  PRIMARY KEY,
    status           VARCHAR(20)  DEFAULT 'valid',  -- 'valid' | 'old'
    building_name    VARCHAR(255),
    address          VARCHAR(255),

    -- 価格・面積
    price_man        NUMERIC(10, 2),
    area_m2          NUMERIC(8, 2),
    balcony_m2       NUMERIC(8, 2),
    floor_plan       VARCHAR(50),

    -- 最寄駅
    station1_access  VARCHAR(100),
    station1_min     NUMERIC(8, 2),

    -- 築年数・階数
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

CREATE INDEX IF NOT EXISTS idx_chuko_status  ON property_chuko(status);
CREATE INDEX IF NOT EXISTS idx_chuko_address ON property_chuko(address);
CREATE INDEX IF NOT EXISTS idx_chuko_price   ON property_chuko(price_man);
