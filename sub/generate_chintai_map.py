"""
sub/generate_map.py
DBから有効物件データを建物単位で集約し、動的フィルタ付きの単体HTMLマップを生成するモジュール。
"""

import time
import json
import numpy as np

from dao import property_chintai_dao as property_dao


def _rent_range_str(min_r, max_r) -> str:
    if min_r is None and max_r is None:
        return '要問合せ'
    if min_r == max_r or max_r is None:
        return f'{min_r:.1f}万円'
    return f'{min_r:.1f}万円 〜 {max_r:.1f}万円'


def generate_map_html(conn, api_key: str, output_path: str = None) -> str | None:
    """
    DBから建物単位で集約した物件データを取得し、フィルタ付きマップHTMLを生成する。
    output_path: 保存先パス。None の場合はカレントディレクトリに日時付きファイル名で保存。
    """
    print("--- 📂 DBから物件データを読み込み中（建物単位集約） ---")
    rows = property_dao.get_properties_aggregated_by_building(conn)

    if not rows:
        print("【警告】座標付きの有効な物件が0件のため、マップは生成できません。")
        return None

    total_buildings = len(rows)
    total_rooms = sum(int(r['count']) for r in rows)
    print(f"  - 集約済み建物数: {total_buildings}棟 / 総部屋数: {total_rooms}件")

    def to_f(val, default=0.0):
        try:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return default
            return float(val)
        except Exception:
            return default

    all_madori = set()
    all_rents  = []
    markers_list = []

    for row in rows:
        props = row['properties']
        if isinstance(props, str):
            props = json.loads(props)

        building = row.get('building_name') or '物件情報'
        lat      = to_f(row['latitude'])
        lng      = to_f(row['longitude'])
        count    = int(row['count'])
        min_rent = to_f(row['min_rent_total'], None)
        max_rent = to_f(row['max_rent_total'], None)

        for p in props:
            m = (p.get('floor_plan') or '').strip()
            if m and m != 'N/A':
                all_madori.add(m)
            r = to_f(p.get('rent_total'), None)
            if r is not None and r > 0:
                all_rents.append(r)

        items_html = ''
        for p in props:
            p_floor_plan = p.get('floor_plan')  or 'N/A'
            p_area       = to_f(p.get('area_m2'),    None)
            p_rent_total = to_f(p.get('rent_total'), None)
            p_floor_str  = p.get('room_floor')  or '?階'
            p_floor_num  = p.get('floor_num')
            p_url        = p.get('room_url')    or '#'
            p_age        = p.get('age_years')
            p_access     = p.get('station1_min')

            area_disp = f"{p_area:.1f}m²"       if p_area        is not None else 'N/A'
            rent_disp = f"{p_rent_total:.1f}万円" if p_rent_total is not None else '要問合せ'

            items_html += (
                f'<li class="prop-item"'
                f' data-rent="{p_rent_total  if p_rent_total  is not None else -1}"'
                f' data-area="{p_area        if p_area        is not None else -1}"'
                f' data-floor="{p_floor_num  if p_floor_num   is not None else -999}"'
                f' data-age="{p_age          if p_age         is not None else -1}"'
                f' data-toho="{p_access      if p_access      is not None else 999}"'
                f' data-madori="{p_floor_plan}">'
                f'<a href="{p_url}" target="_blank">'
                f'<span class="prop-floor">{p_floor_str}</span>: '
                f'<span class="prop-madori">{p_floor_plan}</span> / '
                f'<span class="prop-area">{area_disp}</span> / '
                f'<span class="prop-rent">{rent_disp}</span>'
                f'</a></li>'
            )

        sample_admin  = to_f(props[0].get('admin_fee_man'), 0.0) if props else 0.0
        admin_note    = '（家賃+管理費）' if sample_admin > 0 else ''
        rent_range    = _rent_range_str(
            min_rent if min_rent and min_rent > 0 else None,
            max_rent if max_rent and max_rent > 0 else None,
        )
        sample_access = (props[0].get('station1_access') or '') if props else ''

        infowin_content = (
            f'<div class="iw-wrap">'
            f'<h3 class="iw-title">{building} <span class="iw-count">({count}件)</span></h3>'
            f'<p class="iw-meta">家賃帯: {rent_range}{admin_note}</p>'
            f'<p class="iw-meta">{sample_access}</p>'
            f'<ul class="prop-list" id="prop-list-{len(markers_list)}">{items_html}</ul>'
            f'<p class="iw-no-match" style="display:none">フィルタ条件に一致する部屋がありません</p>'
            f'</div>'
        )

        marker_info = {
            "lat": lat, "lng": lng, "title": building,
            "content": infowin_content, "count": count,
            "min_rent": min_rent if min_rent is not None else -1,
            "max_rent": max_rent if max_rent is not None else -1,
            "props": [
                {
                    "rent":   to_f(p.get('rent_total'),  -1),
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

    max_rent_val = max(all_rents) if all_rents else 30.0
    max_rent_ui  = max(30.0, float(int(np.ceil(max_rent_val / 5.0)) * 5))

    lats = [r['latitude']  for r in rows if r.get('latitude')]
    lngs = [r['longitude'] for r in rows if r.get('longitude')]
    center_lat = float(np.mean(lats)) if lats else 35.6895
    center_lng = float(np.mean(lngs)) if lngs else 139.6917

    markers_json = json.dumps(markers_list, ensure_ascii=False, default=str)
    filename = output_path or f'物件マップ_{time.strftime("%Y%m%d_%H%M%S")}.html'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>SUUMO 賃貸物件 マップ</title>
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
  .dual-slider-wrap {{ position: relative; height: 36px; margin-top: 8px; }}
  .dual-slider-wrap input[type=range] {{ position: absolute; left: 0; right: 0; pointer-events: none; }}
  .dual-slider-wrap input[type=range]::-webkit-slider-thumb {{ pointer-events: all; }}
  .dual-slider-wrap input[type=range]:first-child {{ top: 0; }}
  .dual-slider-wrap input[type=range]:last-child  {{ top: 14px; }}
  #madori-filters {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
  .madori-pill {{ display: inline-flex; align-items: center; padding: 4px 11px; border-radius: 20px; border: 1.5px solid #444; background: #2a2a2a; color: #aaa; font-size: 12px; cursor: pointer; user-select: none; transition: all 0.15s; }}
  .madori-pill.checked {{ background: #1d3d7a; border-color: #4f8cf5; color: #e8f0ff; }}
  .madori-controls {{ display: flex; gap: 8px; margin-bottom: 8px; }}
  .madori-ctrl-btn {{ flex: 1; padding: 5px; font-size: 11px; background: #2a2a2a; border: 1px solid #444; border-radius: 6px; color: #ccc; cursor: pointer; }}
  #map-container {{ flex-grow: 1; position: relative; }}
  #map {{ width: 100%; height: 100%; }}
  #result-count {{ position: absolute; top: 16px; left: 16px; z-index: 1000; background: rgba(50,117,237,0.9); color: #fff; padding: 10px 16px; border-radius: 8px; font-size: 14px; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
  .iw-wrap {{ min-width: 260px; max-width: 360px; font-family: 'Noto Sans JP', sans-serif; }}
  .iw-title {{ font-size: 15px; font-weight: 700; color: #1a56db; margin-bottom: 4px; }}
  .iw-count {{ font-size: 12px; font-weight: 400; color: #555; }}
  .iw-meta {{ font-size: 11px; color: #777; margin-bottom: 4px; }}
  .prop-list {{ list-style: none; max-height: 260px; overflow-y: auto; border-top: 1px solid #e8e8e8; }}
  .prop-list li {{ padding: 7px 4px; border-bottom: 1px solid #f0f0f0; font-size: 13px; line-height: 1.5; }}
  .prop-list li a {{ color: #1a56db; text-decoration: none; }}
  .prop-floor {{ font-weight: 700; color: #222; }}
  .prop-rent {{ font-weight: 700; color: #c0392b; }}
  .iw-no-match {{ font-size: 12px; color: #999; padding: 6px 0; }}
</style>
</head>
<body>
<div id="filter-panel">
  <h2>🏠 SUUMO 賃貸物件フィルタ</h2>
  <div id="result-text">検索中...</div>
  <div class="fg">
    <label>家賃+管費 (万円): <span id="rent-min-val">0.0</span> 〜 <span id="rent-max-val">{max_rent_ui:.1f}</span></label>
    <div class="dual-slider-wrap">
      <input type="range" id="rent-min" min="0" max="{max_rent_ui}" value="0" step="0.5" oninput="syncSliders(this,'min');filterMarkers()">
      <input type="range" id="rent-max" min="0" max="{max_rent_ui}" value="{max_rent_ui}" step="0.5" oninput="syncSliders(this,'max');filterMarkers()">
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
  applyOverlapOffsets();
  markersData.forEach((md, idx) => {{
    const marker = new google.maps.Marker({{ position: {{lat: md.lat, lng: md.lng}}, map: null, title: md.title }});
    marker.addListener('click', () => {{ infoWindow.setContent(buildInfoContent(md)); infoWindow.open(map, marker); map.panTo(marker.getPosition()); }});
    gMarkers.push(marker);
  }});
  document.querySelectorAll('.madori-pill').forEach(pill => {{
    pill.addEventListener('click', () => {{ const cb=pill.querySelector('input[type=checkbox]'); cb.checked=!cb.checked; pill.classList.toggle('checked',cb.checked); filterMarkers(); }});
  }});
  filterMarkers();
}}
function applyOverlapOffsets() {{
  const OFFSET = 0.00012;
  const posMap = {{}};
  markersData.forEach((md, idx) => {{
    const key = md.lat.toFixed(6)+','+md.lng.toFixed(6);
    if (!posMap[key]) posMap[key] = [];
    posMap[key].push(idx);
  }});
  Object.values(posMap).forEach(idxList => {{
    if (idxList.length > 1) {{
      idxList.forEach((idx, i) => {{
        const angle = (2*Math.PI*i)/idxList.length;
        markersData[idx].lat += OFFSET*Math.sin(angle);
        markersData[idx].lng += OFFSET*Math.cos(angle);
      }});
    }}
  }});
}}
function getFilters() {{
  return {{ minRent: parseFloat(document.getElementById('rent-min').value)||0, maxRent: parseFloat(document.getElementById('rent-max').value)||Infinity, minArea: parseFloat(document.getElementById('area-input').value)||0, maxAge: parseFloat(document.getElementById('age-slider').value)||Infinity, maxToho: parseFloat(document.getElementById('toho-slider').value)||Infinity, minFloor: parseFloat(document.getElementById('floor-input').value)||1, madori: [...document.querySelectorAll('.madori-checkbox:checked')].map(c=>c.value) }};
}}
function propPasses(p, f) {{
  if (p.rent>=0&&(p.rent<f.minRent||p.rent>f.maxRent)) return false;
  if (p.area>=0&&p.area<f.minArea) return false;
  if (p.age>=0&&p.age>f.maxAge) return false;
  if (p.toho<=998&&p.toho>f.maxToho) return false;
  if (p.floor>-999&&p.floor<f.minFloor) return false;
  if (p.madori!=='N/A'&&!f.madori.includes(p.madori)) return false;
  return true;
}}
function filterMarkers() {{
  const f=getFilters(); let vm=0,vr=0;
  gMarkers.forEach((marker,idx) => {{
    const md=markersData[idx];
    const passing=md.props.filter(p=>propPasses(p,f));
    if (passing.length>0) {{ marker.setMap(map); vm++; vr+=passing.length; }} else {{ marker.setMap(null); }}
  }});
  document.getElementById('count-display').innerText=vr;
  document.getElementById('result-text').innerText=`検索結果: ${{vr}}件 (${{vm}}棟)`;
}}
function buildInfoContent(md) {{
  const f=getFilters();
  const parser=new DOMParser();
  const doc=parser.parseFromString(md.content,'text/html');
  const filteredItems=[...doc.querySelectorAll('.prop-item')].filter(li=>propPasses({{rent:parseFloat(li.dataset.rent),area:parseFloat(li.dataset.area),age:parseFloat(li.dataset.age),toho:parseFloat(li.dataset.toho),floor:parseFloat(li.dataset.floor),madori:li.dataset.madori}},f));
  const count=filteredItems.length;
  const noMatch=count===0?'<p class="iw-no-match">フィルタ条件に一致する部屋がありません</p>':'';
  const origHeader=doc.querySelector('.iw-wrap').innerHTML.replace(/<ul class="prop-list"[\s\S]*<\/ul>/,'').replace(/<p class="iw-no-match"[\s\S]*<\/p>/,'');
  return `<div class="iw-wrap">${{origHeader}}<ul class="prop-list">${{filteredItems.map(li=>li.outerHTML).join('')}}</ul>${{noMatch}}</div>`;
}}
function syncSliders(slider, type) {{
  const minS=document.getElementById('rent-min'),maxS=document.getElementById('rent-max');
  if (type==='min'&&+minS.value>+maxS.value) minS.value=maxS.value;
  if (type==='max'&&+maxS.value<+minS.value) maxS.value=minS.value;
  document.getElementById('rent-min-val').innerText=(+minS.value).toFixed(1);
  document.getElementById('rent-max-val').innerText=(+maxS.value).toFixed(1);
}}
function setAllMadori(checked) {{
  document.querySelectorAll('.madori-pill').forEach(pill=>{{ const cb=pill.querySelector('input[type=checkbox]'); cb.checked=checked; pill.classList.toggle('checked',checked); }});
  filterMarkers();
}}
const script=document.createElement('script');
script.src='https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap';
script.async=true;
document.head.appendChild(script);
</script>
</body>
</html>"""

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'🎉 マップHTMLを生成しました: {filename}')
    return filename
