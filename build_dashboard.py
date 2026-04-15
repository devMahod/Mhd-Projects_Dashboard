#!/usr/bin/env python3
"""Build Mahod GIS Dashboard - convert shapefiles and generate HTML."""

import json
import math
import base64
import shapefile
from pyproj import Transformer

BASE = "c:/Users/lins/Desktop/Claude"
OUT_HTML = f"{BASE}/dashboard.html"

transformer = Transformer.from_crs("EPSG:2039", "EPSG:4326", always_xy=True)

# ── Helper: read logo as base64 ──────────────────────────────────────
with open(f"{BASE}/Group-184502@2x.png", "rb") as f:
    logo_b64 = base64.b64encode(f.read()).decode("ascii")

# ── Helper: convert shapes ───────────────────────────────────────────
def convert_shapefile(path, encoding="cp1255", skip_fields=None):
    """Return a GeoJSON FeatureCollection dict."""
    sf = shapefile.Reader(path, encoding=encoding)
    field_names = [f[0] for f in sf.fields[1:]]
    features = []
    for sr in sf.iterShapeRecords():
        shape = sr.shape
        rec = sr.record
        props = {}
        for j, name in enumerate(field_names):
            if skip_fields and name in skip_fields:
                continue
            val = rec[j]
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                val = None
            if isinstance(val, str):
                val = val.replace("\xa0", " ").strip()
            props[name] = val

        st = shape.shapeType
        # Polygon / PolygonZ
        if st in (5, 15, 25):
            parts = list(shape.parts) + [len(shape.points)]
            rings = []
            for i in range(len(shape.parts)):
                ring = []
                for pt in shape.points[parts[i]:parts[i+1]]:
                    lon, lat = transformer.transform(pt[0], pt[1])
                    ring.append([round(lon, 6), round(lat, 6)])
                rings.append(ring)
            geom = {"type": "Polygon", "coordinates": rings}
        # Polyline / PolylineZ
        elif st in (3, 13, 23):
            parts = list(shape.parts) + [len(shape.points)]
            lines = []
            for i in range(len(shape.parts)):
                line = []
                for pt in shape.points[parts[i]:parts[i+1]]:
                    lon, lat = transformer.transform(pt[0], pt[1])
                    line.append([round(lon, 6), round(lat, 6)])
                lines.append(line)
            geom = {"type": "LineString", "coordinates": lines[0]} if len(lines) == 1 else {"type": "MultiLineString", "coordinates": lines}
        # Point / PointZ
        elif st in (1, 11, 21):
            pt = shape.points[0]
            lon, lat = transformer.transform(pt[0], pt[1])
            geom = {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}
        else:
            continue

        # centroid for polygons
        if st in (5, 15, 25):
            all_c = [c for ring in rings for c in ring]
            props["_clon"] = round(sum(c[0] for c in all_c) / len(all_c), 6)
            props["_clat"] = round(sum(c[1] for c in all_c) / len(all_c), 6)

        features.append({"type": "Feature", "properties": props, "geometry": geom})
    return {"type": "FeatureCollection", "features": features}

# ── Convert project boundaries ───────────────────────────────────────
print("Converting PRJ_SHP_Merge...")
projects = convert_shapefile(f"{BASE}/PRJ_SHP_Merge", encoding="utf-8")
print(f"  {len(projects['features'])} projects")

# ── Convert statutory plans ──────────────────────────────────────────
print("Converting statutory plans (Land_Use_Plan_605-0150086)...")
statutory = convert_shapefile(f"{BASE}/Land_Use_Plan_605-0150086", encoding="utf-8")
# Convert dates to strings
for feat in statutory["features"]:
    if "DATA_DATE" in feat["properties"]:
        v = feat["properties"]["DATA_DATE"]
        feat["properties"]["DATA_DATE"] = str(v) if v else ""
print(f"  {len(statutory['features'])} statutory cells")

# Group plans by project ID - take the plan-level info from first feature per project
plans_by_project = {}
for feat in statutory["features"]:
    p = feat["properties"]
    prj_id = p.get("Prj_ID_MHD", "")
    if prj_id and prj_id not in plans_by_project:
        plans_by_project[prj_id] = {
            "plan_no": p.get("plan_no", ""),
            "plan": p.get("plan", ""),
            "DATA_DATE": p.get("DATA_DATE", ""),
            "status": p.get("status", ""),
            "district": p.get("district", ""),
            "SUB_D": p.get("SUB_D", ""),
            "authority": p.get("authority", ""),
            "plan_type": p.get("plan_type", ""),
            "initiator": p.get("initiator", ""),
            "Prj_ID_MHD": prj_id,
        }
print(f"  {len(plans_by_project)} projects with plans")

# ── Convert infrastructure layers ────────────────────────────────────
infra_layers = {
    # ביוב
    "biuv_line":           f"{BASE}/UT_BIUV_LINE",
    "biuv_point":          f"{BASE}/UT_BIUV_POINT",
    "biuv_kolhin_line":    f"{BASE}/UT_BIUV_KAV_KOLHIN_ML_LINE",
    "biuv_kolhin_point":   f"{BASE}/UT_BIUV_KAV_KOLHIN_ML_POINT",
    "biuv_snika_line":     f"{BASE}/UT_BIUV_KAV_SNIKA_ML_LINE",
    # דלק
    "delek_line":          f"{BASE}/UT_DELEK_TAHAN_LINE",
    "delek_polygon":       f"{BASE}/UT_DELEK_TAHAN_POLYGON",
    # חשמל
    "hashmal_line":        f"{BASE}/UT_HASHMAL_LINE",
    "hashmal_point":       f"{BASE}/UT_HASHMAL_POINT",
    # מים
    "water_line":          f"{BASE}/UT_WATER_MTL_LINE",
    "water_point":         f"{BASE}/UT_WATER_MTL_POINT",
    "water_mekorot_line":  f"{BASE}/UT_WATER_MTL_MEKOROT_LINE",
    "water_mekorot_point": f"{BASE}/UT_WATER_MTL_MEKOROT_POINT",
    # תקשורת
    "telecom_line":        f"{BASE}/UT_TEL_BEZEQ_MTL_LINE",
    "telecom_point":       f"{BASE}/UT_TEL_BEZEQ_MTL_POINT",
}

infra_data = {}
for key, path in infra_layers.items():
    print(f"Converting {key}...")
    infra_data[key] = convert_shapefile(path)
    print(f"  {len(infra_data[key]['features'])} features")

# Group infra by category for JS
infra_groups = {
    "biuv": {
        "name": "ביוב",
        "color": "#a3e635",
        "lines": ["biuv_line", "biuv_kolhin_line", "biuv_snika_line"],
        "points": ["biuv_point", "biuv_kolhin_point"],
        "polygons": [],
    },
    "delek": {
        "name": "דלק",
        "color": "#a855f7",
        "lines": ["delek_line"],
        "points": [],
        "polygons": ["delek_polygon"],
    },
    "hashmal": {
        "name": "חשמל",
        "color": "#facc15",
        "lines": ["hashmal_line"],
        "points": ["hashmal_point"],
        "polygons": [],
    },
    "water": {
        "name": "מים",
        "color": "#38bdf8",
        "lines": ["water_line", "water_mekorot_line"],
        "points": ["water_point", "water_mekorot_point"],
        "polygons": [],
    },
    "telecom": {
        "name": "תקשורת",
        "color": "#00e5ff",
        "lines": ["telecom_line"],
        "points": ["telecom_point"],
        "polygons": [],
    },
}

# ── Load ortho tiles info ────────────────────────────────────────────
import os
tiles_json_path = f"{BASE}/ortho_tiles/tiles.json"
if os.path.exists(tiles_json_path):
    with open(tiles_json_path, "r") as f:
        ortho_tiles = json.load(f)
    print(f"Loaded {len(ortho_tiles)} ortho tiles")
else:
    ortho_tiles = []
    print("No ortho tiles found")

# ── Load polygon symbology from LYRX ─────────────────────────────────
sym_path = f"{BASE}/symbology_polygon.json"
if os.path.exists(sym_path):
    with open(sym_path, "r", encoding="utf-8") as f:
        polygon_symbology = json.load(f)
    print(f"Loaded {len(polygon_symbology)} symbology entries")
else:
    polygon_symbology = {}

# ── Build HTML ───────────────────────────────────────────────────────
html = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mahod - Projects Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css">
<script src="https://js.arcgis.com/4.30/"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
:root{
    --bg:#0f172a; --bg2:#1e293b; --border:#334155; --text:#e2e8f0; --text-dim:#94a3b8;
    --accent:#38bdf8; --card:#0f172a; --hover:#334155;
}
body.light{
    --bg:#f1f5f9; --bg2:#ffffff; --border:#cbd5e1; --text:#1e293b; --text-dim:#64748b;
    --accent:#0284c7; --card:#f8fafc; --hover:#e2e8f0;
}
body{font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:var(--bg);color:var(--text);overflow:hidden;height:100vh;transition:background 0.3s, color 0.3s;}

/* ── Navbar ─────────────────────────────────────────── */
.navbar{
    display:flex;align-items:center;justify-content:space-between;
    background:var(--bg2);
    padding:10px 24px;border-bottom:1px solid var(--border);height:60px;
    transition:background 0.3s,border-color 0.3s;
}
.navbar-right{display:flex;align-items:center;gap:12px;}
.navbar-logo{height:38px;}
.navbar-left{display:flex;gap:8px;align-items:center;}
.stat-box{text-align:center;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:6px 14px;}
.theme-toggle{
    width:28px;height:28px;border-radius:8px;border:1px solid var(--border);
    background:var(--bg);color:var(--text);cursor:pointer;
    display:flex;align-items:center;justify-content:center;
    font-size:12px;transition:all 0.2s;margin-right:4px;
}
.theme-toggle:hover{border-color:var(--accent);}
.stat-box.clickable{cursor:pointer;transition:border-color 0.2s;}
.stat-box.clickable:hover{border-color:#38bdf8;}
.stat-num{font-size:20px;font-weight:700;color:#38bdf8;}
.stat-label{font-size:10px;color:var(--text-dim);margin-top:1px;}

/* ── Layout ─────────────────────────────────────────── */
.main{display:grid;grid-template-columns:var(--left-w,380px) 1fr 320px;height:calc(100vh - 60px);direction:ltr;}
.panel-left{grid-column:1;}
.map-container{grid-column:2;}
.main>.panel{grid-column:3;}
.main.no-left{--left-w:0px;}
.main.no-left .panel-left{display:none;}
.panel-left{background:var(--bg2);border-right:1px solid var(--border);overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;direction:rtl;}
.panel-left .placeholder{color:#475569;font-size:13px;text-align:center;padding:40px 10px;}
.main>.panel{direction:rtl;}
.map-container{display:flex;flex-direction:column;overflow:hidden;order:2;}
#map{width:100%;height:50%;}
#map2{width:100%;height:calc(50% - 6px);overflow:hidden;position:relative;}
.map-resizer{
    height:6px;background:var(--border);cursor:row-resize;
    display:flex;align-items:center;justify-content:center;
    transition:background 0.15s;flex-shrink:0;position:relative;z-index:500;
}
.map-resizer:hover,.map-resizer.dragging{background:#38bdf8;}
.map-resizer::after{
    content:'';width:40px;height:2px;background:#64748b;border-radius:1px;
    transition:background 0.15s;
}
.map-resizer:hover::after,.map-resizer.dragging::after{background:#fff;}

/* ── Right Panel ────────────────────────────────────── */
.panel{background:var(--bg2);border-left:1px solid var(--border);overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;order:3;}
.panel-title{font-size:12px;font-weight:600;color:var(--text);letter-spacing:1px;padding-bottom:6px;border-bottom:1px solid var(--border);margin-top:4px;}
.search-box{width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;}
.search-box:focus{outline:none;border-color:#38bdf8;}
.search-box::placeholder{color:#64748b;}

/* Project list */
.prj-list{max-height:220px;overflow-y:auto;display:flex;flex-direction:column;gap:2px;}
.prj-item{padding:8px;border-radius:6px;cursor:pointer;transition:background 0.15s;font-size:12px;border:1px solid transparent;}
.prj-item:hover{background:var(--border);}
.prj-item.active{background:rgba(245,158,11,0.12);border-color:#f59e0b;border-width:2px;}
.prj-item .pi-num{font-weight:700;color:#38bdf8;margin-left:6px;}
.prj-item .pi-name{color:var(--text);}
.prj-item .pi-sub{color:var(--text-dim);font-size:11px;margin-top:2px;}

/* Info card */
.info-card{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px;}
.info-card h3{font-size:14px;color:#38bdf8;margin-bottom:10px;font-weight:600;}
.info-row{display:flex;justify-content:space-between;padding:3px 0;font-size:12px;}
.info-label{color:var(--text-dim);}
.info-value{color:var(--text);font-weight:500;max-width:200px;text-align:left;}
.panel-left .info-row{gap:8px;align-items:flex-start;}
.panel-left .info-label{flex-shrink:0;white-space:nowrap;}
.panel-left .info-value{max-width:none;flex:1;text-align:left;word-break:break-word;}
.no-selection{color:#64748b;font-size:13px;text-align:center;padding:30px 0;}

/* Categories */
.cat-grid{display:flex;flex-wrap:wrap;gap:5px;}
.cat-chip{
    display:flex;align-items:center;gap:4px;padding:4px 10px;
    background:var(--bg);border:1px solid var(--border);border-radius:14px;
    font-size:11px;color:var(--text-dim);cursor:pointer;user-select:none;transition:all 0.2s;
}
.cat-chip input{display:none;}
.cat-chip .chip-dot{width:7px;height:7px;border-radius:50%;background:#475569;transition:all 0.2s;}
.cat-chip:has(input:checked){border-color:var(--c);color:var(--text);background:color-mix(in srgb,var(--c) 12%,var(--bg));}
.cat-chip:has(input:checked) .chip-dot{background:var(--c);box-shadow:0 0 5px var(--c);}
.cat-chip:has(input:disabled){opacity:0.35;cursor:default;}

/* Infra sub-chips */
.infra-sub{margin-top:6px;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:8px;display:none;flex-wrap:wrap;gap:5px;}
.infra-sub.visible{display:flex;}
.infra-chip{
    display:flex;align-items:center;gap:4px;padding:3px 8px;
    background:var(--bg2);border:1px solid var(--border);border-radius:10px;
    font-size:10px;color:var(--text-dim);cursor:pointer;user-select:none;transition:all 0.2s;
}
.infra-chip input{display:none;}
.infra-chip .idot{width:6px;height:6px;border-radius:50%;background:#475569;transition:all 0.2s;}
.infra-chip:has(input:checked){border-color:var(--c);color:var(--text);}
.infra-chip:has(input:checked) .idot{background:var(--c);box-shadow:0 0 4px var(--c);}

/* Geometry toggles */
.geom-row{display:flex;gap:14px;}
.toggle-label{display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;color:var(--text);user-select:none;}
.toggle-label input{display:none;}
.toggle-slider{width:32px;height:18px;background:var(--border);border-radius:9px;position:relative;transition:background 0.3s;}
.toggle-slider::after{content:'';position:absolute;width:14px;height:14px;background:var(--text-dim);border-radius:50%;top:2px;left:2px;transition:all 0.3s;}
.toggle-label input:checked+.toggle-slider{background:var(--c,#38bdf8);}
.toggle-label input:checked+.toggle-slider::after{transform:translateX(14px);background:#fff;}
.layer-count{font-size:10px;color:#64748b;margin-top:4px;}

/* Map overlay buttons */
.map-overlay{
    position:absolute;bottom:30px;right:14px;z-index:1000;
    display:none;flex-direction:column;gap:5px;
}
.map-overlay.visible{display:flex;}
.map-btn{
    display:flex;align-items:center;gap:8px;
    padding:7px 18px;border-radius:20px;border:none;
    font-size:12px;font-weight:500;font-family:inherit;
    cursor:pointer;direction:rtl;transition:all 0.25s;
    color:var(--text-dim);min-width:110px;justify-content:center;
    background:rgba(15,23,42,0.75);backdrop-filter:blur(12px);
    border:1px solid var(--border);
}
.map-btn:hover{border-color:#64748b;color:var(--text);}
.map-btn.active{background:rgba(30,41,59,0.9);border-color:#38bdf8;color:var(--text);}
.map-btn .btn-icon{display:flex;align-items:center;justify-content:center;width:16px;height:16px;flex-shrink:0;}
.map-btn.btn-polygon .btn-icon::after{content:'';width:9px;height:9px;background:#f59e0b;transform:rotate(45deg);border-radius:1.5px;opacity:0.6;transition:opacity 0.2s;}
.map-btn.btn-polygon.active .btn-icon::after{opacity:1;box-shadow:0 0 6px rgba(245,158,11,0.5);}
.map-btn.btn-points .btn-icon::after{content:'';width:8px;height:8px;background:#ef4444;border-radius:50%;opacity:0.6;transition:opacity 0.2s;}
.map-btn.btn-points.active .btn-icon::after{opacity:1;box-shadow:0 0 6px rgba(239,68,68,0.5);}
.map-btn.btn-lines .btn-icon{gap:2px;}
.map-btn.btn-lines .btn-icon span{width:6px;height:2px;background:#4ade80;border-radius:1px;opacity:0.6;transition:opacity 0.2s;}
.map-btn.btn-lines.active .btn-icon span{opacity:1;box-shadow:0 0 4px rgba(74,222,128,0.4);}

/* 3D rotation controls */
.rot-controls{
    position:absolute;bottom:20px;left:20px;z-index:1000;
    display:flex;flex-direction:column;gap:4px;
    background:rgba(15,23,42,0.85);backdrop-filter:blur(10px);
    border:1px solid var(--border);border-radius:10px;padding:6px;
}
.rot-btn{
    width:36px;height:36px;border:none;border-radius:6px;
    background:rgba(30,41,59,0.8);color:var(--text-dim);
    font-size:18px;font-weight:600;cursor:pointer;
    transition:all 0.2s;font-family:inherit;
    display:flex;align-items:center;justify-content:center;
}
.rot-btn:hover{background:#38bdf8;color:#fff;}

/* Leaflet popup override */
.leaflet-popup-content-wrapper{background:var(--bg2)!important;color:var(--text)!important;border-radius:10px!important;border:1px solid var(--border);direction:rtl;}
.leaflet-popup-tip{background:var(--bg2)!important;}
.leaflet-popup-content{font-size:12px;line-height:1.5;margin:8px 12px;}

/* Esri 3D popup styling - clean minimal box like Leaflet popup */
.esri-popup__main-container,
.esri-popup--is-docked .esri-popup__main-container,
.esri-popup--is-docked-top-right .esri-popup__main-container{
    background:var(--bg2)!important;color:var(--text)!important;
    border:1px solid var(--border)!important;border-radius:10px!important;
    box-shadow:0 4px 20px rgba(0,0,0,0.4)!important;
    min-height:auto!important;
    max-height:none!important;
    width:auto!important;min-width:0!important;max-width:260px!important;
    height:auto!important;
}
.esri-popup__position-container{width:auto!important;}
.esri-popup--is-docked,
.esri-popup--is-docked-top-right{width:auto!important;height:auto!important;max-width:260px!important;}
.esri-popup__header{display:none!important;}
.esri-popup__footer{display:none!important;}
.esri-popup__navigation{display:none!important;}
.esri-popup__pagination{display:none!important;}
.esri-popup__pagination-previous{display:none!important;}
.esri-popup__pagination-next{display:none!important;}
.esri-popup__action-text{display:none!important;}
.esri-popup__feature-menu-button{display:none!important;}
.esri-popup__inline-actions-container{display:none!important;}
.esri-popup__action[title*="Zoom"]{display:none!important;}
.esri-popup__action{display:none!important;}
.esri-features__container .esri-features__title{display:none!important;}
.esri-features__pagination{display:none!important;}
.esri-features__navigation{display:none!important;}
.esri-features__paging-info{display:none!important;}
.esri-popup__content{
    background:transparent!important;color:var(--text)!important;
    margin:0!important;padding:0!important;
}
.esri-popup__pointer{visibility:hidden;}
.esri-popup-mhd{direction:rtl;font-size:11px;line-height:1.4;padding:8px 11px;min-width:140px;position:relative;}
.esri-popup-mhd .popup-h3{font-size:12px;font-weight:700;color:#38bdf8;margin-bottom:5px;padding-bottom:4px;border-bottom:1px solid var(--border);padding-left:14px;}
.esri-popup-mhd .ir{display:flex;justify-content:space-between;gap:6px;padding:1px 0;}
.esri-popup-mhd .il{color:var(--text-dim);flex-shrink:0;white-space:nowrap;font-size:11px;}
.esri-popup-mhd .iv{color:var(--text);font-weight:500;text-align:left;word-break:break-word;font-size:11px;}

/* Scrollbar */
::-webkit-scrollbar{width:5px;}
::-webkit-scrollbar-track{background:var(--bg);}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
</style>
</head>
<body>

<div class="navbar">
    <div class="navbar-right">
        <img class="navbar-logo" src="data:image/png;base64,LOGO_B64" alt="Mahod">
    </div>
    <div class="navbar-left">
        <div class="stat-box clickable" id="btn-reset" title="חזרה לתצוגת כל הפרויקטים"><div class="stat-num" id="st-total">0</div><div class="stat-label">פרויקטים</div></div>
        <div class="stat-box"><div class="stat-num" id="st-open">0</div><div class="stat-label">פתוחים</div></div>
        <div class="stat-box"><div class="stat-num" id="st-closed">0</div><div class="stat-label">סגורים</div></div>
        <button class="theme-toggle" id="theme-toggle" title="החלף מצב בהיר/כהה">
            <span class="theme-icon">🌙</span>
        </button>
    </div>
</div>

<div class="main">
    <div class="panel-left">
        <div class="placeholder">פאנל שמאלי - בקרוב</div>
    </div>

    <div class="map-container">
        <div id="map" style="position:relative;">
            <div class="map-overlay" id="map-overlay">
                <button class="map-btn btn-polygon active" id="mob-polygon"><span class="btn-icon"></span><span id="mob-label">תיחום</span></button>
                <button class="map-btn btn-points" id="mob-points"><span class="btn-icon"></span>נקודות</button>
                <button class="map-btn btn-lines" id="mob-lines"><span class="btn-icon"><span></span><span></span><span></span></span>קווים</button>
            </div>
        </div>
        <div class="map-resizer" id="map-resizer" title="גרור להרחבה/הקטנה של המפות"></div>
        <div id="map2"></div>
    </div>

    <div class="panel">
        <!-- Search -->
        <div class="panel-title">חיפוש פרויקט</div>
        <input class="search-box" id="search" type="text" placeholder="חיפוש לפי מספר, שם, לקוח...">

        <!-- Project list -->
        <div class="prj-list" id="prj-list"></div>

        <!-- Project info card -->
        <div class="panel-title">פרטי פרויקט</div>
        <div class="info-card" id="info-card">
            <div class="no-selection">בחר פרויקט מהרשימה או מהמפה</div>
        </div>

        <!-- Categories -->
        <div class="panel-title">קטגוריות</div>
        <div class="cat-grid" id="cat-grid">
            <label class="cat-chip" style="--c:#fb923c;"><input type="checkbox" data-cat="transport"><span class="chip-dot"></span>תחבורה</label>
            <label class="cat-chip" style="--c:#34d399;"><input type="checkbox" data-cat="infra"><span class="chip-dot"></span>תיאום תשתיות</label>
            <label class="cat-chip" style="--c:#818cf8;" disabled><input type="checkbox" data-cat="buildings" disabled><span class="chip-dot"></span>מבנים</label>
            <label class="cat-chip" style="--c:#4ade80;" disabled><input type="checkbox" data-cat="vegetation" disabled><span class="chip-dot"></span>צמחייה</label>
            <label class="cat-chip" style="--c:#22d3ee;" disabled><input type="checkbox" data-cat="hydrology" disabled><span class="chip-dot"></span>הידרולוגיה</label>
            <label class="cat-chip" style="--c:#f472b6;" disabled><input type="checkbox" data-cat="acoustics" disabled><span class="chip-dot"></span>אקוסטיקה</label>
            <label class="cat-chip" style="--c:#c084fc;"><input type="checkbox" data-cat="statutory"><span class="chip-dot"></span>סטטוטוריקה</label>
            <label class="cat-chip" style="--c:#fbbf24;" disabled><input type="checkbox" data-cat="geology" disabled><span class="chip-dot"></span>גאולוגיה</label>
        </div>

        <!-- Infra sub-layers (visible when תיאום תשתיות is checked) -->
        <div class="infra-sub" id="infra-sub">
            <label class="infra-chip" style="--c:#a3e635;"><input type="checkbox" data-infra="biuv" checked><span class="idot"></span>ביוב</label>
            <label class="infra-chip" style="--c:#a855f7;"><input type="checkbox" data-infra="delek" checked><span class="idot"></span>דלק</label>
            <label class="infra-chip" style="--c:#facc15;"><input type="checkbox" data-infra="hashmal" checked><span class="idot"></span>חשמל</label>
            <label class="infra-chip" style="--c:#38bdf8;"><input type="checkbox" data-infra="water" checked><span class="idot"></span>מים</label>
            <label class="infra-chip" style="--c:#00e5ff;"><input type="checkbox" data-infra="telecom" checked><span class="idot"></span>תקשורת</label>
        </div>

        <!-- Hidden toggles (controlled by map overlay buttons) -->
        <input type="checkbox" id="show-lines" checked style="display:none;">
        <input type="checkbox" id="show-points" checked style="display:none;">
        <div class="layer-count" id="layer-count"></div>
    </div>

</div>

<script>
// ── Data ────────────────────────────────────────────
const projects = PROJECT_DATA;

const infraGroups = INFRA_GROUPS;
const infraGeoJSON = INFRA_GEOJSON;

const statutoryData = STATUTORY_DATA;
const plansByProject = PLANS_BY_PROJECT;

// ── Ortho tiles data ────────────────────────────────
const orthoTiles = ORTHO_TILES;

// ── Map (top) ───────────────────────────────────────
const map = L.map('map',{center:[31.5,35.0],zoom:8,zoomControl:true});
const darkTile=L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'&copy; OSM & CARTO',maxZoom:19});
const lightTile=L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{attribution:'&copy; OSM & CARTO',maxZoom:19});
const sat=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'&copy; Esri',maxZoom:19});
darkTile.addTo(map);
L.control.layers({'\u05db\u05d4\u05d4':darkTile,'\u05d1\u05d4\u05d9\u05e8':lightTile,'\u05dc\u05d5\u05d5\u05d9\u05df':sat},null,{position:'topright'}).addTo(map);

// ── Vertical resizer between maps ───────────────────
(function setupResizer(){
    const resizer = document.getElementById('map-resizer');
    const mapEl = document.getElementById('map');
    const map2El = document.getElementById('map2');
    const container = document.querySelector('.map-container');
    if (!resizer || !mapEl || !map2El) return;
    let isDragging = false;
    resizer.addEventListener('mousedown', e => {
        isDragging = true;
        resizer.classList.add('dragging');
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'row-resize';
        e.preventDefault();
    });
    document.addEventListener('mousemove', e => {
        if (!isDragging) return;
        const rect = container.getBoundingClientRect();
        const offsetY = e.clientY - rect.top;
        const total = rect.height;
        const minH = 80;
        const topH = Math.max(minH, Math.min(total - minH - 6, offsetY));
        const botH = total - topH - 6;
        mapEl.style.height = topH + 'px';
        map2El.style.height = botH + 'px';
        // Notify Leaflet of size change
        if (typeof map !== 'undefined' && map.invalidateSize) map.invalidateSize();
    });
    document.addEventListener('mouseup', () => {
        if (!isDragging) return;
        isDragging = false;
        resizer.classList.remove('dragging');
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
        if (typeof map !== 'undefined' && map.invalidateSize) map.invalidateSize();
    });
})();

// ── 3D layer refresh ────────────────────────────────
function geoJsonRingsToEsri(geom) {
    if (geom.type === 'Polygon') return geom.coordinates;
    if (geom.type === 'MultiPolygon') return [].concat(...geom.coordinates);
    return [];
}

function hexToRgba(hex, alpha) {
    if (hex.startsWith('rgb')) {
        const m = hex.match(/\d+/g);
        return [parseInt(m[0]),parseInt(m[1]),parseInt(m[2]),alpha];
    }
    const h = hex.replace('#','');
    return [parseInt(h.substr(0,2),16), parseInt(h.substr(2,2),16), parseInt(h.substr(4,2),16), alpha];
}

function refresh3DLayers() {
    if (!projectsGraphicsLayer || !EsriGraphic) return;

    // ── Project polygons ──
    projectsGraphicsLayer.removeAll();
    const filtered = getFilteredProjects();
    const projectPopupTemplate = {
        title: '',
        content: function(feature) {
            const p = feature.graphic.attributes;
            const formatA = a => !a ? '-' : (a > 1e6 ? (a/1e6).toFixed(2)+' \u05e7\u05de"\u05e8' : a > 1000 ? (a/1000).toFixed(1)+' \u05d3\u05d5\u05e0\u05dd' : Math.round(a)+' \u05de"\u05e8');
            return `
                <div class="esri-popup-mhd">
                    <button onclick="sceneView.popup.close()" style="position:absolute;top:5px;left:6px;background:none;border:none;color:#94a3b8;font-size:14px;cursor:pointer;padding:0;line-height:1;z-index:5;">×</button>
                    <div class="popup-h3">${p.Prj_Name||''}</div>
                    <div class="ir"><span class="il">\u05de\u05e1\u05e4\u05e8 \u05e2\u05d1\u05d5\u05d3\u05d4:</span><span class="iv">${p.Work_No||''}</span></div>
                    <div class="ir"><span class="il">\u05e7\u05d8\u05d2\u05d5\u05e8\u05d9\u05d4:</span><span class="iv">${p.Category||''}</span></div>
                    <div class="ir"><span class="il">\u05dc\u05e7\u05d5\u05d7:</span><span class="iv">${p.Client||''}</span></div>
                    <div class="ir"><span class="il">\u05de\u05e0\u05d4\u05dc \u05e6\u05d5\u05d5\u05ea:</span><span class="iv">${p.Team_Leade||''}</span></div>
                    <div class="ir"><span class="il">\u05e8\u05e9\u05d5\u05ea \u05de\u05e7\u05d5\u05de\u05d9\u05ea:</span><span class="iv">${p.Municipali||''}</span></div>
                    <div class="ir"><span class="il">\u05de\u05d7\u05d5\u05d6:</span><span class="iv">${p.Machoz||''}</span></div>
                    <div class="ir"><span class="il">\u05e1\u05d8\u05d8\u05d5\u05e1:</span><span class="iv">${p.Status||''}</span></div>
                    <div class="ir"><span class="il">\u05ea\u05d0\u05e8\u05d9\u05da \u05d4\u05ea\u05d7\u05dc\u05d4:</span><span class="iv">${p.Start_Date||''}</span></div>
                    <div class="ir"><span class="il">\u05ea\u05d0\u05e8\u05d9\u05da \u05e1\u05d9\u05d5\u05dd:</span><span class="iv">${p.End_Date||''}</span></div>
                    <div class="ir"><span class="il">\u05e9\u05d8\u05d7:</span><span class="iv">${formatA(p.Shape_Area)}</span></div>
                </div>`;
        }
    };
    filtered.forEach(f => {
        const isSelected = f.properties.Work_No === selectedProjectId;
        let strokeColor, fillColor;
        if (isSelected) {
            const hl = (f.properties.Status === '\u05e4\u05ea\u05d5\u05d7') ? '#22c55e' : '#ef4444';
            strokeColor = hexToRgba(hl, 1);
            fillColor = hexToRgba(hl, 0.35);
        } else {
            strokeColor = hexToRgba('#38bdf8', 0.7);
            fillColor = hexToRgba('#38bdf8', 0.15);
        }
        const rings = geoJsonRingsToEsri(f.geometry);
        if (!rings.length) return;
        const poly = new EsriPolygon({rings:rings, spatialReference:{wkid:4326}});
        const g = new EsriGraphic({
            geometry: poly,
            symbol: {type:'simple-fill', color:fillColor, outline:{color:strokeColor, width:isSelected?2.5:1.5}},
            attributes: f.properties,
            popupTemplate: projectPopupTemplate
        });
        projectsGraphicsLayer.add(g);
    });
    // Limit click to single feature - prefer statutory over project when both present

    // ── Statutory polygons (only if selected project + statutory category) ──
    statutoryGraphicsLayer.removeAll();
    const statChecked = document.querySelector('[data-cat="statutory"]').checked;
    if (statChecked && selectedProjectId) {
        const projFeats = statutoryData.features.filter(f => String(f.properties.Prj_ID_MHD) === String(selectedProjectId));
        const statPopupTemplate = {
            title: '',
            content: function(feature) {
                const p = feature.graphic.attributes;
                const formatA = a => !a ? '-' : (a >= 1e6 ? (a/1e6).toFixed(2)+' \u05e7\u05de"\u05e8' : a >= 1000 ? (a/1000).toFixed(2)+' \u05d3\u05d5\u05e0\u05dd' : Math.round(a)+' \u05de"\u05e8');
                return `
                    <div class="esri-popup-mhd">
                        <button onclick="sceneView.popup.close()" style="position:absolute;top:5px;left:6px;background:none;border:none;color:#94a3b8;font-size:14px;cursor:pointer;padding:0;line-height:1;z-index:5;">×</button>
                        <div class="popup-h3" style="color:#c084fc;">${p.MAVAT_NAME||''}</div>
                        <div class="ir"><span class="il">\u05de\u05e1\u05e4\u05e8 \u05ea\u05d0:</span><span class="iv">${p.NUM||''}</span></div>
                        <div class="ir"><span class="il">\u05e7\u05d5\u05d3 \u05d9\u05e2\u05d5\u05d3:</span><span class="iv">${p.MAVAT_CODE||''}</span></div>
                        <div class="ir"><span class="il">\u05e9\u05d8\u05d7 \u05ea\u05d0:</span><span class="iv">${formatA(p.AREA)}</span></div>
                    </div>`;
            }
        };
        projFeats.forEach(f => {
            const color = getMavatColor(f.properties.MAVAT_CODE);
            const rings = geoJsonRingsToEsri(f.geometry);
            if (!rings.length) return;
            const poly = new EsriPolygon({rings:rings, spatialReference:{wkid:4326}});
            const g = new EsriGraphic({
                geometry: poly,
                symbol: {type:'simple-fill', color:hexToRgba(color, 0.75), outline:{color:[30,41,59,0.9], width:0.5}},
                attributes: f.properties,
                popupTemplate: statPopupTemplate
            });
            statutoryGraphicsLayer.add(g);
        });
    }
}

// ── Map 2 (bottom - 3D buildings via ArcGIS API) ────
let sceneView = null;
let projectsGraphicsLayer = null;
let statutoryGraphicsLayer = null;
let EsriGraphic = null;
let EsriPolygon = null;
require([
    "esri/views/SceneView",
    "esri/Map",
    "esri/layers/SceneLayer",
    "esri/layers/GraphicsLayer",
    "esri/Graphic",
    "esri/geometry/Polygon",
    "esri/Basemap"
], (SceneView, EsriMap, SceneLayer, GraphicsLayer, Graphic, Polygon, Basemap) => {
    EsriGraphic = Graphic;
    EsriPolygon = Polygon;

    const buildings = new SceneLayer({
        url: "https://basemaps3d.arcgis.com/arcgis/rest/services/Esri3D_Buildings_v1/SceneServer/layers/0"
    });

    projectsGraphicsLayer = new GraphicsLayer({elevationInfo:{mode:'on-the-ground'}});
    statutoryGraphicsLayer = new GraphicsLayer({elevationInfo:{mode:'on-the-ground'}});

    const scene = new EsriMap({
        basemap: "topo-vector",
        ground: "world-elevation",
        layers: [buildings, projectsGraphicsLayer, statutoryGraphicsLayer]
    });
    sceneView = new SceneView({
        container: "map2",
        map: scene,
        camera: {
            position: { longitude: 35.0, latitude: 31.5, z: 5000 },
            tilt: 70,
            heading: 0
        },
        ui: { components: ["zoom", "compass", "navigation-toggle"] },
        constraints: {
            tilt: { max: 90, min: 0 },
            altitude: { min: 50 }
        },
        navigation: {
            mouseWheelZoomEnabled: true,
            browserTouchPanEnabled: true,
            momentumEnabled: true
        },
        popup: {
            dockEnabled: false,
            dockOptions: { buttonEnabled: false, breakpoint: false },
            collapseEnabled: false,
            alignment: "auto"
        }
    });

    // Initial render of project boundaries on 3D
    refresh3DLayers();

    // Sync 2D map -> 3D scene on user interaction (keep user's tilt/heading)
    let syncing = false;
    map.on('drag zoomend', () => {
        if (syncing) return;
        syncing = true;
        const c = map.getCenter();
        const z = map.getZoom();
        const altitude = Math.max(300, 40075000 / Math.pow(2, z));
        sceneView.goTo({
            target: [c.lng, c.lat],
            zoom: z,
            tilt: sceneView.camera.tilt || 70,
            heading: sceneView.camera.heading
        }, { animate: false });
        setTimeout(() => syncing = false, 100);
    });

    // Sync 3D scene -> 2D map on user interaction
    sceneView.watch("stationary", (isStationary) => {
        if (!isStationary || syncing) return;
        syncing = true;
        const c = sceneView.center;
        if (c) {
            const z = Math.max(2, Math.min(19, Math.round(Math.log2(40075000 / sceneView.camera.position.z))));
            map.setView([c.latitude, c.longitude], z, { animate: false });
        }
        setTimeout(() => syncing = false, 100);
    });
});

// ── Project layer ───────────────────────────────────
let projectLayer = null;
let selectedProjectId = null;
let selectedMarker = null;
const PROJ_STYLE = {color:'#38bdf8',weight:2,opacity:0.7,fillColor:'#38bdf8',fillOpacity:0.15};
const PROJ_HIGHLIGHT_OPEN = {color:'#22c55e',weight:3,opacity:1,fillColor:'#22c55e',fillOpacity:0.3};
const PROJ_HIGHLIGHT_CLOSED = {color:'#ef4444',weight:3,opacity:1,fillColor:'#ef4444',fillOpacity:0.3};
function getHighlightStyle(p){return (p.Status==='\u05e4\u05ea\u05d5\u05d7') ? PROJ_HIGHLIGHT_OPEN : PROJ_HIGHLIGHT_CLOSED;}

function renderProjects(featList) {
    if (projectLayer) map.removeLayer(projectLayer);
    projectLayer = L.geoJSON({type:'FeatureCollection',features:featList},{
        style: f => (f.properties.Work_No === selectedProjectId) ? getHighlightStyle(f.properties) : PROJ_STYLE,
        onEachFeature:(f,l)=>{
            l.on('click',()=>selectProject(f.properties.Work_No));
        }
    }).addTo(map);
    if (featList.length) map.fitBounds(projectLayer.getBounds(),{padding:[20,20]});
}

// ── Stats ───────────────────────────────────────────
function updateStats(featList) {
    const total = featList.length;
    const open = featList.filter(f=>f.properties.Status==='\u05e4\u05ea\u05d5\u05d7').length;
    const closed = total - open;
    const area = featList.reduce((s,f)=>s+(f.properties.Shape_Area||0),0);
    document.getElementById('st-total').textContent = total;
    document.getElementById('st-open').textContent = open;
    document.getElementById('st-closed').textContent = closed;
    document.getElementById('st-area').textContent = area > 1000 ? Math.round(area/1000).toLocaleString() : Math.round(area).toLocaleString();
}

// ── Project list ────────────────────────────────────
function renderList(featList) {
    const container = document.getElementById('prj-list');
    container.innerHTML = '';
    featList.forEach(f => {
        const p = f.properties;
        const div = document.createElement('div');
        div.className = 'prj-item' + (p.Work_No === selectedProjectId ? ' active' : '');
        div.innerHTML = `<span class="pi-num">${p.Work_No}</span><span class="pi-name">${p.Prj_Name||''}</span><div class="pi-sub">${p.Client||''} | ${p.Municipali||''}</div>`;
        div.onclick = () => selectProject(p.Work_No);
        container.appendChild(div);
    });
}

// ── Select project ──────────────────────────────────
function selectProject(workNo) {
    selectedProjectId = workNo;
    const feat = projects.features.find(f => f.properties.Work_No === workNo);
    if (!feat) return;
    const p = feat.properties;

    // Remove old marker
    if (selectedMarker) { map.removeLayer(selectedMarker); selectedMarker = null; }

    // Highlight on map and fit bounds to selected polygon
    if (projectLayer) {
        projectLayer.eachLayer(l => {
            if (l.feature.properties.Work_No === workNo) {
                l.setStyle(getHighlightStyle(l.feature.properties));
                l.bringToFront();
                // Fit to polygon bounds with padding
                if (l.getBounds) map.fitBounds(l.getBounds(), {padding:[80,80], maxZoom:16});
            } else {
                l.setStyle(PROJ_STYLE);
            }
        });
    }

    // Add centroid marker with project number - colored by status
    if (p._clat && p._clon) {
        const mc = (p.Status === '\u05e4\u05ea\u05d5\u05d7') ? '#22c55e' : '#ef4444';
        selectedMarker = L.marker([p._clat, p._clon], {
            icon: L.divIcon({
                className: '',
                html: `<div style="width:14px;height:14px;background:${mc};border:2px solid #fff;border-radius:50%;box-shadow:0 0 8px ${mc}99;"></div>`,
                iconSize:[14,14],iconAnchor:[7,7]
            })
        }).addTo(map).bindPopup('<b>\u05ea\u05d9\u05d7\u05d5\u05dd ' + p.Work_No + '</b><br>' + (p.Prj_Name||''));
    }

    // Update map overlay buttons
    updateMapOverlay(workNo);

    // Info card
    const card = document.getElementById('info-card');
    function formatArea(a){if(!a)return'-';if(a>1e6)return (a/1e6).toFixed(2)+' \u05e7\u05de"\u05e8';if(a>1000)return (a/1000).toFixed(1)+' \u05d3\u05d5\u05e0\u05dd';return Math.round(a)+' \u05de"\u05e8';}
    card.innerHTML = `
        <h3>${p.Prj_Name || '\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8 ' + p.Work_No}</h3>
        <div class="info-row"><span class="info-label">\u05de\u05e1\u05e4\u05e8 \u05e2\u05d1\u05d5\u05d3\u05d4:</span><span class="info-value">${p.Work_No||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e7\u05d8\u05d2\u05d5\u05e8\u05d9\u05d4:</span><span class="info-value">${p.Category||''}</span></div>
        <div class="info-row"><span class="info-label">\u05dc\u05e7\u05d5\u05d7:</span><span class="info-value">${p.Client||''}</span></div>
        <div class="info-row"><span class="info-label">\u05de\u05e0\u05d4\u05dc \u05e6\u05d5\u05d5\u05ea:</span><span class="info-value">${p.Team_Leade||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e8\u05e9\u05d5\u05ea \u05de\u05e7\u05d5\u05de\u05d9\u05ea:</span><span class="info-value">${p.Municipali||''}</span></div>
        <div class="info-row"><span class="info-label">\u05de\u05d7\u05d5\u05d6:</span><span class="info-value">${p.Machoz||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e1\u05d8\u05d8\u05d5\u05e1:</span><span class="info-value">${p.Status||''}</span></div>
        <div class="info-row"><span class="info-label">\u05ea\u05d0\u05e8\u05d9\u05da \u05d4\u05ea\u05d7\u05dc\u05d4:</span><span class="info-value">${p.Start_Date||''}</span></div>
        <div class="info-row"><span class="info-label">\u05ea\u05d0\u05e8\u05d9\u05da \u05e1\u05d9\u05d5\u05dd:</span><span class="info-value">${p.End_Date||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e9\u05d8\u05d7:</span><span class="info-value">${formatArea(p.Shape_Area)}</span></div>
        <div class="info-row"><span class="info-label">\u05d4\u05d9\u05e7\u05e3:</span><span class="info-value">${p.Shape_Leng ? p.Shape_Leng.toFixed(0)+' \u05de\u05d8\u05e8' : '-'}</span></div>
    `;

    // Update list active state
    document.querySelectorAll('.prj-item').forEach(el => {
        const num = parseInt(el.querySelector('.pi-num').textContent);
        el.classList.toggle('active', num === workNo);
    });

    // Refresh statutory display if active
    updateStatutory();
    refresh3DLayers();
}

// ── Map overlay buttons ─────────────────────────────
let mapOverlayStates = { polygon: true, points: false, lines: false };

function updateMapOverlay(workNo) {
    const overlay = document.getElementById('map-overlay');
    overlay.classList.add('visible');
    document.getElementById('mob-label').textContent = '\u05ea\u05d9\u05d7\u05d5\u05dd ' + workNo;
    syncOverlayButtons();
}

function hideMapOverlay() {
    document.getElementById('map-overlay').classList.remove('visible');
    mapOverlayStates = { polygon: true, points: false, lines: false };
}

function syncOverlayButtons() {
    document.getElementById('mob-polygon').classList.toggle('active', mapOverlayStates.polygon);
    document.getElementById('mob-points').classList.toggle('active', mapOverlayStates.points);
    document.getElementById('mob-lines').classList.toggle('active', mapOverlayStates.lines);
    // Sync with the panel toggles
    document.getElementById('show-points').checked = mapOverlayStates.points;
    document.getElementById('show-lines').checked = mapOverlayStates.lines;
    // Show/hide project polygon
    if (projectLayer && selectedProjectId) {
        projectLayer.eachLayer(l => {
            if (l.feature.properties.Work_No === selectedProjectId) {
                l.setStyle(mapOverlayStates.polygon ? getHighlightStyle(l.feature.properties) : {opacity:0,fillOpacity:0});
            }
        });
    }
    updateInfra();
}

document.getElementById('mob-polygon').addEventListener('click', () => {
    mapOverlayStates.polygon = !mapOverlayStates.polygon;
    syncOverlayButtons();
});
document.getElementById('mob-points').addEventListener('click', () => {
    mapOverlayStates.points = !mapOverlayStates.points;
    syncOverlayButtons();
});
document.getElementById('mob-lines').addEventListener('click', () => {
    mapOverlayStates.lines = !mapOverlayStates.lines;
    syncOverlayButtons();
});

// ── Search / filter ─────────────────────────────────
function getFilteredProjects() {
    const q = document.getElementById('search').value.toLowerCase();
    return projects.features.filter(f => {
        const p = f.properties;
        if (!q) return true;
        return [String(p.Work_No), p.Prj_Name, p.Client, p.Municipali, p.Team_Leade, p.Category, p.Machoz]
            .join(' ').toLowerCase().includes(q);
    });
}

function refresh() {
    const filtered = getFilteredProjects();
    renderProjects(filtered);
    renderList(filtered);
    updateStats(filtered);
    updateInfra();
    refresh3DLayers();
}

document.getElementById('search').addEventListener('input', refresh);

// ── Infrastructure layers ───────────────────────────
let activeInfraLayers = [];

function makeInfraPopup(p, color) {
    return `
        <div style="font-weight:700;color:${color};margin-bottom:4px;">${p.DATA_OWN||''} - ${p.INFRA_TYPE||p.INFRA_CAT||''}</div>
        <div class="info-row"><span class="info-label">\u05e7\u05d8\u05d2\u05d5\u05e8\u05d9\u05d4:</span><span class="info-value">${p.INFRA_CAT||''}</span></div>
        <div class="info-row"><span class="info-label">\u05ea\u05ea-\u05e7\u05d8\u05d2\u05d5\u05e8\u05d9\u05d4:</span><span class="info-value">${p.INFRA_SUB||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e1\u05d5\u05d2:</span><span class="info-value">${p.INFRA_TYPE||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e1\u05d8\u05d8\u05d5\u05e1:</span><span class="info-value">${p.STATUS||''}</span></div>
        <div class="info-row"><span class="info-label">\u05d7\u05d5\u05de\u05e8:</span><span class="info-value">${p.MATERIAL||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e7\u05d5\u05d8\u05e8:</span><span class="info-value">${p.DIAMETER||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e2\u05d5\u05de\u05e7:</span><span class="info-value">${p.DEPTH_M||''}</span></div>
        <div class="info-row"><span class="info-label">\u05d1\u05e2\u05dc\u05d9\u05dd:</span><span class="info-value">${p.DATA_OWN||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e1\u05e4\u05e7:</span><span class="info-value">${p.PROVIDER||''}</span></div>
        ${p.DESCRIPT?'<div class="info-row"><span class="info-label">\u05ea\u05d9\u05d0\u05d5\u05e8:</span><span class="info-value">'+p.DESCRIPT+'</span></div>':''}
    `;
}

// ── Statutory layer ─────────────────────────────────
let statutoryLayer = null;

// MAVAT code -> {label, color} from ArcGIS Pro LYRX
const MAVAT_SYMBOLOGY = POLYGON_SYMBOLOGY;
function getMavatColor(code) {
    const e = MAVAT_SYMBOLOGY[String(code)];
    return e && e.color ? e.color : '#c084fc';
}

function formatAreaCell(a) {
    if (!a) return '-';
    if (a >= 1e6) return (a/1e6).toFixed(2) + ' \u05e7\u05de"\u05e8';
    if (a >= 1000) return (a/1000).toFixed(2) + ' \u05d3\u05d5\u05e0\u05dd';
    return Math.round(a) + ' \u05de"\u05e8';
}

function makeStatutoryPopup(p) {
    return `
        <div style="font-weight:700;color:#c084fc;margin-bottom:6px;font-size:13px;">${p.MAVAT_NAME||'\u05ea\u05d0 \u05e9\u05d8\u05d7'}</div>
        <div class="info-row"><span class="info-label">\u05de\u05e1\u05e4\u05e8 \u05ea\u05d0:</span><span class="info-value">${p.NUM||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e7\u05d5\u05d3 \u05d9\u05e2\u05d5\u05d3:</span><span class="info-value">${p.MAVAT_CODE||''}</span></div>
        <div class="info-row"><span class="info-label">\u05e9\u05d8\u05d7 \u05ea\u05d0:</span><span class="info-value">${formatAreaCell(p.AREA)}</span></div>
    `;
}

function updateStatutory() {
    if (statutoryLayer) { map.removeLayer(statutoryLayer); statutoryLayer = null; }
    const leftPanel = document.querySelector('.panel-left');
    const statChecked = document.querySelector('[data-cat="statutory"]').checked;
    refresh3DLayers();

    if (!statChecked || !selectedProjectId) {
        leftPanel.innerHTML = '<div class="placeholder">בחר פרויקט וסמן \"סטטוטוריקה\" כדי לראות מידע התכנית</div>';
        return;
    }

    // Filter polygons for this project
    const projectFeats = statutoryData.features.filter(f => {
        return String(f.properties.Prj_ID_MHD) === String(selectedProjectId);
    });

    if (projectFeats.length === 0) {
        leftPanel.innerHTML = '<div class="placeholder">אין מידע סטטוטורי לפרויקט זה</div>';
        return;
    }

    // Render polygons on map - colored per MAVAT code (from ArcGIS Pro LYRX)
    statutoryLayer = L.geoJSON({type:'FeatureCollection',features:projectFeats}, {
        style: f => {
            const color = getMavatColor(f.properties.MAVAT_CODE);
            return {color:'#1e293b', weight:0.5, opacity:0.9, fillColor:color, fillOpacity:0.75};
        },
        onEachFeature:(f,l)=>{
            l.bindPopup(makeStatutoryPopup(f.properties),{maxWidth:280});
            l.on({
                mouseover:e=>e.target.setStyle({weight:2.5,color:'#fff',fillOpacity:0.95}),
                mouseout:e=>e.target.setStyle({weight:0.5,color:'#1e293b',fillOpacity:0.75})
            });
        }
    }).addTo(map);

    // Show plan info in left panel
    const plan = plansByProject[String(selectedProjectId)];
    if (plan) {
        leftPanel.innerHTML = `
            <div class="panel-title">\u05de\u05d9\u05d3\u05e2 \u05ea\u05db\u05e0\u05d9\u05ea</div>
            <div class="info-card">
                <h3 style="color:#c084fc;">${plan.plan||''}</h3>
                <div class="info-row"><span class="info-label">\u05de\u05e1\u05e4\u05e8 \u05ea\u05db\u05e0\u05d9\u05ea:</span><span class="info-value">${plan.plan_no||''}</span></div>
                <div class="info-row"><span class="info-label">\u05e9\u05dd \u05ea\u05db\u05e0\u05d9\u05ea:</span><span class="info-value">${plan.plan||''}</span></div>
                <div class="info-row"><span class="info-label">\u05ea\u05d0\u05e8\u05d9\u05da \u05d0\u05d9\u05e9\u05d5\u05e8:</span><span class="info-value">${plan.DATA_DATE||''}</span></div>
                <div class="info-row"><span class="info-label">\u05de\u05e6\u05d1:</span><span class="info-value">${plan.status||''}</span></div>
                <div class="info-row"><span class="info-label">\u05de\u05d7\u05d5\u05d6:</span><span class="info-value">${plan.district||''}</span></div>
                <div class="info-row"><span class="info-label">\u05e0\u05e4\u05d4:</span><span class="info-value">${plan.SUB_D||''}</span></div>
                <div class="info-row"><span class="info-label">\u05e1\u05de\u05db\u05d5\u05ea \u05ea\u05db\u05e0\u05d5\u05df:</span><span class="info-value">${plan.authority||''}</span></div>
                <div class="info-row"><span class="info-label">\u05e1\u05d9\u05d5\u05d5\u05d2 \u05d4\u05ea\u05db\u05e0\u05d9\u05ea:</span><span class="info-value">${plan.plan_type||''}</span></div>
                <div class="info-row"><span class="info-label">\u05d9\u05d6\u05dd:</span><span class="info-value">${plan.initiator||''}</span></div>
                <div class="info-row"><span class="info-label">\u05de\u05e1\u05e4\u05e8 \u05e4\u05e8\u05d5\u05d9\u05e7\u05d8:</span><span class="info-value">${plan.Prj_ID_MHD||''}</span></div>
                <div class="info-row" style="margin-top:8px;border-top:1px solid #334155;padding-top:6px;"><span class="info-label">\u05ea\u05d0\u05d9 \u05e9\u05d8\u05d7:</span><span class="info-value">${projectFeats.length}</span></div>
            </div>
            <div class="panel-title" style="margin-top:10px;">\u05de\u05e7\u05e8\u05d0 \u05d9\u05e2\u05d5\u05d3\u05d9\u05dd</div>
            <div class="info-card" id="mavat-legend"></div>
        `;

        // Build legend - unique MAVAT codes in this project
        const usedCodes = {};
        projectFeats.forEach(f => {
            const c = String(f.properties.MAVAT_CODE);
            if (!usedCodes[c]) usedCodes[c] = {name: f.properties.MAVAT_NAME, count: 0};
            usedCodes[c].count++;
        });
        const legendHtml = Object.entries(usedCodes)
            .sort((a,b) => b[1].count - a[1].count)
            .map(([code,info]) => {
                const color = getMavatColor(code);
                return `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px;">
                    <span style="width:14px;height:14px;background:${color};border-radius:3px;flex-shrink:0;border:1px solid #334155;"></span>
                    <span style="flex:1;color:#e2e8f0;">${info.name}</span>
                    <span style="color:#94a3b8;font-size:11px;">${info.count}</span>
                </div>`;
            }).join('');
        document.getElementById('mavat-legend').innerHTML = legendHtml;
    }
}

function updateInfra() {
    // Remove old
    activeInfraLayers.forEach(l => map.removeLayer(l));
    activeInfraLayers = [];

    const infraChecked = document.querySelector('[data-cat="infra"]').checked;
    const showLines = document.getElementById('show-lines').checked;
    const showPoints = document.getElementById('show-points').checked;
    const infraPanel = document.getElementById('infra-sub');
    infraPanel.classList.toggle('visible', infraChecked);

    if (!infraChecked) { document.getElementById('layer-count').textContent=''; return; }

    let total = 0;

    Object.keys(infraGroups).forEach(gKey => {
        const chk = document.querySelector(`[data-infra="${gKey}"]`);
        if (!chk || !chk.checked) return;
        const g = infraGroups[gKey];
        const color = g.color;

        // Lines
        if (showLines) {
            g.lines.forEach(k => {
                const data = infraGeoJSON[k];
                if (!data || !data.features.length) return;
                const layer = L.geoJSON(data, {
                    style:{color:color,weight:2.5,opacity:0.8},
                    onEachFeature:(f,l)=>l.bindPopup(makeInfraPopup(f.properties,color),{maxWidth:320})
                }).addTo(map);
                activeInfraLayers.push(layer);
                total += data.features.length;
            });
        }

        // Points
        if (showPoints) {
            g.points.forEach(k => {
                const data = infraGeoJSON[k];
                if (!data || !data.features.length) return;
                const layer = L.geoJSON(data, {
                    pointToLayer:(f,ll)=>L.circleMarker(ll,{radius:4,fillColor:color,color:'#1e293b',weight:1,fillOpacity:0.85}),
                    onEachFeature:(f,l)=>l.bindPopup(makeInfraPopup(f.properties,color),{maxWidth:320})
                }).addTo(map);
                activeInfraLayers.push(layer);
                total += data.features.length;
            });
        }

        // Polygons
        g.polygons.forEach(k => {
            const data = infraGeoJSON[k];
            if (!data || !data.features.length) return;
            const layer = L.geoJSON(data, {
                style:{color:color,weight:2,opacity:0.8,fillColor:color,fillOpacity:0.25},
                onEachFeature:(f,l)=>l.bindPopup(makeInfraPopup(f.properties,color),{maxWidth:320})
            }).addTo(map);
            activeInfraLayers.push(layer);
            total += data.features.length;
        });
    });

    document.getElementById('layer-count').textContent = total > 0 ? '\u05de\u05d5\u05e6\u05d2\u05d9\u05dd ' + total.toLocaleString() + ' \u05d0\u05dc\u05de\u05e0\u05d8\u05d9 \u05ea\u05e9\u05ea\u05d9\u05ea' : '';
}

// Category & infra listeners
function updateLeftPanelVisibility() {
    const anyChecked = Array.from(document.querySelectorAll('[data-cat]')).some(cb => cb.checked);
    document.querySelector('.main').classList.toggle('no-left', !anyChecked);
    setTimeout(() => { if (map && map.invalidateSize) map.invalidateSize(); }, 50);
}
document.querySelectorAll('[data-cat]').forEach(cb => cb.addEventListener('change', () => {
    updateInfra(); updateStatutory(); updateLeftPanelVisibility();
}));
// Initial: hide left panel since no category checked
updateLeftPanelVisibility();
document.querySelectorAll('[data-infra]').forEach(cb => cb.addEventListener('change', updateInfra));
document.getElementById('show-lines').addEventListener('change', updateInfra);
document.getElementById('show-points').addEventListener('change', updateInfra);

// ── Reset ───────────────────────────────────────────
function resetView() {
    selectedProjectId = null;
    if (selectedMarker) { map.removeLayer(selectedMarker); selectedMarker = null; }
    if (statutoryLayer) { map.removeLayer(statutoryLayer); statutoryLayer = null; }
    document.querySelector('.panel-left').innerHTML = '<div class="placeholder">פאנל שמאלי - בקרוב</div>';
    hideMapOverlay();
    document.getElementById('search').value = '';
    document.getElementById('info-card').innerHTML = '<div class="no-selection">\u05d1\u05d7\u05e8 \u05e4\u05e8\u05d5\u05d9\u05e7\u05d8 \u05de\u05d4\u05e8\u05e9\u05d9\u05de\u05d4 \u05d0\u05d5 \u05de\u05d4\u05de\u05e4\u05d4</div>';
    document.querySelectorAll('[data-cat]').forEach(cb => { cb.checked = false; });
    document.getElementById('infra-sub').classList.remove('visible');
    document.getElementById('show-lines').checked = true;
    document.getElementById('show-points').checked = true;
    refresh();
    updateLeftPanelVisibility();
}
document.getElementById('btn-reset').addEventListener('click', resetView);

// ── Theme toggle ────────────────────────────────────
const themeToggle = document.getElementById('theme-toggle');
const themeIcon = themeToggle.querySelector('.theme-icon');
let lightBaseLayer = null;
let darkBaseLayer = null;

function applyTheme(mode) {
    document.body.classList.toggle('light', mode === 'light');
    themeIcon.textContent = mode === 'light' ? '☀️' : '🌙';
    localStorage.setItem('mhd-theme', mode);
    // Switch Leaflet basemap
    if (map) {
        if (mode === 'light') {
            if (darkBaseLayer && map.hasLayer(darkBaseLayer)) map.removeLayer(darkBaseLayer);
            if (!lightBaseLayer) lightBaseLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{attribution:'&copy; OSM & CARTO',maxZoom:19});
            lightBaseLayer.addTo(map);
        } else {
            if (lightBaseLayer && map.hasLayer(lightBaseLayer)) map.removeLayer(lightBaseLayer);
            if (darkBaseLayer) darkBaseLayer.addTo(map);
        }
    }
    // Switch 3D basemap
    if (sceneView && sceneView.map) {
        sceneView.map.basemap = mode === 'light' ? 'topo-vector' : 'dark-gray-vector';
    }
}

// Initialize darkBaseLayer reference from already-added layer
map.eachLayer(l => { if (l._url && l._url.includes('dark_all')) darkBaseLayer = l; });

themeToggle.addEventListener('click', () => {
    const currentMode = document.body.classList.contains('light') ? 'light' : 'dark';
    applyTheme(currentMode === 'light' ? 'dark' : 'light');
});

// Load saved preference
const savedTheme = localStorage.getItem('mhd-theme') || 'dark';
if (savedTheme === 'light') applyTheme('light');

// ── Init ────────────────────────────────────────────
refresh();
</script>
</body>
</html>"""

# ── Inject data ──────────────────────────────────────
projects_str = json.dumps(projects, ensure_ascii=False)
infra_groups_str = json.dumps(infra_groups, ensure_ascii=False)
infra_geojson_str = json.dumps(infra_data, ensure_ascii=False)

ortho_tiles_str = json.dumps(ortho_tiles, ensure_ascii=False)
statutory_str = json.dumps(statutory, ensure_ascii=False)
plans_by_project_str = json.dumps(plans_by_project, ensure_ascii=False)
polygon_sym_str = json.dumps(polygon_symbology, ensure_ascii=False)
html = html.replace("POLYGON_SYMBOLOGY", polygon_sym_str)
html = html.replace("ORTHO_TILES", ortho_tiles_str)
html = html.replace("STATUTORY_DATA", statutory_str)
html = html.replace("PLANS_BY_PROJECT", plans_by_project_str)
html = html.replace("LOGO_B64", logo_b64)
html = html.replace("PROJECT_DATA", projects_str)
html = html.replace("INFRA_GROUPS", infra_groups_str)
html = html.replace("INFRA_GEOJSON", infra_geojson_str)

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nDashboard written to {OUT_HTML}")
print(f"Size: {len(html)/1024/1024:.1f} MB")
