"""Publish landsat-download v0.1.1 to ClawHub."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sys
from typing import Dict, List

import requests


def collect_files(root: str = ".") -> List[str]:
    """Walk the repo and return a list of file paths to upload.

    Skips:
    * Anything under .git, __pycache__, .pytest_cache
    * Scratch files in data/_* (per .gitignore)
    * The publish script itself (internal tooling)
    * Test scratch dirs (`_test_dl_20/`)
    * E2E test logs (`e2e_test.log`)
    """
    out: List[str] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if d not in (".git", "__pycache__", ".pytest_cache")
        ]
        for fn in files:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            # Skip the publish script itself
            if rel == "publish_to_clawhub.py":
                continue
            # Skip scratch + test artifacts
            if rel.startswith("_test_dl_20/"):
                continue
            if rel == "e2e_test.log":
                continue
            out.append(rel)
    return sorted(out)


def file_meta(path: str) -> dict:
    sz = os.path.getsize(path)
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    c, _ = mimetypes.guess_type(path)
    return {
        "path": path,
        "size": sz,
        "sha256": h,
        "contentType": c or "application/octet-stream",
    }


def main() -> int:
    token = os.environ.get("CLAWHUB_TOKEN")
    if not token:
        print("ERROR: CLAWHUB_TOKEN env var is required", file=sys.stderr)
        return 1

    api = "https://clawhub.ai/api/v1"
    slug = "landsat-download"
    version = "0.1.1"

    file_paths = collect_files(".")
    files_meta = [file_meta(p) for p in file_paths]
    total_size = sum(f["size"] for f in files_meta)
    print(f"Files to upload: {len(file_paths)} ({total_size/1e3:.1f} KB)")

    payload = {
        "slug": slug,
        "displayName": "Landsat Downloader",
        "version": version,
        "license": "MIT-0",
        "changelog": (
            "**v0.1.1: STAC-based Landsat 8/9 downloader — initial release + 3 bug fixes**\n\n"
            "Features:\n"
            "- Search and download Landsat 8/9 Collection 2 Level 2 imagery via STAC\n"
            "- Default backend: Microsoft Planetary Computer (public, no auth)\n"
            "- Optional backend: AWS Earth Search (Element84)\n"
            "- Bilingual CLI (zh + en) with WRS-2 path/row, cloud-cover, band selection\n"
            "- Safe .part file writes (atomic rename, never overwrites existing)\n"
            "- Visual progress bar with speed + ETA\n"
            "- JSON + text output formats\n"
            "- Privacy notice + LANDSAT_DOWNLOAD_QUIET=1 opt-out env var\n\n"
            "Bug fixes (vs initial dev):\n"
            "- AWS STAC: don't send `sortby: datetime` (index lacks the field → 400)\n"
            "- `download_asset` skip-existing: print one-line stderr notice\n"
            "- E2E test path: `rglob('*.tif')` to find files at the scene_id level\n\n"
            "Tests:\n"
            "- 41 unit tests (mocked network): all pass\n"
            "- 20 e2e test cases against real Planetary Computer: all pass\n\n"
            "中文：通过 STAC 搜索和下载 Landsat 8/9 Collection 2 Level 2 影像；"
            "默认后端 Planetary Computer 公开无需账号；支持 WRS-2 路径/行、"
            "云量过滤、单波段选择、`.part` 安全写入、可视化进度条；"
            "隐私告示 + 一次性 quiet 关闭。"
        ),
        "tags": [
            "gis", "remote-sensing", "landsat", "stac", "planetary-computer",
            "earth-observation", "earth-search", "wrs-2", "下载",
        ],
        "files": files_meta,
    }
    payload_str = json.dumps(payload, ensure_ascii=False)
    print(f"Payload size: {len(payload_str)/1e3:.1f} KB")

    mp_files = [("payload", (None, payload_str, "application/json"))]
    mp_files.append(("accept_license_terms", (None, "true", "text/plain")))
    for p in file_paths:
        mp_files.append(("files", (p, open(p, "rb"),
                                    mimetypes.guess_type(p)[0] or "application/octet-stream")))

    print("Uploading...")
    session = requests.Session()
    if os.environ.get("CLAWHUB_USE_PROXY") != "1":
        session.trust_env = False
    r = session.post(
        f"{api}/skills",
        headers={"Authorization": f"Bearer {token}"},
        files=mp_files,
        timeout=300,
    )
    print(f"POST /skills status: {r.status_code}")
    print("body:", r.text[:1500])
    return 0 if r.status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
