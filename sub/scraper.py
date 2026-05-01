"""
sub/scraper.py
SUUMOから賃貸物件情報をスクレイピングし、一次クレンジングを行うモジュール。
"""

import requests
import time
from bs4 import BeautifulSoup
import urllib.parse
import pandas as pd
import numpy as np
import functools
import re
import math
import random
import concurrent.futures


def retry(tries=3, delay=10, backoff=2, exceptions=(Exception,)):
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _tries, _delay = tries, delay
            while _tries > 1:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    print(f"エラー発生: {e}。{_delay}秒後にリトライします...")
                    time.sleep(_delay)
                    _tries -= 1
                    _delay *= backoff
            return func(*args, **kwargs)
        return wrapper
    return deco


def clean_price(price_str):
    if not isinstance(price_str, str) or 'N/A' in price_str:
        return np.nan
    try:
        return float(price_str.replace('万円', '').strip())
    except Exception:
        return np.nan


def clean_deposit_gratuity(price_str):
    if not isinstance(price_str, str) or 'N/A' in price_str or 'なし' in price_str or '-' in price_str:
        return 0.0
    try:
        return float(re.sub(r'[^0-9.]', '', price_str))
    except Exception:
        return np.nan


def clean_age(age_str):
    if not isinstance(age_str, str) or 'N/A' in age_str or '新築' in age_str:
        return 0
    match = re.search(r'築(\d+)年', age_str)
    if match:
        return int(match.group(1))
    return np.nan


def clean_menseki(menseki_str):
    if not isinstance(menseki_str, str) or 'N/A' in menseki_str:
        return np.nan
    match = re.search(r'([\d.]+)', menseki_str)
    if match:
        return float(match.group(1))
    return np.nan


def clean_access_time(access_str):
    if not isinstance(access_str, str) or 'N/A' in access_str or 'バス' in access_str:
        return np.nan
    match = re.search(r'(\d+)分', access_str)
    if match:
        return int(match.group(1))
    return np.nan


class Scraper:
    """SUUMOから賃貸物件情報をスクレイピングし、一次クレンジングを行うクラス"""

    def __init__(self, url_templates: list, max_page: int):
        self.url_templates = url_templates
        self.max_page = max_page
        self.columns = [
            'カテゴリ', '建物名', '住所',
            '最寄駅1_アクセス', '最寄駅2_アクセス', '最寄駅3_アクセス',
            '築年数', '階数',
            '部屋_階', '部屋_家賃', '部屋_管理費', '部屋_敷金', '部屋_礼金',
            '部屋_間取り', '部屋_面積', '部屋_URL', '部屋コード',
        ]

    @retry(tries=3, delay=10, backoff=2, exceptions=(requests.exceptions.RequestException,))
    def _load_page(self, url):
        headers = {'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
        )}
        html = requests.get(url, headers=headers, timeout=15)
        html.raise_for_status()
        return BeautifulSoup(html.content, 'html.parser')

    def _scrape_page(self, current_url, page):
        try:
            soup = self._load_page(current_url)
        except Exception as e:
            return page, True, [], f"【エラー】{page}ページ目の取得失敗: {e}。スキップします。"

        mother = soup.find_all(class_='cassetteitem')
        if not mother:
            return page, True, [], None

        data_samples = []
        for child in mother:
            data_home = []
            data_home.append(
                child.find(class_='ui-pct ui-pct--util1').text.strip()
                if child.find(class_='ui-pct ui-pct--util1') else 'N/A'
            )
            data_home.append(
                child.find(class_='cassetteitem_content-title').text.strip()
                if child.find(class_='cassetteitem_content-title') else 'N/A'
            )
            data_home.append(
                child.find(class_='cassetteitem_detail-col1').text.strip()
                if child.find(class_='cassetteitem_detail-col1') else 'N/A'
            )

            children = child.find(class_='cassetteitem_detail-col2')
            access_data = []
            if children:
                for grandchild in children.find_all(class_='cassetteitem_detail-text'):
                    access_data.append(grandchild.text.strip())
            while len(access_data) < 3:
                access_data.append('N/A')
            data_home.extend(access_data)

            children = child.find(class_='cassetteitem_detail-col3')
            age_floor_data = []
            if children:
                for grandchild in children.find_all('div'):
                    age_floor_data.append(grandchild.text.strip())
            while len(age_floor_data) < 2:
                age_floor_data.append('N/A')
            data_home.extend(age_floor_data)

            rooms = child.find(class_='cassetteitem_other')
            if rooms:
                for room in rooms.find_all(class_='js-cassette_link'):
                    data_room = []
                    tds = room.find_all('td')
                    data_room.append(tds[2].text.strip() if len(tds) > 2 else 'N/A')
                    if len(tds) > 3:
                        rent = tds[3].find(class_='cassetteitem_other-emphasis')
                        admin = tds[3].find(class_='cassetteitem_price--administration')
                        data_room.append(rent.text.strip() if rent else 'N/A')
                        data_room.append(admin.text.strip() if admin else 'N/A')
                    else:
                        data_room.extend(['N/A', 'N/A'])
                    if len(tds) > 4:
                        deposit = tds[4].find(class_='cassetteitem_price--deposit')
                        gratuity = tds[4].find(class_='cassetteitem_price--gratuity')
                        data_room.append(deposit.text.strip() if deposit else 'N/A')
                        data_room.append(gratuity.text.strip() if gratuity else 'N/A')
                    else:
                        data_room.extend(['N/A', 'N/A'])
                    if len(tds) > 5:
                        madori = tds[5].find(class_='cassetteitem_madori')
                        menseki = tds[5].find(class_='cassetteitem_menseki')
                        data_room.append(madori.text.strip() if madori else 'N/A')
                        data_room.append(menseki.text.strip() if menseki else 'N/A')
                    else:
                        data_room.extend(['N/A', 'N/A'])
                    if len(tds) > 8:
                        link_tag = tds[8].find(class_='js-cassette_link_href')
                        if link_tag and link_tag.get('href'):
                            abs_url = urllib.parse.urljoin(current_url, link_tag.get('href'))
                            data_room.append(abs_url)
                        else:
                            data_room.append('N/A')
                    else:
                        data_room.append('N/A')
                    try:
                        roomCd = tds[0].find(class_='js-ikkatsuCB')['value']
                        data_room.append(roomCd.strip() if roomCd else 'N/A')
                    except (TypeError, KeyError):
                        data_room.append('N/A')
                    data_samples.append(data_home + data_room)

        return page, False, data_samples, None

    def scrape_and_clean(self):
        data_samples = []
        start_time = time.time()
        MAX_CONSECUTIVE_EMPTY = 3

        print("--- スクレイピング開始 ---")
        for url_template in self.url_templates:
            print(f"\n--- URL処理開始: {url_template.split('?')[0]}... ---")
            consecutive_empty_pages = 0
            batch_size = 50
            for start_page in range(1, self.max_page + 1, batch_size):
                end_page = min(start_page + batch_size, self.max_page + 1)
                with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
                    futures = [
                        executor.submit(self._scrape_page, url_template.format(page), page)
                        for page in range(start_page, end_page)
                    ]
                    break_outer = False
                    for future in futures:
                        page, is_empty, samples, err_msg = future.result()
                        if err_msg:
                            print(err_msg)
                        if samples:
                            data_samples.extend(samples)
                            consecutive_empty_pages = 0
                            break_outer = False
                        else:
                            consecutive_empty_pages += 1
                        print(f'✅ {page}ページ目処理完了 | 総取得件数：{len(data_samples)}')
                        if consecutive_empty_pages >= MAX_CONSECUTIVE_EMPTY:
                            break_outer = True
                time.sleep(random.uniform(1.0, 2.0))
                if break_outer:
                    print(f"⚠️ {MAX_CONSECUTIVE_EMPTY}回連続で空ページ。このURLのスクレイピングを中断します。")
                    break

        print(f'--- スクレイピング完了: 総経過時間 {time.time() - start_time:.2f}秒 ---')
        if not data_samples:
            return pd.DataFrame()

        df = pd.DataFrame(data_samples, columns=self.columns)
        df['家賃_万円']          = df['部屋_家賃'].apply(clean_price)
        df['管理費_万円']         = df['部屋_管理費'].apply(clean_price)
        df['敷金_ヶ月']          = df['部屋_敷金'].apply(clean_deposit_gratuity)
        df['礼金_ヶ月']          = df['部屋_礼金'].apply(clean_deposit_gratuity)
        df['築年数_年']          = df['築年数'].apply(clean_age)
        df['面積_m2']           = df['部屋_面積'].apply(clean_menseki)
        df['最寄駅1_アクセス_分'] = df['最寄駅1_アクセス'].apply(clean_access_time)
        df['最寄駅2_アクセス_分'] = df['最寄駅2_アクセス'].apply(clean_access_time)
        df['最寄駅3_アクセス_分'] = df['最寄駅3_アクセス'].apply(clean_access_time)
        return df

    def filter_data(self, df: pd.DataFrame, filters: dict) -> pd.DataFrame:
        if df.empty:
            return df
        df_filtered = df.copy()
        initial_count = len(df)
        filter_conditions = pd.Series(True, index=df.index)
        print("\n--- フィルタリング適用開始 ---")
        for key, condition in filters.items():
            if key == '家賃_万円' and 'max' in condition:
                filter_conditions &= (
                    df_filtered['家賃_万円'].fillna(0) + df_filtered['管理費_万円'].fillna(0)
                    <= condition['max']
                )
                print(f"  - フィルタ: 家賃+管理費 <= {condition['max']}万円")
            elif key == '築年数_年' and 'max' in condition:
                filter_conditions &= df_filtered['築年数_年'].fillna(np.inf) <= condition['max']
                print(f"  - フィルタ: 築年数 <= {condition['max']}年")
            elif key == '面積_m2' and 'min' in condition:
                filter_conditions &= df_filtered['面積_m2'].fillna(-np.inf) >= condition['min']
                print(f"  - フィルタ: 面積 >= {condition['min']}m2")
            elif key == '最寄駅1_アクセス_分' and 'max' in condition:
                max_time = condition['max']
                filter_conditions &= (
                    (df_filtered['最寄駅1_アクセス_分'].fillna(np.inf) <= max_time) |
                    (df_filtered['最寄駅2_アクセス_分'].fillna(np.inf) <= max_time) |
                    (df_filtered['最寄駅3_アクセス_分'].fillna(np.inf) <= max_time)
                )
                print(f"  - フィルタ: いずれかの最寄駅アクセス <= {max_time}分")
        df_filtered = df_filtered[filter_conditions]
        print(f"--- フィルタリング完了: {initial_count}件 → {len(df_filtered)}件 ---")
        return df_filtered
