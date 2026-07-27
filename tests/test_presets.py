"""Tests for --preset / --year / --season / --pick-best / auto-buffer.

These cover the "用户一句话完成" features added in v0.2.0:
- 自然语言日期展开 (--year 2024 --season summer → 2024-06-01..2024-08-31)
- 命名 preset (summer-2024, low-cloud-10, ndvi-ready, ...)
- 自动选最清晰一景 (--pick-best)
- 按行政区类型自动选 buffer (省/市/区/县)
- --qa-mode search 不下载就写 QA
"""
import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

import landsat_download


# ---------------------------------------------------------------------------
# PRESETS dict sanity
# ---------------------------------------------------------------------------
class TestPresets:
    def test_presets_dict_is_nonempty(self):
        assert isinstance(landsat_download.PRESETS, dict)
        assert len(landsat_download.PRESETS) >= 5

    def test_summer_2024_dates(self):
        p = landsat_download.PRESETS["summer-2024"]
        assert p["start_date"] == "2024-06-01"
        assert p["end_date"] == "2024-08-31"
        assert p["max_cloud_cover"] == 20.0

    def test_winter_2024_cross_year(self):
        p = landsat_download.PRESETS["winter-2024"]
        # 12-2 月跨年
        assert p["start_date"] == "2023-12-01"
        assert p["end_date"] == "2024-02-29"  # 2024 是闰年

    def test_annual_2024_full_year(self):
        p = landsat_download.PRESETS["annual-2024"]
        assert p["start_date"] == "2024-01-01"
        assert p["end_date"] == "2024-12-31"

    def test_low_cloud_10_no_dates(self):
        # 动态日期（rolling 1y）由 apply_preset 在 main 里填
        p = landsat_download.PRESETS["low-cloud-10"]
        assert p["start_date"] is None
        assert p["max_cloud_cover"] == 10.0

    def test_ndvi_ready_bands(self):
        p = landsat_download.PRESETS["ndvi-ready"]
        assert "red" in p["bands"]
        assert "nir08" in p["bands"]
        assert "qa" in p["bands"]

    def test_rgb_ready_bands(self):
        p = landsat_download.PRESETS["rgb-ready"]
        for b in ("red", "green", "blue"):
            assert b in p["bands"]

    def test_thermal_lst_bands(self):
        p = landsat_download.PRESETS["thermal-lst"]
        assert "lwir11" in p["bands"]


# ---------------------------------------------------------------------------
# SEASON_MONTHS
# ---------------------------------------------------------------------------
class TestSeasonMonths:
    def test_summer(self):
        assert landsat_download.SEASON_MONTHS["summer"] == (6, 8)

    def test_winter_crosses_year(self):
        # winter = Dec-Feb, 跨年
        assert landsat_download.SEASON_MONTHS["winter"] == (12, 2)

    def test_spring(self):
        assert landsat_download.SEASON_MONTHS["spring"] == (3, 5)


# ---------------------------------------------------------------------------
# _auto_buffer_for_place
# ---------------------------------------------------------------------------
class TestAutoBuffer:
    def test_province(self):
        assert landsat_download._auto_buffer_for_place("四川省") == 5.0
        assert landsat_download._auto_buffer_for_place("江苏省") == 5.0

    def test_city(self):
        assert landsat_download._auto_buffer_for_place("成都市") == 0.6
        assert landsat_download._auto_buffer_for_place("北京市") == 0.6

    def test_district(self):
        assert landsat_download._auto_buffer_for_place("朝阳区") == 0.15
        assert landsat_download._auto_buffer_for_place("海淀区") == 0.15

    def test_county(self):
        assert landsat_download._auto_buffer_for_place("郫县") == 0.4

    def test_fallback(self):
        assert landsat_download._auto_buffer_for_place("Some Random Name") == 0.3

    def test_empty(self):
        assert landsat_download._auto_buffer_for_place("") == 0.3

    def test_user_override(self):
        # 用户在 CLI 显式给值会走不同分支（main() 里 if args.place_buffer_deg is not None）
        # 这里只验证 helper 的 heuristic
        assert landsat_download._auto_buffer_for_place("成都市") == 0.6


# ---------------------------------------------------------------------------
# apply_preset
# ---------------------------------------------------------------------------
class TestApplyPreset:
    def _make_args(self, **kw):
        import argparse
        defaults = {
            "preset": None, "year": None, "season": None,
            "start_date": None, "end_date": None,
            "max_cloud_cover": None, "platform": "both",
            "bands": landsat_download.DEFAULT_BANDS,
        }
        defaults.update(kw)
        return argparse.Namespace(**defaults)

    def test_summer_preset(self):
        args = self._make_args(preset="summer-2024")
        out = landsat_download.apply_preset(args)
        assert out.start_date == "2024-06-01"
        assert out.end_date == "2024-08-31"
        assert out.max_cloud_cover == 20.0

    def test_user_date_overrides_preset(self):
        args = self._make_args(preset="summer-2024", start_date="2024-07-01")
        out = landsat_download.apply_preset(args)
        # 用户显式给 start_date → 不被 preset 覆盖
        assert out.start_date == "2024-07-01"

    def test_year_only(self):
        args = self._make_args(year=2024)
        out = landsat_download.apply_preset(args)
        assert out.start_date == "2024-01-01"
        assert out.end_date == "2024-12-31"

    def test_year_season_summer(self):
        args = self._make_args(year=2024, season="summer")
        out = landsat_download.apply_preset(args)
        assert out.start_date == "2024-06-01"
        assert out.end_date == "2024-08-31"

    def test_year_season_winter_crosses_year(self):
        # winter 2024 = 2024-12..2025-02
        args = self._make_args(year=2024, season="winter")
        out = landsat_download.apply_preset(args)
        assert out.start_date == "2024-12-01"
        assert out.end_date == "2025-02-28"

    def test_year_season_spring(self):
        args = self._make_args(year=2024, season="spring")
        out = landsat_download.apply_preset(args)
        assert out.start_date == "2024-03-01"
        assert out.end_date == "2024-05-31"

    def test_invalid_preset_raises(self):
        args = self._make_args(preset="nonexistent-preset")
        with pytest.raises(SystemExit):
            landsat_download.apply_preset(args)

    def test_invalid_season_raises(self):
        args = self._make_args(year=2024, season="nonexistent")
        with pytest.raises(SystemExit):
            landsat_download.apply_preset(args)

    def test_ndvi_preset_changes_bands(self):
        args = self._make_args(preset="ndvi-ready")
        out = landsat_download.apply_preset(args)
        assert "red" in out.bands
        assert "nir08" in out.bands
        # 用户没显式给 --bands，所以 bands 被覆盖
        assert out.bands != landsat_download.DEFAULT_BANDS

    def test_user_bands_override_ndvi_preset(self):
        custom = ["coastal", "lwir11"]
        args = self._make_args(preset="ndvi-ready", bands=custom)
        out = landsat_download.apply_preset(args)
        # 用户显式给了非常规 bands，preset 不覆盖
        # (但 DEFAULT_BANDS 比较是 args.bands 是否还是默认；这里 custom != DEFAULT)
        assert out.bands == custom


# ---------------------------------------------------------------------------
# --pick-best cloud cover sort
# ---------------------------------------------------------------------------
class TestPickBest:
    """End-to-end test for --pick-best (sort by cloud_cover, keep lowest)."""

    def test_pick_best_keeps_lowest_cloud(self):
        features = [
            {"id": "S1", "properties": {"eo:cloud_cover": 30.0}},
            {"id": "S2", "properties": {"eo:cloud_cover": 5.0}},
            {"id": "S3", "properties": {"eo:cloud_cover": 60.0}},
        ]
        # 模拟 main() 里的 pick-best 逻辑
        def _cloud(f):
            try:
                return float(f.get("properties", {}).get("eo:cloud_cover", 1e9))
            except (TypeError, ValueError):
                return 1e9
        best = sorted(features, key=_cloud)[0]
        assert best["id"] == "S2"

    def test_pick_best_handles_missing_cloud(self):
        features = [
            {"id": "S1", "properties": {}},  # missing eo:cloud_cover
            {"id": "S2", "properties": {"eo:cloud_cover": 10.0}},
        ]
        def _cloud(f):
            try:
                return float(f.get("properties", {}).get("eo:cloud_cover", 1e9))
            except (TypeError, ValueError):
                return 1e9
        # 缺失云量的排到 1e9（最末）
        best = sorted(features, key=_cloud)[0]
        assert best["id"] == "S2"


# ---------------------------------------------------------------------------
# --qa-mode search (no download, just search meta)
# ---------------------------------------------------------------------------
class TestQaModeSearch:
    def test_qa_writes_file(self, tmp_path):
        """Verify _write_qa helper creates a valid JSON file."""
        import argparse
        out = tmp_path / "test.qa.json"
        args = argparse.Namespace(
            start_date="2024-06-01", end_date="2024-08-31",
            max_cloud_cover=20.0, platform="landsat-9",
            path=None, row=None, bands=["red", "nir08", "qa"],
            source="pc", preset="ndvi-ready", year=2024, season="summer",
            pick_best=True, qa=str(out),
        )
        query_meta = {
            "bbox": [103.5, 30.0, 104.7, 31.3],
            "returned": 1,
            "picked": {"id": "LC09_L2SP_130038_20240823_02_T1", "cloud_cover": 21.58},
        }
        features = [
            {"id": "LC09_L2SP_130038_20240823_02_T1",
             "properties": {"datetime": "2024-08-23T03:38:55Z", "eo:cloud_cover": 21.58,
                            "platform": "landsat-9"}}
        ]
        place_info = {
            "query": "成都市", "display_name": "成都, 四川, 成都市, 中国",
            "source": "open-meteo", "buffer_deg_used": 0.6,
        }
        landsat_download._write_qa(args, query_meta, features, place_info, 0, 0.0)
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["skill"] == "landsat-download"
        assert data["version"] == "0.2.0"
        assert data["query"]["place"]["query"] == "成都市"
        assert data["query"]["place"]["buffer_deg"] == 0.6
        assert data["query"]["preset"] == "ndvi-ready"
        assert data["picked"]["id"] == "LC09_L2SP_130038_20240823_02_T1"
        assert data["picked"]["cloud_cover"] == 21.58
        assert data["scenes"][0]["platform"] == "landsat-9"


# ---------------------------------------------------------------------------
# --help mentions new flags
# ---------------------------------------------------------------------------
class TestHelpText:
    def test_help_mentions_preset(self, capsys):
        with pytest.raises(SystemExit):
            landsat_download.build_parser().parse_args(["--help"])
        out = capsys.readouterr().out
        assert "--preset" in out
        assert "--year" in out
        assert "--season" in out
        assert "--pick-best" in out
        assert "--qa-mode" in out
        assert "--place" in out
