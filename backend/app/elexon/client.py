"""HTTP access to the Elexon BMRS Insights API.

Scope is deliberately narrow: the two datasets the product is built on.

* ``FUELHH`` -- half-hourly generation outturn by fuel type. Filtered upstream
  to ``fuelType=WIND``, which cuts the payload by a factor of twenty.
  Elexon documents that settlement-date and publish-date filters are mutually
  exclusive, so only the settlement-date form is used.
* ``WINDFOR`` -- wind generation forecast. Only publish-time filters exist,
  which suits us: the decision cutoff is itself a constraint on publish time.

The ``/stream`` variants return a bare JSON array with no pagination envelope,
which is why no paging loop is needed; a whole month of either dataset is a
single request of a couple of megabytes.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

import httpx

from ..analysis.timeutils import to_iso
from ..errors import UpstreamError

logger = logging.getLogger(__name__)

#: Transient conditions worth a retry; anything else fails fast.
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class ElexonClient:
    """Thin async wrapper around the two dataset endpoints.

    One :class:`httpx.AsyncClient` is shared for the process lifetime so that
    connections are pooled across requests.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max(1, max_retries)
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "wind-procurement-analytics/1.0"},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_wind_actuals(
        self, settlement_date_from: dt.date, settlement_date_to: dt.date
    ) -> list[dict]:
        """FUELHH wind outturn for an inclusive settlement-date range."""
        return await self._get_json(
            "/datasets/FUELHH/stream",
            {
                "settlementDateFrom": settlement_date_from.isoformat(),
                "settlementDateTo": settlement_date_to.isoformat(),
                "fuelType": "WIND",
            },
        )

    async def fetch_wind_forecasts(
        self, publish_from: dt.datetime, publish_to: dt.datetime
    ) -> list[dict]:
        """Every WINDFOR vintage published in ``[publish_from, publish_to]``."""
        return await self._get_json(
            "/datasets/WINDFOR/stream",
            {
                "publishDateTimeFrom": to_iso(publish_from),
                "publishDateTimeTo": to_iso(publish_to),
            },
        )

    async def probe(self) -> bool:
        """Cheap reachability check used by the health endpoint.

        Asks for a one-hour slice so the response stays tiny.
        """
        now = dt.datetime.now(dt.UTC)
        try:
            await self._get_json(
                "/datasets/WINDFOR/stream",
                {
                    "publishDateTimeFrom": to_iso(now - dt.timedelta(hours=6)),
                    "publishDateTimeTo": to_iso(now),
                },
                retries=1,
            )
        except UpstreamError:
            return False
        return True

    async def _get_json(
        self, path: str, params: dict[str, str], *, retries: int | None = None
    ) -> list[dict]:
        """GET a dataset stream, retrying transient failures with backoff."""
        url = f"{self._base_url}{path}"
        attempts = self._max_retries if retries is None else max(1, retries)
        last_error: str = "no attempt made"

        for attempt in range(1, attempts + 1):
            try:
                response = await self._client.get(url, params=params)
            except httpx.TimeoutException as exc:
                last_error = f"timeout after {self._timeout}s: {exc!s}"
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc!s}"
            else:
                if response.status_code == 200:
                    return _as_rows(response, path)
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in RETRY_STATUS_CODES:
                    logger.warning("elexon %s failed permanently: %s", path, last_error)
                    raise UpstreamError(f"Elexon request to {path} failed: {last_error}")

            if attempt < attempts:
                delay = 0.5 * (2 ** (attempt - 1))
                logger.info(
                    "elexon %s attempt %d/%d failed (%s), retrying in %.1fs",
                    path,
                    attempt,
                    attempts,
                    last_error,
                    delay,
                )
                await asyncio.sleep(delay)

        logger.error("elexon %s exhausted %d attempts: %s", path, attempts, last_error)
        raise UpstreamError(
            f"Elexon request to {path} failed after {attempts} attempt(s): {last_error}"
        )


def _as_rows(response: httpx.Response, path: str) -> list[dict]:
    """Decode a stream response, tolerating the documented envelope form."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamError(f"Elexon {path} returned invalid JSON: {exc!s}") from exc
    if isinstance(payload, list):
        return payload
    # The non-stream endpoints wrap rows in {"data": [...]}; accept either.
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    raise UpstreamError(f"Elexon {path} returned an unexpected payload shape")
