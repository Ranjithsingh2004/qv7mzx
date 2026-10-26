/**
 * A bar whose rounded end always sits at the data end, never at the baseline.
 *
 * Recharts' own `radius` prop rounds a fixed pair of corners, which is wrong
 * for a diverging series: a bar below zero grows downwards, so its data end is
 * its *bottom* edge. This renders the path directly, picking the corners from
 * the sign, and paints the fill from the sign too -- warm above the line for
 * over-forecast, cool below it for under-forecast.
 */

const CORNER_RADIUS = 4;

export interface DivergingBarProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  /** The datum's value, whose sign decides direction. */
  value?: number | null;
  overColor: string;
  underColor: string;
}

export function DivergingBarShape({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  value,
  overColor,
  underColor,
}: DivergingBarProps) {
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(height)) return null;

  const positive = (value ?? 0) >= 0;
  const fill = positive ? overColor : underColor;

  // Recharts gives a negative height for bars below the baseline in some
  // configurations; normalise so the geometry below is always top-down.
  const top = height >= 0 ? y : y + height;
  const span = Math.abs(height);
  if (span === 0) return null;

  const radius = Math.min(CORNER_RADIUS, span, width / 2);

  const path = positive
    ? // rounded at the top (the data end), square where it meets the baseline
      `M${x},${top + span}
       L${x},${top + radius}
       Q${x},${top} ${x + radius},${top}
       L${x + width - radius},${top}
       Q${x + width},${top} ${x + width},${top + radius}
       L${x + width},${top + span} Z`
    : // square at the baseline, rounded at the bottom
      `M${x},${top}
       L${x},${top + span - radius}
       Q${x},${top + span} ${x + radius},${top + span}
       L${x + width - radius},${top + span}
       Q${x + width},${top + span} ${x + width},${top + span - radius}
       L${x + width},${top} Z`;

  return <path d={path} fill={fill} />;
}
