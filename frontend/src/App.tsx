import { useCallback, useState } from 'react';
import { fetchAnalysis, fetchHealth, fetchMeta } from './api/client';
import type { AnalysisParams } from './api/types';
import { ControlBar } from './components/ControlBar';
import { Header } from './components/Header';
import { ErrorState, LoadingState } from './components/common/States';
import { AccuracySection } from './components/sections/AccuracySection';
import { DecisionContextSection } from './components/sections/DecisionContextSection';
import { ErrorAnalysisSection } from './components/sections/ErrorAnalysisSection';
import { ForecastVsActualSection } from './components/sections/ForecastVsActualSection';
import { OverviewSection } from './components/sections/OverviewSection';
import { PeriodDetailSection } from './components/sections/PeriodDetailSection';
import { TransparencySection } from './components/sections/TransparencySection';
import { useAsync } from './hooks/useAsync';
import { useTheme } from './hooks/useTheme';
import './App.css';

/**
 * Defaults match the challenge scope: purchase decisions taken in January
 * 2026, judged against the forecast available by 09:00 London on the day
 * before delivery.
 */
const DEFAULT_PARAMS: AnalysisParams = {
  decisionFrom: '2026-01-01',
  decisionTo: '2026-01-31',
  cutoffTime: '09:00',
  cutoffDaysBefore: 1,
  alignment: 'hourly_mean',
  mapeFloorMw: 100,
};

const FALLBACK_ALIGNMENT_MODES = {
  hourly_mean: 'Mean of the half-hourly settlement periods inside each hour',
  period_start: 'Only the settlement period starting exactly on the hour',
};

export default function App() {
  const [params, setParams] = useState<AnalysisParams>(DEFAULT_PARAMS);
  const { choice: theme, setChoice: setTheme } = useTheme();

  const analysis = useAsync((signal) => fetchAnalysis(params, signal), [params]);
  // Static reference data: fetched once, never re-fetched on a parameter change.
  const meta = useAsync((signal) => fetchMeta(signal), []);
  const health = useAsync((signal) => fetchHealth(true, signal), []);

  const update = useCallback((next: Partial<AnalysisParams>) => {
    setParams((current) => ({ ...current, ...next }));
  }, []);

  const alignmentModes = meta.data?.alignment_modes ?? FALLBACK_ALIGNMENT_MODES;

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to dashboard content
      </a>
      <Header
        analysis={analysis.data}
        health={health.data}
        theme={theme}
        onThemeChange={setTheme}
      />

      <main className="shell" id="main">
        <ControlBar
          params={params}
          onChange={update}
          alignmentModes={alignmentModes}
          disabled={analysis.loading}
        />

        {analysis.loading && <LoadingState />}

        {/* Shown above the dashboard rather than in place of it: a failed
            refetch keeps the last good analysis on screen instead of blanking
            everything, while still reporting the failure. */}
        {analysis.error && <ErrorState error={analysis.error} onRetry={analysis.reload} />}

        {analysis.data && (
          <>
            <OverviewSection
              analysis={analysis.data}
              meta={meta.data}
              refreshing={analysis.refreshing}
            />
            <ForecastVsActualSection
              analysis={analysis.data}
              params={params}
              refreshing={analysis.refreshing}
            />
            <AccuracySection
              analysis={analysis.data}
              params={params}
              meta={meta.data}
              refreshing={analysis.refreshing}
            />
            <ErrorAnalysisSection analysis={analysis.data} refreshing={analysis.refreshing} />
            <PeriodDetailSection
              analysis={analysis.data}
              params={params}
              refreshing={analysis.refreshing}
            />
            <DecisionContextSection
              analysis={analysis.data}
              refreshing={analysis.refreshing}
            />
            <TransparencySection
              analysis={analysis.data}
              meta={meta.data}
              health={health.data}
              refreshing={analysis.refreshing}
            />
          </>
        )}
      </main>

      <footer className="footer">
        <p>
          Windsight — day-ahead wind forecast accuracy, built on Elexon BMRS open data (FUELHH and
          WINDFOR). Pilot build for evaluation; not a trading system.
        </p>
        <p className="footer__meta">
          {meta.data ? `API metric definitions loaded · ${health.data?.version ?? ''}` : ''}
        </p>
      </footer>
    </>
  );
}
