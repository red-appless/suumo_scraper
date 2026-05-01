"""
sub/generate_chuko_map.py
中古マンションDBデータから、住所単位でマーカーを集約したフィルタ付きHTMLマップを生成する。
"""

import json
import time
import numpy as np

from dao import property_chuko_dao as chuko_property_dao


def generate_map_html(conn, api_key: str, output_path: str = None) -> str | None:
    """
    DBから集約済み中古物件データを取得し、マップHTMLを生成する。
    output_path: 保存先パス。None の場合はカレントディレクトリに日時付きファイル名で保存。
    Returns: 生成された HTML ファイルパス。失敗時は None。
    """
    print("--- 📂 DBから中古物件データを読み込み中 ---")
    rows = chuko_property_dao.get_properties_aggregated_by_address(conn)

    if not rows:
        print("【警告】座標付きの有効な中古物件が0件のためマップ生成をスキップします。")
        return None

    print(f"  - 集約済み住所数: {len(rows)}件")
    total_props = sum(r['count'] for r in rows)
    print(f"  - 総物件数: {total_props}件")

    def to_f(val, default=0.0):
        try:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return default
            return float(val)
        except Exception:
            return default

    markers_list = []
    all_madori = set()
    all_prices = []

    for row in rows:
        props = row['properties']
        if isinstance(props, str):
            props = json.loads(props)

        for p in props:
            m = p.get('floor_plan') or 'N/A'
            if m.strip() not in ('', 'N/A'):
                all_madori.add(m)
            price = to_f(p.get('price_man'), None)
            if price is not None:
                all_prices.append(price)

        building  = row.get('building_name') or '物件情報'
        lat       = to_f(row['latitude'])
        lng       = to_f(row['longitude'])
        count     = int(row['count'])
        min_price = to_f(row['min_price_man'], None)
        max_price = to_f(row['max_price_man'], None)
        price_range = _price_range_str(min_price, max_price)

        items_html = ''
        for p in props:
            p_floor_plan = p.get('floor_plan')  or 'N/A'
            p_area       = to_f(p.get('area_m2'), None)
            p_price      = to_f(p.get('price_man'), None)
            p_floor_str  = p.get('room_floor')  or '?階'
            p_floor_num  = p.get('floor_num')
            p_url        = p.get('room_url')    or '#'
            p_age        = p.get('age_years')
            p_access     = p.get('station1_min')

            area_disp  = f"{p_area:.1f}m²"    if p_area  is not None else 'N/A'
            price_disp = f"{p_price:,.0f}万円" if p_price is not None else '要問合せ'

            items_html += (
                f'<li class="prop-item"'
                f' data-price="{p_price if p_price is not None else -1}"'
                f' data-area="{p_area  if p_area  is not None else -1}"'
                f' data-floor="{p_floor_num if p_floor_num is not None else -999}"'
                f' data-age="{p_age     if p_age     is not None else -1}"'
                f' data-toho="{p_access if p_access  is not None else 999}"'
                f' data-madori="{p_floor_plan}">'
                f'<a href="{p_url}" target="_blank">'
                f'<span class="prop-floor">{p_floor_str}</span>: '
                f'<span class="prop-madori">{p_floor_plan}</span> / '
                f'<span class="prop-area">{area_disp}</span> / '
                f'<span class="prop-price">{price_disp}</span>'
                f'</a></li>'
            )

        infowin_content = (
            f'<div class="iw-wrap">'
            f'<h3 class="iw-title">{building}'
            f' <span class="iw-count">({count}件)</span></h3>'
            f'<p class="iw-price-range">価格帯: {price_range}</p>'
            f'<ul class="prop-list" id="prop-list-{len(markers_list)}">'
            f'{items_html}'
            f'</ul>'
            f'<p class="iw-no-match" style="display:none">フィルタ条件に一致する物件がありません</p>'
            f'</div>'
        )

        marker_info = {
            "lat": lat, "lng": lng, "title": building,
            "content": infowin_content, "count": count,
            "min_price": min_price if min_price is not None else -1,
            "max_price": max_price if max_price is not None else -1,
            "props": [
                {
                    "price":  to_f(p.get('price_man'),   -1),
                    "area":   to_f(p.get('area_m2'),     -1),
                    "floor":  p.get('floor_num') if p.get('floor_num') is not None else -999,
                    "age":    to_f(p.get('age_years'),   -1),
                    "toho":   to_f(p.get('station1_min'), 999),
                    "madori": p.get('floor_plan') or 'N/A',
                }
                for p in props
            ],
        }
        markers_list.append(marker_info)

    madori_list = sorted(all_madori)
    madori_pills_html = ''.join(
        f'<label class="madori-pill checked">'
        f'<input type="checkbox" class="madori-checkbox" value="{m}" checked hidden>{m}'
        f'</label>'
        for m in madori_list
    )

    max_price_val = max(all_prices) if all_prices else 10000
    max_price_ui  = max(5000, int(np.ceil(max_price_val / 500)) * 500)

    lats = [r['latitude']  for r in rows if r.get('latitude')]
    lngs = [r['longitude'] for r in rows if r.get('longitude')]
    center_lat = float(np.mean(lats)) if lats else 35.6895
    center_lng = float(np.mean(lngs)) if lngs else 139.6917

    markers_json = json.dumps(markers_list, ensure_ascii=False, default=str)

    filename = output_path or f'中古物件マップ_{time.strftime("%Y%m%d_%H%M%S")}.html'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>SUUMO 中古マンション マップ</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Roboto, 'Noto Sans JP', sans-serif; display: flex; height: 100vh; background: #121212; overflow: hidden; }}
  #filter-panel {{ width: 340px; flex-shrink: 0; background: #1e1e1e; color: #eee; padding: 22px 20px; overflow-y: auto; border-right: 1px solid #2c2c2c; }}
  #filter-panel h2 {{ font-size: 19px; font-weight: 700; color: #fff; margin-bottom: 14px; }}
  #result-text {{ font-size: 14px; font-weight: 600; color: #9cc6ff; margin-bottom: 16px; }}
  .fg {{ background: #262626; border: 1px solid #333; border-radius: 10px; padding: 14px; margin-bottom: 14px; }}
  .fg > label {{ font-size: 12px; opacity: 0.85; display: block; margin-bottom: 6px; font-weight: 500; }}
  .fg input[type="number"] {{ width: 100%; padding: 8px 10px; background: #1f1f1f; border: 1px solid #3a3a3a; border-radius: 6px; color: #fff; font-size: 13px; }}
  input[type=range] {{ -webkit-appearance: none; width: 100%; height: 4px; background: #3a3a3a; border-radius: 2px; outline: none; cursor: pointer; }}
  input[type=range]::-webkit-slider-thumb {{ -webkit-appearance: none; width: 16px; height: 16px; background: #4f8cf5; border-radius: 50%; }}
  #madori-filters {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
  .madori-pill {{ display: inline-flex; align-items: center; padding: 4px 11px; border-radius: 20px; border: 1.5px solid #444; background: #2a2a2a; color: #aaa; font-size: 12px; cursor: pointer; user-select: none; transition: all 0.15s; }}
  .madori-pill.checked {{ background: #1d3d7a; border-color: #4f8cf5; color: #e8f0ff; }}
  .madori-controls {{ display: flex; gap: 8px; margin-bottom: 8px; }}
  .madori-ctrl-btn {{ flex: 1; padding: 5px; font-size: 11px; background: #2a2a2a; border: 1px solid #444; border-radius: 6px; color: #ccc; cursor: pointer; }}
  #map-container {{ flex-grow: 1; position: relative; }}
  #map {{ width: 100%; height: 100%; }}
  #result-count {{ position: absolute; top: 16px; left: 16px; z-index: 1000; background: rgba(50,117,237,0.9); color: #fff; padding: 10px 16px; border-radius: 8px; font-size: 14px; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
  .iw-wrap {{ min-width: 260px; max-width: 340px; font-family: 'Noto Sans JP', sans-serif; }}
  .iw-title {{ font-size: 15px; font-weight: 700; color: #1a56db; margin-bottom: 4px; }}
  .iw-count {{ font-size: 12px; font-weight: 400; color: #555; }}
  .iw-price-range {{ font-size: 11px; color: #777; margin-bottom: 8px; }}
  .prop-list {{ list-style: none; max-height: 240px; overflow-y: auto; border-top: 1px solid #e8e8e8; }}
  .prop-list li {{ padding: 7px 4px; border-bottom: 1px solid #f0f0f0; font-size: 13px; line-height: 1.5; }}
  .prop-list li a {{ color: #1a56db; text-decoration: none; }}
  .prop-floor {{ font-weight: 700; color: #222; }}
  .prop-price {{ font-weight: 700; color: #d13b00; }}
  .iw-no-match {{ font-size: 12px; color: #999; padding: 6px 0; }}
</style>
</head>
<body>
<div id="filter-panel">
  <h2>🏢 中古マンション フィルタ</h2>
  <div id="result-text">検索中...</div>
  <div class="fg">
    <label>価格 (万円): <span id="price-min-val">0</span> 〜 <span id="price-max-val">{max_price_ui}</span></label>
    <div style="position:relative;height:32px;margin-top:8px">
      <input type="range" id="price-min" min="0" max="{max_price_ui}" value="0" step="100" style="position:absolute;top:0" oninput="syncSliders(this,'min');filterMarkers()">
      <input type="range" id="price-max" min="0" max="{max_price_ui}" value="{max_price_ui}" step="100" style="position:absolute;top:12px" oninput="syncSliders(this,'max');filterMarkers()">
    </div>
  </div>
  <div class="fg"><label for="area-input">専有面積 (m²) 以上:</label><input type="number" id="area-input" value="0" min="0" step="5" oninput="filterMarkers()"></div>
  <div class="fg"><label for="age-slider">築年数 (年) 以内: <span id="age-value">50</span></label><input type="range" id="age-slider" min="0" max="60" value="50" step="1" oninput="document.getElementById('age-value').innerText=this.value;filterMarkers()"></div>
  <div class="fg"><label for="toho-slider">最寄駅徒歩 (分) 以内: <span id="toho-value">30</span></label><input type="range" id="toho-slider" min="1" max="60" value="30" step="1" oninput="document.getElementById('toho-value').innerText=this.value;filterMarkers()"></div>
  <div class="fg"><label>所在階 (階) 以上:</label><input type="number" id="floor-input" value="1" min="1" step="1" oninput="filterMarkers()"></div>
  <div class="fg">
    <label>間取り:</label>
    <div class="madori-controls">
      <button class="madori-ctrl-btn" onclick="setAllMadori(true)">✅ すべて選択</button>
      <button class="madori-ctrl-btn" onclick="setAllMadori(false)">☐ すべて解除</button>
    </div>
    <div id="madori-filters">{madori_pills_html}</div>
  </div>
</div>
<div id="map-container">
  <div id="result-count">物件数: <span id="count-display">--</span></div>
  <div id="map"></div>
</div>
<script>
const markersData = {markers_json};
let map, gMarkers = [], infoWindow;
function initMap() {{
  map = new google.maps.Map(document.getElementById('map'), {{ center: {{lat: {center_lat}, lng: {center_lng}}}, zoom: 12 }});
  infoWindow = new google.maps.InfoWindow();
  markersData.forEach((md, idx) => {{
    const marker = new google.maps.Marker({{ position: {{lat: md.lat, lng: md.lng}}, map: null, title: md.title }});
    marker.addListener('click', () => {{ infoWindow.setContent(buildInfoContent(md, idx)); infoWindow.open(map, marker); map.panTo(marker.getPosition()); }});
    gMarkers.push(marker);
  }});
  document.querySelectorAll('.madori-pill').forEach(pill => {{
    pill.addEventListener('click', () => {{ const cb = pill.querySelector('input[type=checkbox]'); cb.checked = !cb.checked; pill.classList.toggle('checked', cb.checked); filterMarkers(); }});
  }});
  filterMarkers();
}}
function getFilters() {{
  return {{ minPrice: parseFloat(document.getElementById('price-min').value)||0, maxPrice: parseFloat(document.getElementById('price-max').value)||Infinity, minArea: parseFloat(document.getElementById('area-input').value)||0, maxAge: parseFloat(document.getElementById('age-slider').value)||Infinity, maxToho: parseFloat(document.getElementById('toho-slider').value)||Infinity, minFloor: parseFloat(document.getElementById('floor-input').value)||1, madori: [...document.querySelectorAll('.madori-checkbox:checked')].map(c=>c.value) }};
}}
function propPasses(p, f) {{
  if (p.price>=0 && (p.price<f.minPrice||p.price>f.maxPrice)) return false;
  if (p.area>=0 && p.area<f.minArea) return false;
  if (p.age>=0 && p.age>f.maxAge) return false;
  if (p.toho<=998 && p.toho>f.maxToho) return false;
  if (p.floor>-999 && p.floor<f.minFloor) return false;
  if (p.madori!=='N/A' && !f.madori.includes(p.madori)) return false;
  return true;
}}
function filterMarkers() {{
  const f = getFilters(); let vm=0, vp=0;
  gMarkers.forEach((marker, idx) => {{
    const md = markersData[idx];
    const passing = md.props.filter(p => propPasses(p, f));
    if (passing.length>0) {{ marker.setMap(map); vm++; vp+=passing.length; }} else {{ marker.setMap(null); }}
  }});
  document.getElementById('count-display').innerText = vp;
  document.getElementById('result-text').innerText = `検索結果: ${{vp}}件 (${{vm}}棟)`;
}}
function buildInfoContent(md, idx) {{
  const f = getFilters();
  const parser = new DOMParser();
  const doc = parser.parseFromString(md.content, 'text/html');
  const filteredItems = [...doc.querySelectorAll('.prop-item')].filter(li => propPasses({{price:parseFloat(li.dataset.price),area:parseFloat(li.dataset.area),age:parseFloat(li.dataset.age),toho:parseFloat(li.dataset.toho),floor:parseFloat(li.dataset.floor),madori:li.dataset.madori}},f));
  const noMatch = filteredItems.length===0 ? '<p class="iw-no-match">フィルタ条件に一致する物件がありません</p>' : '';
  return `<div class="iw-wrap"><h3 class="iw-title">${{md.title}} <span class="iw-count">(${{filteredItems.length}}件)</span></h3><ul class="prop-list">${{filteredItems.map(li=>li.outerHTML).join('')}}</ul>${{noMatch}}</div>`;
}}
function syncSliders(slider, type) {{
  const minS=document.getElementById('price-min'), maxS=document.getElementById('price-max');
  if (type==='min'&&+minS.value>+maxS.value) minS.value=maxS.value;
  if (type==='max'&&+maxS.value<+minS.value) maxS.value=minS.value;
  document.getElementById('price-min-val').innerText=(+minS.value).toLocaleString();
  document.getElementById('price-max-val').innerText=(+maxS.value).toLocaleString();
}}
function setAllMadori(checked) {{
  document.querySelectorAll('.madori-pill').forEach(pill => {{ const cb=pill.querySelector('input[type=checkbox]'); cb.checked=checked; pill.classList.toggle('checked',checked); }});
  filterMarkers();
}}
const script = document.createElement('script');
script.src = 'https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap';
script.async = true;
document.head.appendChild(script);
</script>
</body>
</html>"""

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'🎉 中古マンションマップを生成しました: {filename}')
    return filename


def _price_range_str(min_p, max_p) -> str:
    if min_p is None and max_p is None:
        return '要問合せ'
    if min_p == max_p or max_p is None:
        return f'{min_p:,.0f}万円'
    return f'{min_p:,.0f}万円 〜 {max_p:,.0f}万円'
