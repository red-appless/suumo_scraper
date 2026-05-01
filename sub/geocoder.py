"""
sub/geocoder.py
Google Geocoding API を使って住所を緯度・経度に変換するモジュール。
locations テーブルをキャッシュとして利用し、API呼び出しを最小化する。
"""

import requests
import time
import functools
import random
import numpy as np
import concurrent.futures
import threading

from dao import location_dao


def retry(tries=5, delay=5, backoff=3, exceptions=(requests.exceptions.RequestException,)):
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _tries, _delay = tries, delay
            while _tries > 1:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    print(f"エラー発生: {e}。{_delay:.1f}秒後にリトライします...")
                    time.sleep(_delay)
                    _tries -= 1
                    _delay *= backoff
            return func(*args, **kwargs)
        return wrapper
    return deco


GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"


@retry(tries=5, delay=5, backoff=3, exceptions=(requests.exceptions.RequestException,))
def _call_geocoding_api(address: str, api_key: str):
    params = {"address": address, "key": api_key, "language": "ja"}
    response = requests.get(GEOCODING_URL, params=params, timeout=10)
    response.raise_for_status()
    result = response.json()
    if result['status'] == 'OK' and result['results']:
        loc = result['results'][0]['geometry']['location']
        lat = loc['lat']
        lng = loc['lng']
        return (
            None if np.isnan(float(lat)) else lat,
            None if np.isnan(float(lng)) else lng,
        )
    elif result['status'] == 'ZERO_RESULTS':
        return None, None
    else:
        raise requests.exceptions.RequestException(
            f"Geocoding APIエラー: {result.get('error_message', result['status'])}"
        )


class GeocodingProcessor:
    """
    DB (locations テーブル) をキャッシュとして利用するジオコーディング処理クラス。
    table: 参照する物件テーブル名 ("property_chintai" or "property_chuko")
    """

    def __init__(self, api_key: str, table: str = "property_chintai"):
        self.api_key = api_key
        self.table = table

    def process_geocoding(self, conn) -> int:
        if not self.api_key or self.api_key == "YOUR_GOOGLE_MAPS_API_KEY":
            print("\n【警告】GOOGLE_MAPS_API_KEY が未設定のためジオコーディングをスキップします。")
            return 0

        addresses = location_dao.get_addresses_without_coords(conn, table=self.table)
        total = len(addresses)

        if total == 0:
            print("  - ジオコーディングが必要な住所はありません（全てキャッシュ済み）。")
            return 0

        print(f"\n--- 📍 ジオコーディング開始: {total}件の住所を処理します ---")
        api_call_count = 0
        db_lock = threading.Lock()

        def _process_address(address):
            time.sleep(random.uniform(0.1, 0.5))
            try:
                lat, lng = _call_geocoding_api(address, self.api_key)
                with db_lock:
                    location_dao.update_coordinates(conn, address, lat, lng)
                return address, lat, lng, None
            except Exception as e:
                return address, None, None, e

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(_process_address, addr): addr for addr in addresses}
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                addr = futures[future]
                _, lat, lng, error = future.result()
                if error:
                    print(f"  [{i+1}/{total}] 【エラー】'{addr}': {error}")
                elif lat is not None:
                    api_call_count += 1
                    print(f"  [{i+1}/{total}] ✅ {addr} → ({lat:.6f}, {lng:.6f})")
                else:
                    print(f"  [{i+1}/{total}] ⚠️  {addr} → 座標取得失敗 (ZERO_RESULTS)")

        print(f"--- ジオコーディング完了: APIコール {api_call_count}回 ---")
        return api_call_count
