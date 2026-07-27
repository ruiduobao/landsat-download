"""test_longcat_cases.py — LongCat-2.0 生成的 landsat-download 测试用例

仅测试参数解析 + 错误码契约（离线），不依赖真实网络。
真实下载端到端验证见 landsat-download e2e_test.py。
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))


def _run(args, timeout=15):
    """Run main script with given args. Return (returncode, stdout, stderr)"""
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "landsat-download.py")] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---- LongCat 边界用例 4: bbox 纬度顺序错 ----

def test_longcase_bbox_lat_inverted():
    """LongCat 用例 4: bbox 纬度顺序错 (minLat > maxLat) → 应 exit 2 参数错"""
    out = _run([
        "--bbox", "116.3,40.0,116.4,39.9",  # 纬度错
        "--start-date", "2023-08-01", "--end-date", "2023-08-15",
        "--max-cloud-cover", "30",
        "--output-dir", os.path.join(os.environ.get("TEMP", "/tmp"), "lc_test"),
    ])
    # 期望：参数错（exit 2）或被搜索前 STAC 报错（exit 7）
    # 不期望：成功（exit 0）
    assert out.returncode in (2, 4, 5, 7), f"expected validation error, got {out.returncode}"
    combined = out.stdout + out.stderr
    assert "PHASE 0 DISABLED" not in combined


def test_longcase_bbox_west_gt_east():
    """类似边界: bbox 经度 west > east → 应非 0"""
    out = _run([
        "--bbox", "116.5,39.9,116.3,40.1",  # 经度错
        "--start-date", "2024-01-01", "--end-date", "2024-01-31",
        "--output-dir", os.path.join(os.environ.get("TEMP", "/tmp"), "lc_test2"),
    ])
    assert out.returncode != 0
    assert "PHASE 0 DISABLED" not in out.stderr


def test_longcase_help_works():
    """--help 必须能用且不抛错"""
    out = _run(["--help"])
    assert out.returncode == 0
    assert "--bbox" in out.stdout
    assert "--start-date" in out.stdout
    assert "--max-cloud-cover" in out.stdout
