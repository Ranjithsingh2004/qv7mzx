"""Forecast accuracy metrics.

All metrics are computed from matched periods only -- an hour needs both a
cutoff-eligible forecast and an actual outturn to contribute. Unmatched hours
are counted and surfaced, never treated as zero error.

Sign convention, used consistently everywhere including the UI:

    error = forecast - actual

so a **positive** error (and positive bias) means the forecast was **too
high** -- wind was over-predicted, and a desk trusting it would have
under-procured thermal cover.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

#: Actuals at or below this level are excluded from MAPE by default.
DEFAULT_MAPE_FLOOR_MW = 100.0

METRIC_DEFINITIONS: dict[str, str] = {
    "mae_mw": "Mean Absolute Error: mean(|forecast - actual|). Average miss size in MW, "
    "in the same units as the traded volume.",
    "rmse_mw": "Root Mean Squared Error: sqrt(mean((forecast - actual)^2)). Penalises large "
    "misses more than MAE, so it is the more relevant of the two when a single bad "
    "hour is expensive.",
    "bias_mw": "Mean forecast bias: mean(forecast - actual). Positive means the forecast ran "
    "high (wind over-predicted); negative means it ran low.",
    "error_sd_mw": "Standard deviation of the forecast error about its own mean: the dispersion "
    "that remains once the systematic bias is removed.",
    "bias_share_of_mse": "Fraction of mean squared error attributable to systematic bias "
    "(bias^2 / MSE). High values mean much of the error is a stable offset "
    "that can be corrected rather than irreducible weather uncertainty.",
    "mape_percent": "Mean Absolute Percentage Error: mean(|error| / actual) over matched hours "
    "whose actual exceeds the MAPE floor. Excluded hours are reported so the "
    "denominator policy is visible.",
    "wmape_percent": "Weighted MAPE: sum(|error|) / sum(actual). Defined for every matched hour "
    "including near-zero ones, so it is the percentage figure to prefer.",
    "normalised_mae_percent": "MAE as a percentage of mean actual generation.",
    "correlation": "Pearson correlation between forecast and actual. Measures how well the "
    "forecast tracks the shape of the day, independently of any bias.",
    "max_abs_error_mw": "Largest single-hour absolute error across matched hours.",
    "hours_over_forecast": "Matched hours where the forecast exceeded the actual.",
    "hours_under_forecast": "Matched hours where the forecast fell short of the actual.",
}


@dataclass(frozen=True, slots=True)
class AccuracyMetrics:
    """Accuracy summary over a set of matched hours."""

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

    def as_dict(self) -> dict:
        return asdict(self)


def compute_metrics(
    pairs: list[tuple[float, float]],
    *,
    mape_floor_mw: float = DEFAULT_MAPE_FLOOR_MW,
) -> AccuracyMetrics:
    """Compute accuracy metrics from ``(forecast, actual)`` pairs in MW.

    An empty input is valid and yields ``None`` for every metric with
    ``matched_hours == 0``: the honest answer for a period with no overlap,
    rather than a zero that reads like a perfect forecast.
    """
    if mape_floor_mw < 0:
        raise ValueError("mape_floor_mw must not be negative")

    count = len(pairs)
    if count == 0:
        return AccuracyMetrics(
            matched_hours=0,
            mae_mw=None,
            rmse_mw=None,
            bias_mw=None,
            error_sd_mw=None,
            bias_share_of_mse=None,
            mape_percent=None,
            mape_hours_included=0,
            mape_hours_excluded=0,
            mape_floor_mw=mape_floor_mw,
            wmape_percent=None,
            normalised_mae_percent=None,
            correlation=None,
            max_abs_error_mw=None,
            mean_actual_mw=None,
            mean_forecast_mw=None,
            hours_over_forecast=0,
            hours_under_forecast=0,
        )

    forecasts = [pair[0] for pair in pairs]
    actuals = [pair[1] for pair in pairs]
    errors = [forecast - actual for forecast, actual in pairs]

    mae = sum(abs(error) for error in errors) / count
    mse = sum(error * error for error in errors) / count
    bias = sum(errors) / count
    # Population variance about the mean error; identical to MSE - bias^2, but
    # computed directly to stay numerically well-behaved.
    variance = sum((error - bias) ** 2 for error in errors) / count
    mean_actual = sum(actuals) / count
    mean_forecast = sum(forecasts) / count

    # MAPE is only meaningful away from zero; the floor policy is reported.
    scored = [
        (error, actual)
        for error, actual in zip(errors, actuals, strict=False)
        if actual > mape_floor_mw
    ]
    mape = (
        sum(abs(error) / actual for error, actual in scored) / len(scored) * 100.0
        if scored
        else None
    )

    total_actual = sum(actuals)
    wmape = sum(abs(error) for error in errors) / total_actual * 100.0 if total_actual > 0 else None

    return AccuracyMetrics(
        matched_hours=count,
        mae_mw=mae,
        rmse_mw=math.sqrt(mse),
        bias_mw=bias,
        error_sd_mw=math.sqrt(variance),
        bias_share_of_mse=(bias * bias / mse) if mse > 0 else None,
        mape_percent=mape,
        mape_hours_included=len(scored),
        mape_hours_excluded=count - len(scored),
        mape_floor_mw=mape_floor_mw,
        wmape_percent=wmape,
        normalised_mae_percent=(mae / mean_actual * 100.0) if mean_actual > 0 else None,
        correlation=_pearson(forecasts, actuals),
        max_abs_error_mw=max(abs(error) for error in errors),
        mean_actual_mw=mean_actual,
        mean_forecast_mw=mean_forecast,
        hours_over_forecast=sum(1 for error in errors if error > 0),
        hours_under_forecast=sum(1 for error in errors if error < 0),
    )


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation, or ``None`` when it is undefined.

    Undefined for fewer than two points or when either series is constant --
    both of which happen with short or flat windows, so neither may raise.
    """
    count = len(xs)
    if count < 2:
        return None
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    var_x = sum(value * value for value in dx)
    var_y = sum(value * value for value in dy)
    if var_x <= 0 or var_y <= 0:
        return None
    return sum(a * b for a, b in zip(dx, dy, strict=False)) / math.sqrt(var_x * var_y)
