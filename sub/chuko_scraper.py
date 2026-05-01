"""
sub/chuko_scraper.py
SUUMOの中古マンション一覧ページをスクレイピングし、一次クレンジングを行うモジュール。
"""

import requests
import time
import re
import math
import random
import functools
import urllib.parse
import concurrent.futures
from datetime import date

import pandas as pd
import numpy as np
from bs4 import BeautifulSoup


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


def clean_price_man(price_str):
    if not price_str or 'N/A' in price_str:
        return None
    s = price_str.strip()
    m_oku = re.search(r'(\d+)億(?:(\d+)万)?円?', s)
    if m_oku:
        oku = int(m_oku.group(1)) * 10000
        man = int(m_oku.group(2)) if m_oku.group(2) else 0
        return float(oku + man)
    m_man = re.search(r'([\d,]+)万円?', s)
    if m_man:
        return float(m_man.group(1).replace(',', ''))
    return None


def clean_area_m2(area_str):
    if not area_str or 'N/A' in area_str:
        return None
    m = re.search(r'([\d.]+)\s*m', area_str)
    return float(m.group(1)) if m else None


def clean_access_min(access_str):
    if not access_str or 'N/A' in access_str or 'バス' in access_str:
        return None
    m = re.search(r'徒歩(\d+)分', access_str)
    return float(m.group(1)) if m else None


def clean_built_year_month(built_str):
    if not built_str or 'N/A' in built_str or built_str.strip() in ('', '-', '&nbsp;'):
        return None, None
    m = re.search(r'(\d{4})年', built_str)
    if not m:
        return built_str.strip(), None
    built_year = int(m.group(1))
    age = max(0, date.today().year - built_year)
    return built_str.strip(), age


def extract_floor_num(text):
    if not text:
        return None, None
    m = re.search(r'[Ｂb地下](\d+)階', text)
    if m:
        n = -int(m.group(1))
        return f"B{abs(n)}階", n
    m = re.search(r'(\d{1,3})階部分', text)
    if m:
        n = int(m.group(1))
        return f"{n}階", n
    m = re.search(r'(\d{1,3})階(?=[　\s・、。のにはへよりから,，／/」)※◎◇●]|\Z)', text)
    if m:
        n = int(m.group(1))
        return f"{n}階", n
    return None, None


def _get_dt_value(dottable_line, dt_label):
    for dl in dottable_line.find_all('dl'):
        dt = dl.find('dt')
        dd = dl.find('dd')
        if dt and dd and dt_label in dt.get_text():
            val = dd.get_text(separator='', strip=True)
            if val in ('', '\xa0', '-', '‐', '－'):
                return None
            return val
    return None


class ChukoScraper:
    """SUUMO 中古マンション一覧ページをスクレイピングするクラス"""

    BASE_URL = 'https://suumo.jp'
    COLUMNS = [
        '物件コード', '建物名', '住所',
        '価格_万円', '専有面積_m2', 'バルコニー_m2',
        '間取り', '最寄駅_アクセス', '最寄駅_分',
        '築年月', '築年数_年',
        '所在階', '所在階_数値',
        '物件URL',
    ]

    def __init__(self, url_templates: list[str], max_page: int):
        self.url_templates = url_templates
        self.max_page = max_page

    @retry(tries=3, delay=10, backoff=2, exceptions=(requests.exceptions.RequestException,))
    def _load_page(self, url):
        headers = {'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, 'html.parser')

    def _scrape_page(self, current_url, page):
        try:
            soup = self._load_page(current_url)
        except Exception as e:
            return page, True, [], f"【エラー】{page}ページ目の取得失敗: {e}"
        cards = soup.find_all('div', class_='property_unit')
        if not cards:
            return page, True, [], None
        samples = []
        for card in cards:
            row = self._parse_card(card, current_url)
            if row:
                samples.append(row)
        return page, (len(samples) == 0), samples, None

    def _parse_card(self, card, page_url):
        clipkey_input = card.find('input', class_='js-clipkey')
        if not clipkey_input:
            return None
        property_code = clipkey_input.get('value', '').strip()
        if not property_code:
            return None

        title_tag = card.find('h2', class_='property_unit-title_wide')
        if not title_tag:
            return None
        a_tag = title_tag.find('a')
        building_name = a_tag.get_text(strip=True) if a_tag else 'N/A'
        href = a_tag.get('href', '') if a_tag else ''
        room_url = urllib.parse.urljoin(self.BASE_URL, href) if href else 'N/A'

        dottable = card.find('div', class_='dottable--cassette')
        address = price_str = area_str = balcony_str = access_str = floor_plan = built_str = None
        desc_texts = []
        lead = dottable.find('div', class_='dottable-lead') if dottable else None
        if lead:
            desc_texts.append(lead.get_text(separator=' ', strip=True))

        if dottable:
            for line in dottable.find_all('div', class_='dottable-line'):
                v = _get_dt_value(line, '販売価格')
                if v: price_str = v
                v = _get_dt_value(line, '専有面積')
                if v: area_str = v
                v = _get_dt_value(line, '所在地')
                if v: address = v
                v = _get_dt_value(line, 'バルコニー')
                if v: balcony_str = v
                v = _get_dt_value(line, '沿線・駅')
                if v: access_str = v
                v = _get_dt_value(line, '間取り')
                if v: floor_plan = v
                v = _get_dt_value(line, '築年月')
                if v: built_str = v

        dotblock_desc = card.find('p', class_='dotblock-desc')
        if dotblock_desc:
            desc_texts.append(dotblock_desc.get_text(separator=' ', strip=True))

        room_floor, floor_num = None, None
        for text in desc_texts:
            room_floor, floor_num = extract_floor_num(text)
            if room_floor is not None:
                break

        price_man        = clean_price_man(price_str)
        area_m2          = clean_area_m2(area_str)
        balcony_m2       = clean_area_m2(balcony_str)
        access_min       = clean_access_min(access_str)
        built_ym, age_yr = clean_built_year_month(built_str)

        return [
            property_code, building_name, address or 'N/A',
            price_man, area_m2, balcony_m2,
            floor_plan or 'N/A', access_str or 'N/A', access_min,
            built_ym, age_yr, room_floor, floor_num, room_url,
        ]

    def scrape_and_clean(self) -> pd.DataFrame:
        all_samples = []
        start_time = time.time()
        MAX_CONSECUTIVE_EMPTY = 3
        BATCH_SIZE = 50

        print("--- 中古マンション スクレイピング開始 ---")
        for url_template in self.url_templates:
            print(f"\n--- URL処理開始: {url_template.split('?')[0]}... ---")
            consecutive_empty = 0
            for start_page in range(1, self.max_page + 1, BATCH_SIZE):
                end_page = min(start_page + BATCH_SIZE, self.max_page + 1)
                break_outer = False
                with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
                    futures = [
                        executor.submit(self._scrape_page, url_template.format(p), p)
                        for p in range(start_page, end_page)
                    ]
                    for future in futures:
                        page, is_empty, samples, err_msg = future.result()
                        if err_msg:
                            print(err_msg)
                        if samples:
                            all_samples.extend(samples)
                            consecutive_empty = 0
                            break_outer = False
                        else:
                            consecutive_empty += 1
                        print(f'✅ {page}ページ目完了 | 総取得件数: {len(all_samples)}')
                        if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                            break_outer = True
                time.sleep(random.uniform(1.0, 2.0))
                if break_outer:
                    print(f"⚠️ {MAX_CONSECUTIVE_EMPTY}回連続空ページ。このURLを中断します。")
                    break

        elapsed = time.time() - start_time
        print(f'--- スクレイピング完了: 総経過時間 {elapsed:.2f}秒 ---')
        if not all_samples:
            return pd.DataFrame(columns=self.COLUMNS)
        df = pd.DataFrame(all_samples, columns=self.COLUMNS)
        df = df.drop_duplicates(subset=['物件コード'], keep='first').reset_index(drop=True)
        print(f"  - 重複除去後: {len(df)}件")
        return df

    def filter_data(self, df: pd.DataFrame, filters: dict) -> pd.DataFrame:
        if df.empty:
            return df
        cond = pd.Series(True, index=df.index)
        print("\n--- フィルタリング適用開始 ---")
        for key, rule in filters.items():
            if key not in df.columns:
                continue
            if 'max' in rule:
                cond &= df[key].fillna(np.inf) <= rule['max']
                print(f"  - {key} <= {rule['max']}")
            if 'min' in rule:
                cond &= df[key].fillna(-np.inf) >= rule['min']
                print(f"  - {key} >= {rule['min']}")
        filtered = df[cond].copy()
        print(f"--- フィルタリング完了: {len(df)}件 → {len(filtered)}件 ---")
        return filtered
