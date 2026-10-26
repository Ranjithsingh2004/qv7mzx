"""Application service: validate a request, fetch what it needs, analyse, cache.

The HTTP layer in :mod:`app.main` does no data work of its own; it validates
shapes, calls in here, and serialises the result.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from .analysis.align import ALIGNMENT_MODES, AlignmentMode
from .analysis.pipeline import AnalysisResult, build_analysis, delivery_window
from .analysis.timeutils import (
    london_day_start,
    parse_date,
    parse_time_of_day,
    to_iso,
)
from .analysis.vintage import CutoffPolicy, ForecastVintageIndex
from .cache import TTLCache
from .config import Settings
from .elexon.client import ElexonClient
from .elexon.normalise import (
    NormaliseReport,
    normalise_actuals,
    normalise_forecasts,
)
from .errors import ValidationError

logger = logging.getLogger(__name__)

#: Guard against a request that would pull years of data in one go.
MAX_DECISION_DAYS = 120

#: Extra days of settlement data fetched either side of the delivery window, so
#: that hour bucketing at the window edges is never short of a period.
ACTUALS_PADDING_DAYS = 1

#: How far before the earliest cutoff to look for forecast vintages. A WINDFOR
#: vintage spans roughly three days, so three days back guarantees that every
#: target hour in the window has its full vintage history available.
FORECAST_LOOKBACK_DAYS = 3


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """A validated analysis request."""

    decision_from: dt.date
    decision_to: dt.date
    cutoff: CutoffPolicy
    alignment_mode: AlignmentMode
    mape_floor_mw: float

    def cache_key(self) -> str:
        return "|".join(
            [
                self.decision_from.isoformat(),
                self.decision_to.isoformat(),
                self.cutoff.time_of_day.strftime("%H:%M:%S"),
                str(self.cutoff.days_before),
                self.alignment_mode,
                f"{self.mape_floor_mw:.3f}",
            ]
        )


def parse_request(
    settings: Settings,
    *,
    decision_from: str | None = None,
    decision_to: str | None = None,
    cutoff_time: str | None = None,
    cutoff_days_before: int | None = None,
    alignment: str | None = None,
    mape_floor_mw: float | None = None,
) -> AnalysisRequest:
    """Validate raw query parameters into an :class:`AnalysisRequest`.

    Every failure raises :class:`ValidationError` with a message naming the
    offending parameter, so a caller can correct it without guessing.
    """
    try:
        start = (
            parse_date(decision_from)
            if decision_from
            else parse_date(settings.default_decision_from)
        )
    except ValueError as exc:
        raise ValidationError(f"decision_from: {exc}") from exc
    try:
        end = parse_date(decision_to) if decision_to else parse_date(settings.default_decision_to)
    except ValueError as exc:
        raise ValidationError(f"decision_to: {exc}") from exc

    if end < start:
        raise ValidationError("decision_to must not be earlier than decision_from")
    span_days = (end - start).days + 1
    if span_days > MAX_DECISION_DAYS:
        raise ValidationError(
            f"decision window of {span_days} days exceeds the {MAX_DECISION_DAYS}-day maximum"
        )

    try:
        time_of_day = parse_time_of_day(cutoff_time or settings.default_cutoff_time)
    except ValueError as exc:
        raise ValidationError(f"cutoff_time: {exc}") from exc

    days_before = (
        settings.default_cutoff_days_before if cutoff_days_before is None else cutoff_days_before
    )
    if not isinstance(days_before, int) or not (0 <= days_before <= 7):
        raise ValidationError("cutoff_days_before must be an integer between 0 and 7")

    mode = alignment or "hourly_mean"
    if mode not in ALIGNMENT_MODES:
        raise ValidationError(
            f"alignment must be one of {', '.join(sorted(ALIGNMENT_MODES))}; got {mode!r}"
        )

    floor = settings.default_mape_floor_mw if mape_floor_mw is None else float(mape_floor_mw)
    if floor < 0:
        raise ValidationError("mape_floor_mw must not be negative")

    return AnalysisRequest(
        decision_from=start,
        decision_to=end,
        cutoff=CutoffPolicy(time_of_day=time_of_day, days_before=days_before),
        alignment_mode=mode,  # type: ignore[arg-type]
        mape_floor_mw=floor,
    )


@dataclass
class FetchedData:
    """Normalised source records plus the windows they were fetched over."""

    actuals: list
    forecasts: list
    actual_report: NormaliseReport
    forecast_report: NormaliseReport
    settlement_from: dt.date
    settlement_to: dt.date
    publish_from: dt.datetime
    publish_to: dt.datetime

    def describe_source(self) -> dict:
        return {
            "actuals": {
                "dataset": "FUELHH",
                "filter": "fuelType=WIND",
                "settlement_date_from": self.settlement_from.isoformat(),
                "settlement_date_to": self.settlement_to.isoformat(),
                "records": len(self.actuals),
            },
            "forecasts": {
                "dataset": "WINDFOR",
                "publish_time_from": to_iso(self.publish_from),
                "publish_time_to": to_iso(self.publish_to),
                "records": len(self.forecasts),
            },
        }


class AnalysisService:
    """Fetches Elexon data and produces analyses, with caching."""

    def __init__(self, *, client: ElexonClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._analyses: TTLCache[tuple[AnalysisResult, FetchedData]] = TTLCache(
            ttl_seconds=settings.cache_ttl_seconds, max_entries=settings.cache_max_entries
        )
        self._raw: TTLCache[FetchedData] = TTLCache(
            ttl_seconds=settings.cache_ttl_seconds, max_entries=settings.cache_max_entries
        )

    @property
    def cache_stats(self) -> dict:
        return {"analyses": self._analyses.stats(), "source_data": self._raw.stats()}

    def clear_cache(self) -> None:
        self._analyses.clear()
        self._raw.clear()

    async def fetch(self, request: AnalysisRequest) -> FetchedData:
        """Fetch and normalise the source data a request needs.

        Cached on the fetch window rather than the full request, so changing
        only the cutoff time or alignment mode reuses the downloaded data.
        """
        delivery_from, delivery_to = delivery_window(
            request.decision_from, request.decision_to, request.cutoff
        )
        settlement_from = delivery_from - dt.timedelta(days=ACTUALS_PADDING_DAYS)
        settlement_to = delivery_to + dt.timedelta(days=ACTUALS_PADDING_DAYS)

        # Vintages from well before the first cutoff, through the end of the
        # delivery window. Fetching past the cutoff is deliberate: the UI shows
        # later vintages as explicitly excluded, which is how the rule is
        # demonstrated. Selection itself is cutoff-bound and cannot use them.
        #
        # The window is anchored to London day boundaries rather than to the
        # cutoff instant, so it depends only on the delivery window and
        # `days_before`. That makes it identical across cutoff *times*, which
        # is what lets the cutoff sweep -- and a user dragging the cutoff
        # control -- reuse one download instead of refetching per cutoff.
        publish_from = london_day_start(
            delivery_from - dt.timedelta(days=request.cutoff.days_before + FORECAST_LOOKBACK_DAYS)
        )
        publish_to = london_day_start(delivery_to + dt.timedelta(days=1))

        key = "|".join(
            [
                settlement_from.isoformat(),
                settlement_to.isoformat(),
                to_iso(publish_from),
                to_iso(publish_to),
            ]
        )
        cached = self._raw.get(key)
        if cached is not None:
            logger.debug("source data cache hit for %s", key)
            return cached

        logger.info(
            "fetching elexon: FUELHH/WIND %s..%s, WINDFOR published %s..%s",
            settlement_from,
            settlement_to,
            to_iso(publish_from),
            to_iso(publish_to),
        )
        actual_rows = await self._client.fetch_wind_actuals(settlement_from, settlement_to)
        forecast_rows = await self._client.fetch_wind_forecasts(publish_from, publish_to)

        actuals, actual_report = normalise_actuals(actual_rows)
        forecasts, forecast_report = normalise_forecasts(forecast_rows)
        logger.info(
            "normalised %d wind actuals and %d forecast values",
            len(actuals),
            len(forecasts),
        )

        fetched = FetchedData(
            actuals=actuals,
            forecasts=forecasts,
            actual_report=actual_report,
            forecast_report=forecast_report,
            settlement_from=settlement_from,
            settlement_to=settlement_to,
            publish_from=publish_from,
            publish_to=publish_to,
        )
        self._raw.set(key, fetched)
        return fetched

    async def analyse(self, request: AnalysisRequest) -> tuple[AnalysisResult, FetchedData]:
        """Run (or reuse) the analysis for a request."""
        key = request.cache_key()
        cached = self._analyses.get(key)
        if cached is not None:
            logger.debug("analysis cache hit for %s", key)
            return cached

        fetched = await self.fetch(request)
        result = build_analysis(
            actuals=fetched.actuals,
            forecasts=fetched.forecasts,
            decision_from=request.decision_from,
            decision_to=request.decision_to,
            cutoff=request.cutoff,
            alignment_mode=request.alignment_mode,
            mape_floor_mw=request.mape_floor_mw,
            actual_report=fetched.actual_report,
            forecast_report=fetched.forecast_report,
        )
        self._analyses.set(key, (result, fetched))
        return result, fetched

    async def cutoff_sweep(self, request: AnalysisRequest, cutoff_times: list[str]) -> list[dict]:
        """Metrics recomputed at several decision cutoffs.

        Quantifies the value of deciding later: the same outturn judged against
        whatever forecast each deadline would have allowed. One download serves
        every cutoff, so this is cheap.
        """
        fetched = await self.fetch(request)
        rows: list[dict] = []
        for raw_time in cutoff_times:
            try:
                time_of_day = parse_time_of_day(raw_time)
            except ValueError as exc:
                raise ValidationError(f"cutoff_times: {exc}") from exc
            policy = CutoffPolicy(time_of_day=time_of_day, days_before=request.cutoff.days_before)
            result = build_analysis(
                actuals=fetched.actuals,
                forecasts=fetched.forecasts,
                decision_from=request.decision_from,
                decision_to=request.decision_to,
                cutoff=policy,
                alignment_mode=request.alignment_mode,
                mape_floor_mw=request.mape_floor_mw,
            )
            metrics = result.metrics
            rows.append(
                {
                    "cutoff_time": time_of_day.strftime("%H:%M"),
                    "cutoff_description": policy.describe(),
                    "matched_hours": metrics.matched_hours,
                    "mae_mw": metrics.mae_mw,
                    "rmse_mw": metrics.rmse_mw,
                    "bias_mw": metrics.bias_mw,
                    "error_sd_mw": metrics.error_sd_mw,
                    "wmape_percent": metrics.wmape_percent,
                    "mean_horizon_hours": _mean_horizon(result),
                }
            )
        return rows

    async def vintages_for_target(self, request: AnalysisRequest, target_iso: str) -> dict:
        """Every forecast vintage for one target hour, flagged against the cutoff.

        This is the inspector that makes the selection rule auditable: a
        reviewer picks an hour and sees which vintages existed, which the
        deadline allowed, and which one was used.
        """
        from .analysis.timeutils import hour_floor, parse_timestamp

        try:
            target = hour_floor(parse_timestamp(target_iso))
        except ValueError as exc:
            raise ValidationError(f"target: {exc}") from exc

        fetched = await self.fetch(request)
        index = ForecastVintageIndex(fetched.forecasts)
        cutoff = request.cutoff.for_target(target)
        vintages = index.vintages_for(target, cutoff)
        if not vintages:
            raise ValidationError(
                f"no forecast vintages were published for target hour {to_iso(target)}"
            )
        return {"target_start": target, "decision_cutoff": cutoff, "vintages": vintages}


def _mean_horizon(result: AnalysisResult) -> float | None:
    horizons = [
        record.horizon_hours for record in result.records if record.horizon_hours is not None
    ]
    return sum(horizons) / len(horizons) if horizons else None
