"""Pytest configuration for landsat-download tests.

Loads the ``landsat-download.py`` module (whose filename has a hyphen,
so Python's normal ``import`` machinery can't import it directly) and
registers it as ``landsat_download`` in ``sys.modules`` so test files
can simply do ``import landsat_download``.
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
SCRIPT_PATH = os.path.join(PROJECT_ROOT, "landsat-download.py")

# Add project root to sys.path so sibling imports work
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load the hyphenated module and register it as a regular importable module
_spec = importlib.util.spec_from_file_location("landsat_download", SCRIPT_PATH)
_module = importlib.util.module_from_spec(_spec)
sys.modules["landsat_download"] = _module
_spec.loader.exec_module(_module)
