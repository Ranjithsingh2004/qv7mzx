import { useEffect, useMemo, useState } from 'react';
import type { Analysis, AnalysisParams, PeriodRecord } from '../../api/types';
import { fetchVintages } from '../../api/client';
import { useAsync } from '../../hooks/useAsync';
import { ForecastVsActualChart } from '../charts/ForecastVsActualChart';
import { VintageChart } from '../charts/VintageChart';
import { Card } from '../common/Card';
import { Legend } from '../common/Legend';
import { ErrorState, LoadingState } from '../common/States';
import { StatTile } from '../common/StatTile';
import { count, deliveryDayLabel, hours, londonDateTime, mw, signedMw } from '../../lib/format';
import { useChartPalette } from '../../lib/palette';
import './sections.css';

const ALL_DAYS = 'all';

/**
 * The forecast-against-outturn view, plus the vintage inspector.
 *
 * The inspector is the part a reviewer should linger on: it takes one target
 * hour and shows every forecast ever published for it, with the ones that
 * arrived after the cutoff marked excluded. That is the difference between
 * measuring a forecast and measuring hindsight.
 */
export function ForecastVsActualSection({
  analysis,
  params,
  refreshing,
}: {
  analysis: Analysis;
  params: AnalysisParams;
  refreshing: boolean;
}) {
  const palette = useChartPalette();
  const [day, setDay] = useState<string>(ALL_DAYS);

  const matched = useMemo(
    () => analysis.records.filter((record) => record.status === 'matched'),
    [analysis.records],
  );

  // Default the inspector to the window's worst hour: the most instructive
  // single period, and the one a desk would ask about first.
  const worstHour = useMemo(
    () =>
      matched.reduce<PeriodRecord | null>(
        (worst, record) =>
          worst === null || Math.abs(record.error_mw ?? 0) > Math.abs(worst.error_mw ?? 0)
            ? record
            : worst,
        null,
      ),
    [matched],
  );

  const [targetIso, setTargetIso] = useState<string | null>(null);
  useEffect(() => {
    setTargetIso(worstHour?.target_start ?? analysis.records[0]?.target_start ?? null);
  }, [worstHour, analysis.records]);

  const visible = useMemo(
    () =>
      day === ALL_DAYS
        ? analysis.records
        : analysis.records.filter((record) => record.delivery_date === day),
    [analysis.records, day],
  );

  const vintages = useAsync(
    (signal) =>
      targetIso
        ? fetchVintages(params, targetIso, signal)
        : Promise.resolve(null),
    [params, targetIso],
  );

  const selectedRecord = analysis.records.find((record) => record.target_start === targetIso);

  return (
    <section className="section" id="forecast-vs-actual" aria-labelledby="fva-heading">
      <div className="section__head">
        <h2 className="section__title" id="fva-heading">
          Forecast versus actual
        </h2>
        <p className="section__lede">
          The dashed line is the forecast the desk actually had at the cutoff — not the latest
          forecast available today. Both series are wind generation in MW on one axis. Drag the
          handles beneath the chart to zoom, or pick a single delivery day.
        </p>
      </div>

      <Card
        refreshing={refreshing}
        title="Day-ahead wind forecast against measured outturn"
        subtitle={`${count(visible.length)} hourly periods · all times Europe/London`}
        actions={
          <div className="toolbar">
            <label className="field">
              <span className="field__label">Delivery day</span>
              <select
                className="field__input"
                value={day}
                onChange={(event) => setDay(event.target.value)}
              >
                <option value={ALL_DAYS}>All {count(analysis.daily.length)} days</option>
                {analysis.daily.map((row) => (
                  <option key={row.delivery_date} value={row.delivery_date}>
                    {deliveryDayLabel(row.delivery_date)}
                  </option>
                ))}
              </select>
            </label>
            <Legend
              items={[
                { label: 'Actual (FUELHH wind)', color: palette.actual, shape: 'line' },
                {
                  label: 'Forecast at cutoff (WINDFOR)',
                  color: palette.forecast,
                  shape: 'dashed-line',
                },
              ]}
            />
          </div>
        }
      >
        <ForecastVsActualChart records={visible} onSelectHour={setTargetIso} />
        <p className="section__note">
          Select any point to inspect the forecast vintages behind that hour. Breaks in a line are
          genuine gaps in the source data, never interpolated.
        </p>
      </Card>

      <Card
        refreshing={refreshing}
        title="Forecast vintage inspector"
        subtitle={
          selectedRecord
            ? `Every WINDFOR publication for ${londonDateTime(selectedRecord.target_start)} London`
            : 'Select an hour to inspect'
        }
      >
        {targetIso && (
          <div className="toolbar">
            <label className="field">
              <span className="field__label">Target hour</span>
              <select
                className="field__input"
                value={targetIso}
                onChange={(event) => setTargetIso(event.target.value)}
              >
                {analysis.records.map((record) => (
                  <option key={record.target_start} value={record.target_start}>
                    {londonDateTime(record.target_start)}
                    {record.error_mw !== null ? ` · error ${signedMw(record.error_mw)}` : ''}
                  </option>
                ))}
              </select>
            </label>
            {worstHour && targetIso !== worstHour.target_start && (
              <button
                type="button"
                className="button"
                onClick={() => setTargetIso(worstHour.target_start)}
              >
                Jump to the window&rsquo;s largest error
              </button>
            )}
          </div>
        )}

        {vintages.loading && <LoadingState label="Loading forecast vintages…" />}
        {vintages.error && <ErrorState error={vintages.error} onRetry={vintages.reload} />}

        {vintages.data && selectedRecord && (
          <>
            <div className="grid grid--metrics">
              <StatTile
                label="Vintages published for this hour"
                value={count(vintages.data.vintages.length)}
                detail={`${count(
                  vintages.data.vintages.filter((v) => v.eligible).length,
                )} available by the cutoff`}
              />
              <StatTile
                label="Forecast used"
                value={mw(selectedRecord.forecast_mw)}
                detail={
                  selectedRecord.forecast_publish_time
                    ? `Published ${londonDateTime(selectedRecord.forecast_publish_time)}`
                    : 'No eligible forecast'
                }
              />
              <StatTile
                label="Actual outturn"
                value={mw(selectedRecord.actual_mw)}
                detail={
                  selectedRecord.settlement_periods.length > 0
                    ? `Settlement periods ${selectedRecord.settlement_periods.join(' & ')}`
                    : 'No actual published'
                }
              />
              <StatTile
                label="Error on this hour"
                value={signedMw(selectedRecord.error_mw)}
                tone={(selectedRecord.error_mw ?? 0) >= 0 ? 'over' : 'under'}
                detail={`Lead time ${hours(selectedRecord.horizon_hours)}`}
              />
            </div>

            <VintageChart
              vintages={vintages.data.vintages}
              cutoffIso={vintages.data.decision_cutoff}
              targetIso={vintages.data.target_start}
            />

            <div className="callout">
              <p className="callout__title">Why this matters</p>
              <p className="callout__body">
                Forecasts for this hour kept being revised right up to delivery. Judging the
                decision against a later revision would credit the desk with information it did
                not have. Windsight takes the last publication at or before{' '}
                {vintages.data.cutoff_description} — here{' '}
                {londonDateTime(vintages.data.decision_cutoff)} — and discards the rest.
              </p>
            </div>
          </>
        )}
      </Card>
    </section>
  );
}
