"""Normalisation of raw Elexon payloads: filtering, validation, duplicates."""

from __future__ import annotations

import datetime as dt

import pytest

from app.analysis.timeutils import parse_timestamp
from app.elexon.normalise import normalise_actuals, normalise_forecasts


def actual_row(**overrides) -> dict:
    row = {
        "dataset": "FUELHH",
        "publishTime": "2026-01-05T00:30:00Z",
        "startTime": "2026-01-05T00:00:00Z",
        "settlementDate": "2026-01-05",
        "settlementPeriod": 1,
        "fuelType": "WIND",
        "generation": 10601,
    }
    row.update(overrides)
    return row


def forecast_row(**overrides) -> dict:
    row = {
        "dataset": "WINDFOR",
        "publishTime": "2026-01-04T07:30:00Z",
        "startTime": "2026-01-05T00:00:00Z",
        "generation": 10204,
    }
    row.update(overrides)
    return row


class TestWindFiltering:
    def test_keeps_only_wind_from_a_mixed_payload(self):
        rows = [
            actual_row(fuelType="CCGT", generation=20000),
            actual_row(fuelType="NUCLEAR", generation=5000),
            actual_row(fuelType="WIND", generation=10601),
        ]
        records, report = normalise_actuals(rows)
        assert len(records) == 1
        assert records[0].generation == 10601
        assert report.dropped_wrong_fuel == 2

    def test_fuel_type_match_is_case_insensitive(self):
        records, _ = normalise_actuals([actual_row(fuelType="wind")])
        assert len(records) == 1

    def test_row_without_fuel_type_is_not_assumed_to_be_wind(self):
        # Guessing here would silently fold other fuels into the wind series.
        rows = [actual_row()]
        del rows[0]["fuelType"]
        records, report = normalise_actuals(rows)
        assert records == []
        assert report.dropped_wrong_fuel == 1

    def test_real_fixture_is_all_wind(self, fuelhh_rows):
        records, report = normalise_actuals(fuelhh_rows)
        assert len(records) == len(fuelhh_rows)
        assert report.dropped_wrong_fuel == 0
        assert report.dropped_malformed == 0


class TestActualValidation:
    @pytest.mark.parametrize(
        "bad_value", [None, "", "abc", float("nan"), float("inf"), True, {}, []]
    )
    def test_unusable_generation_is_dropped_not_zeroed(self, bad_value):
        records, report = normalise_actuals([actual_row(generation=bad_value)])
        assert records == []
        assert report.dropped_malformed == 1

    def test_negative_generation_is_kept(self):
        # Wind farms can net-consume; -5 MW is data, not an error.
        records, _ = normalise_actuals([actual_row(generation=-5)])
        assert records[0].generation == -5

    @pytest.mark.parametrize("bad", ["", "nonsense", None])
    def test_unusable_start_time_is_dropped(self, bad):
        records, report = normalise_actuals([actual_row(startTime=bad)])
        assert records == []
        assert report.dropped_malformed == 1

    def test_non_dict_rows_are_dropped(self):
        records, report = normalise_actuals(["nope", 42, None])
        assert records == []
        assert report.dropped_malformed == 3

    def test_unparseable_publish_time_is_tolerated(self):
        # publishTime only ranks revisions, so it must not fail a usable row.
        records, _ = normalise_actuals([actual_row(publishTime="broken")])
        assert len(records) == 1
        assert records[0].publish_time is None

    def test_issue_list_is_bounded(self):
        records, report = normalise_actuals([actual_row(generation=None)] * 50)
        assert records == []
        assert report.dropped_malformed == 50
        assert len(report.issues) <= 10


class TestActualDuplicates:
    def test_revision_with_later_publish_time_wins(self):
        rows = [
            actual_row(generation=10000, publishTime="2026-01-05T00:30:00Z"),
            actual_row(generation=10601, publishTime="2026-01-05T02:00:00Z"),
        ]
        records, report = normalise_actuals(rows)
        assert len(records) == 1
        assert records[0].generation == 10601
        assert report.duplicates_collapsed == 1

    def test_earlier_revision_does_not_overwrite_later_one(self):
        rows = [
            actual_row(generation=10601, publishTime="2026-01-05T02:00:00Z"),
            actual_row(generation=10000, publishTime="2026-01-05T00:30:00Z"),
        ]
        records, _ = normalise_actuals(rows)
        assert records[0].generation == 10601

    def test_revision_with_publish_time_beats_one_without(self):
        rows = [actual_row(generation=1, publishTime=None), actual_row(generation=2)]
        records, _ = normalise_actuals(rows)
        assert records[0].generation == 2

    def test_output_is_sorted_by_start_time(self):
        rows = [
            actual_row(startTime="2026-01-05T01:00:00Z", settlementPeriod=3),
            actual_row(startTime="2026-01-05T00:00:00Z", settlementPeriod=1),
            actual_row(startTime="2026-01-05T00:30:00Z", settlementPeriod=2),
        ]
        records, _ = normalise_actuals(rows)
        assert [r.start_time for r in records] == sorted(r.start_time for r in records)


class TestForecastNormalisation:
    def test_keeps_every_vintage_for_a_target(self):
        # Collapsing vintages would destroy the cutoff logic entirely.
        rows = [
            forecast_row(publishTime="2026-01-04T02:30:00Z", generation=100),
            forecast_row(publishTime="2026-01-04T07:30:00Z", generation=200),
            forecast_row(publishTime="2026-01-04T11:30:00Z", generation=300),
        ]
        records, report = normalise_forecasts(rows)
        assert len(records) == 3
        assert report.duplicates_collapsed == 0
        assert {r.generation for r in records} == {100, 200, 300}

    def test_duplicate_vintage_and_target_is_collapsed(self):
        rows = [forecast_row(generation=100), forecast_row(generation=100)]
        records, report = normalise_forecasts(rows)
        assert len(records) == 1
        assert report.duplicates_collapsed == 1

    def test_off_grid_start_time_is_floored_to_the_hour(self):
        records, _ = normalise_forecasts([forecast_row(startTime="2026-01-05T00:17:00Z")])
        assert records[0].start_time == parse_timestamp("2026-01-05T00:00:00Z")

    def test_flooring_collapses_rather_than_duplicating_a_target(self):
        rows = [
            forecast_row(startTime="2026-01-05T00:00:00Z", generation=10),
            forecast_row(startTime="2026-01-05T00:17:00Z", generation=11),
        ]
        records, report = normalise_forecasts(rows)
        assert len(records) == 1
        assert report.duplicates_collapsed == 1

    @pytest.mark.parametrize("missing", ["publishTime", "startTime", "generation"])
    def test_rows_missing_a_required_field_are_dropped(self, missing):
        row = forecast_row()
        del row[missing]
        records, report = normalise_forecasts([row])
        assert records == []
        assert report.dropped_malformed == 1

    def test_real_fixture_has_no_duplicates_or_losses(self, windfor_rows):
        records, report = normalise_forecasts(windfor_rows)
        assert len(records) == len(windfor_rows)
        assert report.dropped_malformed == 0
        assert report.duplicates_collapsed == 0

    def test_timestamps_are_utc_aware(self, windfor_rows):
        records, _ = normalise_forecasts(windfor_rows[:20])
        assert all(r.start_time.tzinfo == dt.UTC for r in records)
        assert all(r.publish_time.tzinfo == dt.UTC for r in records)
