"""Aligning half-hourly actuals onto the hourly forecast grid.

The two datasets do not share a time resolution, which is the first real
modelling decision in this product:

* ``FUELHH`` wind outturn is half-hourly -- 48 settlement periods a day, each
  an average MW over 30 minutes.
* ``WINDFOR`` forecasts are hourly, published on the hour.

Comparison therefore happens on the hourly grid, and the half-hourly actuals
are reduced onto it. Two reductions are offered because the choice is a
judgement rather than a fact, and a reviewer should be able to see that the
headline numbers do not hinge on it:

``hourly_mean`` (default)
    Average the settlement periods falling inside the hour. Uses every actual
    observation and is the natural like-for-like against an hourly average.

``period_start``
    Take only the settlement period beginning exactly on the hour. Discards
    half the actuals but involves no aggregation at all.

Neither reduction invents data: an hour with no actual at all stays unmatched,
and an hour backed by fewer periods than the grid expects is reported as
partial rather than quietly averaged as if complete.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from ..elexon.normalise import ActualRecord
from .timeutils import ensure_utc, hour_floor

AlignmentMode = Literal["hourly_mean", "period_start"]

ALIGNMENT_MODES: dict[AlignmentMode, str] = {
    "hourly_mean": "Mean of the half-hourly settlement periods inside each hour",
    "period_start": "Only the settlement period starting exactly on the hour",
}

#: Half-hourly data gives two settlement periods per clock hour.
PERIODS_PER_HOUR = 2


@dataclass(frozen=True, slots=True)
class AlignedActual:
    """Wind outturn for one target hour, with its provenance."""

    generation: float
    #: Settlement periods that contributed, for audit and partial-data display.
    contributing_periods: tuple[int, ...]
    settlement_date: str | None
    #: True when fewer periods contributed than the hour should contain.
    partial: bool


class ActualHourlyIndex:
    """Half-hourly actuals reduced onto the hourly grid."""

    def __init__(
        self, records: Iterable[ActualRecord], *, mode: AlignmentMode = "hourly_mean"
    ) -> None:
        if mode not in ALIGNMENT_MODES:
            raise ValueError(f"unknown alignment mode: {mode!r}")
        self._mode: AlignmentMode = mode
        self._buckets: dict[dt.datetime, list[ActualRecord]] = {}
        for record in records:
            self._buckets.setdefault(hour_floor(record.start_time), []).append(record)
        for bucket in self._buckets.values():
            bucket.sort(key=lambda record: record.start_time)

    @property
    def mode(self) -> AlignmentMode:
        return self._mode

    @property
    def half_hourly_count(self) -> int:
        return sum(len(bucket) for bucket in self._buckets.values())

    @property
    def hours_covered(self) -> int:
        return len(self._buckets)

    def get(self, target_hour: dt.datetime) -> AlignedActual | None:
        """Reduced actual for a target hour, or ``None`` if there is no data."""
        bucket = self._buckets.get(ensure_utc(target_hour))
        if not bucket:
            return None

        if self._mode == "period_start":
            exact = [r for r in bucket if r.start_time == ensure_utc(target_hour)]
            if not exact:
                return None
            record = exact[0]
            return AlignedActual(
                generation=record.generation,
                contributing_periods=_periods(exact),
                settlement_date=record.settlement_date,
                partial=False,
            )

        total = sum(record.generation for record in bucket)
        return AlignedActual(
            generation=total / len(bucket),
            contributing_periods=_periods(bucket),
            settlement_date=bucket[0].settlement_date,
            partial=len(bucket) < PERIODS_PER_HOUR,
        )


def _periods(records: list[ActualRecord]) -> tuple[int, ...]:
    return tuple(r.settlement_period for r in records if r.settlement_period is not None)
