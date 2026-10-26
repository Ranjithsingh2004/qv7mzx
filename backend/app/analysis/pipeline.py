"""Orchestration: raw Elexon rows in, analysis result out.

Pure and synchronous -- all I/O happens in the service layer above. That keeps
the whole analysis reproducible from fixtures in tests, with no network.

The period is expressed the way the brief does: the days on which *purchase
decisions* are made. Delivery follows ``cutoff.days_before`` later, so a month
of January decisions delivers from 2 January to 1 February. Both windows are
returned, because conflating them is an easy and expensive mistake.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..elexon.normalise import ActualRecord, ForecastRecord, NormaliseReport
from .align import ALIGNMENT_MODES, ActualHourlyIndex, AlignmentMode
from .metrics import AccuracyMetrics, compute_metrics
from .timeutils import (
    hours_between,
    london_day_start,
    london_days_between,
    settlement_periods_in_day,
)
from .vintage import CutoffPolicy, ForecastVintageIndex

#: Why a target hour did not contribute to the metrics.
STATUS_MATCHED = "matched"
STATUS_NO_ELIGIBLE_FORECAST = "no_eligible_forecast"
STATUS_NO_FORECAST_PUBLISHED = "no_forecast_published"
STATUS_NO_ACTUAL = "no_actual"


@dataclass(frozen=True, slots=True)
class PeriodRecord:
    """One target hour: the forecast the desk had, and what actually happened."""

    target_start: dt.datetime
    delivery_date: dt.date
    decision_cutoff: dt.datetime
    status: str
    actual_mw: float | None = None
    actual_partial: bool = False
    settlement_periods: tuple[int, ...] = ()
    forecast_mw: float | None = None
    forecast_publish_time: dt.datetime | None = None
    horizon_hours: float | None = None
    vintages_available: int = 0
    vintages_eligible: int = 0

    @property
    def error_mw(self) -> float | None:
        """Forecast minus actual; positive means the forecast ran high."""
        if self.forecast_mw is None or self.actual_mw is None:
            return None
        return self.forecast_mw - self.actual_mw


@dataclass(frozen=True, slots=True)
class Coverage:
    """How complete the analysis is, and where the holes are."""

    delivery_days: int
    expected_hours: int
    hours_with_forecast: int
    hours_with_actual: int
    matched_hours: int
    hours_missing_forecast: int
    hours_missing_actual: int
    hours_partial_actual: int
    #: Half-hourly periods the delivery window should contain (48/46/50 a day).
    expected_settlement_periods: int
    #: Half-hourly actuals that actually contributed to the analysed hours.
    actual_settlement_periods: int
    forecast_vintages_seen: int

    @property
    def matched_percent(self) -> float:
        return (self.matched_hours / self.expected_hours * 100.0) if self.expected_hours else 0.0


@dataclass
class AnalysisResult:
    """Everything the API returns for one parameter set."""

    decision_from: dt.date
    decision_to: dt.date
    delivery_from: dt.date
    delivery_to: dt.date
    cutoff: CutoffPolicy
    alignment_mode: AlignmentMode
    mape_floor_mw: float
    metrics: AccuracyMetrics
    coverage: Coverage
    records: list[PeriodRecord]
    daily: list[dict] = field(default_factory=list)
    by_horizon: list[dict] = field(default_factory=list)
    by_hour_of_day: list[dict] = field(default_factory=list)
    data_quality: dict = field(default_factory=dict)


def delivery_window(
    decision_from: dt.date, decision_to: dt.date, cutoff: CutoffPolicy
) -> tuple[dt.date, dt.date]:
    """Delivery days served by decisions taken between two dates."""
    offset = dt.timedelta(days=cutoff.days_before)
    return decision_from + offset, decision_to + offset


def build_analysis(
    *,
    actuals: list[ActualRecord],
    forecasts: list[ForecastRecord],
    decision_from: dt.date,
    decision_to: dt.date,
    cutoff: CutoffPolicy,
    alignment_mode: AlignmentMode = "hourly_mean",
    mape_floor_mw: float = 100.0,
    actual_report: NormaliseReport | None = None,
    forecast_report: NormaliseReport | None = None,
) -> AnalysisResult:
    """Run the full analysis over a decision window."""
    if alignment_mode not in ALIGNMENT_MODES:
        raise ValueError(f"unknown alignment mode: {alignment_mode!r}")
    if decision_to < decision_from:
        raise ValueError("decision_to must not precede decision_from")

    delivery_from, delivery_to = delivery_window(decision_from, decision_to, cutoff)
    actual_index = ActualHourlyIndex(actuals, mode=alignment_mode)
    forecast_index = ForecastVintageIndex(forecasts)

    records: list[PeriodRecord] = []
    expected_periods = 0

    for day in london_days_between(delivery_from, delivery_to):
        expected_periods += settlement_periods_in_day(day)
        day_cutoff = cutoff.for_delivery_day(day)
        # Bound the day in London, iterate in UTC: correct on 23- and 25-hour days.
        for hour in hours_between(
            london_day_start(day), london_day_start(day + dt.timedelta(days=1))
        ):
            selected = forecast_index.select(hour, day_cutoff)
            available = forecast_index.vintages_available(hour)
            actual = actual_index.get(hour)

            if selected is None:
                status = STATUS_NO_ELIGIBLE_FORECAST if available else STATUS_NO_FORECAST_PUBLISHED
            elif actual is None:
                status = STATUS_NO_ACTUAL
            else:
                status = STATUS_MATCHED

            records.append(
                PeriodRecord(
                    target_start=hour,
                    delivery_date=day,
                    decision_cutoff=day_cutoff,
                    status=status,
                    actual_mw=actual.generation if actual else None,
                    actual_partial=bool(actual and actual.partial),
                    settlement_periods=actual.contributing_periods if actual else (),
                    forecast_mw=selected.generation if selected else None,
                    forecast_publish_time=selected.publish_time if selected else None,
                    horizon_hours=selected.horizon_hours if selected else None,
                    vintages_available=available,
                    vintages_eligible=selected.vintages_eligible if selected else 0,
                )
            )

    matched = [r for r in records if r.status == STATUS_MATCHED]
    metrics = compute_metrics(
        [(r.forecast_mw, r.actual_mw) for r in matched], mape_floor_mw=mape_floor_mw
    )

    coverage = Coverage(
        delivery_days=(delivery_to - delivery_from).days + 1,
        expected_hours=len(records),
        hours_with_forecast=sum(1 for r in records if r.forecast_mw is not None),
        hours_with_actual=sum(1 for r in records if r.actual_mw is not None),
        matched_hours=len(matched),
        hours_missing_forecast=sum(
            1
            for r in records
            if r.status in (STATUS_NO_ELIGIBLE_FORECAST, STATUS_NO_FORECAST_PUBLISHED)
        ),
        hours_missing_actual=sum(1 for r in records if r.status == STATUS_NO_ACTUAL),
        hours_partial_actual=sum(1 for r in records if r.actual_partial),
        expected_settlement_periods=expected_periods,
        actual_settlement_periods=sum(len(r.settlement_periods) for r in records),
        forecast_vintages_seen=forecast_index.vintage_count(),
    )

    return AnalysisResult(
        decision_from=decision_from,
        decision_to=decision_to,
        delivery_from=delivery_from,
        delivery_to=delivery_to,
        cutoff=cutoff,
        alignment_mode=alignment_mode,
        mape_floor_mw=mape_floor_mw,
        metrics=metrics,
        coverage=coverage,
        records=records,
        daily=_summarise_daily(records),
        by_horizon=_summarise_horizon(matched),
        by_hour_of_day=_summarise_hour_of_day(matched),
        data_quality=_data_quality(actual_report, forecast_report),
    )


def _summarise_daily(records: list[PeriodRecord]) -> list[dict]:
    """Per delivery day: mean levels, bias and MAE, plus unmatched counts."""
    grouped: dict[dt.date, list[PeriodRecord]] = {}
    for record in records:
        grouped.setdefault(record.delivery_date, []).append(record)

    summaries: list[dict] = []
    for day in sorted(grouped):
        day_records = grouped[day]
        matched = [r for r in day_records if r.status == STATUS_MATCHED]
        errors = [r.error_mw for r in matched]
        summaries.append(
            {
                "delivery_date": day,
                "hours": len(day_records),
                "matched_hours": len(matched),
                "unmatched_hours": len(day_records) - len(matched),
                "mean_actual_mw": _mean([r.actual_mw for r in matched]),
                "mean_forecast_mw": _mean([r.forecast_mw for r in matched]),
                "mae_mw": _mean([abs(error) for error in errors]),
                "bias_mw": _mean(errors),
                "max_abs_error_mw": max((abs(e) for e in errors), default=None),
            }
        )
    return summaries


def _summarise_horizon(matched: list[PeriodRecord], *, bucket_hours: int = 6) -> list[dict]:
    """Error grouped by forecast lead time, to show skill decaying with horizon."""
    grouped: dict[int, list[PeriodRecord]] = {}
    for record in matched:
        if record.horizon_hours is None:
            continue
        bucket = int(record.horizon_hours // bucket_hours) * bucket_hours
        grouped.setdefault(bucket, []).append(record)

    return [
        {
            "horizon_from_hours": bucket,
            "horizon_to_hours": bucket + bucket_hours,
            "matched_hours": len(group),
            "mae_mw": _mean([abs(r.error_mw) for r in group]),
            "bias_mw": _mean([r.error_mw for r in group]),
        }
        for bucket, group in sorted(grouped.items())
    ]


def _summarise_hour_of_day(matched: list[PeriodRecord]) -> list[dict]:
    """Error by hour of the London delivery day, to expose a diurnal pattern.

    The hour is an offset from the start of the London day rather than a UTC
    hour, so the buckets line up with the trader's clock through BST and read
    0-22 or 0-24 on the two transition days.
    """
    grouped: dict[int, list[PeriodRecord]] = {}
    for record in matched:
        day_start = london_day_start(record.delivery_date)
        offset = int((record.target_start - day_start).total_seconds() // 3600)
        grouped.setdefault(offset, []).append(record)

    return [
        {
            "hour_of_day": hour,
            "matched_hours": len(group),
            "mae_mw": _mean([abs(r.error_mw) for r in group]),
            "bias_mw": _mean([r.error_mw for r in group]),
            "mean_actual_mw": _mean([r.actual_mw for r in group]),
        }
        for hour, group in sorted(grouped.items())
    ]


def _data_quality(
    actual_report: NormaliseReport | None, forecast_report: NormaliseReport | None
) -> dict:
    """Normalisation counts, surfaced so coverage gaps are visible in the UI."""

    def summarise(report: NormaliseReport | None) -> dict:
        if report is None:
            return {}
        return {
            "rows_received": report.received,
            "rows_accepted": report.accepted,
            "rows_dropped_malformed": report.dropped_malformed,
            "rows_dropped_wrong_fuel": report.dropped_wrong_fuel,
            "duplicates_collapsed": report.duplicates_collapsed,
            "issues": list(report.issues),
        }

    return {"actuals": summarise(actual_report), "forecasts": summarise(forecast_report)}


def _mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None
