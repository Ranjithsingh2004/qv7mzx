import type { ReactNode } from 'react';
import './ChartFrame.css';

/**
 * A chart plus its accessible equivalent.
 *
 * Recharts renders to SVG that a screen reader cannot usefully traverse, so
 * every chart ships a `<table>` of the same numbers. It stays in the DOM --
 * collapsed into a `<details>` rather than hidden -- so the values are
 * reachable by keyboard and by search, and so the colour-contrast relief rule
 * is satisfied for any series that needs it.
 */
export function ChartFrame({
  height,
  description,
  table,
  tableLabel = 'View as a table',
  children,
}: {
  height: number;
  /** A sentence naming what is plotted, for assistive technology. */
  description: string;
  table: ReactNode;
  tableLabel?: string;
  children: ReactNode;
}) {
  return (
    <div className="frame">
      <div className="frame__plot" style={{ height }} role="img" aria-label={description}>
        {children}
      </div>
      <details className="frame__table">
        <summary className="frame__summary">{tableLabel}</summary>
        <div className="frame__scroll">{table}</div>
      </details>
    </div>
  );
}
