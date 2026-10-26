"""End-to-end analysis over fixtures: matching, coverage and gap handling."""

from __future__ import annotations

import datetime as dt
from itertools import pairwise

import pytest

from app.analysis.pipeline import (
    STATUS_MATCHED,
    STATUS_NO_ACTUAL,
    STATUS_NO_ELIGIBLE_FORECAST,
    STATUS_NO_FORECAST_PUBLISHED,
    build_analysis,
    delivery_window,
)
from app.analysis.timeutils import parse_timestamp
from app.analysis.vintage import CutoffPolicy
from app.elexon.normalise import (
    ActualRecord,
    ForecastRecord,
    normalise_actuals,
    normalise_forecasts,
)

DAY_AHEAD = CutoffPolicy(dt.time(9, 0), days_before=1)


@pytest.fixture
def real(fuelhh_rows, windfor_rows):
    actuals, actual_report = normalise_actuals(fuelhh_rows)
    forecasts, forecast_report = normalise_forecasts(windfor_rows)
    return actuals, forecasts, actual_report, forecast_report


def analyse(actuals, forecasts, **kwargs):
    params = {
        "actuals": actuals,
        "forecasts": forecasts,
        "decision_from": dt.date(2026, 1, 1),
        "decision_to": dt.date(2026, 1, 2),
        "cutoff": DAY_AHEAD,
    }
    params.update(kwargs)
    return build_analysis(**params)


class TestDeliveryWindow:
    def test_a_decision_day_serves_the_next_delivery_day(self):
        assert delivery_window(dt.date(2026, 1, 1), dt.date(2026, 1, 31), DAY_AHEAD) == (
            dt.date(2026, 1, 2),
            dt.date(2026, 2, 1),
        )

    def test_same_day_cutoff_leaves_the_window_unshifted(self):
        policy = CutoffPolicy(dt.time(9, 0), days_before=0)
        assert delivery_window(dt.date(2026, 1, 1), dt.date(2026, 1, 2), policy) == (
            dt.date(2026, 1, 1),
            dt.date(2026, 1, 2),
        )

    def test_reversed_window_is_rejected(self):
        with pytest.raises(ValueError, match="decision_to"):
            build_analysis(
                actuals=[],
                forecasts=[],
                decision_from=dt.date(2026, 1, 10),
                decision_to=dt.date(2026, 1, 1),
                cutoff=DAY_AHEAD,
            )

    def test_unknown_alignment_mode_is_rejected(self):
        with pytest.raises(ValueError, match="alignment mode"):
            build_analysis(
                actuals=[],
                forecasts=[],
                decision_from=dt.date(2026, 1, 1),
                decision_to=dt.date(2026, 1, 1),
                cutoff=DAY_AHEAD,
                alignment_mode="median",  # type: ignore[arg-type]
            )


class TestRealDataAnalysis:
    def test_two_delivery_days_are_fully_matched(self, real):
        actuals, forecasts, *_ = real
        result = analyse(actuals, forecasts)
        assert result.delivery_from == dt.date(2026, 1, 2)
        assert result.delivery_to == dt.date(2026, 1, 3)
        assert result.coverage.expected_hours == 48
        assert result.coverage.matched_hours == 48
        assert result.coverage.matched_percent == 100.0
        assert all(r.status == STATUS_MATCHED for r in result.records)

    def test_every_record_uses_a_forecast_published_before_its_cutoff(self, real):
        """The invariant that makes the whole analysis defensible."""
        actuals, forecasts, *_ = real
        for record in analyse(actuals, forecasts).records:
            assert record.forecast_publish_time is not None
            assert record.forecast_publish_time <= record.decision_cutoff

    def test_horizons_are_day_ahead_not_intraday(self, real):
        actuals, forecasts, *_ = real
        horizons = [r.horizon_hours for r in analyse(actuals, forecasts).records]
        # A 09:00 D-1 deadline cannot see anything closer than ~15 hours out.
        assert min(horizons) > 15
        assert max(horizons) < 48

    def test_settlement_periods_are_recorded_for_audit(self, real):
        actuals, forecasts, *_ = real
        result = analyse(actuals, forecasts)
        assert result.coverage.expected_settlement_periods == 96
        assert result.coverage.actual_settlement_periods == 96
        assert all(len(r.settlement_periods) == 2 for r in result.records)

    def test_metrics_are_computed_over_matched_hours_only(self, real):
        actuals, forecasts, *_ = real
        result = analyse(actuals, forecasts)
        assert result.metrics.matched_hours == result.coverage.matched_hours
        assert result.metrics.mae_mw is not None

    def test_summaries_are_shaped_as_the_ui_expects(self, real):
        actuals, forecasts, *_ = real
        result = analyse(actuals, forecasts)
        assert [row["delivery_date"] for row in result.daily] == [
            dt.date(2026, 1, 2),
            dt.date(2026, 1, 3),
        ]
        assert all(row["hours"] == 24 for row in result.daily)
        assert len(result.by_hour_of_day) == 24
        assert result.by_horizon and all(
            bucket["horizon_to_hours"] > bucket["horizon_from_hours"]
            for bucket in result.by_horizon
        )

    def test_alignment_mode_is_reported_and_changes_the_actual(self, real):
        actuals, forecasts, *_ = real
        mean_result = analyse(actuals, forecasts, alignment_mode="hourly_mean")
        start_result = analyse(actuals, forecasts, alignment_mode="period_start")
        assert start_result.alignment_mode == "period_start"
        assert all(len(r.settlement_periods) == 1 for r in start_result.records)
        # Same hours, same count; only the reduction differs.
        assert mean_result.coverage.matched_hours == start_result.coverage.matched_hours

    def test_data_quality_counts_are_passed_through(self, real):
        actuals, forecasts, actual_report, forecast_report = real
        result = analyse(
            actuals,
            forecasts,
            actual_report=actual_report,
            forecast_report=forecast_report,
        )
        assert result.data_quality["actuals"]["rows_accepted"] == len(actuals)
        assert result.data_quality["forecasts"]["rows_accepted"] == len(forecasts)


class TestMissingData:
    def test_a_missing_actual_is_unmatched_not_zero(self, real):
        actuals, forecasts, *_ = real
        dropped = parse_timestamp("2026-01-02T12:00:00Z")
        thinned = [
            a for a in actuals if a.start_time not in (dropped, dropped + dt.timedelta(minutes=30))
        ]
        result = analyse(thinned, forecasts)
        record = next(r for r in result.records if r.target_start == dropped)
        assert record.status == STATUS_NO_ACTUAL
        assert record.actual_mw is None
        assert record.error_mw is None
        assert result.coverage.matched_hours == 47
        assert result.coverage.hours_missing_actual == 1
        assert result.metrics.matched_hours == 47

    def test_one_missing_half_hour_leaves_a_partial_hour(self, real):
        actuals, forecasts, *_ = real
        dropped = parse_timestamp("2026-01-02T12:30:00Z")
        thinned = [a for a in actuals if a.start_time != dropped]
        result = analyse(thinned, forecasts)
        record = next(
            r for r in result.records if r.target_start == parse_timestamp("2026-01-02T12:00:00Z")
        )
        # Still matched, but visibly backed by one period rather than two.
        assert record.status == STATUS_MATCHED
        assert record.actual_partial is True
        assert result.coverage.hours_partial_actual == 1
        assert result.coverage.actual_settlement_periods == 95

    def test_forecasts_published_only_after_the_cutoff_are_unusable(self):
        """Distinguished from "no forecast at all", because the fix differs."""
        target = parse_timestamp("2026-01-02T12:00:00Z")
        result = build_analysis(
            actuals=[
                ActualRecord(start_time=target, generation=9000, settlement_period=25),
                ActualRecord(
                    start_time=target + dt.timedelta(minutes=30),
                    generation=9100,
                    settlement_period=26,
                ),
            ],
            forecasts=[
                ForecastRecord(
                    start_time=target,
                    publish_time=parse_timestamp("2026-01-02T10:00:00Z"),  # too late
                    generation=9500,
                )
            ],
            decision_from=dt.date(2026, 1, 1),
            decision_to=dt.date(2026, 1, 1),
            cutoff=DAY_AHEAD,
        )
        record = next(r for r in result.records if r.target_start == target)
        assert record.status == STATUS_NO_ELIGIBLE_FORECAST
        assert record.forecast_mw is None
        assert record.vintages_available == 1
        assert record.vintages_eligible == 0
        assert result.metrics.matched_hours == 0
        assert result.metrics.mae_mw is None

    def test_no_forecast_published_is_its_own_status(self):
        result = build_analysis(
            actuals=[],
            forecasts=[],
            decision_from=dt.date(2026, 1, 1),
            decision_to=dt.date(2026, 1, 1),
            cutoff=DAY_AHEAD,
        )
        assert result.coverage.expected_hours == 24
        assert all(r.status == STATUS_NO_FORECAST_PUBLISHED for r in result.records)
        assert result.coverage.hours_missing_forecast == 24
        assert result.metrics.matched_hours == 0


class TestDaylightSaving:
    @pytest.mark.parametrize(
        "decision_day,expected_hours,expected_periods",
        [
            (dt.date(2026, 3, 28), 23, 46),  # delivery 29 March: clocks forward
            (dt.date(2026, 10, 24), 25, 50),  # delivery 25 October: clocks back
        ],
    )
    def test_transition_days_get_the_right_number_of_hours(
        self, decision_day, expected_hours, expected_periods
    ):
        """A 23- or 25-hour delivery day must not be padded to 24."""
        result = build_analysis(
            actuals=[],
            forecasts=[],
            decision_from=decision_day,
            decision_to=decision_day,
            cutoff=DAY_AHEAD,
        )
        assert result.coverage.expected_hours == expected_hours
        assert result.coverage.expected_settlement_periods == expected_periods

    def test_hours_are_contiguous_across_a_transition(self):
        result = build_analysis(
            actuals=[],
            forecasts=[],
            decision_from=dt.date(2026, 10, 24),
            decision_to=dt.date(2026, 10, 24),
            cutoff=DAY_AHEAD,
        )
        starts = [r.target_start for r in result.records]
        assert starts == sorted(starts)
        gaps = {(b - a).total_seconds() for a, b in pairwise(starts)}
        assert gaps == {3600.0}
