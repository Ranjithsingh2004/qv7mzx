"""Turn raw Elexon payloads into validated domain records.

Kept deliberately free of HTTP and of FastAPI so it can be unit-tested against
fixtures, and so the quirks of the upstream feed are handled in exactly one
place. Both datasets are normalised defensively: a single malformed row is
dropped and counted rather than failing the whole analysis.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..analysis.timeutils import hour_floor, parse_timestamp

#: FUELHH reports every fuel category; only wind is in scope for this product.
WIND_FUEL_TYPE = "WIND"


@dataclass(frozen=True, slots=True)
class ActualRecord:
    """One half-hourly wind generation outturn (FUELHH, ``fuelType=WIND``).

    ``generation`` is the average MW over the settlement period, as documented
    by Elexon for FUELHH.
    """

    start_time: dt.datetime
    generation: float
    settlement_date: str | None = None
    settlement_period: int | None = None
    publish_time: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    """One hourly wind generation forecast value from one WINDFOR vintage.

    ``publish_time`` identifies the vintage: the instant the forecast became
    available, which is what makes it eligible (or not) for a given decision.
    """

    start_time: dt.datetime
    publish_time: dt.datetime
    generation: float


@dataclass
class NormaliseReport:
    """Counts of what normalisation accepted, dropped and de-duplicated."""

    received: int = 0
    accepted: int = 0
    dropped_malformed: int = 0
    dropped_wrong_fuel: int = 0
    duplicates_collapsed: int = 0
    issues: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        # Bounded so a systematically broken feed cannot grow the response.
        if len(self.issues) < 10:
            self.issues.append(message)


def _coerce_generation(value: object) -> float:
    """Validate a generation value in MW.

    Rejects ``None``, booleans, non-numerics and non-finite values. Negative
    values are kept: wind farms can legitimately net-consume a little.
    """
    if value is None or isinstance(value, bool):
        raise ValueError("generation missing")
    number = float(value)  # raises TypeError/ValueError for junk
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("generation not finite")
    return number


def normalise_actuals(
    rows: list[dict],
    *,
    report: NormaliseReport | None = None,
) -> tuple[list[ActualRecord], NormaliseReport]:
    """Normalise FUELHH rows, keeping only ``fuelType == WIND``.

    The WIND filter is applied here as well as in the upstream query, so the
    guarantee holds even if the request is built differently or the upstream
    ignores the parameter.

    Where the same settlement period appears more than once (a revision), the
    row with the later ``publishTime`` wins; that is the current value.
    """
    report = report or NormaliseReport()
    best: dict[dt.datetime, ActualRecord] = {}

    for row in rows:
        report.received += 1
        if not isinstance(row, dict):
            report.dropped_malformed += 1
            report.note("row is not an object")
            continue

        fuel = row.get("fuelType")
        if isinstance(fuel, str) and fuel.strip().upper() != WIND_FUEL_TYPE:
            report.dropped_wrong_fuel += 1
            continue
        if fuel is None:
            report.dropped_wrong_fuel += 1
            report.note("row has no fuelType")
            continue

        try:
            start = parse_timestamp(row["startTime"])
            generation = _coerce_generation(row.get("generation"))
        except (KeyError, TypeError, ValueError) as exc:
            report.dropped_malformed += 1
            report.note(f"unusable FUELHH row: {exc}")
            continue

        published = None
        if row.get("publishTime"):
            try:
                published = parse_timestamp(row["publishTime"])
            except (TypeError, ValueError):
                published = None  # non-fatal: only used to rank revisions

        period = row.get("settlementPeriod")
        record = ActualRecord(
            start_time=start,
            generation=generation,
            settlement_date=row.get("settlementDate"),
            settlement_period=int(period) if isinstance(period, int | float) else None,
            publish_time=published,
        )

        existing = best.get(start)
        if existing is None:
            best[start] = record
            continue

        report.duplicates_collapsed += 1
        if _is_newer(record.publish_time, existing.publish_time):
            best[start] = record

    report.accepted = len(best)
    return [best[key] for key in sorted(best)], report


def normalise_forecasts(
    rows: list[dict],
    *,
    report: NormaliseReport | None = None,
) -> tuple[list[ForecastRecord], NormaliseReport]:
    """Normalise WINDFOR rows.

    WINDFOR is published on an hourly target grid. ``startTime`` is floored to
    the hour so that a feed which ever emitted an off-grid minute still lands
    on the analysis grid, and the duplicate is collapsed rather than silently
    creating a second vintage entry.

    The key is ``(publishTime, startTime)``: one value per vintage per target
    hour. Vintages are *not* merged -- keeping them all is what allows the
    decision cutoff to pick a historically correct one.
    """
    report = report or NormaliseReport()
    best: dict[tuple[dt.datetime, dt.datetime], ForecastRecord] = {}

    for row in rows:
        report.received += 1
        if not isinstance(row, dict):
            report.dropped_malformed += 1
            report.note("row is not an object")
            continue
        try:
            start = hour_floor(parse_timestamp(row["startTime"]))
            published = parse_timestamp(row["publishTime"])
            generation = _coerce_generation(row.get("generation"))
        except (KeyError, TypeError, ValueError) as exc:
            report.dropped_malformed += 1
            report.note(f"unusable WINDFOR row: {exc}")
            continue

        key = (published, start)
        if key in best:
            report.duplicates_collapsed += 1
            continue  # identical vintage+target: first value kept
        best[key] = ForecastRecord(start_time=start, publish_time=published, generation=generation)

    report.accepted = len(best)
    return [best[key] for key in sorted(best)], report


def _is_newer(candidate: dt.datetime | None, incumbent: dt.datetime | None) -> bool:
    """Whether ``candidate`` is a later publication than ``incumbent``."""
    if candidate is None:
        return False
    if incumbent is None:
        return True
    return candidate > incumbent
