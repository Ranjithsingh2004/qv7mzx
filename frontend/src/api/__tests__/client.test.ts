import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  csvExportUrl,
  fetchAnalysis,
  fetchCutoffSweep,
  fetchVintages,
} from '../client';
import type { AnalysisParams } from '../types';

const PARAMS: AnalysisParams = {
  decisionFrom: '2026-01-01',
  decisionTo: '2026-01-31',
  cutoffTime: '09:00',
  cutoffDaysBefore: 1,
  alignment: 'hourly_mean',
  mapeFloorMw: 100,
};

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  const fn = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}), ...response });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe('request building', () => {
  beforeEach(() => mockFetch({}));

  it('sends every analysis parameter as a query string', async () => {
    const fn = mockFetch({ json: async () => ({ ok: true }) });
    await fetchAnalysis(PARAMS);
    const url = new URL((fn.mock.calls[0][0] as string), 'http://localhost');
    expect(url.pathname).toBe('/api/analysis');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      decision_from: '2026-01-01',
      decision_to: '2026-01-31',
      cutoff_time: '09:00',
      cutoff_days_before: '1',
      alignment: 'hourly_mean',
      mape_floor_mw: '100',
    });
  });

  it('uses a relative path so the app never depends on a hard-coded host', async () => {
    const fn = mockFetch({ json: async () => ({}) });
    await fetchAnalysis(PARAMS);
    expect(fn.mock.calls[0][0] as string).toMatch(/^\/api\//);
  });

  it('adds the target hour to a vintage request', async () => {
    const fn = mockFetch({ json: async () => ({}) });
    await fetchVintages(PARAMS, '2026-01-15T18:00:00Z');
    const url = new URL(fn.mock.calls[0][0] as string, 'http://localhost');
    expect(url.pathname).toBe('/api/analysis/vintages');
    expect(url.searchParams.get('target')).toBe('2026-01-15T18:00:00Z');
  });

  it('joins sweep cutoffs with commas', async () => {
    const fn = mockFetch({ json: async () => ({}) });
    await fetchCutoffSweep(PARAMS, ['06:00', '09:00', '17:00']);
    const url = new URL(fn.mock.calls[0][0] as string, 'http://localhost');
    expect(url.searchParams.get('cutoff_times')).toBe('06:00,09:00,17:00');
  });
});

describe('csvExportUrl', () => {
  it('points at the API export endpoint with the same parameters', () => {
    const url = new URL(csvExportUrl(PARAMS), 'http://localhost');
    expect(url.pathname).toBe('/api/analysis/export.csv');
    // The export must be scoped identically to what is on screen, or the file
    // and the dashboard would disagree.
    expect(url.searchParams.get('decision_from')).toBe('2026-01-01');
    expect(url.searchParams.get('cutoff_time')).toBe('09:00');
    expect(url.searchParams.get('alignment')).toBe('hourly_mean');
  });
});

describe('error handling', () => {
  it('surfaces the API message and code from an error body', async () => {
    mockFetch({
      ok: false,
      status: 422,
      json: async () => ({ code: 'invalid_request', message: 'cutoff_time: out of range' }),
    });
    await expect(fetchAnalysis(PARAMS)).rejects.toMatchObject({
      code: 'invalid_request',
      status: 422,
      message: 'cutoff_time: out of range',
    });
  });

  it('falls back to a generic message when the body is not JSON', async () => {
    mockFetch({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error('not json');
      },
    });
    await expect(fetchAnalysis(PARAMS)).rejects.toMatchObject({
      code: 'http_error',
      status: 500,
    });
  });

  it('reports a transport failure as a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const error = await fetchAnalysis(PARAMS).catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe('network_error');
  });

  it('propagates an abort rather than reporting it as a failure', async () => {
    // A superseded request must not surface an error to the user.
    const abort = new DOMException('aborted', 'AbortError');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort));
    await expect(fetchAnalysis(PARAMS)).rejects.toBe(abort);
  });
});
