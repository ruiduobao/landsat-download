#!/usr/bin/env python3
"""Landsat Downloader | Landsat 8/9 影像下载器

通过 STAC API 搜索并下载 Landsat 8 / Landsat 9 Collection 2 Level 2 影像。
沿用 Sentinel Downloader 的架构（STAC + 单文件 CLI + 可视化进度 +
`.part` 安全写入），但适配 Landsat 8/9 的元数据约定（WRS-2 路径/行、
Collection 2 Level 2 资产命名、`eo:cloud_cover` 云量字段）。

数据源 / Source
----------------
* **Planetary Computer**（默认） — 公开 STAC + Azure Blob，无凭证
* **AWS Open Data / Element84 Earth Search**（可选） — 公开 STAC

Privacy disclosure
------------------
When this script runs, it sends:
* The bounding box + date range + cloud-cover limit to a STAC search API
  (Planetary Computer or AWS Earth Search). No API keys, no local files,
  no PII are sent.
* One HTTP request to the Planetary Computer signing endpoint to obtain
  a short-lived SAS token for each scene. The token is cached locally in
  memory for the duration of the run.

What is NOT sent: any data from the local filesystem, any environment
variables, any login credentials.

To suppress the one-line privacy notice: set ``LANDSAT_DOWNLOAD_QUIET=1``.

Public domain notice
--------------------
Landsat Collection 2 data is held by USGS and is in the **public domain**.
This skill does not bypass any authentication, login, or access control.
The STAC APIs used are public, free, and require no account.

Usage
-----
::

    python landsat-download.py \\
        --bbox 116.0 39.0 117.0 40.0 \\
        --start-date 2024-01-01 \\
        --end-date 2024-12-31

    # Search + download
    python landsat-download.py \\
        --bbox 116.0 39.0 117.0 40.0 \\
        --start-date 2024-01-01 \\
        --end-date 2024-12-31 \\
        --max-cloud-cover 20 \\
        --download \\
        --output-dir ./data

License
-------
MIT-0. Landsat data © USGS (public domain).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

# Local helper: --place resolution (vendored copy of _place_resolver.py)
try:
    from _place import resolve_place as _resolve_place
except ImportError:  # pragma: no cover
    def _resolve_place(*_a, **_kw):  # type: ignore
        raise RuntimeError("place resolution helper (_place.py) not available in this folder")


# ---------------------------------------------------------------------------
# STAC endpoints
# ---------------------------------------------------------------------------

STAC_ENDPOINTS = {
    "pc": {
        "search": "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        "root": "https://planetarycomputer.microsoft.com/api/stac/v1/",
        "sign": "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}",
    },
    "aws": {
        "search": "https://earth-search.aws.element84.com/v1/search",
        "root": "https://earth-search.aws.element84.com/v1/",
        "sign": None,  # AWS Open Data blobs are public, no signing needed
    },
}

LANDSAT_COLLECTION = "landsat-c2-l2"

# Default bands for download (surface reflectance + thermal + QA).
# Users can override with --bands. Valid assets for landsat-c2-l2:
# https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2
DEFAULT_BANDS = ["red", "green", "blue", "nir08", "swir16", "swir22"]
QA_BANDS = ["qa", "qa_pixel", "qa_radsat"]
THERMAL_BANDS = ["lwir11", "trad", "urad", "drad", "emis", "emsd", "atran", "cdist"]
METADATA_BANDS = ["mtl.txt", "mtl.xml", "ang"]

# Map of asset key → human-readable description (for the --help text and
# the --list-bands interactive output). Bilingual.
#
# Note: these are the STAC asset keys exposed by the Planetary Computer
# "landsat-c2-l2" collection, NOT the USGS Collection 2 file names. For
# example, the surface reflectance red band is `red` here, but the file
# inside the .tar would be named SR_B4.TIF. The STAC layer normalizes
# the naming.
BAND_DESCRIPTIONS: Dict[str, Tuple[str, str]] = {
    "coastal": ("Coastal Aerosol (USGS SR_B1)", "沿海气溶胶 (USGS SR_B1)"),
    "blue":    ("Blue (USGS SR_B2)",            "蓝光 (USGS SR_B2)"),
    "green":   ("Green (USGS SR_B3)",           "绿光 (USGS SR_B3)"),
    "red":     ("Red (USGS SR_B4)",             "红光 (USGS SR_B4)"),
    "nir08":   ("NIR (USGS SR_B5)",             "近红外 (USGS SR_B5)"),
    "swir16":  ("SWIR1 (USGS SR_B6)",           "短波红外 1 (USGS SR_B6)"),
    "swir22":  ("SWIR2 (USGS SR_B7)",           "短波红外 2 (USGS SR_B7)"),
    "lwir11":  ("Thermal (USGS ST_B10)",        "热红外 (USGS ST_B10)"),
    "qa":      ("Pixel Quality (QA_PIXEL)",     "像元质量 QA_PIXEL（云/雪/水）"),
    "qa_pixel":  ("Pixel Quality (alt name)",  "像元质量 QA_PIXEL（别名）"),
    "qa_radsat": ("Radiometric Saturation (QA_RADSAT)", "辐射饱和度 QA_RADSAT"),
    "drad":    ("Downwelled Radiance (ST_DRAD)",  "下行辐射 ST_DRAD"),
    "urad":    ("Upwelled Radiance (ST_URAD)",    "上行辐射 ST_URAD"),
    "atran":   ("Atmospheric Transmittance (ST_ATRAN)", "大气透过率 ST_ATRAN"),
    "cdist":   ("Cloud Distance (ST_CDIST)",      "云距离 ST_CDIST"),
    "emis":    ("Emissivity (ST_EMIS)",           "比辐射率 ST_EMIS"),
    "emsd":    ("Emissivity Stddev (ST_EMSD)",    "比辐射率标准差 ST_EMSD"),
    "trad":    ("Thermal Radiance (ST_TRAD)",     "热辐射 ST_TRAD"),
    "mtl.txt": ("Metadata (text)",                "元数据（文本）"),
    "mtl.xml": ("Metadata (XML)",                 "元数据（XML）"),
    "mtl.json":("Metadata (JSON)",                "元数据（JSON）"),
    "ang":     ("Angle Coefficients",             "角度系数"),
}

USER_AGENT = "landsat-download/0.2.0 (+https://clawhub.ai/skills/landsat-download)"


# ---------------------------------------------------------------------------
# Presets / 日期预设
# ---------------------------------------------------------------------------
# 用户最常见的一句话任务，例如：
#   "成都市 2024 年夏季低云量 Landsat 9 影像"
#   "2024 年冬季北京市 NDVI 影像"
#   "2023 年成都市全年低云 Landsat 9 影像"
#
# 一个 preset 自动展开为：start_date / end_date / platform / max_cloud_cover / bands
# 用户仍可用 --start-date / --max-cloud-cover 等显式覆盖。
#
# 说明：以下日期使用 Northern-Hemisphere 季节（适合绝大多数中国用户）；
#      南半球用户请用 --start-date / --end-date 显式指定。

PRESETS: Dict[str, Dict[str, Any]] = {
    "summer-2024": {
        "description": "2024 年夏季 (6-8 月) Landsat 8+9 全场景 / 2024 Northern-Hemisphere summer (Jun-Aug)",
        "start_date": "2024-06-01",
        "end_date": "2024-08-31",
        "platform": "both",
        "max_cloud_cover": 20.0,
    },
    "winter-2024": {
        "description": "2024 年冬季 (12-2 月) Landsat 8+9 / 2024 Northern-Hemisphere winter (Dec-Feb)",
        "start_date": "2023-12-01",
        "end_date": "2024-02-29",
        "platform": "both",
        "max_cloud_cover": 20.0,
    },
    "annual-2024": {
        "description": "2024 年全年 Landsat 8+9 / 2024 full year",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "platform": "both",
        "max_cloud_cover": 30.0,
    },
    "low-cloud-10": {
        "description": "近 1 年 (rolling 365d) 内云量 ≤10% 的低云量场景 / lowest cloud cover, rolling 1 year",
        "start_date": None,  # main() 动态计算为今天 - 365 天
        "end_date": None,
        "platform": "both",
        "max_cloud_cover": 10.0,
    },
    "ndvi-ready": {
        "description": "NDVI 所需波段 (red + nir08 + qa)，低云量夏季 / bands for NDVI",
        "start_date": None,  # main() 默认填近 1 年
        "end_date": None,
        "platform": "both",
        "max_cloud_cover": 20.0,
        "bands": ["red", "nir08", "qa"],
    },
    "rgb-ready": {
        "description": "真彩色 RGB 影像 (red + green + blue) / natural color",
        "start_date": None,
        "end_date": None,
        "platform": "both",
        "max_cloud_cover": 20.0,
        "bands": ["red", "green", "blue"],
    },
    "thermal-lst": {
        "description": "地表温度 (LST) 所需波段 (lwir11 + qa) / thermal for LST",
        "start_date": None,
        "end_date": None,
        "platform": "both",
        "max_cloud_cover": 20.0,
        "bands": ["lwir11", "qa"],
    },
}

# 季节展开（用户说 "summer" 自动展开为 6-8 月）
SEASON_MONTHS: Dict[str, Tuple[int, int]] = {
    "spring": (3, 5),
    "summer": (6, 8),
    "autumn": (9, 11),
    "fall": (9, 11),
    "winter": (12, 2),  # 跨年特殊处理
}


def _auto_buffer_for_place(place_name: str) -> float:
    """Heuristic auto buffer (degrees) for a Chinese place-name.

    Landsat scene is ~185 km wide (≈1.67° at equator). 0.1° is too small for
    a city — usually returns 0 scenes. We use admin-level heuristics:

    * ends with "省"/"自治区"/"盟" → 5.0°  (province)
    * ends with "市" (prefecture-level) → 0.6°  (covers a city + outskirts)
    * ends with "区" (district) → 0.15°
    * ends with "县" (county) → 0.4°
    * otherwise → 0.3°
    """
    if not place_name:
        return 0.3
    name = place_name.strip()
    if name.endswith(("省", "自治区")) or "省" in name[-3:]:
        return 5.0
    if name.endswith("市"):
        return 0.6
    if name.endswith("区"):
        return 0.15
    if name.endswith(("县", "旗")):
        return 0.4
    return 0.3


def apply_preset(args: argparse.Namespace) -> argparse.Namespace:
    """Apply --preset (and optional --year/--season) to fill in date / cloud / bands.

    Priority (lowest → highest):
      preset defaults  <  user-provided --start-date / --end-date / --max-cloud-cover
    """
    if not (args.preset or args.season or args.year):
        return args

    today = time.strftime("%Y-%m-%d")

    # 1) --preset
    if args.preset:
        if args.preset not in PRESETS:
            valid = ", ".join(sorted(PRESETS.keys()))
            raise SystemExit(f"ERROR: --preset must be one of: {valid}")
        spec = PRESETS[args.preset]
        # 只有用户没显式给才覆盖
        if not args.start_date:
            args.start_date = spec.get("start_date") or (today if spec.get("end_date") is None else None)
        if not args.end_date:
            args.end_date = spec.get("end_date") or today
        if args.max_cloud_cover is None:
            mc = spec.get("max_cloud_cover")
            if mc is not None:
                args.max_cloud_cover = float(mc)
        # platform / bands：用户没显式给才覆盖
        if args.platform == "both" and "platform" in spec:
            args.platform = spec["platform"]
        if args.bands == DEFAULT_BANDS and "bands" in spec:
            args.bands = spec["bands"]
        # rolling 1 year 默认
        if args.preset == "low-cloud-10" and (not args.start_date or not args.end_date):
            t = time.time()
            args.end_date = today
            args.start_date = time.strftime("%Y-%m-%d", time.gmtime(t - 365 * 24 * 3600))

    # 2) --year + --season 组合（先 season，更精确）
    if args.season and args.year and not args.start_date:
        s = args.season.lower()
        if s not in SEASON_MONTHS:
            raise SystemExit(f"ERROR: --season must be one of: {', '.join(sorted(SEASON_MONTHS.keys()))}")
        m1, m2 = SEASON_MONTHS[s]
        y = args.year
        if m1 <= m2:
            args.start_date = f"{y}-{m1:02d}-01"
            # 算下个月第一天 - 1 天
            import calendar
            last_day = calendar.monthrange(y, m2)[1]
            args.end_date = f"{y}-{m2:02d}-{last_day}"
        else:  # winter 跨年
            args.start_date = f"{y}-{m1:02d}-01"
            import calendar
            last_day = calendar.monthrange(y + 1, m2)[1]
            args.end_date = f"{y + 1}-{m2:02d}-{last_day}"

    # 3) --year 单独使用（仅当 start_date 仍未填）
    if args.year and not args.start_date:
        y = args.year
        args.start_date = f"{y}-01-01"
        args.end_date = f"{y}-12-31"

    return args


# Optional: requests trust_env to skip system proxies (avoids noisy
# local VPN/proxy ports when the user is on a direct connection). Users who
# NEED the proxy can set LANDSAT_DOWNLOAD_USE_PROXY=1 to fall back to env defaults.
DEFAULT_TRUST_ENV = os.environ.get("LANDSAT_DOWNLOAD_USE_PROXY") == "1"

# SAS token cache: collection → (token, expires_at_epoch_seconds)
_SAS_CACHE: Dict[str, Tuple[str, float]] = {}


# ---------------------------------------------------------------------------
# Privacy notice helper
# ---------------------------------------------------------------------------

def _quiet() -> bool:
    return os.environ.get("LANDSAT_DOWNLOAD_QUIET") == "1"


def _emit_privacy_notice(source: str) -> None:
    """One-line stderr note about what the script is doing on the network."""
    if _quiet():
        return
    msg = (
        f"[landsat-download] contacting {source} STAC endpoint "
        f"(no API keys / no local files / no PII sent; "
        f"Landsat data © USGS public domain). "
        f"Set LANDSAT_DOWNLOAD_QUIET=1 to suppress this notice."
    )
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# STAC search
# ---------------------------------------------------------------------------

def stac_search(
    *,
    bbox: Tuple[float, float, float, float],
    start_date: str,
    end_date: str,
    max_cloud_cover: Optional[float] = None,
    platform: str = "both",
    path: Optional[int] = None,
    row: Optional[int] = None,
    limit: int = 10,
    source: str = "pc",
    timeout: int = 60,
) -> Dict[str, Any]:
    """Search the STAC catalog for Landsat 8/9 scenes.

    Parameters
    ----------
    bbox : tuple of 4 floats
        (min_lon, min_lat, max_lon, max_lat) in WGS84.
    start_date, end_date : str
        ISO date ``YYYY-MM-DD``.
    max_cloud_cover : float, optional
        Maximum scene cloud cover percent (0–100).
    platform : {"landsat-8", "landsat-9", "both"}
    path, row : int, optional
        WRS-2 path/row filter.
    limit : int
        Maximum number of items to return (passed as STAC ``limit``).
    source : {"pc", "aws"}
        STAC backend.

    Returns
    -------
    dict
        Raw STAC ``/search`` response. The ``features`` list contains the
        scene metadata.
    """
    if source not in STAC_ENDPOINTS:
        raise ValueError(f"Unknown source: {source!r}; expected one of {list(STAC_ENDPOINTS)}")

    # Build the query
    datetime_range = f"{start_date}T00:00:00Z/{end_date}T23:59:59Z"

    query: Dict[str, Any] = {}
    if max_cloud_cover is not None:
        query["eo:cloud_cover"] = {"lt": float(max_cloud_cover)}

    if platform == "landsat-8":
        query["platform"] = {"eq": "landsat-8"}
    elif platform == "landsat-9":
        query["platform"] = {"eq": "landsat-9"}
    elif platform == "both":
        query["platform"] = {"in": ["landsat-8", "landsat-9"]}
    else:
        raise ValueError(f"Unknown platform: {platform!r}")

    if path is not None:
        query["landsat:wrs_path"] = {"eq": str(int(path))}
    if row is not None:
        query["landsat:wrs_row"] = {"eq": str(int(row))}

    body: Dict[str, Any] = {
        "collections": [LANDSAT_COLLECTION],
        "bbox": list(bbox),
        "datetime": datetime_range,
        "limit": int(limit),
        "query": query,
    }
    # AWS Earth Search does not allow sorting by `datetime` on the
    # landsat-c2-l2 collection (the index lacks a datetime sort field).
    # Planetary Computer is fine with it.
    if source == "pc":
        body["sortby"] = [{"field": "datetime", "direction": "desc"}]

    session = requests.Session()
    session.trust_env = DEFAULT_TRUST_ENV
    session.headers.update({"User-Agent": USER_AGENT, "Content-Type": "application/json"})

    url = STAC_ENDPOINTS[source]["search"]
    _emit_privacy_notice("Planetary Computer" if source == "pc" else "AWS Earth Search")

    r = session.post(url, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Planetary Computer signing
# ---------------------------------------------------------------------------

def get_signed_href(item: Dict[str, Any], asset_key: str, source: str = "pc") -> Optional[str]:
    """Return the signed (downloadable) URL for a STAC asset.

    For ``pc`` source, the asset HREF must be signed via the Planetary
    Computer SAS endpoint. The signed token is cached in memory.

    For ``aws`` source, the HREF is already a public S3 URL.
    """
    asset = item.get("assets", {}).get(asset_key)
    if not asset:
        return None
    href = asset.get("href")
    if not href:
        return None

    if source == "aws":
        return href  # AWS Open Data blobs are public, no signing needed

    # Planetary Computer: fetch a SAS token for the collection, then append
    # it to the URL. The token is cached for 1 hour (Planetary Computer's
    # tokens are valid for 1 hour).
    collection = item.get("collection", LANDSAT_COLLECTION)
    token, expires_at = _SAS_CACHE.get(collection, ("", 0.0))
    now = time.time()
    if not token or now >= expires_at - 60:  # refresh 60s before expiry
        sign_url = STAC_ENDPOINTS["pc"]["sign"].format(collection=collection)
        session = requests.Session()
        session.trust_env = DEFAULT_TRUST_ENV
        session.headers.update({"User-Agent": USER_AGENT})
        r = session.get(sign_url, timeout=30)
        r.raise_for_status()
        token = r.json().get("token") or r.text.strip().strip('"')
        # Tokens are valid for 1 hour; cache for 50 minutes to be safe.
        _SAS_CACHE[collection] = (token, now + 50 * 60)
    return f"{href}?{token}"


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _format_scene_text(item: Dict[str, Any], idx: int) -> str:
    """Format one scene for the text output."""
    item_id = item.get("id", "?")
    props = item.get("properties", {})
    datetime_str = props.get("datetime", "")[:10] or "?"
    cloud = props.get("eo:cloud_cover")
    cloud_str = f"{cloud:.2f}%" if isinstance(cloud, (int, float)) else "?"
    platform = props.get("platform", "?")
    path = props.get("landsat:wrs_path", "?")
    row = props.get("landsat:wrs_row", "?")
    assets = list(item.get("assets", {}).keys())
    assets_str = " ".join(assets) if assets else "-"
    if len(assets_str) > 60:
        assets_str = assets_str[:57] + "..."
    return (
        f"  {idx}. {item_id}\n"
        f"     Date:    {datetime_str}\n"
        f"     Cloud:   {cloud_str}\n"
        f"     Platform: {platform}\n"
        f"     Path/Row: {path} / {row}\n"
        f"     Assets:  {assets_str}\n"
    )


def _format_scene_json(item: Dict[str, Any]) -> Dict[str, Any]:
    """Format one scene for the JSON output."""
    props = item.get("properties", {})
    return {
        "id": item.get("id"),
        "datetime": props.get("datetime"),
        "platform": props.get("platform"),
        "cloud_cover": props.get("eo:cloud_cover"),
        "path": props.get("landsat:wrs_path"),
        "row": props.get("landsat:wrs_row"),
        "assets": list(item.get("assets", {}).keys()),
        "bbox": item.get("bbox"),
    }


def format_results_text(query_meta: Dict[str, Any], features: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append(f"[landsat-download] found {len(features)} scene(s)")
    if query_meta.get("max_cloud_cover") is not None:
        lines.append(f"[landsat-download] cloud cover ≤ {query_meta['max_cloud_cover']}%")
    if query_meta.get("path") is not None:
        lines.append(f"[landsat-download] WRS-2 path/row = {query_meta['path']}/{query_meta.get('row', '?')}")
    lines.append("")
    for i, f in enumerate(features, 1):
        lines.append(_format_scene_text(f, i))
    if not features:
        lines.append("  (no scenes match the query — try widening bbox, date range, or raising --max-cloud-cover)")
    return "\n".join(lines)


def format_results_json(query_meta: Dict[str, Any], features: List[Dict[str, Any]]) -> str:
    return json.dumps(
        {
            "query": query_meta,
            "count": len(features),
            "scenes": [_format_scene_json(f) for f in features],
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Download with progress
# ---------------------------------------------------------------------------

def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _render_progress(downloaded: int, total: Optional[int], speed_bps: float,
                     eta_seconds: Optional[float], bar_width: int = 30) -> str:
    """Render a single-line progress bar."""
    if total and total > 0:
        pct = downloaded / total
        filled = int(bar_width * pct)
        bar = "█" * filled + "░" * (bar_width - filled)
        pct_str = f"{pct * 100:5.1f}%"
    else:
        bar = "?" * bar_width
        pct_str = "  ?  %"
    dl_str = _human_bytes(downloaded)
    if total and total > 0:
        tot_str = _human_bytes(total)
    else:
        tot_str = "??"
    speed_str = f"{_human_bytes(int(speed_bps))}/s"
    if eta_seconds is not None and eta_seconds >= 0:
        m, s = divmod(int(eta_seconds), 60)
        eta_str = f"{m}:{s:02d}"
    else:
        eta_str = "  ?  "
    return f"┃{bar}┃ {pct_str}  {dl_str:>9s} / {tot_str:<9s}  {speed_str:>11s}  ETA {eta_str}"


def download_asset(
    url: str,
    dest_path: str,
    timeout: int = 600,
    show_progress: bool = True,
) -> Tuple[bool, str]:
    """Download one asset to ``dest_path`` via a ``.part`` temp file.

    Returns ``(ok, message)``. On success the ``.part`` file is renamed
    to the final ``dest_path``. On failure the ``.part`` file is removed
    and any existing ``dest_path`` is left untouched.
    """
    tmp_path = dest_path + ".part"
    if os.path.exists(dest_path) and not os.path.exists(tmp_path):
        # File already exists; skip re-download unless user explicitly resets
        if not _quiet():
            print(f"  ↳ {os.path.basename(dest_path):<20s} already exists, skipping", file=sys.stderr)
        return True, f"already exists, skipping"

    try:
        with requests.get(url, stream=True, timeout=timeout,
                          headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0)) or None
            downloaded = 0
            t0 = time.time()
            last_print = t0

            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if show_progress and not _quiet() and (now - last_print) > 0.1:
                        elapsed = now - t0
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        eta = ((total - downloaded) / speed) if (total and speed > 0) else None
                        line = _render_progress(downloaded, total, speed, eta)
                        sys.stdout.write(f"\r  ↳ {os.path.basename(dest_path):<20s} {line}")
                        sys.stdout.flush()
                        last_print = now

        if show_progress and not _quiet():
            sys.stdout.write("\n")
            sys.stdout.flush()
        os.replace(tmp_path, dest_path)
        return True, "ok"
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False, str(e)[:200]


def download_scene(
    item: Dict[str, Any],
    bands: List[str],
    output_dir: str,
    source: str = "pc",
    timeout: int = 600,
    show_progress: bool = True,
) -> Dict[str, Any]:
    """Download all selected bands for one STAC item.

    Returns a per-scene result dict with ``scene_id``, ``ok`` (bool),
    ``files`` (list of {asset, path, ok, message}), and ``total_bytes``.
    """
    item_id = item.get("id", "unknown")
    scene_dir = os.path.join(output_dir, item_id)
    os.makedirs(scene_dir, exist_ok=True)

    result: Dict[str, Any] = {
        "scene_id": item_id,
        "ok": True,
        "files": [],
        "total_bytes": 0,
    }

    if not _quiet():
        print(f"\n[landsat-download] downloading {item_id}", file=sys.stderr)

    for band in bands:
        if band not in item.get("assets", {}):
            result["files"].append({"asset": band, "ok": False,
                                    "message": "asset not in item"})
            result["ok"] = False
            continue
        href = get_signed_href(item, band, source=source)
        if not href:
            result["files"].append({"asset": band, "ok": False,
                                    "message": "no signed href"})
            result["ok"] = False
            continue
        # Determine extension from the href
        ext = ".tif"
        if band in METADATA_BANDS:
            ext = os.path.splitext(href.split("?")[0])[1] or ".txt"
        dest = os.path.join(scene_dir, f"{band}{ext}")
        ok, msg = download_asset(href, dest, timeout=timeout,
                                 show_progress=show_progress)
        result["files"].append({"asset": band, "path": dest, "ok": ok,
                                "message": msg})
        if ok and os.path.exists(dest):
            result["total_bytes"] += os.path.getsize(dest)
        if not ok:
            result["ok"] = False

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="landsat-download",
        description=(
            "Search and download Landsat 8/9 Collection 2 Level 2 imagery "
            "via STAC. Default backend: Microsoft Planetary Computer (public). "
            "通过 STAC 搜索和下载 Landsat 8/9 Collection 2 Level 2 影像。"
        ),
    )
    p.add_argument("--bbox", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
                   help="Geographic extent in WGS84 / 地理范围 [minLon minLat maxLon maxLat]")
    p.add_argument("--start-date", help="Start date YYYY-MM-DD / 开始日期")
    p.add_argument("--end-date", help="End date YYYY-MM-DD / 结束日期")
    p.add_argument("--platform", default="both", choices=["landsat-8", "landsat-9", "both"],
                   help="Satellite platform (default: both) / 选择卫星")
    p.add_argument("--max-cloud-cover", type=float, default=None, metavar="PCT",
                   help="Max scene cloud cover percent 0-100 / 最大云量")
    p.add_argument("--path", type=int, default=None, help="WRS-2 path / 路径号")
    p.add_argument("--row", type=int, default=None, help="WRS-2 row / 行号")
    p.add_argument("--limit", type=int, default=10,
                   help="Max scenes to return (default 10) / 限制返回条数")
    p.add_argument("--bands", nargs="+", default=DEFAULT_BANDS,
                   help=f"Assets to download (default: {' '.join(DEFAULT_BANDS)})")
    p.add_argument("--download", action="store_true",
                   help="Trigger actual download (default: search only) / 实际下载")
    p.add_argument("--output-dir", default="./landsat_data",
                   help="Download directory (default ./landsat_data) / 下载目录")
    p.add_argument("--output-format", default="text", choices=["text", "json"],
                   help="Output format / 输出格式")
    p.add_argument("--source", default="pc", choices=["pc", "aws"],
                   help="STAC backend (default pc=Planetary Computer) / 后端")
    p.add_argument("--no-progress", action="store_true",
                   help="Disable visual progress bar / 关闭进度条")
    p.add_argument("--download-timeout", type=int, default=600,
                   help="Per-asset download timeout in seconds (default 600)")
    p.add_argument("--list-bands", action="store_true",
                   help="List all available bands and exit / 列出所有波段")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress progress + privacy notice (also LANDSAT_DOWNLOAD_QUIET=1)")
    p.add_argument(
        "--place",
        help="Place name (Chinese or English). Auto-resolved to bbox via Open-Meteo + Nominatim. "
             "Mutually exclusive with --bbox / 行政地名 (自动解析为 bbox)",
    )
    p.add_argument(
        "--place-buffer-deg",
        type=float,
        default=None,
        help="Buffer (degrees) added around the resolved point when --place is used. "
             "Default auto: city=0.5°, district=0.15°, province=4°. "
             "Use this to override the auto value / 围绕地名的 bbox 缓冲（度）。",
    )
    p.add_argument(
        "--no-nominatim",
        action="store_true",
        help="Skip Nominatim lookup in --place resolution / --place 解析时跳过 Nominatim",
    )
    p.add_argument(
        "--qa",
        metavar="PATH",
        help="Write a JSON QA summary to PATH. "
             "By default implies --download (full QA includes download stats). "
             "Use --qa-mode search to write only search results without downloading. / 写出 QA 摘要 JSON",
    )
    p.add_argument(
        "--qa-mode",
        choices=["search", "full"],
        default="full",
        help="What to record in --qa. 'search' = just search meta (no download). "
             "'full' = search + download stats (implies --download). Default: full.",
    )
    p.add_argument(
        "--preset",
        choices=sorted(PRESETS.keys()),
        help="One-line preset (auto-fills date / platform / cloud / bands). "
             f"Available: {', '.join(sorted(PRESETS.keys()))}. "
             "显式给出的 --start-date / --max-cloud-cover 等参数会覆盖 preset 默认值。",
    )
    p.add_argument(
        "--year",
        type=int,
        help="Shortcut for full-year search: --year 2024 → --start-date 2024-01-01 --end-date 2024-12-31. "
             "与 --season 组合：--year 2024 --season summer → 2024-06-01..2024-08-31.",
    )
    p.add_argument(
        "--season",
        choices=sorted(SEASON_MONTHS.keys()),
        help="Northern-Hemisphere season (需配合 --year). e.g. --year 2024 --season summer.",
    )
    p.add_argument(
        "--pick-best",
        action="store_true",
        help="After searching, only download the single scene with the lowest cloud cover. "
             "Useful for '找一个最清晰的' workflows. / 仅下载云量最低的一景",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    # Apply --preset / --year / --season BEFORE --list-bands
    # (presets may also affect --bands default)
    try:
        args = apply_preset(args)
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: --preset expansion failed: {e}", file=sys.stderr)
        return 2

    # --list-bands
    if args.list_bands:
        print("Available Landsat Collection 2 Level 2 assets:")
        print("-" * 60)
        for k, (en, zh) in BAND_DESCRIPTIONS.items():
            print(f"  {k:<12s}  {en:<40s}  {zh}")
        return 0

    # Required args check
    missing = []
    if not args.bbox and not args.place: missing.append("--bbox or --place")
    if not args.start_date: missing.append("--start-date")
    if not args.end_date: missing.append("--end-date")
    if missing:
        print(f"ERROR: missing required arguments: {', '.join(missing)}", file=sys.stderr)
        print(f"Run with --help for usage.", file=sys.stderr)
        return 2

    # --quiet on CLI overrides env
    if args.quiet:
        os.environ["LANDSAT_DOWNLOAD_QUIET"] = "1"

    # Resolve --place to bbox if given
    place_info: Optional[Dict[str, Any]] = None
    if args.place:
        if args.bbox:
            print("ERROR: --place and --bbox are mutually exclusive; pick one.", file=sys.stderr)
            return 2
        try:
            place_info = _resolve_place(args.place, allow_nominatim=not args.no_nominatim)
        except Exception as e:
            print(f"ERROR: --place resolution failed: {e}", file=sys.stderr)
            return 2
        # Auto buffer by admin-level heuristics (省/市/区/县)
        buf = args.place_buffer_deg if args.place_buffer_deg is not None else _auto_buffer_for_place(args.place)
        w = place_info["lon"] - buf
        e = place_info["lon"] + buf
        s = place_info["lat"] - buf
        n = place_info["lat"] + buf
        args.bbox = [w, s, e, n]
        # Save the actual buffer used in place_info for QA
        place_info["buffer_deg_used"] = buf
        if not _quiet():
            print(f"[landsat-download] place: {place_info.get('display_name') or args.place}", file=sys.stderr)
            print(f"[landsat-download] resolved to bbox {args.bbox} (buffer {buf}°)", file=sys.stderr)
            print(f"[landsat-download] geocoder source: {place_info.get('source')}", file=sys.stderr)

    # --qa implies --download only in 'full' mode
    if args.qa and args.qa_mode == "full":
        args.download = True

    bbox = tuple(args.bbox)
    query_meta = {
        "bbox": list(bbox),
        "start_date": args.start_date,
        "end_date": args.end_date,
        "max_cloud_cover": args.max_cloud_cover,
        "platform": args.platform,
        "path": args.path,
        "row": args.row,
        "limit": args.limit,
        "source": args.source,
    }

    # Search
    try:
        resp = stac_search(
            bbox=bbox,
            start_date=args.start_date,
            end_date=args.end_date,
            max_cloud_cover=args.max_cloud_cover,
            platform=args.platform,
            path=args.path,
            row=args.row,
            limit=args.limit,
            source=args.source,
        )
    except requests.HTTPError as e:
        print(f"ERROR: STAC search failed: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"  body: {e.response.text[:300]}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"ERROR: network error during STAC search: {e}", file=sys.stderr)
        return 1

    features = resp.get("features", [])
    query_meta["returned"] = len(features)

    # --pick-best: 仅保留云量最低的一景
    if args.pick_best and features:
        def _cloud(f):
            try:
                return float(f.get("properties", {}).get("eo:cloud_cover", 1e9))
            except (TypeError, ValueError):
                return 1e9
        features_sorted = sorted(features, key=_cloud)
        best = features_sorted[0]
        cc = _cloud(best)
        if not _quiet():
            print(f"[landsat-download] --pick-best: chose 1 scene with cloud cover = {cc}%",
                  file=sys.stderr)
        features = [best]
        query_meta["picked"] = {"id": best.get("id"), "cloud_cover": cc}

    # Output search results
    if args.output_format == "json":
        print(format_results_json(query_meta, features))
    else:
        if not _quiet():
            print("[landsat-download] searching Planetary Computer STAC ..."
                  if args.source == "pc" else "[landsat-download] searching AWS Earth Search STAC ...",
                  file=sys.stderr)
            print(f"[landsat-download] bbox:     [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]",
                  file=sys.stderr)
            print(f"[landsat-download] date:     {args.start_date} → {args.end_date}",
                  file=sys.stderr)
            print(f"[landsat-download] platform: {args.platform}", file=sys.stderr)
            if args.max_cloud_cover is not None:
                print(f"[landsat-download] cloud:    ≤ {args.max_cloud_cover}%", file=sys.stderr)
        print(format_results_text(query_meta, features))

    # Download?
    if not args.download:
        # search-only QA: still write QA even if not downloading
        if args.qa and args.qa_mode == "search":
            _write_qa(args, query_meta, features, place_info, total_bytes=0, elapsed=0.0)
            if not _quiet():
                print(f"[landsat-download] wrote search-only QA to {args.qa}", file=sys.stderr)
        if not _quiet():
            print("\n[landsat-download] search done. Add --download to fetch.",
                  file=sys.stderr)
        return 0

    # Download loop
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    if not features:
        if not _quiet():
            print("[landsat-download] no scenes to download.", file=sys.stderr)
        return 0

    if not _quiet():
        print(f"\n[landsat-download] downloading {len(features)} scene(s) to {output_dir}",
              file=sys.stderr)
        print(f"[landsat-download] bands: {' '.join(args.bands)}", file=sys.stderr)

    overall_ok = True
    total_bytes = 0
    t0 = time.time()
    for i, item in enumerate(features, 1):
        if not _quiet():
            print(f"\n[{i}/{len(features)}]", file=sys.stderr)
        r = download_scene(
            item, bands=args.bands, output_dir=output_dir,
            source=args.source, timeout=args.download_timeout,
            show_progress=not args.no_progress,
        )
        total_bytes += r["total_bytes"]
        if not r["ok"]:
            overall_ok = False
            if not _quiet():
                print(f"  [landsat-download] some assets failed for {r['scene_id']}",
                      file=sys.stderr)
    elapsed = time.time() - t0
    if not _quiet():
        print(f"\n[landsat-download] done in {elapsed:.0f}s — "
              f"downloaded {_human_bytes(total_bytes)} across {len(features)} scene(s)",
              file=sys.stderr)

    # Optional QA summary
    if args.qa:
        try:
            _write_qa(args, query_meta, features, place_info, total_bytes, elapsed)
            if not _quiet():
                print(f"[landsat-download] wrote QA summary to {args.qa}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: --qa write failed: {e}", file=sys.stderr)
            return 3

    return 0 if overall_ok else 1


def _write_qa(args, query_meta, features, place_info, total_bytes, elapsed):
    """Write QA JSON to args.qa (called from search-only or full mode)."""
    qa = {
        "skill": "landsat-download",
        "version": "0.2.0",
        "query": {
            "bbox": list(query_meta.get("bbox") or []),
            "start_date": args.start_date,
            "end_date": args.end_date,
            "max_cloud_cover": args.max_cloud_cover,
            "platform": args.platform,
            "path": args.path,
            "row": args.row,
            "bands": args.bands,
            "source": args.source,
            "place": (
                {
                    "query": place_info.get("query") if place_info else None,
                    "display_name": place_info.get("display_name") if place_info else None,
                    "source": place_info.get("source") if place_info else None,
                    "buffer_deg": place_info.get("buffer_deg_used") if place_info else None,
                }
                if place_info
                else None
            ),
            "preset": args.preset,
            "year": args.year,
            "season": args.season,
            "pick_best": args.pick_best,
        },
        "searched": len(features),
        "picked": query_meta.get("picked"),
        "downloaded": sum(1 for f in features if f.get("_ok", True)),
        "failed": sum(1 for f in features if not f.get("_ok", True)),
        "total_bytes": total_bytes,
        "elapsed_seconds": round(elapsed, 1),
        "scenes": [
            {
                "id": f.get("id"),
                "datetime": f.get("properties", {}).get("datetime"),
                "cloud_cover": f.get("properties", {}).get("eo:cloud_cover"),
                "platform": f.get("properties", {}).get("platform"),
            }
            for f in features
        ],
    }
    with open(args.qa, "w", encoding="utf-8") as f:
        json.dump(qa, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
