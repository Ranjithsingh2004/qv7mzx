"""Integration checks against the real Elexon API.

Marked ``live`` and excluded from the default run, so the suite stays offline
and deterministic. These exist because fixtures can only prove we parse what
Elexon returned once; this proves the contract still holds.

Run with:  pytest -m live
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.analysis.align import ActualHourlyIndex
from app.analysis.timeutils import parse_timestamp
from app.analysis.vintage import CutoffPolicy, ForecastVintageIndex
from app.config import Settings
from app.elexon.client import ElexonClient
from app.elexon.normalise import normalise_actuals, normalise_forecasts

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


@pytest.fixture
async def client():
    settings = Settings()
    api = ElexonClient(base_url=settings.elexon_base_url)
    yield api
    await api.aclose()


async def test_fuelhh_contract_still_holds(client):
    rows = await client.fetch_wind_actuals(dt.date(2026, 1, 5), dt.date(2026, 1, 5))
    assert rows, "Elexon returned no FUELHH rows for 2026-01-05"
    assert {"startTime", "generation", "fuelType", "settlementDate", "settlementPeriod"} <= set(
        rows[0]
    )
    # The upstream fuelType filter must actually be applied.
    assert {row["fuelType"] for row in rows} == {"WIND"}

    actuals, report = normalise_actuals(rows)
    assert report.dropped_malformed == 0
    # A full day is 48 half-hourly periods.
    assert len(actuals) == 48
    index = ActualHourlyIndex(actuals)
    assert index.hours_covered == 24
    assert all(
        not index.get(hour).partial
        for hour in (
            parse_timestamp("2026-01-05T00:00:00Z"),
            parse_timestamp("2026-01-05T12:00:00Z"),
        )
    )


async def test_windfor_contract_and_hourly_resolution(client):
    rows = await client.fetch_wind_forecasts(
        parse_timestamp("2026-01-04T00:00:00Z"), parse_timestamp("2026-01-05T00:00:00Z")
    )
    assert rows, "Elexon returned no WINDFOR rows for 2026-01-04"
    assert {"startTime", "publishTime", "generation"} <= set(rows[0])

    forecasts, report = normalise_forecasts(rows)
    assert report.dropped_malformed == 0
    # WINDFOR targets whole hours, unlike the half-hourly actuals.
    assert {record.start_time.minute for record in forecasts} == {0}
    # Several vintages a day, each covering a multi-day horizon.
    assert len({record.publish_time for record in forecasts}) >= 4


async def test_day_ahead_selection_against_the_live_feed(client):
    """A 09:00 D-1 cutoff must pick a vintage published before that instant."""
    forecasts, _ = normalise_forecasts(
        await client.fetch_wind_forecasts(
            parse_timestamp("2026-01-10T00:00:00Z"), parse_timestamp("2026-01-13T00:00:00Z")
        )
    )
    index = ForecastVintageIndex(forecasts)
    policy = CutoffPolicy(dt.time(9, 0), days_before=1)
    target = parse_timestamp("2026-01-12T18:00:00Z")
    cutoff = policy.for_target(target)
    selected = index.select(target, cutoff)
    assert selected is not None
    assert selected.publish_time <= cutoff
    assert 15 < selected.horizon_hours < 48
    # Later vintages exist for this target and must not have been chosen.
    assert selected.vintages_eligible < selected.vintages_available


async def test_health_probe_reaches_upstream(client):
    assert await client.probe() is True
