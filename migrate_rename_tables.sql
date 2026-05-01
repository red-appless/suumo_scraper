-- ============================================================
-- migrate_rename_tables.sql
-- 既存の PostgreSQL (suumo_db) でテーブル名を変更する
--
-- 実行方法:
--   psql -h localhost -U postgres -d suumo_db -f migrate_rename_tables.sql
--
-- または Supabase の SQL Editor に貼り付けて実行
-- ============================================================

BEGIN;

-- 1. 賃貸物件テーブル: properties → property_chintai
ALTER TABLE IF EXISTS properties RENAME TO property_chintai;

-- インデックス名も揃える（任意）
ALTER INDEX IF EXISTS idx_properties_status  RENAME TO idx_chintai_status;
ALTER INDEX IF EXISTS idx_properties_address RENAME TO idx_chintai_address;
ALTER INDEX IF EXISTS idx_properties_rent    RENAME TO idx_chintai_rent;

-- 外部キー制約名も更新（任意）
ALTER TABLE property_chintai
    RENAME CONSTRAINT fk_properties_address TO fk_property_chintai_address;


-- 2. 中古マンションテーブル: chuko_properties → property_chuko
ALTER TABLE IF EXISTS chuko_properties RENAME TO property_chuko;

-- インデックス名も揃える（任意）
ALTER INDEX IF EXISTS idx_chuko_status  RENAME TO idx_chuko_status;
ALTER INDEX IF EXISTS idx_chuko_address RENAME TO idx_chuko_address;
ALTER INDEX IF EXISTS idx_chuko_price   RENAME TO idx_chuko_price;

-- 外部キー制約名も更新（任意）
ALTER TABLE property_chuko
    RENAME CONSTRAINT fk_chuko_address TO fk_property_chuko_address;


COMMIT;

-- 確認用クエリ
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
