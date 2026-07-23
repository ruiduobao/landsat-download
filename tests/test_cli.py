"""Tests for CLI argument parsing, output formatting, and edge cases."""

import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

import pytest

# `landsat-download.py` has a hyphen in its filename, so it can't be
# imported directly. conftest.py loads it via importlib and registers it
# as the module `landsat_download` in sys.modules. The next import therefore
# picks up the already-loaded module.
import landsat_download


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

SAMPLE_FEATURES = [
    {
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
        "assets": {"red": {}, "green": {}, "blue": {}},
    },
]


def test_format_scene_text_includes_key_fields():
    text = landsat_download._format_scene_text(SAMPLE_FEATURES[0], 1)
    assert "LC08_L2SP_123034_20240615_02_T1" in text
    assert "2024-06-15" in text
    assert "4.20%" in text
    assert "landsat-8" in text
    assert "123" in text


def test_format_scene_json_has_all_keys():
    d = landsat_download._format_scene_json(SAMPLE_FEATURES[0])
    assert d["id"] == "LC08_L2SP_123034_20240615_02_T1"
    assert d["platform"] == "landsat-8"
    assert d["cloud_cover"] == 4.20
    assert d["path"] == "123"
    assert d["row"] == "034"
    assert "red" in d["assets"]


def test_format_results_text_no_features():
    text = landsat_download.format_results_text(
        {"max_cloud_cover": 20}, [],
    )
    assert "0 scene(s)" in text
    assert "no scenes match" in text


def test_format_results_text_with_features():
    text = landsat_download.format_results_text(
        {"max_cloud_cover": 20}, SAMPLE_FEATURES,
    )
    assert "1 scene(s)" in text
    assert "LC08" in text


def test_format_results_json_is_valid_json():
    out = landsat_download.format_results_json(
        {"max_cloud_cover": 20, "path": 123}, SAMPLE_FEATURES,
    )
    parsed = json.loads(out)  # must not raise
    assert parsed["count"] == 1
    assert parsed["query"]["path"] == 123
    assert parsed["scenes"][0]["id"] == SAMPLE_FEATURES[0]["id"]


# ---------------------------------------------------------------------------
# Privacy / quiet mode
# ---------------------------------------------------------------------------

def test_quiet_when_env_set():
    old = os.environ.get("LANDSAT_DOWNLOAD_QUIET")
    try:
        os.environ["LANDSAT_DOWNLOAD_QUIET"] = "1"
        assert landsat_download._quiet() is True
    finally:
        if old is None:
            os.environ.pop("LANDSAT_DOWNLOAD_QUIET", None)
        else:
            os.environ["LANDSAT_DOWNLOAD_QUIET"] = old


def test_quiet_when_env_unset():
    old = os.environ.get("LANDSAT_DOWNLOAD_QUIET")
    try:
        os.environ.pop("LANDSAT_DOWNLOAD_QUIET", None)
        assert landsat_download._quiet() is False
    finally:
        if old is not None:
            os.environ["LANDSAT_DOWNLOAD_QUIET"] = old


def test_privacy_notice_is_quiet_in_quiet_mode(capsys):
    os.environ["LANDSAT_DOWNLOAD_QUIET"] = "1"
    try:
        landsat_download._emit_privacy_notice("test")
        captured = capsys.readouterr()
        assert captured.err == ""
    finally:
        os.environ.pop("LANDSAT_DOWNLOAD_QUIET", None)


def test_privacy_notice_prints_in_normal_mode(capsys):
    old = os.environ.get("LANDSAT_DOWNLOAD_QUIET")
    try:
        os.environ.pop("LANDSAT_DOWNLOAD_QUIET", None)
        landsat_download._emit_privacy_notice("Planetary Computer")
        captured = capsys.readouterr()
        assert "Planetary Computer" in captured.err
        assert "no API keys" in captured.err
    finally:
        if old is not None:
            os.environ["LANDSAT_DOWNLOAD_QUIET"] = old


# ---------------------------------------------------------------------------
# CLI: required-arg validation
# ---------------------------------------------------------------------------

def test_main_missing_args_returns_2(capsys):
    rc = landsat_download.main([])
    captured = capsys.readouterr()
    assert rc == 2
    assert "missing required arguments" in captured.err


def test_main_list_bands(capsys):
    rc = landsat_download.main(["--list-bands"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "red" in captured.out
    assert "blue" in captured.out
    assert "nir08" in captured.out


def test_main_help_runs():
    """argparse --help exits with code 0 and prints usage."""
    with pytest.raises(SystemExit) as e:
        landsat_download.main(["--help"])
    assert e.value.code == 0
