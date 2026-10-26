"""HTTP layer: routes, validation, serialisation, error mapping.

No analysis happens here. Routes validate query parameters, delegate to
:class:`app.service.AnalysisService`, and serialise the result.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import schemas
from .analysis.timeutils import to_iso
from .config import Settings, settings
from .elexon.client import ElexonClient
from .errors import AppError
from .service import AnalysisRequest, AnalysisService, parse_request

VERSION = "1.0.0"
SERVICE_NAME = "wind-forecast-accuracy-api"

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
Day-ahead wind forecast accuracy analytics for GB power procurement.

Compares Elexon **WINDFOR** wind generation forecasts against **FUELHH**
(`fuelType=WIND`) outturn, using only forecast vintages that were published
before an explicit decision cutoff -- so the comparison reflects what a
day-ahead desk actually knew when it committed.

`error = forecast - actual`; a positive error means wind was over-forecast.
"""


def _build_service(app_settings: Settings) -> AnalysisService:
    client = ElexonClient(
        base_url=app_settings.elexon_base_url,
        timeout_seconds=app_settings.elexon_timeout_seconds,
        max_retries=app_settings.elexon_max_retries,
    )
    return AnalysisService(client=client, settings=app_settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own the HTTP client for the process lifetime, so connections pool."""
    app.state.settings = settings
    app.state.service = _build_service(settings)
    logger.info("%s %s started", SERVICE_NAME, VERSION)
    try:
        yield
    finally:
        await app.state.service._client.aclose()


app = FastAPI(
    title="GB Wind Forecast Accuracy API",
    description=DESCRIPTION,
    version=VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    """Map domain errors onto documented status codes and a stable body."""
    if exc.status_code >= 500:
        logger.error("%s: %s", exc.code, exc.message)
    else:
        logger.info("%s: %s", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code, content={"code": exc.code, "message": exc.message}
    )


@app.exception_handler(RequestValidationError)
async def handle_query_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Give FastAPI's own parameter errors the same body as our domain errors.

    Without this, a bad `cutoff_days_before` returns FastAPI's nested detail
    array while a bad `cutoff_time` returns `{code, message}` -- two shapes for
    one class of mistake, which the frontend would have to special-case.
    """
    problems = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", []) if part != "query")
        problems.append(f"{location or 'request'}: {error.get('msg', 'invalid value')}")
    return JSONResponse(
        status_code=422,
        content={"code": "invalid_request", "message": "; ".join(problems)},
    )


def get_service(request: Request) -> AnalysisService:
    return request.app.state.service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


# --- shared query parameters -------------------------------------------------

DecisionFrom = Query(
    None,
    description="First day (yyyy-MM-dd) on which a purchase decision is taken. "
    "Defaults to 2026-01-01.",
    examples=["2026-01-01"],
)
DecisionTo = Query(
    None,
    description="Last decision day (yyyy-MM-dd). Defaults to 2026-01-31.",
    examples=["2026-01-31"],
)
CutoffTime = Query(
    None,
    description="Decision cutoff as HH:MM wall-clock time in Europe/London. Defaults to 09:00.",
    examples=["09:00"],
)
CutoffDaysBefore = Query(
    None,
    ge=0,
    le=7,
    description="How many days before delivery the cutoff falls. Defaults to 1 (day-ahead).",
)
Alignment = Query(
    None,
    description="How half-hourly actuals are reduced onto the hourly forecast grid: "
    "'hourly_mean' (default) or 'period_start'.",
)
MapeFloor = Query(
    None,
    ge=0,
    description="Actuals at or below this MW level are excluded from MAPE. Defaults to 100.",
)


def _request_from_query(
    app_settings: Settings,
    decision_from: str | None,
    decision_to: str | None,
    cutoff_time: str | None,
    cutoff_days_before: int | None,
    alignment: str | None,
    mape_floor_mw: float | None,
) -> AnalysisRequest:
    return parse_request(
        app_settings,
        decision_from=decision_from,
        decision_to=decision_to,
        cutoff_time=cutoff_time,
        cutoff_days_before=cutoff_days_before,
        alignment=alignment,
        mape_floor_mw=mape_floor_mw,
    )


# --- routes ------------------------------------------------------------------


@app.get(
    "/api/health",
    response_model=schemas.HealthResponse,
    tags=["service"],
    summary="Liveness check, with optional upstream probe",
)
async def health(
    probe: bool = Query(False, description="Also check that Elexon is reachable."),
    service: AnalysisService = Depends(get_service),
) -> dict:
    upstream = "not_probed"
    if probe:
        upstream = "reachable" if await service._client.probe() else "unreachable"
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": VERSION,
        "time_utc": to_iso(dt.datetime.now(dt.UTC)),
        "upstream": upstream,
        "cache": service.cache_stats,
    }


@app.get(
    "/api/meta",
    response_model=schemas.MetaResponse,
    tags=["service"],
    summary="Metric definitions, defaults and documented assumptions",
)
async def meta(app_settings: Settings = Depends(get_settings)) -> dict:
    return schemas.meta_payload(app_settings)


@app.get(
    "/api/analysis",
    response_model=schemas.AnalysisResponse,
    responses={422: {"model": schemas.ErrorResponse}, 502: {"model": schemas.ErrorResponse}},
    tags=["analysis"],
    summary="Forecast-versus-actual analysis for a decision window",
)
async def analysis(
    decision_from: str | None = DecisionFrom,
    decision_to: str | None = DecisionTo,
    cutoff_time: str | None = CutoffTime,
    cutoff_days_before: int | None = CutoffDaysBefore,
    alignment: str | None = Alignment,
    mape_floor_mw: float | None = MapeFloor,
    service: AnalysisService = Depends(get_service),
    app_settings: Settings = Depends(get_settings),
) -> dict:
    request = _request_from_query(
        app_settings,
        decision_from,
        decision_to,
        cutoff_time,
        cutoff_days_before,
        alignment,
        mape_floor_mw,
    )
    result, fetched = await service.analyse(request)
    return schemas.analysis_payload(result, fetched)


@app.get(
    "/api/analysis/vintages",
    response_model=schemas.VintageResponse,
    responses={422: {"model": schemas.ErrorResponse}, 502: {"model": schemas.ErrorResponse}},
    tags=["analysis"],
    summary="Every forecast vintage for one target hour, flagged against the cutoff",
)
async def vintages(
    target: str = Query(
        ...,
        description="Target hour as an ISO-8601 UTC timestamp, e.g. 2026-01-15T18:00:00Z.",
        examples=["2026-01-15T18:00:00Z"],
    ),
    decision_from: str | None = DecisionFrom,
    decision_to: str | None = DecisionTo,
    cutoff_time: str | None = CutoffTime,
    cutoff_days_before: int | None = CutoffDaysBefore,
    service: AnalysisService = Depends(get_service),
    app_settings: Settings = Depends(get_settings),
) -> dict:
    request = _request_from_query(
        app_settings, decision_from, decision_to, cutoff_time, cutoff_days_before, None, None
    )
    raw = await service.vintages_for_target(request, target)
    return schemas.vintage_payload(raw, request.cutoff.describe())


@app.get(
    "/api/analysis/cutoff-sweep",
    response_model=schemas.CutoffSweepResponse,
    responses={422: {"model": schemas.ErrorResponse}, 502: {"model": schemas.ErrorResponse}},
    tags=["analysis"],
    summary="Accuracy recomputed at several decision cutoffs",
)
async def cutoff_sweep(
    cutoff_times: str = Query(
        "06:00,09:00,12:00,17:00,23:30",
        description="Comma-separated HH:MM cutoffs to evaluate, all on the same D-n day.",
    ),
    decision_from: str | None = DecisionFrom,
    decision_to: str | None = DecisionTo,
    cutoff_days_before: int | None = CutoffDaysBefore,
    alignment: str | None = Alignment,
    service: AnalysisService = Depends(get_service),
    app_settings: Settings = Depends(get_settings),
) -> dict:
    request = _request_from_query(
        app_settings, decision_from, decision_to, None, cutoff_days_before, alignment, None
    )
    wanted = [part.strip() for part in cutoff_times.split(",") if part.strip()]
    if not wanted:
        from .errors import ValidationError

        raise ValidationError("cutoff_times must list at least one HH:MM time")
    rows = await service.cutoff_sweep(request, wanted)
    return {
        "decision_from": request.decision_from,
        "decision_to": request.decision_to,
        "alignment_mode": request.alignment_mode,
        "rows": rows,
    }


CSV_COLUMNS = [
    "target_start_utc",
    "target_start_london",
    "delivery_date",
    "decision_cutoff_utc",
    "status",
    "actual_mw",
    "actual_partial",
    "settlement_periods",
    "forecast_mw",
    "forecast_publish_time_utc",
    "forecast_horizon_hours",
    "error_mw",
    "abs_error_mw",
    "vintages_available",
    "vintages_eligible",
]


@app.get(
    "/api/analysis/export.csv",
    tags=["analysis"],
    summary="CSV export of the analysed records",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/csv": {}}, "description": "One row per target hour."},
        422: {"model": schemas.ErrorResponse},
    },
)
async def export_csv(
    decision_from: str | None = DecisionFrom,
    decision_to: str | None = DecisionTo,
    cutoff_time: str | None = CutoffTime,
    cutoff_days_before: int | None = CutoffDaysBefore,
    alignment: str | None = Alignment,
    mape_floor_mw: float | None = MapeFloor,
    service: AnalysisService = Depends(get_service),
    app_settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Export exactly the records the dashboard shows.

    Served from the same analysis the JSON endpoint returns, so an exported
    file and the screen can never disagree. Unmatched hours are included with
    empty value columns and their ``status`` intact, so gaps stay visible in a
    spreadsheet instead of looking like zeroes.
    """
    request = _request_from_query(
        app_settings,
        decision_from,
        decision_to,
        cutoff_time,
        cutoff_days_before,
        alignment,
        mape_floor_mw,
    )
    result, _ = await service.analyse(request)

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for record in result.records:
        payload = schemas.record_payload(record)
        error = payload["error_mw"]
        writer.writerow(
            [
                payload["target_start"],
                payload["target_start_london"],
                payload["delivery_date"].isoformat(),
                payload["decision_cutoff"],
                payload["status"],
                _csv_number(payload["actual_mw"]),
                "true" if payload["actual_partial"] else "false",
                " ".join(str(period) for period in payload["settlement_periods"]),
                _csv_number(payload["forecast_mw"]),
                payload["forecast_publish_time"] or "",
                _csv_number(payload["horizon_hours"]),
                _csv_number(error),
                _csv_number(abs(error) if error is not None else None),
                payload["vintages_available"],
                payload["vintages_eligible"],
            ]
        )

    filename = (
        f"wind-forecast-accuracy_{request.decision_from:%Y%m%d}-{request.decision_to:%Y%m%d}"
        f"_cutoff{request.cutoff.time_of_day:%H%M}.csv"
    )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_number(value: float | None) -> str:
    """Render a number for CSV, leaving genuinely missing values empty."""
    if value is None:
        return ""
    return f"{value:.3f}".rstrip("0").rstrip(".") if value % 1 else str(int(value))
