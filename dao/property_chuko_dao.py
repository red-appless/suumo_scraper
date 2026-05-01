"""
dao/chuko_property_dao.py
中古マンション物件テーブル (property_chuko) の操作を担当するモジュール。
"""

import math


def _to_db_val(val):
    """NaN / 'N/A' / 空文字列 などを None (SQL NULL) に正規化する"""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, str) and val.strip() in ('', 'N/A', 'nan'):
        return None
    return val


def mark_all_as_old(conn):
    """スクレイピング開始時に全中古物件を 'old' に更新する"""
    with conn.cursor() as cur:
        cur.execute("UPDATE property_chuko SET status = 'old';")
    conn.commit()
    print("  - 全中古物件ステータスを 'old' に更新しました")


def upsert_property(conn, row_dict: dict) -> bool:
    """
    中古マンション物件を INSERT または UPDATE する。
    Returns: True=新規追加、False=既存更新
    """
    sql = """
        INSERT INTO property_chuko (
            property_code, status, building_name, address,
            price_man, area_m2, balcony_m2, floor_plan,
            station1_access, station1_min,
            built_year_month, age_years,
            room_floor, floor_num,
            room_url, updated_at
        ) VALUES (
            %(property_code)s, 'valid', %(building_name)s, %(address)s,
            %(price_man)s, %(area_m2)s, %(balcony_m2)s, %(floor_plan)s,
            %(station1_access)s, %(station1_min)s,
            %(built_year_month)s, %(age_years)s,
            %(room_floor)s, %(floor_num)s,
            %(room_url)s, CURRENT_TIMESTAMP
        )
        ON CONFLICT (property_code) DO UPDATE SET
            status           = 'valid',
            building_name    = EXCLUDED.building_name,
            address          = EXCLUDED.address,
            price_man        = EXCLUDED.price_man,
            area_m2          = EXCLUDED.area_m2,
            balcony_m2       = EXCLUDED.balcony_m2,
            floor_plan       = EXCLUDED.floor_plan,
            station1_access  = EXCLUDED.station1_access,
            station1_min     = EXCLUDED.station1_min,
            built_year_month = EXCLUDED.built_year_month,
            age_years        = EXCLUDED.age_years,
            room_floor       = EXCLUDED.room_floor,
            floor_num        = EXCLUDED.floor_num,
            room_url         = EXCLUDED.room_url,
            updated_at       = CURRENT_TIMESTAMP
        RETURNING (xmax = 0) AS is_new_row;
    """
    params = {
        'property_code':    _to_db_val(row_dict.get('物件コード')),
        'building_name':    _to_db_val(row_dict.get('建物名')),
        'address':          _to_db_val(row_dict.get('住所')),
        'price_man':        _to_db_val(row_dict.get('価格_万円')),
        'area_m2':          _to_db_val(row_dict.get('専有面積_m2')),
        'balcony_m2':       _to_db_val(row_dict.get('バルコニー_m2')),
        'floor_plan':       _to_db_val(row_dict.get('間取り')),
        'station1_access':  _to_db_val(row_dict.get('最寄駅_アクセス')),
        'station1_min':     _to_db_val(row_dict.get('最寄駅_分')),
        'built_year_month': _to_db_val(row_dict.get('築年月')),
        'age_years':        _to_db_val(row_dict.get('築年数_年')),
        'room_floor':       _to_db_val(row_dict.get('所在階')),
        'floor_num':        _to_db_val(row_dict.get('所在階_数値')),
        'room_url':         _to_db_val(row_dict.get('物件URL')),
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        result = cur.fetchone()
    conn.commit()
    return bool(result and result[0])


def get_properties_aggregated_by_address(conn) -> list[dict]:
    """
    status='valid' かつ座標済みの中古物件を、住所単位で集約して返す。
    """
    sql = """
        SELECT
            l.address,
            l.latitude,
            l.longitude,
            MIN(p.building_name)  AS building_name,
            MIN(p.price_man)      AS min_price_man,
            MAX(p.price_man)      AS max_price_man,
            COUNT(*)              AS count,
            jsonb_agg(
                jsonb_build_object(
                    'property_code',    p.property_code,
                    'building_name',    p.building_name,
                    'floor_plan',       p.floor_plan,
                    'area_m2',          p.area_m2,
                    'price_man',        p.price_man,
                    'room_floor',       p.room_floor,
                    'floor_num',        p.floor_num,
                    'station1_access',  p.station1_access,
                    'station1_min',     p.station1_min,
                    'built_year_month', p.built_year_month,
                    'age_years',        p.age_years,
                    'room_url',         p.room_url
                )
                ORDER BY
                    p.floor_num   DESC NULLS LAST,
                    p.price_man   ASC  NULLS LAST
            ) AS properties
        FROM property_chuko p
        INNER JOIN locations l ON l.address = p.address
        WHERE p.status    = 'valid'
          AND l.latitude  IS NOT NULL
          AND l.longitude IS NOT NULL
        GROUP BY l.address, l.latitude, l.longitude
        ORDER BY MIN(p.price_man) ASC NULLS LAST;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]
