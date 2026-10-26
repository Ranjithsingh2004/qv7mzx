"""Timezone-aware time handling for GB settlement data.

Conventions used throughout the application:

* Every ``datetime`` crossing a module boundary is timezone-aware and in UTC.
  Naive datetimes are rejected rather than silently assumed to be UTC.
* "Delivery day" means a calendar day in ``Europe/London``, because that is the
  day a GB settlement date refers to and the day a trader thinks in. A London
  day is 23, 24 or 25 hours long across daylight-saving transitions, so day
  boundaries are always computed in London and then converted to UTC.
* Elexon publishes ISO-8601 timestamps with a ``Z`` suffix (UTC).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

UTC = dt.UTC
LONDON = ZoneInfo("Europe/London")

#: GB settlement periods are half-hourly.
SETTLEMENT_PERIOD_MINUTES = 30


def parse_timestamp(value: str) -> dt.datetime:
    """Parse an Elexon ISO-8601 timestamp into an aware UTC datetime.

    Accepts a trailing ``Z`` (which :func:`datetime.fromisoformat` only learned
    to handle in Python 3.11) and any explicit offset. A timestamp with no
    offset is treated as UTC, which is what the Elexon payloads use; this is
    recorded here rather than scattered through the parsers.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"not a timestamp: {value!r}")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"not an ISO-8601 timestamp (expected e.g. 2026-01-15T18:00:00Z): {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def ensure_utc(value: dt.datetime) -> dt.datetime:
    """Return ``value`` as UTC, rejecting naive datetimes."""
    if value.tzinfo is None:
        raise ValueError("naive datetime: timezone must be explicit")
    return value.astimezone(UTC)


def parse_date(value: str) -> dt.date:
    """Parse a ``yyyy-MM-dd`` date, the format Elexon requires."""
    try:
        return dt.date.fromisoformat(value.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"not a yyyy-MM-dd date: {value!r}") from exc


def london_date(moment: dt.datetime) -> dt.date:
    """The ``Europe/London`` calendar date that ``moment`` falls on."""
    return ensure_utc(moment).astimezone(LONDON).date()


def london_day_start(day: dt.date) -> dt.datetime:
    """Midnight at the start of a London day, as UTC.

    ``fold=0`` resolves the ambiguous hour that would occur if a transition
    ever landed on midnight, picking the first occurrence.
    """
    naive = dt.datetime.combine(day, dt.time(0, 0), tzinfo=LONDON)
    return naive.replace(fold=0).astimezone(UTC)


def london_time_on(day: dt.date, time_of_day: dt.time) -> dt.datetime:
    """A wall-clock London time on a London date, as UTC.

    During the spring-forward gap the requested wall-clock time does not exist;
    ``zoneinfo`` maps it forward, which is the behaviour we want for a cutoff
    (the deadline effectively lands at the next real instant).
    """
    return dt.datetime.combine(day, time_of_day, tzinfo=LONDON).astimezone(UTC)


def parse_time_of_day(value: str) -> dt.time:
    """Parse ``HH:MM`` (or ``HH:MM:SS``) into a :class:`datetime.time`."""
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        raise ValueError(f"not an HH:MM time: {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    second = int(parts[2]) if len(parts) == 3 else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError(f"time out of range: {value!r}")
    return dt.time(hour, minute, second)


def hour_floor(moment: dt.datetime) -> dt.datetime:
    """Truncate a UTC instant to the start of its UTC hour."""
    return ensure_utc(moment).replace(minute=0, second=0, microsecond=0)


def hours_between(start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    """Every whole UTC hour in the half-open interval ``[start, end)``.

    Both bounds must already be on an hour boundary. Iterating in UTC and
    bounding in London is what makes 23- and 25-hour days come out right.
    """
    start, end = ensure_utc(start), ensure_utc(end)
    out: list[dt.datetime] = []
    cursor = start
    while cursor < end:
        out.append(cursor)
        cursor += dt.timedelta(hours=1)
    return out


def london_days_between(first: dt.date, last: dt.date) -> list[dt.date]:
    """Inclusive list of London dates from ``first`` to ``last``."""
    if last < first:
        return []
    return [first + dt.timedelta(days=offset) for offset in range((last - first).days + 1)]


def settlement_periods_in_day(day: dt.date) -> int:
    """How many half-hourly settlement periods a London day contains.

    48 on a normal day, 46 when the clocks go forward, 50 when they go back.
    """
    span = london_day_start(day + dt.timedelta(days=1)) - london_day_start(day)
    return int(span.total_seconds() // (SETTLEMENT_PERIOD_MINUTES * 60))


def to_iso(moment: dt.datetime) -> str:
    """Render a UTC instant as ``...Z``, the form Elexon and our API use."""
    return ensure_utc(moment).strftime("%Y-%m-%dT%H:%M:%SZ")
