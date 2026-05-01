"""
main_chintai.py
賃貸物件版のワークフロー制御。

処理フロー:
1. DB接続・テーブル初期化
2. 全物件ステータスを 'old' に一括更新
3. スクレイピング＆フィルタリング
4. DB への住所登録 (locations) ＆ 物件 upsert (property_chintai)
5. ジオコーディング
6. HTML マップ生成
7. Gmail 通知
"""

import argparse
import sys
import time

from dao.db_connection import get_connection, initialize_tables
from dao import property_chintai_dao as property_dao, location_dao
from sub.chintai_scraper import ChintaiScraper
from sub.geocoder import GeocodingProcessor
from sub.generate_chintai_map import generate_map_html
from sub.notifier import notify_completion
from config import GOOGLE_MAPS_API_KEY

MAX_PAGE = 2000


def setup_arg_parser():
    parser = argparse.ArgumentParser(
        description='SUUMOの賃貸物件情報をスクレイピングし、DBに保存してマップを生成する'
    )
    parser.add_argument('--urls', type=str,
        default='https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&sngz=&ta=14&sa=02&page={}',
        help='スクレイピング対象のSUUMO URL ({}=ページ番号)')
    parser.add_argument('--max_rent',   type=float, default=30.0,  help='家賃+管理費の最大値 (万円)')
    parser.add_argument('--max_age',    type=int,   default=30,    help='築年数の最大値 (年)')
    parser.add_argument('--min_m2',     type=float, default=20.0,  help='面積の最小値 (m2)')
    parser.add_argument('--max_access', type=int,   default=30,    help='最寄駅アクセス時間の最大値 (分)')
    parser.add_argument('--api_key',    type=str,   default=None,  help='Google Maps Platform API Key')
    parser.add_argument('--email',      type=str,   default=None,  help='通知送信先メールアドレス')
    parser.add_argument('--output',     type=str,   default=None,  help='HTML出力パス')
    return parser.parse_args()


def main():
    start_all = time.time()
    args = setup_arg_parser()

    api_key  = args.api_key or GOOGLE_MAPS_API_KEY
    url_list = [u.strip() for u in args.urls.split(',') if u.strip()]

    filters = {
        '家賃_万円':          {'max': args.max_rent},
        '築年数_年':          {'max': args.max_age},
        '面積_m2':           {'min': args.min_m2},
        '最寄駅1_アクセス_分': {'max': args.max_access},
    }

    print("\n=== フェーズ 1: DB 初期化 ===")
    try:
        conn = get_connection()
    except Exception as e:
        print(f"【致命的エラー】DB への接続に失敗しました: {e}")
        sys.exit(1)
    initialize_tables(conn)

    print("\n=== フェーズ 2: スクレイピング前処理 ===")
    property_dao.mark_all_as_old(conn)

    print("\n=== フェーズ 3: スクレイピング ===")
    scraper = ChintaiScraper(url_templates=url_list, max_page=MAX_PAGE)
    df_raw = scraper.scrape_and_clean()

    if df_raw.empty:
        print("スクレイピング結果が空のため処理を終了します。")
        conn.close()
        return

    df_filtered = scraper.filter_data(df_raw, filters)
    if df_filtered.empty:
        print("フィルタリング後のデータが空のため処理を終了します。")
        conn.close()
        return

    print(f"\n=== フェーズ 4: DB 保存 ({len(df_filtered)}件) ===")
    new_count = update_count = 0
    for _, row in df_filtered.iterrows():
        row_dict = row.to_dict()
        address = row_dict.get('住所')
        if address and address != 'N/A':
            location_dao.ensure_address_exists(conn, address)
        is_new = property_dao.upsert_property(conn, row_dict)
        if is_new:
            new_count += 1
        else:
            update_count += 1
    print(f"  - 新規追加: {new_count}件 / 更新: {update_count}件")

    print("\n=== フェーズ 5: ジオコーディング ===")
    geocoder = GeocodingProcessor(api_key=api_key, table="property_chintai")
    geocoder.process_geocoding(conn)

    print("\n=== フェーズ 6: HTML マップ生成 ===")
    map_html = generate_map_html(conn, api_key=api_key, output_path=args.output)

    conn.close()

    print("\n=== フェーズ 7: 通知 ===")
    if map_html:
        notify_completion(
            property_type="chintai",
            count=len(df_filtered),
            map_html_path=map_html,
            to_email=args.email,
        )

    elapsed = time.time() - start_all
    print(f"\n{'='*44}")
    print(f"全ての処理が完了しました")
    print(f"総実行時間: {elapsed:.2f}秒")
    if map_html:
        print(f"▶ 生成されたマップ: {map_html}")
    print(f"{'='*44}")


if __name__ == "__main__":
    main()
