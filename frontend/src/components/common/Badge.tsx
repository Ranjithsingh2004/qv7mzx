import type { ReactNode } from 'react';
import './Badge.css';

type Tone = 'neutral' | 'good' | 'warning' | 'critical' | 'info';

/**
 * A small status marker.
 *
 * Every tone pairs its colour with a glyph and a text label, so state is never
 * communicated by colour alone.
 */
export function Badge({
  tone = 'neutral',
  children,
  glyph,
}: {
  tone?: Tone;
  children: ReactNode;
  glyph?: string;
}) {
  return (
    <span className={`badge badge--${tone}`}>
      {glyph && (
        <span className="badge__glyph" aria-hidden="true">
          {glyph}
        </span>
      )}
      {children}
    </span>
  );
}
