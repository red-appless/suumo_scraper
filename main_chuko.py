"""
main_chuko.py
中古マンション版のワークフロー制御。

処理フロー:
1. DB接続・テーブル初期化
2. 全中古物件ステータスを 'old' に一括更新
3. スクレイピング＆フィルタリング (ChukoScraper)
4. DB への住所登録 (locations) ＆ 物件 upsert (property_chuko)
5. ジオコーディング
6. HTML マップ生成
7. Gmail 通知
"""

import argparse
import sys
import time
import pandas as pd

from dao.db_connection import get_connection, initialize_tables
from dao import property_chuko_dao as chuko_property_dao, location_dao
from sub.chuko_scraper import ChukoScraper
from sub.geocoder import GeocodingProcessor
from sub.generate_chuko_map import generate_map_html
from sub.notifier import notify_completion
from config import GOOGLE_MAPS_API_KEY

MAX_PAGE = 2000


def setup_arg_parser():
    parser = argparse.ArgumentParser(
        description='SUUMOの中古マンション情報をスクレイピングし、DBに保存してマップを生成する'
    )
    # 東京都 中古マンション全域
    _URL_TOKYO    = ('https://suumo.jp/jj/bukken/ichiran/JJ012FC002/?ar=030&bknlistmodeflg=2&bs=011'
                     '&cn=9999999&cnb=0&ekTjCd=&ekTjNm=&kb=1&kt=9999999&mb=0&mt=9999999'
                     '&ta=13&tj=0&po=0&pj=1&pc=100&pn={}')
    # 神奈川県 主要エリア 中古マンション
    _URL_KANAGAWA = ('https://suumo.jp/jj/bukken/ichiran/JJ012FC002/?ar=030&bs=011&ta=14'
                     '&bknlistmodeflg=2&cn=9999999&cnb=0&kb=1&kt=9999999&mb=0&mt=9999999'
                     '&pc=100&pj=1&po=0&tj=0&pn={}')
    parser.add_argument('--urls', type=str,
        default=f'{_URL_TOKYO},{_URL_KANAGAWA}',
        help='スクレイピング対象の SUUMO URL ({}=ページ番号、カンマ区切りで複数指定可)')
    parser.add_argument('--max_price',  type=float, default=10000.0, help='価格上限 (万円)')
    parser.add_argument('--max_age',    type=int,   default=40,      help='築年数上限 (年)')
    parser.add_argument('--min_area',   type=float, default=20.0,    help='専有面積下限 (m²)')
    parser.add_argument('--max_toho',   type=int,   default=30,      help='最寄駅徒歩上限 (分)')
    parser.add_argument('--min_floor',  type=int,   default=1,       help='所在階下限')
    parser.add_argument('--api_key',    type=str,   default=None,    help='Google Maps API Key')
    parser.add_argument('--email',      type=str,   default=None,    help='通知送信先メールアドレス')
    parser.add_argument('--output',     type=str,   default=None,    help='HTML出力パス')
    return parser.parse_args()


def main():
    start_all = time.time()
    args = setup_arg_parser()

    api_key  = args.api_key or GOOGLE_MAPS_API_KEY
    url_list = [u.strip() for u in args.urls.split(',') if u.strip()]

    filters = {
        '価格_万円':    {'max': args.max_price},
        '築年数_年':    {'max': args.max_age},
        '専有面積_m2':  {'min': args.min_area},
        '最寄駅_分':    {'max': args.max_toho},
    }
    if args.min_floor > 1:
        filters['所在階_数値'] = {'min': args.min_floor}

    print("\n=== フェーズ 1: DB 初期化 ===")
    try:
        conn = get_connection()
    except Exception as e:
        print(f"【致命的エラー】DB接続失敗: {e}")
        sys.exit(1)
    initialize_tables(conn)

    print("\n=== フェーズ 2: スクレイピング前処理 ===")
    chuko_property_dao.mark_all_as_old(conn)

    print("\n=== フェーズ 3: スクレイピング ===")
    scraper = ChukoScraper(url_templates=url_list, max_page=MAX_PAGE)
    df_raw = scraper.scrape_and_clean()

    if df_raw.empty:
        print("スクレイピング結果が空のため終了します。")
        conn.close()
        return

    df_filtered = scraper.filter_data(df_raw, filters)
    if df_filtered.empty:
        print("フィルタリング後のデータが空のため終了します。")
        conn.close()
        return

    print(f"\n=== フェーズ 4: DB 保存 ({len(df_filtered)}件) ===")
    new_count = update_count = 0
    for _, row in df_filtered.iterrows():
        row_dict = row.where(pd.notnull(row), None).to_dict()
        address = row_dict.get('住所')
        if address and address != 'N/A':
            location_dao.ensure_address_exists(conn, address)
        is_new = chuko_property_dao.upsert_property(conn, row_dict)
        if is_new:
            new_count += 1
        else:
            update_count += 1
    print(f"  - 新規追加: {new_count}件 / 更新: {update_count}件")

    print("\n=== フェーズ 5: ジオコーディング ===")
    geocoder = GeocodingProcessor(api_key=api_key, table="property_chuko")
    geocoder.process_geocoding(conn)

    print("\n=== フェーズ 6: マップ生成 ===")
    map_html = generate_map_html(conn, api_key=api_key, output_path=args.output)

    conn.close()

    print("\n=== フェーズ 7: 通知 ===")
    if map_html:
        notify_completion(
            property_type="chuko",
            count=len(df_filtered),
            map_html_path=map_html,
            to_email=args.email,
        )

    elapsed = time.time() - start_all
    print(f"\n{'='*44}")
    print(f"全処理完了 (総実行時間: {elapsed:.2f}秒)")
    if map_html:
        print(f"▶ 生成されたマップ: {map_html}")
    print(f"{'='*44}")


if __name__ == '__main__':
    main()
