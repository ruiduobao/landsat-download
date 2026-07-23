#!/usr/bin/env bash
# Landsat Downloader — bash wrapper for the Python CLI
#
# Usage:
#   ./landsat-download.sh --check-deps
#   ./landsat-download.sh --bbox 116.0 39.0 117.0 40.0 --start-date 2024-01-01 --end-date 2024-12-31
#
# Forwards all arguments to landsat-download.py. If `--check-deps` is the
# only argument, runs a dependency check and exits.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${HERE}/landsat-download.py"

if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: ${PY_SCRIPT} not found" >&2
    exit 2
fi

# Check python
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    echo "ERROR: python3 (or python) not found in PATH" >&2
    exit 2
fi
PY="$(command -v python3 || command -v python)"

# Dependency check
check_deps() {
    echo "[landsat-download.sh] checking dependencies ..."
    "${PY}" -c "import requests; print(f'  requests {requests.__version__} — OK')" \
        || { echo "  requests NOT installed. Run: pip install 'requests>=2.28.0'" >&2; exit 1; }
    echo "[landsat-download.sh] all dependencies OK"
}

# If first arg is --check-deps, run check and exit
if [[ "${1:-}" == "--check-deps" ]]; then
    check_deps
    exit 0
fi

# Otherwise, ensure dependencies before running
"${PY}" -c "import requests" 2>/dev/null || {
    echo "[landsat-download.sh] 'requests' not installed. Running check-deps ..." >&2
    check_deps
}

exec "${PY}" "${PY_SCRIPT}" "$@"
