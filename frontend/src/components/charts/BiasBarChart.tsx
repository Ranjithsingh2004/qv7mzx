import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useChartPalette } from '../../lib/palette';
import { count, mwTick, signedMw } from '../../lib/format';
import { DataTable } from '../common/DataTable';
import type { Column } from '../common/DataTable';
import { ChartFrame } from './ChartFrame';
import { ChartTooltip } from './ChartTooltip';
import { DivergingBarShape } from './DivergingBarShape';

export interface BiasDatum {
  key: string;
  label: string;
  bias: number | null;
  mae: number | null;
  hours: number;
}

/**
 * Mean bias across a set of ordered buckets -- delivery days, lead-time bands
 * or hours of the day.
 *
 * One diverging measure on one axis. MAE is deliberately *not* plotted beside
 * the bias bars: they are different quantities and overlaying them invites the
 * reader to compare heights that are not comparable. MAE stays in the tooltip
 * and the table, where it is read as a number.
 */
export function BiasBarChart({
  data,
  xLabel,
  height = 240,
  description,
}: {
  data: BiasDatum[];
  xLabel: string;
  height?: number;
  description: string;
}) {
  const palette = useChartPalette();

  const columns: Column<BiasDatum>[] = [
    { key: 'label', header: xLabel, render: (row) => row.label },
    { key: 'bias', header: 'Mean bias', numeric: true, render: (row) => signedMw(row.bias) },
    { key: 'mae', header: 'MAE', numeric: true, render: (row) => signedMw(row.mae) },
    { key: 'hours', header: 'Hours', numeric: true, render: (row) => count(row.hours) },
  ];

  return (
    <ChartFrame
      height={height}
      description={description}
      table={
        <DataTable
          columns={columns}
          rows={data}
          rowKey={(row) => row.key}
          caption={description}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={palette.grid} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: palette.textMuted, fontSize: 11 }}
            stroke={palette.axis}
            interval="preserveStartEnd"
            minTickGap={16}
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
              const row = payload[0].payload as BiasDatum;
              return (
                <ChartTooltip
                  heading={row.label}
                  rows={[
                    { label: 'Mean bias', value: signedMw(row.bias) },
                    { label: 'MAE', value: signedMw(row.mae) },
                    { label: 'Matched hours', value: count(row.hours) },
                  ]}
                />
              );
            }}
          />
          {/* 4px rounded data-end, square at the baseline, capped thickness. */}
          <Bar
            dataKey="bias"
            name="Mean bias"
            maxBarSize={24}
            isAnimationActive={false}
            shape={(props: object) => (
              <DivergingBarShape
                {...(props as { x: number; y: number; width: number; height: number })}
                value={(props as { bias?: number | null }).bias}
                overColor={palette.over}
                underColor={palette.under}
              />
            )}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
