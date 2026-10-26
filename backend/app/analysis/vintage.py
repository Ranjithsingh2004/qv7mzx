"""Decision cutoffs and forecast-vintage selection.

This is the heart of the product's correctness claim. A forecast may only be
used to judge a purchase decision if it existed when the decision was made.
Comparing an outturn against the *latest* forecast available today would
flatter the forecaster and mislead the desk, so every comparison here is
anchored to a publication time that preceded an explicit cutoff.
"""

from __future__ import annotations

import datetime as dt
from bisect import bisect_right
from dataclasses import dataclass

from .timeutils import ensure_utc, london_date, london_time_on


@dataclass(frozen=True, slots=True)
class CutoffPolicy:
    """When the desk is assumed to stop taking new information.

    ``time_of_day`` is a wall-clock time in ``Europe/London``; ``days_before``
    is how many London days before the delivery day it falls on. The default
    used by the product -- 09:00 London on D-1 -- is a documented assumption,
    chosen to sit ahead of GB day-ahead auction gate closure. It is not a
    market rule, and it is configurable.
    """

    time_of_day: dt.time
    days_before: int = 1
    timezone_name: str = "Europe/London"

    def for_delivery_day(self, day: dt.date) -> dt.datetime:
        """The cutoff instant (UTC) that applies to a delivery day."""
        return london_time_on(day - dt.timedelta(days=self.days_before), self.time_of_day)

    def for_target(self, target: dt.datetime) -> dt.datetime:
        """The cutoff instant (UTC) that applies to a target half-hour/hour."""
        return self.for_delivery_day(london_date(target))

    def describe(self) -> str:
        label = "the delivery day" if self.days_before == 0 else f"D-{self.days_before}"
        return f"{self.time_of_day.strftime('%H:%M')} {self.timezone_name} on {label}"


@dataclass(frozen=True, slots=True)
class SelectedForecast:
    """The forecast vintage chosen for one target period."""

    generation: float
    publish_time: dt.datetime
    #: Hours between publication and the target period.
    horizon_hours: float
    #: How many vintages existed for this target, and how many were eligible.
    vintages_available: int
    vintages_eligible: int


class ForecastVintageIndex:
    """Forecast values indexed by target period, ordered by publication time.

    Built once per analysis. Lookups are a binary search over the publication
    times for a target, so selecting across a month of hourly targets and
    several candidate cutoffs stays cheap.
    """

    def __init__(self, records) -> None:
        grouped: dict[dt.datetime, list[tuple[dt.datetime, float]]] = {}
        for record in records:
            grouped.setdefault(record.start_time, []).append(
                (record.publish_time, record.generation)
            )
        # Sorted publication times per target let us binary-search the cutoff.
        self._by_target: dict[dt.datetime, tuple[list[dt.datetime], list[float]]] = {}
        for target, pairs in grouped.items():
            pairs.sort(key=lambda pair: pair[0])
            self._by_target[target] = (
                [pair[0] for pair in pairs],
                [pair[1] for pair in pairs],
            )

    @property
    def targets(self) -> list[dt.datetime]:
        return sorted(self._by_target)

    def vintage_count(self) -> int:
        """Number of distinct publication times across all targets."""
        seen: set[dt.datetime] = set()
        for published, _ in self._by_target.values():
            seen.update(published)
        return len(seen)

    def vintages_available(self, target: dt.datetime) -> int:
        """How many vintages exist for a target, regardless of eligibility."""
        entry = self._by_target.get(ensure_utc(target))
        return 0 if entry is None else len(entry[0])

    def select(self, target: dt.datetime, cutoff: dt.datetime) -> SelectedForecast | None:
        """Most recent forecast for ``target`` published at or before ``cutoff``.

        The cutoff is inclusive: a forecast published exactly at the deadline
        was available to the decision.

        Returns ``None`` when the target is unknown or every vintage for it was
        published too late. The caller records that as an unmatched period --
        never as a substitution with a later forecast, which is the specific
        error this module exists to prevent. Use :meth:`vintages_available` to
        tell "no forecast at all" from "forecast existed but came too late".
        """
        entry = self._by_target.get(ensure_utc(target))
        if entry is None:
            return None
        published, values = entry
        eligible_count = bisect_right(published, ensure_utc(cutoff))
        if eligible_count == 0:
            return None
        chosen = eligible_count - 1
        return SelectedForecast(
            generation=values[chosen],
            publish_time=published[chosen],
            horizon_hours=(target - published[chosen]).total_seconds() / 3600.0,
            vintages_available=len(published),
            vintages_eligible=eligible_count,
        )

    def vintages_for(self, target: dt.datetime, cutoff: dt.datetime) -> list[dict]:
        """Every vintage for one target, flagged against a cutoff.

        Powers the UI's vintage inspector, which is how a reviewer can see the
        selection rule applied to a single hour.
        """
        entry = self._by_target.get(ensure_utc(target))
        if entry is None:
            return []
        published, values = entry
        cutoff = ensure_utc(cutoff)
        eligible_times = [p for p in published if p <= cutoff]
        latest_eligible = max(eligible_times) if eligible_times else None
        return [
            {
                "publish_time": publish_time,
                "generation": value,
                "horizon_hours": (target - publish_time).total_seconds() / 3600.0,
                "eligible": publish_time <= cutoff,
                "selected": publish_time == latest_eligible,
            }
            for publish_time, value in zip(published, values, strict=False)
        ]
