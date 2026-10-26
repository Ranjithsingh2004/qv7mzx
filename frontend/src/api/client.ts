/**
 * The single place the frontend talks to the API.
 *
 * `API_BASE` is empty by default so every request is a relative `/api/...`
 * call against whatever origin serves the app. That is what keeps the
 * deployment free of a hard-coded backend host: in development Vite proxies
 * `/api`, in production the platform rewrites it to the Python function.
 * `VITE_API_BASE_URL` is only needed when the API is on a different origin.
 */

import type {
  Analysis,
  AnalysisParams,
  CutoffSweepResponse,
  Health,
  Meta,
  VintageResponse,
} from './types';

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

/** An error carrying the API's `{code, message}` body, or a transport failure. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

function query(params: AnalysisParams): URLSearchParams {
  return new URLSearchParams({
    decision_from: params.decisionFrom,
    decision_to: params.decisionTo,
    cutoff_time: params.cutoffTime,
    cutoff_days_before: String(params.cutoffDaysBefore),
    alignment: params.alignment,
    mape_floor_mw: String(params.mapeFloorMw),
  });
}

/** Build the URL for a path and search params, for fetching or for a download link. */
export function apiUrl(path: string, search?: URLSearchParams): string {
  const suffix = search && [...search.keys()].length > 0 ? `?${search}` : '';
  return `${API_BASE}${path}${suffix}`;
}

async function request<T>(path: string, search?: URLSearchParams, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path, search), {
      signal,
      headers: { Accept: 'application/json' },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError(
      'Could not reach the analytics API. Check your connection and try again.',
      'network_error',
      0,
    );
  }

  if (!response.ok) {
    // The API returns {code, message} for both its own errors and FastAPI's
    // parameter errors, so one shape covers every failure.
    let code = 'http_error';
    let message = `The API responded with HTTP ${response.status}.`;
    try {
      const body = (await response.json()) as { code?: string; message?: string };
      if (body.code) code = body.code;
      if (body.message) message = body.message;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(message, code, response.status);
  }

  return (await response.json()) as T;
}

export function fetchAnalysis(params: AnalysisParams, signal?: AbortSignal): Promise<Analysis> {
  return request<Analysis>('/api/analysis', query(params), signal);
}

export function fetchMeta(signal?: AbortSignal): Promise<Meta> {
  return request<Meta>('/api/meta', undefined, signal);
}

export function fetchHealth(probe = false, signal?: AbortSignal): Promise<Health> {
  return request<Health>(
    '/api/health',
    probe ? new URLSearchParams({ probe: 'true' }) : undefined,
    signal,
  );
}

export function fetchVintages(
  params: AnalysisParams,
  targetIso: string,
  signal?: AbortSignal,
): Promise<VintageResponse> {
  const search = query(params);
  search.set('target', targetIso);
  return request<VintageResponse>('/api/analysis/vintages', search, signal);
}

export function fetchCutoffSweep(
  params: AnalysisParams,
  cutoffTimes: string[],
  signal?: AbortSignal,
): Promise<CutoffSweepResponse> {
  const search = query(params);
  search.set('cutoff_times', cutoffTimes.join(','));
  return request<CutoffSweepResponse>('/api/analysis/cutoff-sweep', search, signal);
}

/** The CSV endpoint is a plain link, so the browser handles the download. */
export function csvExportUrl(params: AnalysisParams): string {
  return apiUrl('/api/analysis/export.csv', query(params));
}
