"""Decision cutoffs and forecast-vintage selection.

The behaviour these tests pin down is the product's central correctness claim:
a forecast is only usable if it existed before the decision was made.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.analysis.timeutils import parse_timestamp
from app.analysis.vintage import CutoffPolicy, ForecastVintageIndex
from app.elexon.normalise import ForecastRecord, normalise_forecasts


def record(publish: str, target: str, generation: float) -> ForecastRecord:
    return ForecastRecord(
        start_time=parse_timestamp(target),
        publish_time=parse_timestamp(publish),
        generation=generation,
    )


TARGET = "2026-01-05T18:00:00Z"


@pytest.fixture
def index() -> ForecastVintageIndex:
    """Four vintages for one target, published across two days."""
    return ForecastVintageIndex(
        [
            record("2026-01-03T22:30:00Z", TARGET, 7000),
            record("2026-01-04T07:30:00Z", TARGET, 8000),  # last before 09:00 D-1
            record("2026-01-04T09:30:00Z", TARGET, 9000),  # after cutoff
            record("2026-01-05T15:30:00Z", TARGET, 9500),  # same-day, far too late
        ]
    )


class TestCutoffPolicy:
    def test_day_ahead_cutoff_lands_on_the_previous_day(self):
        policy = CutoffPolicy(dt.time(9, 0), days_before=1)
        assert policy.for_delivery_day(dt.date(2026, 1, 15)) == parse_timestamp(
            "2026-01-14T09:00:00Z"
        )

    def test_cutoff_follows_london_wall_clock_through_bst(self):
        policy = CutoffPolicy(dt.time(9, 0), days_before=1)
        # 09:00 London is 08:00 UTC during BST: the deadline is a local time.
        assert policy.for_delivery_day(dt.date(2026, 7, 15)) == parse_timestamp(
            "2026-07-14T08:00:00Z"
        )

    def test_days_before_zero_means_same_day(self):
        policy = CutoffPolicy(dt.time(12, 0), days_before=0)
        assert policy.for_delivery_day(dt.date(2026, 1, 15)) == parse_timestamp(
            "2026-01-15T12:00:00Z"
        )

    def test_for_target_uses_the_london_delivery_date(self):
        policy = CutoffPolicy(dt.time(9, 0), days_before=1)
        # 23:30 UTC on 14 July is already 15 July in London, so the cutoff is
        # the one for the 15th, not the 14th.
        target = parse_timestamp("2026-07-14T23:30:00Z")
        assert policy.for_target(target) == parse_timestamp("2026-07-14T08:00:00Z")

    def test_describe_is_human_readable(self):
        assert CutoffPolicy(dt.time(9, 0), 1).describe() == "09:00 Europe/London on D-1"
        assert "the delivery day" in CutoffPolicy(dt.time(9, 0), 0).describe()


class TestVintageSelection:
    def test_selects_the_most_recent_eligible_vintage(self, index):
        selected = index.select(parse_timestamp(TARGET), parse_timestamp("2026-01-04T09:00:00Z"))
        assert selected is not None
        assert selected.generation == 8000
        assert selected.publish_time == parse_timestamp("2026-01-04T07:30:00Z")

    def test_never_uses_a_forecast_published_after_the_cutoff(self, index):
        """The specific failure this module exists to prevent."""
        selected = index.select(parse_timestamp(TARGET), parse_timestamp("2026-01-04T09:00:00Z"))
        assert selected.generation not in (9000, 9500)
        assert selected.publish_time <= parse_timestamp("2026-01-04T09:00:00Z")

    def test_cutoff_is_inclusive_of_a_forecast_published_exactly_on_it(self, index):
        # A forecast published at the deadline was available to the decision.
        selected = index.select(parse_timestamp(TARGET), parse_timestamp("2026-01-04T09:30:00Z"))
        assert selected.generation == 9000

    def test_returns_none_when_every_vintage_is_too_late(self, index):
        selected = index.select(parse_timestamp(TARGET), parse_timestamp("2026-01-01T00:00:00Z"))
        assert selected is None

    def test_vintages_available_distinguishes_late_from_absent(self, index):
        target = parse_timestamp(TARGET)
        # Vintages exist, they were simply all published too late...
        assert index.select(target, parse_timestamp("2026-01-01T00:00:00Z")) is None
        assert index.vintages_available(target) == 4
        # ...whereas this target has none at all.
        assert index.vintages_available(parse_timestamp("2026-02-02T00:00:00Z")) == 0

    def test_unknown_target_returns_none(self, index):
        assert (
            index.select(
                parse_timestamp("2026-02-02T00:00:00Z"), parse_timestamp("2026-02-01T09:00:00Z")
            )
            is None
        )

    def test_horizon_is_measured_from_publication_to_target(self, index):
        selected = index.select(parse_timestamp(TARGET), parse_timestamp("2026-01-04T09:00:00Z"))
        # 2026-01-04T07:30Z -> 2026-01-05T18:00Z is 34.5 hours.
        assert selected.horizon_hours == pytest.approx(34.5)

    def test_counts_report_available_and_eligible(self, index):
        selected = index.select(parse_timestamp(TARGET), parse_timestamp("2026-01-04T09:00:00Z"))
        assert selected.vintages_available == 4
        assert selected.vintages_eligible == 2

    def test_input_order_does_not_affect_selection(self):
        rows = [
            record("2026-01-04T07:30:00Z", TARGET, 8000),
            record("2026-01-03T22:30:00Z", TARGET, 7000),
        ]
        for ordered in (rows, list(reversed(rows))):
            selected = ForecastVintageIndex(ordered).select(
                parse_timestamp(TARGET), parse_timestamp("2026-01-04T09:00:00Z")
            )
            assert selected.generation == 8000

    def test_naive_cutoff_is_rejected(self):
        index = ForecastVintageIndex([record("2026-01-04T07:30:00Z", TARGET, 8000)])
        with pytest.raises(ValueError, match="naive"):
            index.select(parse_timestamp(TARGET), dt.datetime(2026, 1, 4, 9, 0))


class TestVintageInspector:
    def test_flags_eligibility_and_the_single_selection(self, index):
        rows = index.vintages_for(parse_timestamp(TARGET), parse_timestamp("2026-01-04T09:00:00Z"))
        assert len(rows) == 4
        assert [r["eligible"] for r in rows] == [True, True, False, False]
        assert sum(1 for r in rows if r["selected"]) == 1
        assert next(r for r in rows if r["selected"])["generation"] == 8000

    def test_rows_are_ordered_by_publication_time(self, index):
        rows = index.vintages_for(parse_timestamp(TARGET), parse_timestamp("2026-01-04T09:00:00Z"))
        times = [r["publish_time"] for r in rows]
        assert times == sorted(times)

    def test_nothing_is_selected_when_nothing_is_eligible(self, index):
        rows = index.vintages_for(parse_timestamp(TARGET), parse_timestamp("2026-01-01T00:00:00Z"))
        assert rows and not any(r["selected"] for r in rows)
        assert not any(r["eligible"] for r in rows)

    def test_unknown_target_gives_no_rows(self, index):
        assert (
            index.vintages_for(
                parse_timestamp("2026-02-02T00:00:00Z"), parse_timestamp("2026-02-01T09:00:00Z")
            )
            == []
        )


class TestAgainstRealVintages:
    def test_real_feed_selects_the_expected_day_ahead_vintage(self, windfor_rows):
        """With a 09:00 D-1 cutoff the 07:30 D-1 publication is the live one.

        WINDFOR publishes at 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30
        and 22:30 UTC, so 07:30 on D-1 is the last before a 09:00 deadline.
        """
        forecasts, _ = normalise_forecasts(windfor_rows)
        index = ForecastVintageIndex(forecasts)
        policy = CutoffPolicy(dt.time(9, 0), days_before=1)
        target = parse_timestamp("2026-01-03T12:00:00Z")
        selected = index.select(target, policy.for_target(target))
        assert selected is not None
        assert selected.publish_time == parse_timestamp("2026-01-02T07:30:00Z")

    def test_irregular_publication_times_are_handled_by_time_not_slot(self):
        """The real feed contains off-schedule publications.

        One vintage in January 2026 was published at 12:25Z rather than on the
        usual half-hour cadence, so selection must compare instants and not
        assume a fixed set of publication slots.
        """
        index = ForecastVintageIndex(
            [
                record("2026-01-15T11:30:00Z", "2026-01-15T18:00:00Z", 8000),
                record("2026-01-15T12:25:00Z", "2026-01-15T18:00:00Z", 9053),
            ]
        )
        selected = index.select(
            parse_timestamp("2026-01-15T18:00:00Z"), parse_timestamp("2026-01-15T13:00:00Z")
        )
        assert selected.generation == 9053
