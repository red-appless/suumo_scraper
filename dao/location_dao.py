"""
dao/location_dao.py
住所・座標キャッシュテーブル (locations) の操作を担当するモジュール。
賃貸・中古マンションの両物件種別で共有して使う。
"""


def ensure_address_exists(conn, address: str):
    """住所が locations テーブルに存在しない場合のみ INSERT する"""
    if not address:
        return
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO locations (address)
            VALUES (%s)
            ON CONFLICT (address) DO NOTHING;
        """, (address,))
    conn.commit()


def get_coordinates(conn, address: str):
    """住所に対応する座標を返す。未登録または座標なしは (None, None)"""
    if not address:
        return None, None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT latitude, longitude FROM locations WHERE address = %s;",
            (address,)
        )
        row = cur.fetchone()
    if row is None:
        return None, None
    return row[0], row[1]


def update_coordinates(conn, address: str, latitude, longitude):
    """ジオコーディング済みの座標で locations テーブルを更新する"""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE locations
            SET latitude = %s, longitude = %s
            WHERE address = %s;
        """, (latitude, longitude, address))
    conn.commit()


def get_addresses_without_coords(conn, table: str = "property_chintai") -> list[str]:
    """
    座標がまだ入っていない住所の一覧を返す。
    table: 参照する物件テーブル名 ("property_chintai" or "property_chuko")
    """
    allowed = {"property_chintai", "property_chuko"}
    if table not in allowed:
        raise ValueError(f"table は {allowed} のいずれかを指定してください")

    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT l.address
            FROM locations l
            INNER JOIN {table} p ON p.address = l.address
            WHERE p.status = 'valid'
              AND (l.latitude IS NULL OR l.longitude IS NULL);
        """)
        rows = cur.fetchall()
    return [row[0] for row in rows if row[0]]
