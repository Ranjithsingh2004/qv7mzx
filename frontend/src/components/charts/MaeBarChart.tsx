import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useChartPalette } from '../../lib/palette';
import { count, hours, mw, mwTick, signedMw } from '../../lib/format';
import { DataTable } from '../common/DataTable';
import type { Column } from '../common/DataTable';
import { ChartFrame } from './ChartFrame';
import { ChartTooltip } from './ChartTooltip';

export interface MaeDatum {
  key: string;
  label: string;
  mae: number | null;
  rmse?: number | null;
  bias?: number | null;
  hours?: number;
  meanHorizon?: number | null;
  detail?: string;
}

/**
 * A single magnitude measure across labelled categories.
 *
 * One series, one colour -- the bar length already encodes the magnitude, so
 * shading bars darker where they are bigger would spend the only free channel
 * on information the chart shows twice. With few enough bars every value is
 * labelled on the cap, which is what satisfies the contrast relief rule.
 */
export function MaeBarChart({
  data,
  xLabel,
  height = 240,
  description,
  labelValues = true,
}: {
  data: MaeDatum[];
  xLabel: string;
  height?: number;
  description: string;
  labelValues?: boolean;
}) {
  const palette = useChartPalette();

  const columns: Column<MaeDatum>[] = [
    { key: 'label', header: xLabel, render: (row) => row.label },
    { key: 'mae', header: 'MAE', numeric: true, render: (row) => mw(row.mae) },
    ...(data.some((row) => row.rmse !== undefined)
      ? [{ key: 'rmse', header: 'RMSE', numeric: true, render: (row: MaeDatum) => mw(row.rmse) }]
      : []),
    ...(data.some((row) => row.bias !== undefined)
      ? [
          {
            key: 'bias',
            header: 'Bias',
            numeric: true,
            render: (row: MaeDatum) => signedMw(row.bias),
          },
        ]
      : []),
    ...(data.some((row) => row.meanHorizon !== undefined)
      ? [
          {
            key: 'horizon',
            header: 'Mean lead time',
            numeric: true,
            render: (row: MaeDatum) => hours(row.meanHorizon),
          },
        ]
      : []),
  ];

  return (
    <ChartFrame
      height={height}
      description={description}
      table={
        <DataTable columns={columns} rows={data} rowKey={(row) => row.key} caption={description} />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 22, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={palette.grid} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: palette.textMuted, fontSize: 11 }}
            stroke={palette.axis}
            interval={0}
          />
          <YAxis
            tickFormatter={mwTick}
            tick={{ fill: palette.textMuted, fontSize: 11 }}
            stroke={palette.axis}
            width={48}
          />
          <Tooltip
            cursor={{ fill: palette.grid, fillOpacity: 0.35 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as MaeDatum;
              return (
                <ChartTooltip
                  heading={row.detail ? `${row.label} — ${row.detail}` : row.label}
                  rows={[
                    { label: 'MAE', value: mw(row.mae) },
                    ...(row.rmse !== undefined ? [{ label: 'RMSE', value: mw(row.rmse) }] : []),
                    ...(row.bias !== undefined
                      ? [{ label: 'Bias', value: signedMw(row.bias) }]
                      : []),
                    ...(row.meanHorizon !== undefined
                      ? [{ label: 'Mean lead time', value: hours(row.meanHorizon) }]
                      : []),
                    ...(row.hours !== undefined
                      ? [{ label: 'Matched hours', value: count(row.hours) }]
                      : []),
                  ]}
                />
              );
            }}
          />
          <Bar
            dataKey="mae"
            name="MAE"
            fill={palette.actual}
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          >
            {labelValues && (
              <LabelList
                dataKey="mae"
                position="top"
                offset={8}
                formatter={(value: number) => mwTick(value)}
                fill={palette.textSecondary}
                fontSize={11}
              />
            )}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
