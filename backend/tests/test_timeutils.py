"""Timezone and daylight-saving behaviour."""

from __future__ import annotations

import datetime as dt

import pytest

from app.analysis.timeutils import (
    LONDON,
    ensure_utc,
    hour_floor,
    hours_between,
    london_date,
    london_day_start,
    london_time_on,
    parse_date,
    parse_time_of_day,
    parse_timestamp,
    settlement_periods_in_day,
    to_iso,
)


class TestParseTimestamp:
    def test_accepts_elexon_z_suffix(self):
        assert parse_timestamp("2026-01-05T11:30:00Z") == dt.datetime(
            2026, 1, 5, 11, 30, tzinfo=dt.UTC
        )

    def test_accepts_explicit_offset_and_converts_to_utc(self):
        # 10:30 at +01:00 is 09:30 UTC.
        assert parse_timestamp("2026-07-05T10:30:00+01:00") == dt.datetime(
            2026, 7, 5, 9, 30, tzinfo=dt.UTC
        )

    def test_naive_timestamp_is_treated_as_utc(self):
        assert parse_timestamp("2026-01-05T11:30:00").tzinfo == dt.UTC

    @pytest.mark.parametrize("bad", ["", "   ", "garbage", "2026-13-01T00:00:00Z", None, 17])
    def test_rejects_junk(self, bad):
        with pytest.raises(ValueError):
            parse_timestamp(bad)

    def test_error_message_shows_expected_form(self):
        with pytest.raises(ValueError, match="ISO-8601"):
            parse_timestamp("garbage")


class TestEnsureUtc:
    def test_rejects_naive_datetime(self):
        # Silently assuming UTC here is exactly how timezone bugs get in.
        with pytest.raises(ValueError, match="naive"):
            ensure_utc(dt.datetime(2026, 1, 1, 12, 0))

    def test_converts_aware_datetime(self):
        london_noon = dt.datetime(2026, 7, 1, 12, 0, tzinfo=LONDON)
        assert ensure_utc(london_noon).hour == 11  # BST is UTC+1


class TestLondonDays:
    def test_london_date_differs_from_utc_date_in_summer(self):
        # 23:30 UTC on 1 July is already 2 July in London.
        assert london_date(parse_timestamp("2026-07-01T23:30:00Z")) == dt.date(2026, 7, 2)

    def test_london_day_start_is_midnight_local(self):
        assert london_day_start(dt.date(2026, 1, 15)) == parse_timestamp("2026-01-15T00:00:00Z")
        assert london_day_start(dt.date(2026, 7, 15)) == parse_timestamp("2026-07-14T23:00:00Z")

    @pytest.mark.parametrize(
        "day,expected_periods",
        [
            (dt.date(2026, 1, 15), 48),  # ordinary day
            (dt.date(2026, 3, 29), 46),  # clocks forward: 23-hour day
            (dt.date(2026, 10, 25), 50),  # clocks back: 25-hour day
        ],
    )
    def test_settlement_periods_track_dst(self, day, expected_periods):
        assert settlement_periods_in_day(day) == expected_periods

    @pytest.mark.parametrize(
        "day,expected_hours",
        [(dt.date(2026, 1, 15), 24), (dt.date(2026, 3, 29), 23), (dt.date(2026, 10, 25), 25)],
    )
    def test_hour_grid_matches_london_day_length(self, day, expected_hours):
        hours = hours_between(london_day_start(day), london_day_start(day + dt.timedelta(days=1)))
        assert len(hours) == expected_hours
        assert all(h.tzinfo == dt.UTC for h in hours)

    def test_london_time_on_shifts_with_bst(self):
        # The same 09:00 wall clock is 09:00Z in winter and 08:00Z in summer.
        assert london_time_on(dt.date(2026, 1, 14), dt.time(9, 0)).hour == 9
        assert london_time_on(dt.date(2026, 7, 14), dt.time(9, 0)).hour == 8


class TestMisc:
    def test_hour_floor_truncates(self):
        assert hour_floor(parse_timestamp("2026-01-05T11:30:45Z")) == parse_timestamp(
            "2026-01-05T11:00:00Z"
        )

    def test_to_iso_round_trips(self):
        moment = parse_timestamp("2026-01-05T11:30:00Z")
        assert to_iso(moment) == "2026-01-05T11:30:00Z"
        assert parse_timestamp(to_iso(moment)) == moment

    @pytest.mark.parametrize("value,expected", [("09:00", (9, 0)), ("23:59:30", (23, 59))])
    def test_parse_time_of_day(self, value, expected):
        parsed = parse_time_of_day(value)
        assert (parsed.hour, parsed.minute) == expected

    @pytest.mark.parametrize("bad", ["", "9", "99:99", "aa:bb", "12:60", "-1:00"])
    def test_parse_time_of_day_rejects_junk(self, bad):
        with pytest.raises(ValueError):
            parse_time_of_day(bad)

    def test_parse_date_rejects_other_formats(self):
        # Elexon requires yyyy-MM-dd exactly.
        with pytest.raises(ValueError):
            parse_date("01/02/2026")
