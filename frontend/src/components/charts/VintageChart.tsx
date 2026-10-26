import { useMemo } from 'react';
import {
  CartesianGrid,
  Cell,
  Line,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { Vintage } from '../../api/types';
import { useChartPalette } from '../../lib/palette';
import { hours, londonDateTime, mw, mwTick } from '../../lib/format';
import { Badge } from '../common/Badge';
import { DataTable } from '../common/DataTable';
import type { Column } from '../common/DataTable';
import { ChartFrame } from './ChartFrame';
import { ChartTooltip } from './ChartTooltip';

interface Point extends Vintage {
  t: number;
}

/**
 * Every forecast vintage for one target hour, against the decision cutoff.
 *
 * This is the audit view for the product's central rule. The horizontal axis
 * is *publication* time, not target time, so the reader watches the forecast
 * for a single fixed hour change as new runs arrive. The cutoff is drawn as a
 * labelled vertical reference: points to its left were available to the
 * decision, points to its right were not and are rendered in a muted ink with
 * an "excluded" label, never silently dropped.
 *
 * Eligibility is carried by fill, by position relative to the labelled cutoff
 * line, and by a text column in the table, so it never rests on colour alone.
 */
export function VintageChart({
  vintages,
  cutoffIso,
  targetIso,
}: {
  vintages: Vintage[];
  cutoffIso: string;
  targetIso: string;
}) {
  const palette = useChartPalette();

  const data = useMemo<Point[]>(
    () => vintages.map((v) => ({ ...v, t: new Date(v.publish_time).getTime() })),
    [vintages],
  );
  const cutoffAt = new Date(cutoffIso).getTime();
  const selected = data.find((point) => point.selected);

  // Successive runs of the same forecast differ by a few hundred MW against a
  // level of twenty-odd gigawatts, so a zero-based axis flattens the revision
  // path into a straight line and hides the one thing this chart is for. The
  // axis is zoomed to the data with padding instead. That is safe here because
  // nothing is encoded by length -- these are points on a shared level scale,
  // not bars whose height is the measure -- and the axis stays labelled in MW.
  const values = data.map((point) => point.generation);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const pad = Math.max((high - low) * 0.25, 50);
  const domain: [number, number] = [
    Math.max(0, Math.floor((low - pad) / 50) * 50),
    Math.ceil((high + pad) / 50) * 50,
  ];

  const columns: Column<Point>[] = [
    { key: 'pub', header: 'Published (London)', render: (row) => londonDateTime(row.publish_time) },
    { key: 'gen', header: 'Forecast', numeric: true, render: (row) => mw(row.generation) },
    { key: 'lead', header: 'Lead time', numeric: true, render: (row) => hours(row.horizon_hours) },
    {
      key: 'state',
      header: 'Used for this decision',
      render: (row) =>
        row.selected ? (
          <Badge tone="good" glyph="✔">
            Selected
          </Badge>
        ) : row.eligible ? (
          <Badge tone="neutral">Available, superseded</Badge>
        ) : (
          <Badge tone="warning" glyph="✕">
            Excluded — published after cutoff
          </Badge>
        ),
    },
  ];

  return (
    <ChartFrame
      height={300}
      description={
        `Forecast values for the single target hour ${londonDateTime(targetIso)} London, ` +
        `plotted against the time each forecast was published. A vertical reference line ` +
        `marks the decision cutoff; the ${data.filter((p) => !p.eligible).length} points to ` +
        `its right were published too late to inform the decision and are excluded.`
      }
      table={
        <DataTable
          columns={columns}
          rows={data}
          rowKey={(row) => row.publish_time}
          caption="Forecast vintages for the selected target hour"
        />
      }
      tableLabel="View every vintage as a table"
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={palette.grid} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(value: number) => londonDateTime(new Date(value).toISOString())}
            tick={{ fill: palette.textMuted, fontSize: 11 }}
            stroke={palette.axis}
            minTickGap={64}
            label={{
              value: 'Forecast publication time',
              position: 'insideBottom',
              offset: -2,
              fill: palette.textMuted,
              fontSize: 11,
            }}
          />
          <YAxis
            domain={domain}
            allowDataOverflow={false}
            tickFormatter={mwTick}
            tick={{ fill: palette.textMuted, fontSize: 11 }}
            stroke={palette.axis}
            width={52}
            label={{
              value: 'MW (axis zoomed to range)',
              angle: -90,
              position: 'insideLeft',
              style: { textAnchor: 'middle' },
              fill: palette.textMuted,
              fontSize: 11,
            }}
          />
          {/* The line only joins successive runs so the revision path is
              readable; identity still comes from the points. */}
          <Line
            type="linear"
            dataKey="generation"
            stroke={palette.axis}
            strokeWidth={2}
            dot={false}
            activeDot={false}
            isAnimationActive={false}
            legendType="none"
          />
          <ReferenceLine
            x={cutoffAt}
            stroke={palette.textPrimary}
            strokeWidth={1}
            strokeDasharray="4 3"
            label={{
              value: 'Decision cutoff',
              position: 'top',
              fill: palette.textSecondary,
              fontSize: 11,
            }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const point = payload[payload.length - 1].payload as Point;
              return (
                <ChartTooltip
                  heading={`Published ${londonDateTime(point.publish_time)} · London`}
                  rows={[
                    { label: 'Forecast', value: mw(point.generation) },
                    { label: 'Lead time', value: hours(point.horizon_hours) },
                    {
                      label: 'Status',
                      value: point.selected
                        ? 'Selected for this decision'
                        : point.eligible
                          ? 'Available but superseded'
                          : 'Excluded — after cutoff',
                    },
                  ]}
                />
              );
            }}
          />
          {/* Each point carries a 2px surface ring so it stays legible where
              it crosses the revision line, and the ring is part of its hit
              target. */}
          <Scatter dataKey="generation" isAnimationActive={false}>
            {data.map((point) => (
              <Cell
                key={point.publish_time}
                fill={
                  point.selected
                    ? palette.forecast
                    : point.eligible
                      ? palette.actual
                      : palette.surface
                }
                stroke={point.eligible ? palette.surface : palette.textMuted}
                strokeWidth={2}
                r={point.selected ? 7 : 5}
              />
            ))}
          </Scatter>
        </ComposedChart>
      </ResponsiveContainer>
      {selected && (
        <p className="sr-only">
          The selected forecast for this hour is {mw(selected.generation)}, published{' '}
          {londonDateTime(selected.publish_time)} London, {hours(selected.horizon_hours)} ahead of
          delivery.
        </p>
      )}
    </ChartFrame>
  );
}
