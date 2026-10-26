import { useMemo } from 'react';
import type { Analysis } from '../../api/types';
import { BiasBarChart, type BiasDatum } from '../charts/BiasBarChart';
import { ErrorOverTimeChart } from '../charts/ErrorOverTimeChart';
import { Card } from '../common/Card';
import { Legend } from '../common/Legend';
import { EmptyState } from '../common/States';
import { count, deliveryDayLabel, mw, percent, signedMw } from '../../lib/format';
import { useChartPalette } from '../../lib/palette';
import './sections.css';

/**
 * Where the error comes from: through time, by lead time, by hour of day, and
 * day by day. The question each chart answers is whether the miss is
 * systematic -- and therefore correctable -- or not.
 */
export function ErrorAnalysisSection({
  analysis,
  refreshing,
}: {
  analysis: Analysis;
  refreshing: boolean;
}) {
  const palette = useChartPalette();
  const { metrics, coverage } = analysis;

  const daily = useMemo<BiasDatum[]>(
    () =>
      analysis.daily.map((row) => ({
        key: row.delivery_date,
        label: deliveryDayLabel(row.delivery_date),
        bias: row.bias_mw,
        mae: row.mae_mw,
        hours: row.matched_hours,
      })),
    [analysis.daily],
  );

  const horizon = useMemo<BiasDatum[]>(
    () =>
      analysis.by_horizon.map((row) => ({
        key: `${row.horizon_from_hours}`,
        label: `${row.horizon_from_hours}–${row.horizon_to_hours} h`,
        bias: row.bias_mw,
        mae: row.mae_mw,
        hours: row.matched_hours,
      })),
    [analysis.by_horizon],
  );

  const hourOfDay = useMemo<BiasDatum[]>(
    () =>
      analysis.by_hour_of_day.map((row) => ({
        key: `${row.hour_of_day}`,
        label: `${String(row.hour_of_day).padStart(2, '0')}:00`,
        bias: row.bias_mw,
        mae: row.mae_mw,
        hours: row.matched_hours,
      })),
    [analysis.by_hour_of_day],
  );

  const daysOver = analysis.daily.filter((row) => (row.bias_mw ?? 0) > 0).length;
  const daysScored = analysis.daily.filter((row) => row.bias_mw !== null).length;
  const overShare = metrics.matched_hours
    ? (metrics.hours_over_forecast / metrics.matched_hours) * 100
    : null;

  const divergingLegend = (
    <Legend
      items={[
        { label: 'Over-forecast (forecast above actual)', color: palette.over, shape: 'swatch' },
        { label: 'Under-forecast (forecast below actual)', color: palette.under, shape: 'swatch' },
      ]}
    />
  );

  return (
    <section className="section" id="error-analysis" aria-labelledby="error-heading">
      <div className="section__head">
        <h2 className="section__title" id="error-heading">
          Forecast error analysis
        </h2>
        <p className="section__lede">
          Forecast minus actual, so a column above the line is an hour where wind was
          over-predicted and the desk would have under-bought thermal cover.
        </p>
      </div>

      <Card
        refreshing={refreshing}
        title="Forecast error through the window"
        subtitle="One column per target hour"
        actions={divergingLegend}
      >
        <ErrorOverTimeChart records={analysis.records} />
        <p className="section__note">
          {overShare !== null && (
            <>
              {count(metrics.hours_over_forecast)} of {count(metrics.matched_hours)} matched hours
              ({percent(overShare)}) were over-forecast, and {daysOver} of {daysScored} delivery
              days had a positive mean bias.{' '}
            </>
          )}
          {coverage.hours_missing_forecast + coverage.hours_missing_actual > 0
            ? `${count(
                coverage.hours_missing_forecast + coverage.hours_missing_actual,
              )} hours have no column because the source data is missing — a gap, not a zero.`
            : 'No hours are missing from this window, so every column is a measured error.'}
        </p>
      </Card>

      <div className="grid grid--two">
        <Card
          refreshing={refreshing}
          title="Error by forecast lead time"
          subtitle="How far ahead of delivery the selected forecast was published"
          actions={divergingLegend}
        >
          {horizon.length === 0 ? (
            <EmptyState
              title="No matched hours to group"
              body="No hour in this window has both an eligible forecast and an actual."
            />
          ) : (
            <BiasBarChart
              data={horizon}
              xLabel="Lead time"
              description="Column chart of mean forecast bias in megawatts grouped by forecast lead time in hours."
            />
          )}
          <p className="section__note">
            A single decision cutoff still produces a spread of lead times, because one forecast
            publication covers a whole delivery day: the first hour of the day is nearer to
            publication than the last.
          </p>
        </Card>

        <Card
          refreshing={refreshing}
          title="Error by hour of the delivery day"
          subtitle="Hours counted from midnight London, so the buckets follow the trader's clock"
          actions={divergingLegend}
        >
          {hourOfDay.length === 0 ? (
            <EmptyState
              title="No matched hours to group"
              body="No hour in this window has both an eligible forecast and an actual."
            />
          ) : (
            <BiasBarChart
              data={hourOfDay}
              xLabel="Hour of day"
              description="Column chart of mean forecast bias in megawatts for each hour of the delivery day."
            />
          )}
        </Card>
      </div>

      <Card
        refreshing={refreshing}
        title="Mean bias by delivery day"
        subtitle="Whether the forecast leaned the same way every day, or only on particular ones"
        actions={divergingLegend}
      >
        {daily.length === 0 ? (
          <EmptyState title="No delivery days in range" body="Widen the decision window." />
        ) : (
          <BiasBarChart
            data={daily}
            xLabel="Delivery day"
            height={260}
            description="Column chart of mean forecast bias in megawatts for each delivery day in the window."
          />
        )}
        <p className="section__note">
          Worst day in this window:{' '}
          {(() => {
            const worst = [...analysis.daily]
              .filter((row) => row.mae_mw !== null)
              .sort((a, b) => (b.mae_mw ?? 0) - (a.mae_mw ?? 0))[0];
            return worst
              ? `${deliveryDayLabel(worst.delivery_date)}, MAE ${mw(
                  worst.mae_mw,
                )} against mean outturn of ${mw(worst.mean_actual_mw)} (bias ${signedMw(
                  worst.bias_mw,
                )}).`
              : 'not available.';
          })()}
        </p>
      </Card>
    </section>
  );
}
