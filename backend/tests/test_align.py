"""Reducing half-hourly actuals onto the hourly forecast grid."""

from __future__ import annotations

import pytest

from app.analysis.align import ActualHourlyIndex
from app.analysis.timeutils import parse_timestamp
from app.elexon.normalise import ActualRecord, normalise_actuals


def actual(target: str, generation: float, period: int | None = 1) -> ActualRecord:
    return ActualRecord(
        start_time=parse_timestamp(target),
        generation=generation,
        settlement_date=target[:10],
        settlement_period=period,
    )


HOUR = "2026-01-05T12:00:00Z"


class TestHourlyMean:
    def test_averages_the_two_settlement_periods_in_the_hour(self):
        index = ActualHourlyIndex(
            [actual(HOUR, 10000, 25), actual("2026-01-05T12:30:00Z", 11000, 26)]
        )
        aligned = index.get(parse_timestamp(HOUR))
        assert aligned.generation == 10500
        assert aligned.contributing_periods == (25, 26)
        assert aligned.partial is False

    def test_a_single_period_is_flagged_partial_not_averaged_as_complete(self):
        # Treating one period as a full hour would hide a coverage gap.
        index = ActualHourlyIndex([actual(HOUR, 10000, 25)])
        aligned = index.get(parse_timestamp(HOUR))
        assert aligned.generation == 10000
        assert aligned.partial is True
        assert aligned.contributing_periods == (25,)

    def test_missing_hour_returns_none_rather_than_zero(self):
        index = ActualHourlyIndex([actual(HOUR, 10000)])
        assert index.get(parse_timestamp("2026-01-05T13:00:00Z")) is None

    def test_periods_are_bucketed_into_their_own_hour(self):
        index = ActualHourlyIndex(
            [
                actual(HOUR, 10000, 25),
                actual("2026-01-05T12:30:00Z", 11000, 26),
                actual("2026-01-05T13:00:00Z", 12000, 27),
            ]
        )
        assert index.get(parse_timestamp(HOUR)).generation == 10500
        assert index.get(parse_timestamp("2026-01-05T13:00:00Z")).generation == 12000
        assert index.hours_covered == 2
        assert index.half_hourly_count == 3


class TestPeriodStart:
    def test_takes_only_the_period_beginning_on_the_hour(self):
        index = ActualHourlyIndex(
            [actual(HOUR, 10000, 25), actual("2026-01-05T12:30:00Z", 11000, 26)],
            mode="period_start",
        )
        aligned = index.get(parse_timestamp(HOUR))
        assert aligned.generation == 10000
        assert aligned.contributing_periods == (25,)

    def test_returns_none_when_only_the_half_past_period_exists(self):
        index = ActualHourlyIndex([actual("2026-01-05T12:30:00Z", 11000, 26)], mode="period_start")
        assert index.get(parse_timestamp(HOUR)) is None


class TestModeValidation:
    def test_unknown_mode_is_rejected(self):
        with pytest.raises(ValueError, match="alignment mode"):
            ActualHourlyIndex([], mode="median")  # type: ignore[arg-type]


class TestAgainstRealActuals:
    def test_every_hour_of_the_fixture_has_both_periods(self, fuelhh_rows):
        actuals, _ = normalise_actuals(fuelhh_rows)
        index = ActualHourlyIndex(actuals)
        assert index.half_hourly_count == len(actuals)
        assert index.hours_covered == len(actuals) // 2
        aligned = index.get(parse_timestamp("2026-01-02T00:00:00Z"))
        assert aligned is not None
        assert aligned.partial is False
        assert len(aligned.contributing_periods) == 2

    def test_the_two_modes_agree_to_within_intra_hour_variation(self, fuelhh_rows):
        """Both reductions should describe the same hour, not a different one."""
        actuals, _ = normalise_actuals(fuelhh_rows)
        mean_index = ActualHourlyIndex(actuals, mode="hourly_mean")
        start_index = ActualHourlyIndex(actuals, mode="period_start")
        hour = parse_timestamp("2026-01-02T12:00:00Z")
        mean_value = mean_index.get(hour).generation
        start_value = start_index.get(hour).generation
        assert abs(mean_value - start_value) < 0.1 * max(mean_value, 1)
