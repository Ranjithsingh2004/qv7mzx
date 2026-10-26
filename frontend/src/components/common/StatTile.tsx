import type { ReactNode } from 'react';
import { InfoHint } from './InfoHint';
import './StatTile.css';

interface StatTileProps {
  label: string;
  value: string;
  /** Secondary line: a comparison, a count, or the unit context. */
  detail?: ReactNode;
  /** Definition shown on demand, so the metric is never unexplained. */
  hint?: string;
  /** `hero` renders the one headline figure for the view. */
  size?: 'hero' | 'default';
  /** Signed emphasis for a direction-carrying value such as bias. */
  tone?: 'neutral' | 'over' | 'under';
}

export function StatTile({
  label,
  value,
  detail,
  hint,
  size = 'default',
  tone = 'neutral',
}: StatTileProps) {
  return (
    <div className={`stat stat--${size}`}>
      <div className="stat__label">
        <span>{label}</span>
        {hint && <InfoHint label={`About ${label}`} text={hint} />}
      </div>
      <div className={`stat__value stat__value--${tone}`}>{value}</div>
      {detail && <div className="stat__detail">{detail}</div>}
    </div>
  );
}
