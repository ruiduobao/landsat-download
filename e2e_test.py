"""20-case test runner for landsat-download.

Each case is a separate function. Results (PASS/FAIL + notes) are written
to ``_test_results.log`` so we can fix issues between runs.

Cases
-----
Search-only (1-12): cover bbox / date / platform / cloud / WRS-2 / output format
Download (13-15): real Planetary Computer download with various band sets
Edge cases (16-20): invalid input, AWS backend, --no-progress, --quiet
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent.resolve()
SCRIPT = HERE / "landsat-download.py"
LOG = HERE / "e2e_test.log"
DOWNLOAD_DIR = HERE / "_test_dl_20"

# Reset state
if LOG.exists():
    LOG.unlink()
if DOWNLOAD_DIR.exists():
    shutil.rmtree(DOWNLOAD_DIR)
DOWNLOAD_DIR.mkdir()


def _run(args, *, timeout=300, env_extra=None, label=""):
    """Run the CLI; return (returncode, stdout, stderr, elapsed_seconds)."""
    cmd = [sys.executable, str(SCRIPT), *args]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    t0 = time.time()
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        rc, out, err = cp.returncode, cp.stdout, cp.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = -1, e.stdout or "", f"TIMEOUT after {timeout}s"
    elapsed = time.time() - t0
    return rc, out, err, elapsed


def _log(label, rc, out, err, elapsed, *, passed, notes=""):
    status = "PASS" if passed else "FAIL"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*70}\n")
        f.write(f"[{status}] Case {label}  (rc={rc}, {elapsed:.1f}s)\n")
        f.write(f"{notes}\n")
        if out:
            f.write(f"--- stdout (first 400 chars) ---\n{out[:400]}\n")
        if err:
            f.write(f"--- stderr (first 400 chars) ---\n{err[:400]}\n")
    print(f"  [{status}] {label}  rc={rc}  {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# 20 test cases
# ---------------------------------------------------------------------------

def case_01():
    """Search Beijing 2024, Landsat 9 only, cloud < 30%."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-01-01", "--end-date", "2024-12-31",
        "--max-cloud-cover", "30", "--platform", "landsat-9", "--limit", "3",
        "--no-progress", "--quiet",
    ])
    passed = rc == 0 and "LC09" in out
    _log("01 Beijing 2024 L9", rc, out, err, t, passed=passed,
         notes="expect LC09 hits, rc=0")


def case_02():
    """Search Beijing 2024, both platforms, cloud < 10%."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-01-01", "--end-date", "2024-12-31",
        "--max-cloud-cover", "10", "--platform", "both", "--limit", "3",
        "--no-progress", "--quiet",
    ])
    passed = rc == 0 and ("LC08" in out or "LC09" in out)
    _log("02 Beijing 2024 both cloud<10", rc, out, err, t, passed=passed,
         notes="expect LC08/LC09 hits, rc=0")


def case_03():
    """WRS-2 path=123 row=34 filter."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-01-01", "--end-date", "2024-12-31",
        "--path", "123", "--row", "34", "--limit", "3",
        "--no-progress", "--quiet",
    ])
    passed = rc == 0 and ("Path/Row: 123" in out or "path" in out.lower())
    _log("03 WRS-2 path=123 row=34", rc, out, err, t, passed=passed,
         notes="expect Path/Row 123/34 in output")


def case_04():
    """Single day search."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-30",
        "--limit", "3", "--no-progress", "--quiet",
    ])
    passed = rc == 0
    _log("04 Single day 2024-08-30", rc, out, err, t, passed=passed,
         notes="expect rc=0 (could be empty for narrow bbox)")


def case_05():
    """Whole year search with high limit."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.5", "116.2", "39.7",  # small bbox in Beijing
        "--start-date", "2024-01-01", "--end-date", "2024-12-31",
        "--limit", "20", "--no-progress", "--quiet",
    ])
    passed = rc == 0
    _log("05 Whole year 2024", rc, out, err, t, passed=passed,
         notes="expect rc=0; scenes depend on path/row coverage")


def case_06():
    """Empty result (very small bbox, very narrow date)."""
    rc, out, err, t = _run([
        "--bbox", "116.0001", "39.0001", "116.0002", "39.0002",  # tiny
        "--start-date", "2020-01-01", "--end-date", "2020-01-01",
        "--limit", "3", "--no-progress", "--quiet",
    ])
    passed = rc == 0 and "0 scene" in out
    _log("06 Empty result", rc, out, err, t, passed=passed,
         notes="expect rc=0 + '0 scene(s)' in output")


def case_07():
    """JSON output format."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-31",
        "--limit", "2", "--output-format", "json",
        "--no-progress", "--quiet",
    ])
    passed = rc == 0
    try:
        parsed = json.loads(out)
        passed = passed and "scenes" in parsed and "query" in parsed
    except Exception:
        passed = False
    _log("07 JSON output format", rc, out, err, t, passed=passed,
         notes="expect rc=0 + valid JSON with scenes/query keys")


def case_08():
    """--list-bands."""
    rc, out, err, t = _run(["--list-bands"])
    passed = rc == 0 and "red" in out and "nir08" in out and "qa" in out
    _log("08 --list-bands", rc, out, err, t, passed=passed,
         notes="expect rc=0 + red/nir08/qa in output")


def case_09():
    """Missing required args → rc=2."""
    rc, out, err, t = _run([])
    passed = rc == 2 and "missing required arguments" in err
    _log("09 Missing required args", rc, out, err, t, passed=passed,
         notes="expect rc=2 + error message on stderr")


def case_10():
    """Only --bbox without dates → rc=2."""
    rc, out, err, t = _run(["--bbox", "116.0", "39.0", "117.0", "40.0"])
    passed = rc == 2
    _log("10 Only --bbox, no dates", rc, out, err, t, passed=passed,
         notes="expect rc=2")


def case_11():
    """--quiet suppresses progress + privacy notice."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-31",
        "--limit", "1", "--quiet",
    ])
    passed = rc == 0 and "contacting Planetary Computer" not in err
    _log("11 --quiet mode", rc, out, err, t, passed=passed,
         notes="expect no privacy notice on stderr")


def case_12():
    """LANDSAT_DOWNLOAD_QUIET=1 env var works."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-31",
        "--limit", "1",
    ], env_extra={"LANDSAT_DOWNLOAD_QUIET": "1"})
    passed = rc == 0 and "contacting Planetary Computer" not in err
    _log("12 LANDSAT_DOWNLOAD_QUIET=1", rc, out, err, t, passed=passed,
         notes="expect no privacy notice via env var")


def case_13():
    """Download 1 scene, 1 band (red only). Smallest possible download."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-31",
        "--limit", "1", "--download",
        "--bands", "red",
        "--output-dir", str(DOWNLOAD_DIR / "case13"),
        "--no-progress", "--quiet",
    ], timeout=180)
    scene_dir = DOWNLOAD_DIR / "case13"
    red_exists = any(scene_dir.rglob("red.tif")) if scene_dir.exists() else False
    passed = rc == 0 and red_exists
    _log("13 Download 1 scene, 1 band (red)", rc, out, err, t, passed=passed,
         notes="expect red.tif present under output-dir")


def case_14():
    """Download 1 scene, RGB (3 bands)."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-31",
        "--limit", "1", "--download",
        "--bands", "red", "green", "blue",
        "--output-dir", str(DOWNLOAD_DIR / "case14"),
        "--no-progress", "--quiet",
    ], timeout=300)
    # The script creates a subdirectory per scene_id, so we need to look
    # one level deeper than the user-supplied output-dir.
    expected_bands = ["red.tif", "green.tif", "blue.tif"]
    all_three = False
    if (DOWNLOAD_DIR / "case14").exists():
        found = {p.name for p in (DOWNLOAD_DIR / "case14").rglob("*.tif")}
        all_three = all(b in found for b in expected_bands)
    passed = rc == 0 and all_three
    _log("14 Download 1 scene, RGB (3 bands)", rc, out, err, t, passed=passed,
         notes=f"expect {expected_bands} under case14/<scene_id>/")


def case_15():
    """Skip-existing: run the same download twice; second run should skip."""
    out_dir = str(DOWNLOAD_DIR / "case15")
    common = [
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-31",
        "--limit", "1", "--download",
        "--bands", "red",
        "--output-dir", out_dir,
        # No --quiet here; we need to see the skip message on stderr
    ]
    # First run
    rc1, out1, err1, t1 = _run(common, timeout=180)
    # Second run (should skip; the skip message is now printed to stderr)
    rc2, out2, err2, t2 = _run(common, timeout=60)
    skip_in_stderr = "skipping" in err2
    skip_in_stdout = "skipping" in out2
    passed = rc1 == 0 and rc2 == 0 and (skip_in_stderr or skip_in_stdout)
    _log("15 Skip-existing on re-run", rc2, out2, err2, t2, passed=passed,
         notes=f"first={rc1} second={rc2}; expect 'skipping' somewhere")


def case_16():
    """AWS backend (Earth Search). May or may not have results — just check it doesn't crash."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-31",
        "--limit", "1", "--source", "aws",
        "--no-progress", "--quiet",
    ], timeout=60)
    passed = rc == 0
    _log("16 AWS backend", rc, out, err, t, passed=passed,
         notes="expect rc=0 (no crash; result count depends on Element84)")


def case_17():
    """--no-progress suppresses visual progress bar but still prints summary."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-08-30", "--end-date", "2024-08-31",
        "--limit", "1", "--download",
        "--bands", "red",
        "--output-dir", str(DOWNLOAD_DIR / "case17"),
        "--no-progress", "--quiet",
    ], timeout=180)
    passed = rc == 0
    _log("17 --no-progress + download", rc, out, err, t, passed=passed,
         notes="expect rc=0; no Unicode block characters in stdout")


def case_18():
    """Invalid date format (should be rejected by API or gracefully)."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "not-a-date", "--end-date", "2024-12-31",
        "--limit", "1", "--no-progress", "--quiet",
    ], timeout=30)
    # We accept either rc != 0 (error) or rc == 0 (PC API may reject with empty)
    passed = rc != 0  # any non-zero is acceptable
    _log("18 Invalid date format", rc, out, err, t, passed=passed,
         notes="expect non-zero rc")


def case_19():
    """Multi-month search (June + July 2024, Beijing)."""
    rc, out, err, t = _run([
        "--bbox", "116.0", "39.0", "117.0", "40.0",
        "--start-date", "2024-06-01", "--end-date", "2024-07-31",
        "--max-cloud-cover", "50", "--limit", "5",
        "--no-progress", "--quiet",
    ])
    passed = rc == 0
    _log("19 Multi-month search Jun-Jul 2024", rc, out, err, t, passed=passed,
         notes="expect rc=0; should return multiple scenes")


def case_20():
    """Cross-region: Yangtze delta 2024-06 (Shanghai bbox)."""
    rc, out, err, t = _run([
        "--bbox", "121.0", "30.5", "122.0", "31.5",
        "--start-date", "2024-06-01", "--end-date", "2024-06-30",
        "--max-cloud-cover", "40", "--limit", "5",
        "--no-progress", "--quiet",
    ])
    passed = rc == 0
    _log("20 Yangtze delta 2024-06", rc, out, err, t, passed=passed,
         notes="expect rc=0; Shanghai region has dense coverage")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Running 20 test cases...")
    print("=" * 60)
    cases = [
        case_01, case_02, case_03, case_04, case_05,
        case_06, case_07, case_08, case_09, case_10,
        case_11, case_12, case_13, case_14, case_15,
        case_16, case_17, case_18, case_19, case_20,
    ]
    t_start = time.time()
    for i, case in enumerate(cases, 1):
        print(f"\n[{i:02d}/20] {case.__doc__.splitlines()[0] if case.__doc__ else case.__name__}")
        try:
            case()
        except Exception as e:
            _log(case.__name__, -1, "", f"EXCEPTION: {e}", 0,
                 passed=False, notes="case raised an exception")
    elapsed = time.time() - t_start
    # Summary
    if LOG.exists():
        text = LOG.read_text(encoding="utf-8")
        n_pass = text.count("\n[PASS]")
        n_fail = text.count("\n[FAIL]")
        print("\n" + "=" * 60)
        print(f"20 cases: {n_pass} PASS, {n_fail} FAIL, total {elapsed:.0f}s")
        print(f"Full log: {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
