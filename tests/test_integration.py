"""Integration smoke tests against the real Planetary Computer STAC.

These hit the real network and are slow. Skipped by default; run with::

    pytest -m integration tests/test_integration.py

or::

    RUN_LANDSAT_INTEGRATION=1 pytest tests/test_integration.py

Marked with @pytest.mark.integration so you can opt in selectively.
"""

import os
import sys

import pytest

# `landsat-download.py` has a hyphen in its filename, so it can't be
# imported directly. conftest.py loads it via importlib and registers it
# as the module `landsat_download` in sys.modules. The next import therefore
# picks up the already-loaded module.
import landsat_download


def _should_run() -> bool:
    return os.environ.get("RUN_LANDSAT_INTEGRATION") == "1"


pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.environ.get("RUN_LANDSAT_INTEGRATION"),
    reason="set RUN_LANDSAT_INTEGRATION=1 to run real-network tests",
)
def test_real_stac_search_returns_scene():
    """A real search for a known scene should return at least one result."""
    resp = landsat_download.stac_search(
        bbox=(116.0, 39.0, 117.0, 40.0),
        start_date="2024-08-30",
        end_date="2024-08-31",
        platform="landsat-9",
        limit=5,
        source="pc",
    )
    features = resp.get("features", [])
    assert len(features) >= 1
    assert "LC09" in features[0]["id"]


@pytest.mark.skipif(
    not os.environ.get("RUN_LANDSAT_INTEGRATION"),
    reason="set RUN_LANDSAT_INTEGRATION=1 to run real-network tests",
)
def test_real_list_bands_endpoint():
    """The Planetary Computer collection definition should have our asset keys."""
    import requests
    session = requests.Session()
    # Match the main script's proxy behaviour: bypass system proxy by default
    # (LANDSAT_DOWNLOAD_USE_PROXY=1 to enable). This avoids proxy-related
    # SSL errors when the test runs behind a VPN.
    if os.environ.get("LANDSAT_DOWNLOAD_USE_PROXY") != "1":
        session.trust_env = False
    r = session.get(
        "https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2",
        timeout=30,
    )
    r.raise_for_status()
    coll = r.json()
    asset_keys = set((coll.get("item_assets") or {}).keys())
    # Every default band must be available in the collection
    for b in landsat_download.DEFAULT_BANDS:
        assert b in asset_keys, f"default band {b!r} not in collection item_assets: {sorted(asset_keys)}"
