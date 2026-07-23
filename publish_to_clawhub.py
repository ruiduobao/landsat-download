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
    version = "0.1.2"

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
            "**v0.1.2: remove hardcoded proxy port references, clarify docs**\n\n"
            "Changes:\n"
            "- Removed hardcoded 7897 port references from code and docs\n"
            "- Proxy feature preserved via LANDSAT_DOWNLOAD_USE_PROXY=1 (default: direct)\n"
            "- SKILL.md: clarified proxy env var description\n"
            "- publish_to_clawhub.py: use trust_env=False by default\n\n"
            "Tests:\n"
            "- 41 unit tests: all pass\n"
            "- 2 integration tests (real Planetary Computer): all pass\n\n"
            "中文：移除代码和文档中硬编码的 7897 端口引用；"
            "保留代理功能（LANDSAT_DOWNLOAD_USE_PROXY=1 启用，默认直连）。"
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
