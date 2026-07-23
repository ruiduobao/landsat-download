"""Security / privacy baseline tests for landsat-download.

These verify the v0.4.1-style security hardening that should be in every
published skill (privacy notice, opt-out, no stealth / anti-bot, no LLM).
"""

import os
import re
import subprocess
import sys

import pytest

# `landsat-download.py` has a hyphen in its filename, so it can't be
# imported directly. conftest.py loads it via importlib and registers it
# as the module `landsat_download` in sys.modules. The next import therefore
# picks up the already-loaded module.
import landsat_download


def test_module_docstring_has_privacy_section():
    """The module docstring must document what is / is not sent over the network."""
    doc = landsat_download.__doc__ or ""
    assert "Privacy" in doc, "module docstring must have a Privacy section"
    assert "no API keys" in doc.lower() or "no login" in doc.lower() or "not bypass" in doc.lower()


def test_module_docstring_makes_public_domain_clear():
    """Landsat Collection 2 is public domain; the docstring must say so."""
    doc = landsat_download.__doc__ or ""
    assert "public domain" in doc.lower(), "must say 'public domain'"


def test_no_anti_bot_patterns():
    """The script must not contain anti-bot / stealth / fingerprinting code."""
    src_path = os.path.join(
        os.path.dirname(landsat_download.__file__), "landsat-download.py",
    )
    src_path = os.path.abspath(src_path)
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    # These patterns should NEVER appear in this public-data skill
    forbidden = ["STEALTH_JS", "stealth", "anti-bot", "anti_bot", "hide webdriver",
                 "fingerprint_normaliz", "BROWSER_FINGERPRINT"]
    for pat in forbidden:
        assert pat.lower() not in src.lower(), f"forbidden pattern {pat!r} found in source"


def test_no_llm_imports():
    """No LLM dependencies — this skill works without any LLM."""
    src_path = os.path.abspath(os.path.join(
        os.path.dirname(landsat_download.__file__), "landsat-download.py",
    ))
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    forbidden = ["import openai", "import anthropic", "from openai", "from anthropic",
                 "mimo-v", "chat.completions"]
    for pat in forbidden:
        assert pat not in src, f"forbidden import {pat!r} found in source"


def test_uses_requests_only():
    """The script should only depend on requests, not other heavy libraries."""
    src_path = os.path.abspath(os.path.join(
        os.path.dirname(landsat_download.__file__), "landsat-download.py",
    ))
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    # Should NOT import pystac, planetary_computer, rasterio, geopandas etc.
    heavy = ["import pystac", "from pystac", "import planetary_computer",
             "import rasterio", "import geopandas", "import shapely"]
    for pat in heavy:
        assert pat not in src, f"unwanted heavy import {pat!r}"


def test_user_agent_identifies_skill():
    """The User-Agent must identify the skill (helps API hosts understand traffic)."""
    assert "landsat-download" in landsat_download.USER_AGENT


def test_trust_env_default_disabled():
    """trust_env defaults to False to avoid system proxy interference."""
    # The default value is read at import time, so we just check the env
    # is consulted. If user has not set LANDSAT_DOWNLOAD_USE_PROXY=1,
    # the default is False.
    if os.environ.get("LANDSAT_DOWNLOAD_USE_PROXY") != "1":
        assert landsat_download.DEFAULT_TRUST_ENV is False


def test_quiet_env_var_opt_out():
    """LANDSAT_DOWNLOAD_QUIET=1 must suppress the privacy notice."""
    os.environ["LANDSAT_DOWNLOAD_QUIET"] = "1"
    try:
        assert landsat_download._quiet() is True
    finally:
        os.environ.pop("LANDSAT_DOWNLOAD_QUIET", None)
