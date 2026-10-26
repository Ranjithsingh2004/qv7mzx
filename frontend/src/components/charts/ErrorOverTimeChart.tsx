import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { PeriodRecord } from '../../api/types';
import { useChartPalette } from '../../lib/palette';
import { londonDateTime, mw, mwTick, signedMw } from '../../lib/format';
import { DataTable } from '../common/DataTable';
import type { Column } from '../common/DataTable';
import { ChartFrame } from './ChartFrame';
import { ChartTooltip } from './ChartTooltip';

interface Point {
  t: number;
  iso: string;
  error: number | null;
  actual: number | null;
  forecast: number | null;
}

/**
 * Signed forecast error through the window.
 *
 * Error has a sign that means something operationally, so this is a diverging
 * encoding: a warm hue above the zero line for over-forecast, a cool hue below
 * for under-forecast, and a labelled zero reference between them. Sign is also
 * stated in the tooltip text, so the polarity never depends on hue alone.
 */
export function ErrorOverTimeChart({ records }: { records: PeriodRecord[] }) {
  const palette = useChartPalette();

  const data = useMemo<Point[]>(
    () =>
      records.map((record) => ({
        t: new Date(record.target_start).getTime(),
        iso: record.target_start,
        error: record.error_mw,
        actual: record.actual_mw,
        forecast: record.forecast_mw,
      })),
    [records],
  );

  const columns: Column<Point>[] = [
    { key: 'time', header: 'Hour (London)', render: (row) => londonDateTime(row.iso) },
    { key: 'error', header: 'Error', numeric: true, render: (row) => signedMw(row.error) },
    {
      key: 'dir',
      header: 'Direction',
      render: (row) =>
        row.error === null ? '—' : row.error > 0 ? 'Over-forecast' : 'Under-forecast',
    },
  ];

  return (
    <ChartFrame
      height={260}
      description={
        'Column chart of forecast minus actual wind generation in megawatts by hour. ' +
        'Columns above zero are over-forecast, columns below zero are under-forecast.'
      }
      table={
        <DataTable
          columns={columns}
          rows={data}
          rowKey={(row) => row.iso}
          caption="Forecast error by hour"
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }} barGap={0}>
          <CartesianGrid stroke={palette.grid} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(value: number) => londonDateTime(new Date(value).toISOString())}
            tick={{ fill: palette.textMuted, fontSize: 11 }}
            stroke={palette.axis}
            minTickGap={56}
          />
          <YAxis
            tickFormatter={mwTick}
            tick={{ fill: palette.textMuted, fontSize: 11 }}
            stroke={palette.axis}
            width={48}
          />
          <ReferenceLine y={0} stroke={palette.axis} strokeWidth={1} />
          <Tooltip
            cursor={{ fill: palette.grid, fillOpacity: 0.35 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const point = payload[0].payload as Point;
              const direction =
                point.error === null
                  ? 'No matched data'
                  : point.error > 0
                    ? 'Over-forecast'
                    : 'Under-forecast';
              return (
                <ChartTooltip
                  heading={`${londonDateTime(point.iso)} · London`}
                  rows={[
                    { label: 'Error', value: signedMw(point.error) },
                    { label: 'Direction', value: direction },
                    { label: 'Actual', value: mw(point.actual) },
                    { label: 'Forecast', value: mw(point.forecast) },
                  ]}
                />
              );
            }}
          />
          <Bar dataKey="error" name="Forecast error" isAnimationActive={false}>
            {data.map((point) => (
              <Cell
                key={point.iso}
                fill={(point.error ?? 0) >= 0 ? palette.over : palette.under}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
