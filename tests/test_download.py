"""Tests for the download + .part file safety logic.

These use a local HTTP server (http.server in a thread) so we exercise
the real download path without hitting the network.
"""

import os
import socket
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

# `landsat-download.py` has a hyphen in its filename, so it can't be
# imported directly. conftest.py loads it via importlib and registers it
# as the module `landsat_download` in sys.modules. The next import therefore
# picks up the already-loaded module.
import landsat_download


# ---------------------------------------------------------------------------
# Tiny HTTP server fixture
# ---------------------------------------------------------------------------

class _FixtureHandler(BaseHTTPRequestHandler):
    """Serves a few pre-defined payloads at /file, /large, /slow."""

    payloads = {
        "/file":    (b"hello fixture",                     "text/plain"),
        "/large":   (b"x" * (1 * 1024 * 1024),             "application/octet-stream"),  # 1 MB
        "/twobyte": (b"\x89\x50",                           "image/tiff"),
    }
    delay = 0.0

    def log_message(self, format, *args):
        # silence stderr access log
        pass

    def do_GET(self):
        # Strip the query string — PC source appends `?token=...` for
        # signing which would otherwise fail the `self.path in payloads`
        # check below.
        from urllib.parse import urlparse
        parsed = urlparse(self.path)
        path_only = parsed.path
        if path_only in self.payloads:
            body, ct = self.payloads[path_only]
            if self.delay:
                time.sleep(self.delay)
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def http_server():
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _FixtureHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield port
    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------------------
# Human-bytes helper
# ---------------------------------------------------------------------------

def test_human_bytes():
    assert landsat_download._human_bytes(0) == "0 B"
    assert landsat_download._human_bytes(500) == "500 B"
    assert landsat_download._human_bytes(1024) == "1.0 KB"
    assert landsat_download._human_bytes(1024 * 1024) == "1.0 MB"
    assert landsat_download._human_bytes(int(1024 * 1024 * 1024 * 2.5)) == "2.5 GB"


# ---------------------------------------------------------------------------
# Progress bar rendering
# ---------------------------------------------------------------------------

def test_render_progress_with_known_total():
    bar = landsat_download._render_progress(
        downloaded=500, total=1000, speed_bps=100, eta_seconds=5.0,
    )
    assert "50.0%" in bar
    assert "500" in bar
    assert "1.0 KB" in bar or "1,000" in bar or "1000" in bar
    assert "0:05" in bar


def test_render_progress_with_unknown_total():
    bar = landsat_download._render_progress(
        downloaded=200, total=None, speed_bps=50, eta_seconds=None,
    )
    assert "?  %" in bar
    assert "200" in bar
    assert "??" in bar or "  ?" in bar


# ---------------------------------------------------------------------------
# download_asset — happy path
# ---------------------------------------------------------------------------

def test_download_asset_writes_to_part_then_renames(tmp_path, http_server):
    dest = tmp_path / "out.txt"
    ok, msg = landsat_download.download_asset(
        url=f"http://127.0.0.1:{http_server}/file",
        dest_path=str(dest),
        timeout=10,
        show_progress=False,
    )
    assert ok is True
    assert msg == "ok"
    assert dest.exists()
    assert dest.read_bytes() == b"hello fixture"
    # The .part file must not linger
    assert not (tmp_path / "out.txt.part").exists()


def test_download_asset_skips_existing_file(tmp_path, http_server):
    """If the final file already exists (and no .part), skip the download."""
    dest = tmp_path / "out.txt"
    dest.write_bytes(b"already here")
    ok, msg = landsat_download.download_asset(
        url=f"http://127.0.0.1:{http_server}/file",
        dest_path=str(dest),
        timeout=10,
        show_progress=False,
    )
    assert ok is True
    assert "skip" in msg.lower()
    assert dest.read_bytes() == b"already here"


def test_download_asset_large_file(tmp_path, http_server):
    """A 1 MB download should complete with the right byte count."""
    dest = tmp_path / "big.bin"
    ok, msg = landsat_download.download_asset(
        url=f"http://127.0.0.1:{http_server}/large",
        dest_path=str(dest),
        timeout=10,
        show_progress=False,
    )
    assert ok is True
    assert dest.stat().st_size == 1 * 1024 * 1024


# ---------------------------------------------------------------------------
# download_asset — error path
# ---------------------------------------------------------------------------

def test_download_asset_404_does_not_create_file(tmp_path, http_server):
    """A 404 from the server must NOT create the final file."""
    dest = tmp_path / "out.txt"
    # Intentionally do NOT pre-create the file — we want to test that a
    # failed download does not leave behind a partial result.
    ok, msg = landsat_download.download_asset(
        url=f"http://127.0.0.1:{http_server}/nonexistent",
        dest_path=str(dest),
        timeout=10,
        show_progress=False,
    )
    assert ok is False
    assert not dest.exists()
    # The .part file must be cleaned up on failure
    assert not (tmp_path / "out.txt.part").exists()


# ---------------------------------------------------------------------------
# download_scene — end-to-end with mocked STAC signing
# ---------------------------------------------------------------------------

def test_download_scene_writes_files(tmp_path, http_server):
    """One scene with two assets (red + green) should create two files."""
    item = {
        "id": "LC08_TEST",
        "collection": "landsat-c2-l2",
        "assets": {
            "red":   {"href": f"http://127.0.0.1:{http_server}/file"},
            "green": {"href": f"http://127.0.0.1:{http_server}/file"},
        },
    }
    # PC source requires a SAS token; stub it
    landsat_download._SAS_CACHE["landsat-c2-l2"] = ("token=abc", time.time() + 600)
    result = landsat_download.download_scene(
        item, bands=["red", "green"],
        output_dir=str(tmp_path), source="pc",
        show_progress=False,
    )
    assert result["scene_id"] == "LC08_TEST"
    assert result["ok"] is True
    assert len(result["files"]) == 2
    # Each file should now exist (renamed from .part)
    scene_dir = tmp_path / "LC08_TEST"
    assert (scene_dir / "red.tif").exists()
    assert (scene_dir / "green.tif").exists()
    # Each should have the fixture payload
    assert (scene_dir / "red.tif").read_bytes() == b"hello fixture"


def test_download_scene_missing_asset_marked_failed(tmp_path, http_server):
    """An asset not in the STAC item is marked failed but does not crash."""
    item = {
        "id": "LC08_PARTIAL",
        "collection": "landsat-c2-l2",
        "assets": {
            "red": {"href": f"http://127.0.0.1:{http_server}/file"},
        },
    }
    result = landsat_download.download_scene(
        item, bands=["red", "green", "lwir11"],  # 2 of 3 are missing
        output_dir=str(tmp_path), source="pc",
        show_progress=False,
    )
    # The scene as a whole is marked failed because at least one asset failed
    assert result["ok"] is False
    # The one good asset did get written
    assert (tmp_path / "LC08_PARTIAL" / "red.tif").exists()
    # The two missing assets are reported in the per-file list
    msgs = [f["message"] for f in result["files"] if not f["ok"]]
    assert all("not in item" in m for m in msgs)
