"""Test setup: a temporary hub DB (volunteers/sessions) and the real catalog.sqlite."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="d4gc-test-")
os.environ["D4GC_HUB_DB"] = str(Path(_TMP) / "hub_test.sqlite")   # must be set before hub.* is imported

from common.config import load  # noqa: E402

if not load()["paths"]["catalog_db"].exists():
    pytest.exit("data/catalog.sqlite missing: run  python preprocess/build_catalog.py  first", returncode=1)
