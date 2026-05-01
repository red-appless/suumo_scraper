"""
dao/property_dao.py
賃貸物件テーブル (property_chintai) の操作を担当するモジュール。
"""

import math


def _to_db_val(val):
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, str) and val.strip() in ('', 'N/A', 'nan'):
        return None
    return val


def mark_all_as_old(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE property_chintai SET status = 'old';")
    conn.commit()
    print("  - 全物件ステータスを 'old' に更新しました")


def upsert_property(conn, row_dict: dict) -> bool:
    """
    物件を INSERT または UPDATE する。
    Returns: True=新規追加、False=既存更新
    """
    sql = """
        INSERT INTO property_chintai (
            room_code, status, category, building_name, address,
            station1_access, station1_min,
            station2_access, station2_min,
            station3_access, station3_min,
            age_str, age_years, floors_str, room_floor,
            rent_man, admin_fee_man, deposit_month, gratuity_month,
            floor_plan, area_m2, room_url,
            updated_at
        ) VALUES (
            %(room_code)s, 'valid', %(category)s, %(building_name)s, %(address)s,
            %(station1_access)s, %(station1_min)s,
            %(station2_access)s, %(station2_min)s,
            %(station3_access)s, %(station3_min)s,
            %(age_str)s, %(age_years)s, %(floors_str)s, %(room_floor)s,
            %(rent_man)s, %(admin_fee_man)s, %(deposit_month)s, %(gratuity_month)s,
            %(floor_plan)s, %(area_m2)s, %(room_url)s,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (room_code) DO UPDATE SET
            status          = 'valid',
            category        = EXCLUDED.category,
            building_name   = EXCLUDED.building_name,
            address         = EXCLUDED.address,
            station1_access = EXCLUDED.station1_access,
            station1_min    = EXCLUDED.station1_min,
            station2_access = EXCLUDED.station2_access,
            station2_min    = EXCLUDED.station2_min,
            station3_access = EXCLUDED.station3_access,
            station3_min    = EXCLUDED.station3_min,
            age_str         = EXCLUDED.age_str,
            age_years       = EXCLUDED.age_years,
            floors_str      = EXCLUDED.floors_str,
            room_floor      = EXCLUDED.room_floor,
            rent_man        = EXCLUDED.rent_man,
            admin_fee_man   = EXCLUDED.admin_fee_man,
            deposit_month   = EXCLUDED.deposit_month,
            gratuity_month  = EXCLUDED.gratuity_month,
            floor_plan      = EXCLUDED.floor_plan,
            area_m2         = EXCLUDED.area_m2,
            room_url        = EXCLUDED.room_url,
            updated_at      = CURRENT_TIMESTAMP
        RETURNING (xmax = 0) AS is_new_row;
    """
    params = {
        'room_code':       _to_db_val(row_dict.get('部屋コード')),
        'category':        _to_db_val(row_dict.get('カテゴリ')),
        'building_name':   _to_db_val(row_dict.get('建物名')),
        'address':         _to_db_val(row_dict.get('住所')),
        'station1_access': _to_db_val(row_dict.get('最寄駅1_アクセス')),
        'station1_min':    _to_db_val(row_dict.get('最寄駅1_アクセス_分')),
        'station2_access': _to_db_val(row_dict.get('最寄駅2_アクセス')),
        'station2_min':    _to_db_val(row_dict.get('最寄駅2_アクセス_分')),
        'station3_access': _to_db_val(row_dict.get('最寄駅3_アクセス')),
        'station3_min':    _to_db_val(row_dict.get('最寄駅3_アクセス_分')),
        'age_str':         _to_db_val(row_dict.get('築年数')),
        'age_years':       _to_db_val(row_dict.get('築年数_年')),
        'floors_str':      _to_db_val(row_dict.get('階数')),
        'room_floor':      _to_db_val(row_dict.get('部屋_階')),
        'rent_man':        _to_db_val(row_dict.get('家賃_万円')),
        'admin_fee_man':   _to_db_val(row_dict.get('管理費_万円')),
        'deposit_month':   _to_db_val(row_dict.get('敷金_ヶ月')),
        'gratuity_month':  _to_db_val(row_dict.get('礼金_ヶ月')),
        'floor_plan':      _to_db_val(row_dict.get('部屋_間取り')),
        'area_m2':         _to_db_val(row_dict.get('面積_m2')),
        'room_url':        _to_db_val(row_dict.get('部屋_URL')),
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        result = cur.fetchone()
    conn.commit()
    return bool(result and result[0])


def get_properties_aggregated_by_building(conn) -> list[dict]:
    """住所＋正規化済みマンション名でグループ化し、建物単位に集約した物件データを返す"""
    FW_FROM = (
        'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ'
        'ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
        '０１２３４５６７８９'
    )
    FW_TO = (
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        'abcdefghijklmnopqrstuvwxyz'
        '0123456789'
    )
    sql = f"""
    WITH normalized AS (
        SELECT
            p.*,
            l.latitude::float  AS latitude,
            l.longitude::float AS longitude,
            NULLIF(
                regexp_replace(COALESCE(p.room_floor, ''), '[^0-9]', '', 'g'),
                ''
            )::integer AS floor_num,
            lower(
                regexp_replace(
                    translate(
                        COALESCE(p.building_name, ''),
                        '{FW_FROM}',
                        '{FW_TO}'
                    ),
                    '[\\u3000 \\t・ー\\-－–—･]',
                    '',
                    'g'
                )
            ) AS norm_building
        FROM property_chintai p
        INNER JOIN locations l ON l.address = p.address
        WHERE p.status    = 'valid'
          AND l.latitude  IS NOT NULL
          AND l.longitude IS NOT NULL
    )
    SELECT
        address,
        norm_building,
        MIN(building_name)                                           AS building_name,
        AVG(latitude)                                                AS latitude,
        AVG(longitude)                                               AS longitude,
        COUNT(*)                                                     AS count,
        MIN(rent_man + COALESCE(admin_fee_man, 0))                   AS min_rent_total,
        MAX(rent_man + COALESCE(admin_fee_man, 0))                   AS max_rent_total,
        jsonb_agg(
            jsonb_build_object(
                'room_code',      room_code,
                'building_name',  building_name,
                'floor_plan',     floor_plan,
                'area_m2',        area_m2,
                'rent_man',       rent_man,
                'admin_fee_man',  COALESCE(admin_fee_man, 0),
                'rent_total',     rent_man + COALESCE(admin_fee_man, 0),
                'room_floor',     room_floor,
                'floor_num',      floor_num,
                'age_years',      age_years,
                'station1_min',   station1_min,
                'station1_access',station1_access,
                'room_url',       room_url
            )
            ORDER BY floor_num DESC NULLS LAST,
                     (rent_man + COALESCE(admin_fee_man, 0)) ASC NULLS LAST
        ) AS properties
    FROM normalized
    GROUP BY address, norm_building
    ORDER BY MIN(rent_man + COALESCE(admin_fee_man, 0)) ASC NULLS LAST;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]
