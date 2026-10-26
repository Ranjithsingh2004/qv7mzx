"""Shared fixtures.

The JSON fixtures are verbatim slices of real Elexon responses (two delivery
days plus padding), so the tests exercise the same shapes production sees
without needing the network.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fuelhh_rows() -> list[dict]:
    """FUELHH wind rows for settlement dates 2026-01-01..2026-01-04."""
    return json.loads((FIXTURES / "fuelhh_wind_sample.json").read_text())


@pytest.fixture(scope="session")
def windfor_rows() -> list[dict]:
    """WINDFOR rows: 32 vintages targeting 2026-01-02..2026-01-03."""
    return json.loads((FIXTURES / "windfor_sample.json").read_text())


@pytest.fixture
def utc():
    return dt.UTC
