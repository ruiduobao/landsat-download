"""Tests for STAC search and signing.

These mock the network — they do not hit the real Planetary Computer API.
Real-network smoke tests are in test_integration.py (skipped by default).
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# `landsat-download.py` has a hyphen in its filename, so it can't be
# imported directly. conftest.py loads it via importlib and registers it
# as the module `landsat_download` in sys.modules. The next import therefore
# picks up the already-loaded module.
import landsat_download


# ---------------------------------------------------------------------------
# Sample STAC fixtures
# ---------------------------------------------------------------------------

SAMPLE_STAC_RESPONSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "LC08_L2SP_123034_20240615_02_T1",
            "collection": "landsat-c2-l2",
            "bbox": [116.0, 39.0, 117.0, 40.0],
            "properties": {
                "datetime": "2024-06-15T03:12:34.000Z",
                "platform": "landsat-8",
                "eo:cloud_cover": 4.20,
                "landsat:wrs_path": "123",
                "landsat:wrs_row": "034",
            },
            "assets": {
                "red":  {"href": "https://landsateuwest.blob.core.windows.net/landsat-c2/red.tif"},
                "green":{"href": "https://landsateuwest.blob.core.windows.net/landsat-c2/green.tif"},
                "blue": {"href": "https://landsateuwest.blob.core.windows.net/landsat-c2/blue.tif"},
                "qa":   {"href": "https://landsateuwest.blob.core.windows.net/landsat-c2/qa.tif"},
                "mtl.txt": {"href": "https://landsateuwest.blob.core.windows.net/landsat-c2/MTL.txt"},
            },
        },
        {
            "type": "Feature",
            "id": "LC09_L2SP_122033_20240831_02_T1",
            "collection": "landsat-c2-l2",
            "bbox": [116.0, 39.0, 117.0, 40.0],
            "properties": {
                "datetime": "2024-08-31T02:47:30.469664Z",
                "platform": "landsat-9",
                "eo:cloud_cover": 25.34,
                "landsat:wrs_path": "122",
                "landsat:wrs_row": "033",
            },
            "assets": {
                "red":   {"href": "https://landsateuwest.blob.core.windows.net/landsat-c2/red.tif"},
                "green": {"href": "https://landsateuwest.blob.core.windows.net/landsat-c2/green.tif"},
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_stac_endpoints_have_required_keys():
    """The STAC endpoint table must define search + sign for each backend."""
    for src, cfg in landsat_download.STAC_ENDPOINTS.items():
        assert "search" in cfg, f"missing 'search' for {src}"
        assert "root" in cfg, f"missing 'root' for {src}"
        # aws may not need signing (public S3), but pc always does
        if src == "pc":
            assert cfg.get("sign") is not None, f"missing 'sign' for {src}"


def test_default_bands_match_stac_asset_keys():
    """The default --bands list must be valid STAC asset keys."""
    assert landsat_download.DEFAULT_BANDS == [
        "red", "green", "blue", "nir08", "swir16", "swir22",
    ]


def test_band_descriptions_covers_default_bands():
    """BAND_DESCRIPTIONS must document every default band."""
    for b in landsat_download.DEFAULT_BANDS:
        assert b in landsat_download.BAND_DESCRIPTIONS, f"missing description for {b!r}"


def test_stac_search_builds_correct_query():
    """The STAC request body must have collections / bbox / datetime / query."""
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=SAMPLE_STAC_RESPONSE)
        return resp

    with patch.object(landsat_download.requests, "Session") as MockSession:
        session = MagicMock()
        session.trust_env = False
        session.headers = {}
        session.post = fake_post
        MockSession.return_value = session

        landsat_download.stac_search(
            bbox=(116.0, 39.0, 117.0, 40.0),
            start_date="2024-06-01",
            end_date="2024-08-31",
            max_cloud_cover=20.0,
            platform="both",
            limit=5,
            source="pc",
        )

    body = captured["json"]
    assert body["collections"] == ["landsat-c2-l2"]
    assert body["bbox"] == [116.0, 39.0, 117.0, 40.0]
    assert body["datetime"] == "2024-06-01T00:00:00Z/2024-08-31T23:59:59Z"
    assert body["limit"] == 5
    assert body["query"]["eo:cloud_cover"]["lt"] == 20.0
    assert body["query"]["platform"]["in"] == ["landsat-8", "landsat-9"]


def test_stac_search_platform_filter_landsat_8_only():
    """With --platform landsat-8, the query must use eq (not in)."""
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=SAMPLE_STAC_RESPONSE)
        return resp

    with patch.object(landsat_download.requests, "Session") as MockSession:
        session = MagicMock()
        session.trust_env = False
        session.headers = {}
        session.post = fake_post
        MockSession.return_value = session

        landsat_download.stac_search(
            bbox=(116.0, 39.0, 117.0, 40.0),
            start_date="2024-06-01",
            end_date="2024-06-30",
            platform="landsat-8",
            source="pc",
        )

    assert captured["json"]["query"]["platform"] == {"eq": "landsat-8"}


def test_stac_search_wrs_path_row_filter():
    """With --path / --row, the query must include landsat:wrs_path / row."""
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=SAMPLE_STAC_RESPONSE)
        return resp

    with patch.object(landsat_download.requests, "Session") as MockSession:
        session = MagicMock()
        session.trust_env = False
        session.headers = {}
        session.post = fake_post
        MockSession.return_value = session

        landsat_download.stac_search(
            bbox=(116.0, 39.0, 117.0, 40.0),
            start_date="2024-06-01",
            end_date="2024-06-30",
            platform="both",
            path=123, row=34,
            source="pc",
        )

    assert captured["json"]["query"]["landsat:wrs_path"] == {"eq": "123"}
    assert captured["json"]["query"]["landsat:wrs_row"] == {"eq": "34"}


def test_stac_search_invalid_source_raises():
    with pytest.raises(ValueError, match="Unknown source"):
        landsat_download.stac_search(
            bbox=(0, 0, 1, 1),
            start_date="2024-01-01",
            end_date="2024-01-02",
            source="bogus",
        )


def test_stac_search_invalid_platform_raises():
    with pytest.raises(ValueError, match="Unknown platform"):
        landsat_download.stac_search(
            bbox=(0, 0, 1, 1),
            start_date="2024-01-01",
            end_date="2024-01-02",
            platform="bogus",
        )


def test_get_signed_href_aws_returns_href_unchanged():
    """For AWS source, the public S3 href is returned as-is (no signing)."""
    item = SAMPLE_STAC_RESPONSE["features"][0]
    href = landsat_download.get_signed_href(item, "red", source="aws")
    assert href == "https://landsateuwest.blob.core.windows.net/landsat-c2/red.tif"


def test_get_signed_href_pc_appends_token():
    """For PC source, the signed token is appended via query string."""
    # Clear the cache to force a fresh sign
    landsat_download._SAS_CACHE.clear()

    fake_token = "se=2026-01-01&sp=rl&sv=2023-11-03&sr=c&skoid=..."
    with patch.object(landsat_download.requests, "Session") as MockSession:
        session = MagicMock()
        session.trust_env = False
        session.headers = {}
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"token": fake_token})
        session.get = MagicMock(return_value=resp)
        MockSession.return_value = session

        item = SAMPLE_STAC_RESPONSE["features"][0]
        href = landsat_download.get_signed_href(item, "red", source="pc")

    assert href.startswith("https://landsateuwest.blob.core.windows.net/landsat-c2/red.tif?")
    assert fake_token in href


def test_get_signed_href_pc_caches_token():
    """The PC SAS token is cached for ~1 hour (only fetched once per run)."""
    landsat_download._SAS_CACHE.clear()
    fake_token = "se=cache-test&sv=2023-11-03"
    with patch.object(landsat_download.requests, "Session") as MockSession:
        session = MagicMock()
        session.trust_env = False
        session.headers = {}
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"token": fake_token})
        session.get = MagicMock(return_value=resp)
        MockSession.return_value = session

        item = SAMPLE_STAC_RESPONSE["features"][0]
        # Two calls — only one HTTP request
        landsat_download.get_signed_href(item, "red", source="pc")
        landsat_download.get_signed_href(item, "green", source="pc")
        # The session.get should have been called only once
        assert session.get.call_count == 1


def test_get_signed_href_missing_asset_returns_none():
    item = SAMPLE_STAC_RESPONSE["features"][0]
    assert landsat_download.get_signed_href(item, "nonexistent_asset", source="pc") is None
