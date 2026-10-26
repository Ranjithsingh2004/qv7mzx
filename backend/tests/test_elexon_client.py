"""Elexon HTTP client: request shape, retries, timeouts, failure mapping.

All upstream traffic is mocked with respx, so these run offline.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
import respx

from app.elexon.client import ElexonClient
from app.errors import UpstreamError

BASE = "https://data.elexon.co.uk/bmrs/api/v1"
FUELHH = f"{BASE}/datasets/FUELHH/stream"
WINDFOR = f"{BASE}/datasets/WINDFOR/stream"


@pytest.fixture
def client():
    return ElexonClient(base_url=BASE, timeout_seconds=1.0, max_retries=3)


@pytest.mark.asyncio
class TestRequestShape:
    @respx.mock
    async def test_actuals_request_uses_settlement_dates_and_wind_filter(self, client):
        route = respx.get(FUELHH).mock(return_value=httpx.Response(200, json=[]))
        await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 31))
        params = route.calls.last.request.url.params
        assert params["settlementDateFrom"] == "2026-01-01"
        assert params["settlementDateTo"] == "2026-01-31"
        # Filtering upstream cuts the payload by ~20x.
        assert params["fuelType"] == "WIND"
        # Elexon rejects mixing settlement-date and publish-date filters.
        assert "publishDateTimeFrom" not in params

    @respx.mock
    async def test_forecast_request_uses_publish_time_window(self, client):
        route = respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=[]))
        await client.fetch_wind_forecasts(
            dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.UTC),
            dt.datetime(2026, 2, 1, 0, 0, tzinfo=dt.UTC),
        )
        params = route.calls.last.request.url.params
        assert params["publishDateTimeFrom"] == "2026-01-01T09:00:00Z"
        assert params["publishDateTimeTo"] == "2026-02-01T00:00:00Z"

    @respx.mock
    async def test_bare_json_array_is_returned_as_rows(self, client):
        rows = [{"startTime": "2026-01-01T00:00:00Z", "generation": 1}]
        respx.get(FUELHH).mock(return_value=httpx.Response(200, json=rows))
        assert await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1)) == rows

    @respx.mock
    async def test_wrapped_data_envelope_is_also_accepted(self, client):
        rows = [{"startTime": "2026-01-01T00:00:00Z", "generation": 1}]
        respx.get(FUELHH).mock(return_value=httpx.Response(200, json={"data": rows}))
        assert await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1)) == rows


@pytest.mark.asyncio
class TestFailureHandling:
    @respx.mock
    async def test_transient_error_is_retried_then_succeeds(self, client):
        route = respx.get(FUELHH).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=[{"startTime": "2026-01-01T00:00:00Z", "generation": 1}]),
            ]
        )
        rows = await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1))
        assert len(rows) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_retries_are_exhausted_then_reported(self, client):
        route = respx.get(FUELHH).mock(return_value=httpx.Response(503))
        with pytest.raises(UpstreamError, match="after 3 attempt"):
            await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1))
        assert route.call_count == 3

    @respx.mock
    async def test_client_error_is_not_retried(self, client):
        # A 400 will not fix itself; retrying only adds latency.
        route = respx.get(FUELHH).mock(return_value=httpx.Response(400))
        with pytest.raises(UpstreamError, match="HTTP 400"):
            await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1))
        assert route.call_count == 1

    @respx.mock
    async def test_timeout_is_retried_and_surfaces_as_upstream_error(self, client):
        route = respx.get(FUELHH).mock(side_effect=httpx.ReadTimeout("too slow"))
        with pytest.raises(UpstreamError, match="timeout"):
            await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1))
        assert route.call_count == 3

    @respx.mock
    async def test_connection_error_surfaces_as_upstream_error(self, client):
        respx.get(FUELHH).mock(side_effect=httpx.ConnectError("no route"))
        with pytest.raises(UpstreamError, match="transport error"):
            await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1))

    @respx.mock
    async def test_invalid_json_surfaces_as_upstream_error(self, client):
        respx.get(FUELHH).mock(return_value=httpx.Response(200, content=b"<html>nope</html>"))
        with pytest.raises(UpstreamError, match="invalid JSON"):
            await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1))

    @respx.mock
    async def test_unexpected_payload_shape_surfaces_as_upstream_error(self, client):
        respx.get(FUELHH).mock(return_value=httpx.Response(200, json={"unexpected": True}))
        with pytest.raises(UpstreamError, match="unexpected payload"):
            await client.fetch_wind_actuals(dt.date(2026, 1, 1), dt.date(2026, 1, 1))


@pytest.mark.asyncio
class TestProbe:
    @respx.mock
    async def test_probe_is_true_when_upstream_answers(self, client):
        respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=[]))
        assert await client.probe() is True

    @respx.mock
    async def test_probe_is_false_rather_than_raising(self, client):
        # The health endpoint must still answer when Elexon is down.
        respx.get(WINDFOR).mock(return_value=httpx.Response(503))
        assert await client.probe() is False
