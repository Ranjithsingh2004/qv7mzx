"""Request validation, fetch-window derivation and caching behaviour."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
import respx

from app.cache import TTLCache
from app.config import Settings
from app.elexon.client import ElexonClient
from app.errors import ValidationError
from app.service import AnalysisService, parse_request

FUELHH = "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream"
WINDFOR = "https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream"


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def service(settings):
    return AnalysisService(
        client=ElexonClient(base_url=settings.elexon_base_url, max_retries=1),
        settings=settings,
    )


class TestParseRequest:
    def test_defaults_target_the_challenge_window(self, settings):
        request = parse_request(settings)
        assert request.decision_from == dt.date(2026, 1, 1)
        assert request.decision_to == dt.date(2026, 1, 31)
        assert request.cutoff.time_of_day == dt.time(9, 0)
        assert request.cutoff.days_before == 1
        assert request.alignment_mode == "hourly_mean"
        assert request.mape_floor_mw == 100.0

    def test_explicit_values_override_defaults(self, settings):
        request = parse_request(
            settings,
            decision_from="2026-01-05",
            decision_to="2026-01-06",
            cutoff_time="12:30",
            cutoff_days_before=2,
            alignment="period_start",
            mape_floor_mw=250,
        )
        assert request.decision_from == dt.date(2026, 1, 5)
        assert request.cutoff.time_of_day == dt.time(12, 30)
        assert request.cutoff.days_before == 2
        assert request.alignment_mode == "period_start"
        assert request.mape_floor_mw == 250

    @pytest.mark.parametrize(
        "kwargs,fragment",
        [
            ({"decision_from": "2026-13-01"}, "decision_from"),
            ({"decision_to": "nope"}, "decision_to"),
            ({"decision_from": "2026-01-10", "decision_to": "2026-01-01"}, "not be earlier"),
            ({"decision_from": "2025-01-01", "decision_to": "2026-01-01"}, "maximum"),
            ({"cutoff_time": "25:00"}, "cutoff_time"),
            ({"cutoff_days_before": 8}, "cutoff_days_before"),
            ({"cutoff_days_before": -1}, "cutoff_days_before"),
            ({"cutoff_days_before": 1.5}, "cutoff_days_before"),
            ({"alignment": "mean"}, "alignment"),
            ({"mape_floor_mw": -1}, "mape_floor_mw"),
        ],
    )
    def test_invalid_input_names_the_offending_parameter(self, settings, kwargs, fragment):
        with pytest.raises(ValidationError, match=fragment):
            parse_request(settings, **kwargs)

    def test_single_day_window_is_allowed(self, settings):
        request = parse_request(settings, decision_from="2026-01-05", decision_to="2026-01-05")
        assert request.decision_from == request.decision_to

    def test_cache_key_separates_differing_parameters(self, settings):
        base = parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-02")
        for kwargs in (
            {"cutoff_time": "12:00"},
            {"alignment": "period_start"},
            {"mape_floor_mw": 250},
            {"cutoff_days_before": 2},
            {"decision_to": "2026-01-03"},
        ):
            params = {"decision_from": "2026-01-01", "decision_to": "2026-01-02", **kwargs}
            other = parse_request(settings, **params)
            assert other.cache_key() != base.cache_key(), kwargs

    def test_cache_key_is_stable_for_equal_requests(self, settings):
        first = parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-02")
        second = parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-02")
        assert first.cache_key() == second.cache_key()


@pytest.mark.asyncio
class TestFetchWindows:
    @respx.mock
    async def test_actuals_window_pads_the_delivery_window(self, service, settings):
        actuals = respx.get(FUELHH).mock(return_value=httpx.Response(200, json=[]))
        respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=[]))
        await service.fetch(
            parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-31")
        )
        params = actuals.calls.last.request.url.params
        # Delivery is 02 Jan..01 Feb; one day of padding either side.
        assert params["settlementDateFrom"] == "2026-01-01"
        assert params["settlementDateTo"] == "2026-02-02"

    @respx.mock
    async def test_forecast_window_is_independent_of_cutoff_time(self, service, settings):
        """Anchoring to day boundaries is what makes the cutoff sweep cheap."""
        forecasts = respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=[]))
        respx.get(FUELHH).mock(return_value=httpx.Response(200, json=[]))
        windows = []
        for cutoff_time in ("06:00", "09:00", "23:30"):
            service.clear_cache()
            await service.fetch(
                parse_request(
                    settings,
                    decision_from="2026-01-01",
                    decision_to="2026-01-02",
                    cutoff_time=cutoff_time,
                )
            )
            params = forecasts.calls.last.request.url.params
            windows.append((params["publishDateTimeFrom"], params["publishDateTimeTo"]))
        assert len(set(windows)) == 1

    @respx.mock
    async def test_forecast_window_reaches_back_past_the_earliest_cutoff(self, service, settings):
        forecasts = respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=[]))
        respx.get(FUELHH).mock(return_value=httpx.Response(200, json=[]))
        request = parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-02")
        await service.fetch(request)
        published_from = forecasts.calls.last.request.url.params["publishDateTimeFrom"]
        earliest_cutoff = request.cutoff.for_delivery_day(dt.date(2026, 1, 2))
        assert published_from < earliest_cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.asyncio
class TestCaching:
    @respx.mock
    async def test_identical_requests_fetch_once(
        self, service, settings, fuelhh_rows, windfor_rows
    ):
        actuals = respx.get(FUELHH).mock(return_value=httpx.Response(200, json=fuelhh_rows))
        respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=windfor_rows))
        request = parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-02")
        await service.analyse(request)
        await service.analyse(request)
        assert actuals.call_count == 1

    @respx.mock
    async def test_changing_only_the_cutoff_reuses_the_download(
        self, service, settings, fuelhh_rows, windfor_rows
    ):
        actuals = respx.get(FUELHH).mock(return_value=httpx.Response(200, json=fuelhh_rows))
        respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=windfor_rows))
        for cutoff_time in ("06:00", "09:00", "12:00", "23:00"):
            await service.analyse(
                parse_request(
                    settings,
                    decision_from="2026-01-01",
                    decision_to="2026-01-02",
                    cutoff_time=cutoff_time,
                )
            )
        assert actuals.call_count == 1

    @respx.mock
    async def test_cutoff_sweep_downloads_once_for_many_cutoffs(
        self, service, settings, fuelhh_rows, windfor_rows
    ):
        actuals = respx.get(FUELHH).mock(return_value=httpx.Response(200, json=fuelhh_rows))
        respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=windfor_rows))
        rows = await service.cutoff_sweep(
            parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-02"),
            ["06:00", "09:00", "12:00", "17:00", "23:30"],
        )
        assert len(rows) == 5
        assert actuals.call_count == 1

    @respx.mock
    async def test_sweep_rejects_a_bad_cutoff_time(
        self, service, settings, fuelhh_rows, windfor_rows
    ):
        respx.get(FUELHH).mock(return_value=httpx.Response(200, json=fuelhh_rows))
        respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=windfor_rows))
        with pytest.raises(ValidationError, match="cutoff_times"):
            await service.cutoff_sweep(
                parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-02"),
                ["09:00", "nonsense"],
            )

    @respx.mock
    async def test_clear_cache_forces_a_refetch(self, service, settings, fuelhh_rows, windfor_rows):
        actuals = respx.get(FUELHH).mock(return_value=httpx.Response(200, json=fuelhh_rows))
        respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=windfor_rows))
        request = parse_request(settings, decision_from="2026-01-01", decision_to="2026-01-02")
        await service.analyse(request)
        service.clear_cache()
        await service.analyse(request)
        assert actuals.call_count == 2


class TestTTLCache:
    def test_stores_and_returns_a_value(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=4)
        cache.set("k", "v")
        assert cache.get("k") == "v"
        assert cache.hits == 1

    def test_missing_key_counts_as_a_miss(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=4)
        assert cache.get("absent") is None
        assert cache.misses == 1

    def test_expired_entry_is_discarded(self, monkeypatch):
        cache: TTLCache[str] = TTLCache(ttl_seconds=10, max_entries=4)
        clock = [1000.0]
        monkeypatch.setattr("app.cache.time.monotonic", lambda: clock[0])
        cache.set("k", "v")
        clock[0] += 11
        assert cache.get("k") is None

    def test_least_recently_used_entry_is_evicted(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=2)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.get("a")  # 'a' becomes most recently used
        cache.set("c", "3")  # evicts 'b'
        assert cache.get("a") == "1"
        assert cache.get("b") is None

    def test_stats_report_configuration_and_counters(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=30, max_entries=5)
        cache.set("k", "v")
        cache.get("k")
        cache.get("nope")
        stats = cache.stats()
        assert stats == {"entries": 1, "max_entries": 5, "ttl_seconds": 30, "hits": 1, "misses": 1}
