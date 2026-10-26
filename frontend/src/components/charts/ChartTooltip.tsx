import './ChartTooltip.css';

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
  dashed?: boolean;
}

/**
 * The shared tooltip body.
 *
 * Values lead and labels follow -- the reader already knows which series they
 * are looking at and wants the number. Series are keyed with a short stroke
 * of their colour rather than a filled box, which at this density would be
 * data-weight ink doing a label's job.
 *
 * Every value here is also reachable without hovering, via the settlement
 * period table, so the tooltip enhances and never gates.
 */
export function ChartTooltip({ heading, rows }: { heading: string; rows: TooltipRow[] }) {
  return (
    <div className="tip" role="tooltip">
      <p className="tip__heading">{heading}</p>
      <dl className="tip__rows">
        {rows.map((row) => (
          <div className="tip__row" key={row.label}>
            <dt className="tip__label">
              {row.color && (
                <span
                  className={row.dashed ? 'tip__key tip__key--dashed' : 'tip__key'}
                  style={{ color: row.color }}
                  aria-hidden="true"
                />
              )}
              {row.label}
            </dt>
            <dd className="tip__value tnum">{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
