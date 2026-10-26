"""API response models and the mapping from domain objects onto them.

Declared with Pydantic so the OpenAPI document is accurate and the HTTP layer
has one obvious place where domain objects become JSON. Timestamps serialise
as ISO-8601 UTC with a ``Z`` suffix, matching the upstream convention.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from .analysis.align import ALIGNMENT_MODES
from .analysis.metrics import METRIC_DEFINITIONS, AccuracyMetrics
from .analysis.pipeline import AnalysisResult, Coverage, PeriodRecord
from .analysis.timeutils import to_iso
from .service import FetchedData


class HealthResponse(BaseModel):
    """Liveness, and optionally upstream reachability."""

    status: str = Field(examples=["ok"])
    service: str
    version: str
    time_utc: str
    upstream: str = Field(
        description="'reachable', 'unreachable', or 'not_probed' when no probe was requested.",
        examples=["not_probed"],
    )
    cache: dict


class MetricsModel(BaseModel):
    """Accuracy metrics over matched hours. ``null`` where undefined."""

    matched_hours: int
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    error_sd_mw: float | None
    bias_share_of_mse: float | None
    mape_percent: float | None
    mape_hours_included: int
    mape_hours_excluded: int
    mape_floor_mw: float
    wmape_percent: float | None
    normalised_mae_percent: float | None
    correlation: float | None
    max_abs_error_mw: float | None
    mean_actual_mw: float | None
    mean_forecast_mw: float | None
    hours_over_forecast: int
    hours_under_forecast: int


class CoverageModel(BaseModel):
    """Completeness of the analysis, and where the gaps are."""

    delivery_days: int
    expected_hours: int
    hours_with_forecast: int
    hours_with_actual: int
    matched_hours: int
    matched_percent: float
    hours_missing_forecast: int
    hours_missing_actual: int
    hours_partial_actual: int
    expected_settlement_periods: int
    actual_settlement_periods: int
    forecast_vintages_seen: int


class PeriodRecordModel(BaseModel):
    """One target hour: the forecast available at the cutoff, and the outturn."""

    target_start: str = Field(description="Start of the target hour, UTC.")
    target_start_london: str = Field(description="Same instant as London wall-clock time.")
    delivery_date: dt.date
    decision_cutoff: str
    status: str = Field(
        description=(
            "'matched', 'no_eligible_forecast' (vintages existed but all published after the "
            "cutoff), 'no_forecast_published', or 'no_actual'."
        )
    )
    actual_mw: float | None
    actual_partial: bool
    settlement_periods: list[int]
    forecast_mw: float | None
    forecast_publish_time: str | None
    horizon_hours: float | None
    error_mw: float | None = Field(description="forecast - actual; positive means over-forecast.")
    vintages_available: int
    vintages_eligible: int


class DailySummaryModel(BaseModel):
    delivery_date: dt.date
    hours: int
    matched_hours: int
    unmatched_hours: int
    mean_actual_mw: float | None
    mean_forecast_mw: float | None
    mae_mw: float | None
    bias_mw: float | None
    max_abs_error_mw: float | None


class HorizonBucketModel(BaseModel):
    horizon_from_hours: int
    horizon_to_hours: int
    matched_hours: int
    mae_mw: float | None
    bias_mw: float | None


class HourOfDayModel(BaseModel):
    hour_of_day: int
    matched_hours: int
    mae_mw: float | None
    bias_mw: float | None
    mean_actual_mw: float | None


class CutoffModel(BaseModel):
    time_of_day: str
    days_before: int
    timezone: str
    description: str
    earliest_cutoff_utc: str
    latest_cutoff_utc: str


class AnalysisResponse(BaseModel):
    """Full analysis for one parameter set."""

    data_mode: str = Field(
        description="'live_elexon' when every figure derives from Elexon BMRS responses.",
        examples=["live_elexon"],
    )
    decision_from: dt.date = Field(description="First day a purchase decision is taken.")
    decision_to: dt.date
    delivery_from: dt.date = Field(description="First delivery day covered by those decisions.")
    delivery_to: dt.date
    cutoff: CutoffModel
    alignment_mode: str
    alignment_description: str
    mape_floor_mw: float
    metrics: MetricsModel
    coverage: CoverageModel
    daily: list[DailySummaryModel]
    by_horizon: list[HorizonBucketModel]
    by_hour_of_day: list[HourOfDayModel]
    records: list[PeriodRecordModel]
    sources: dict
    data_quality: dict
    generated_at: str


class VintageModel(BaseModel):
    publish_time: str
    generation: float
    horizon_hours: float
    eligible: bool = Field(description="Published at or before the decision cutoff.")
    selected: bool = Field(description="The latest eligible vintage: the one used.")


class VintageResponse(BaseModel):
    target_start: str
    target_start_london: str
    decision_cutoff: str
    cutoff_description: str
    vintages: list[VintageModel]


class CutoffSweepRow(BaseModel):
    cutoff_time: str
    cutoff_description: str
    matched_hours: int
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    error_sd_mw: float | None
    wmape_percent: float | None
    mean_horizon_hours: float | None


class CutoffSweepResponse(BaseModel):
    decision_from: dt.date
    decision_to: dt.date
    alignment_mode: str
    rows: list[CutoffSweepRow]


class MetaResponse(BaseModel):
    """Metric definitions, defaults and documented assumptions for the UI."""

    metric_definitions: dict[str, str]
    alignment_modes: dict[str, str]
    datasets: dict
    defaults: dict
    assumptions: list[str]
    sign_convention: str


class ErrorResponse(BaseModel):
    code: str
    message: str


# --- domain -> payload -------------------------------------------------------


def _london(moment: dt.datetime) -> str:
    from .analysis.timeutils import LONDON

    return moment.astimezone(LONDON).strftime("%Y-%m-%dT%H:%M:%S%z")


def metrics_payload(metrics: AccuracyMetrics) -> dict:
    return metrics.as_dict()


def coverage_payload(coverage: Coverage) -> dict:
    payload = {
        field: getattr(coverage, field)
        for field in (
            "delivery_days",
            "expected_hours",
            "hours_with_forecast",
            "hours_with_actual",
            "matched_hours",
            "hours_missing_forecast",
            "hours_missing_actual",
            "hours_partial_actual",
            "expected_settlement_periods",
            "actual_settlement_periods",
            "forecast_vintages_seen",
        )
    }
    payload["matched_percent"] = coverage.matched_percent
    return payload


def record_payload(record: PeriodRecord) -> dict:
    return {
        "target_start": to_iso(record.target_start),
        "target_start_london": _london(record.target_start),
        "delivery_date": record.delivery_date,
        "decision_cutoff": to_iso(record.decision_cutoff),
        "status": record.status,
        "actual_mw": record.actual_mw,
        "actual_partial": record.actual_partial,
        "settlement_periods": list(record.settlement_periods),
        "forecast_mw": record.forecast_mw,
        "forecast_publish_time": (
            to_iso(record.forecast_publish_time) if record.forecast_publish_time else None
        ),
        "horizon_hours": record.horizon_hours,
        "error_mw": record.error_mw,
        "vintages_available": record.vintages_available,
        "vintages_eligible": record.vintages_eligible,
    }


def analysis_payload(result: AnalysisResult, fetched: FetchedData) -> dict:
    earliest = result.cutoff.for_delivery_day(result.delivery_from)
    latest = result.cutoff.for_delivery_day(result.delivery_to)
    return {
        # Every number in this response is derived from Elexon BMRS responses.
        # The product has no synthetic or demo data path.
        "data_mode": "live_elexon",
        "decision_from": result.decision_from,
        "decision_to": result.decision_to,
        "delivery_from": result.delivery_from,
        "delivery_to": result.delivery_to,
        "cutoff": {
            "time_of_day": result.cutoff.time_of_day.strftime("%H:%M"),
            "days_before": result.cutoff.days_before,
            "timezone": result.cutoff.timezone_name,
            "description": result.cutoff.describe(),
            "earliest_cutoff_utc": to_iso(earliest),
            "latest_cutoff_utc": to_iso(latest),
        },
        "alignment_mode": result.alignment_mode,
        "alignment_description": ALIGNMENT_MODES[result.alignment_mode],
        "mape_floor_mw": result.mape_floor_mw,
        "metrics": metrics_payload(result.metrics),
        "coverage": coverage_payload(result.coverage),
        "daily": result.daily,
        "by_horizon": result.by_horizon,
        "by_hour_of_day": result.by_hour_of_day,
        "records": [record_payload(record) for record in result.records],
        "sources": fetched.describe_source(),
        "data_quality": result.data_quality,
        "generated_at": to_iso(dt.datetime.now(dt.UTC)),
    }


def vintage_payload(raw: dict, cutoff_description: str) -> dict:
    return {
        "target_start": to_iso(raw["target_start"]),
        "target_start_london": _london(raw["target_start"]),
        "decision_cutoff": to_iso(raw["decision_cutoff"]),
        "cutoff_description": cutoff_description,
        "vintages": [
            {
                "publish_time": to_iso(vintage["publish_time"]),
                "generation": vintage["generation"],
                "horizon_hours": vintage["horizon_hours"],
                "eligible": vintage["eligible"],
                "selected": vintage["selected"],
            }
            for vintage in raw["vintages"]
        ],
    }


def meta_payload(settings) -> dict:
    return {
        "metric_definitions": METRIC_DEFINITIONS,
        "alignment_modes": dict(ALIGNMENT_MODES),
        "datasets": {
            "actuals": {
                "name": "FUELHH",
                "description": (
                    "Half-hourly generation outturn by fuel type, filtered to fuelType=WIND. "
                    "Values are average MW over each 30-minute settlement period."
                ),
                "resolution": "30 minutes",
                "units": "MW",
                "documentation": (
                    "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream"
                ),
            },
            "forecasts": {
                "name": "WINDFOR",
                "description": (
                    "Wind generation forecast. Each publication (vintage) carries a publishTime "
                    "and covers roughly three days of hourly target periods."
                ),
                "resolution": "60 minutes",
                "units": "MW",
                "documentation": (
                    "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream"
                ),
            },
        },
        "defaults": {
            "decision_from": settings.default_decision_from,
            "decision_to": settings.default_decision_to,
            "cutoff_time": settings.default_cutoff_time,
            "cutoff_days_before": settings.default_cutoff_days_before,
            "mape_floor_mw": settings.default_mape_floor_mw,
            "alignment": "hourly_mean",
        },
        "assumptions": [
            "The decision cutoff defaults to 09:00 Europe/London on the day before delivery. "
            "GB day-ahead auctions close mid-morning on D-1, so this sits ahead of gate closure. "
            "It is a documented product assumption, configurable in the UI, not a confirmed "
            "market rule.",
            "WINDFOR is hourly and FUELHH is half-hourly, so comparison happens on the hourly "
            "grid. By default each hour's actual is the mean of the settlement periods inside "
            "it; 'period_start' alignment compares only the period starting on the hour.",
            "A decision taken on day D is assumed to procure for delivery on D+1 "
            "(cutoff_days_before), so a January decision window delivers 2 January to "
            "1 February.",
            "MAPE is computed only over hours whose actual exceeds the MAPE floor (100 MW by "
            "default); the included and excluded counts are always reported. wMAPE is reported "
            "alongside because it is defined for every matched hour.",
            "FUELHH wind outturn and the WINDFOR forecast are not documented by Elexon as "
            "covering an identical set of wind assets. A persistent level difference between "
            "them may therefore reflect scope as well as forecast skill; the brief limits this "
            "product to these two datasets, so the two cannot be separated here.",
        ],
        "sign_convention": "error = forecast - actual; positive means wind was over-forecast.",
    }
