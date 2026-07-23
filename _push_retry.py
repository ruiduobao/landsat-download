"""Retry git push a few times with backoff.

Reads the token from GITHUB_TOKEN env var (NEVER hardcode the token).
"""
import subprocess
import time
import os
import sys

os.chdir(r"Z:\Mywork\自媒体\公众号\我的产品推文\Landsat_download")
token = os.environ.get("GITHUB_TOKEN")
if not token:
    print("ERROR: GITHUB_TOKEN env var is required", file=sys.stderr)
    sys.exit(1)
url = f"https://{token}@github.com/ruiduobao/landsat-download.git"

for i in range(1, 6):
    print(f"\n=== Attempt {i} ===")
    cp = subprocess.run(
        ["git", "-c", "http.proxy=", "-c", "https.proxy=", "push", url, "master"],
        capture_output=True, text=True, timeout=60,
    )
    out = (cp.stdout + cp.stderr).strip()
    print(out[:500])
    if cp.returncode == 0:
        print("\n  PUSH SUCCEEDED")
        sys.exit(0)
    if "Connection was reset" in out or "Failed to connect" in out:
        wait = 15 * i
        print(f"  443 blocked, retry in {wait}s")
        time.sleep(wait)
    else:
        sys.exit(cp.returncode)
sys.exit(1)
