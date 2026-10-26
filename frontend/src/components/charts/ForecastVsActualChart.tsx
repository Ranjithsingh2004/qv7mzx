import { useMemo } from 'react';
import {
  Brush,
  CartesianGrid,
  Line,
  LineChart,
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
  actual: number | null;
  forecast: number | null;
  error: number | null;
  publish: string | null;
}

/**
 * Day-ahead forecast against measured outturn, on one MW axis.
 *
 * Both series are the same measure in the same units, so they share an axis.
 * The forecast is dashed as well as differently coloured, which keeps the two
 * distinguishable without relying on hue.
 *
 * Gaps are real gaps: an unmatched hour carries `null` and `connectNulls` is
 * off, so a missing period shows as a break in the line rather than being
 * interpolated across.
 */
export function ForecastVsActualChart({
  records,
  onSelectHour,
}: {
  records: PeriodRecord[];
  /** Selecting a point opens that hour in the vintage inspector. */
  onSelectHour?: (iso: string) => void;
}) {
  const palette = useChartPalette();

  const data = useMemo<Point[]>(
    () =>
      records.map((record) => ({
        t: new Date(record.target_start).getTime(),
        iso: record.target_start,
        actual: record.actual_mw,
        forecast: record.forecast_mw,
        error: record.error_mw,
        publish: record.forecast_publish_time,
      })),
    [records],
  );

  const columns: Column<Point>[] = [
    { key: 'time', header: 'Hour (London)', render: (row) => londonDateTime(row.iso) },
    { key: 'actual', header: 'Actual', numeric: true, render: (row) => mw(row.actual) },
    { key: 'forecast', header: 'Forecast', numeric: true, render: (row) => mw(row.forecast) },
    { key: 'error', header: 'Error', numeric: true, render: (row) => signedMw(row.error) },
  ];

  return (
    <ChartFrame
      height={380}
      description={
        `Line chart of day-ahead wind generation forecast against actual wind generation in ` +
        `megawatts, over ${records.length} hourly periods.`
      }
      table={
        <DataTable
          columns={columns}
          rows={data}
          rowKey={(row) => row.iso}
          caption="Forecast and actual wind generation by hour"
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 8, right: 12, bottom: 4, left: 4 }}
          onClick={(state) => {
            const point = state?.activePayload?.[0]?.payload as Point | undefined;
            if (point && onSelectHour) onSelectHour(point.iso);
          }}
        >
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
            label={{
              value: 'MW',
              position: 'insideTopLeft',
              fill: palette.textMuted,
              fontSize: 11,
              offset: 0,
            }}
          />
          {/* One crosshair tooltip lists every series at that hour, so the
              pointer never has to land on a 2px line. */}
          <Tooltip
            cursor={{ stroke: palette.axis, strokeWidth: 1 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const point = payload[0].payload as Point;
              return (
                <ChartTooltip
                  heading={`${londonDateTime(point.iso)} · London`}
                  rows={[
                    { label: 'Actual', value: mw(point.actual), color: palette.actual },
                    {
                      label: 'Forecast',
                      value: mw(point.forecast),
                      color: palette.forecast,
                      dashed: true,
                    },
                    { label: 'Error', value: signedMw(point.error) },
                    {
                      label: 'Forecast published',
                      value: point.publish ? londonDateTime(point.publish) : '—',
                    },
                  ]}
                />
              );
            }}
          />
          <Line
            type="monotone"
            dataKey="actual"
            name="Actual"
            stroke={palette.actual}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: palette.surface }}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="forecast"
            name="Forecast"
            stroke={palette.forecast}
            strokeWidth={2}
            strokeDasharray="5 4"
            strokeLinecap="round"
            strokeLinejoin="round"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: palette.surface }}
            connectNulls={false}
          />
          <Brush
            dataKey="t"
            height={26}
            travellerWidth={8}
            stroke={palette.axis}
            fill={palette.surface}
            tickFormatter={() => ''}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
