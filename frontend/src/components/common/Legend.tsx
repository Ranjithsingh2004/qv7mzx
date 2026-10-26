import './Legend.css';

export interface LegendItem {
  label: string;
  color: string;
  /** Legends mirror the mark: a line key for lines, a swatch for bars/areas. */
  shape?: 'line' | 'dashed-line' | 'swatch';
}

/**
 * A chart legend, always present where two or more series are plotted.
 *
 * Identity comes from the keyed mark beside the text; the label itself stays
 * in a text token rather than wearing the series colour.
 */
export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="legend">
      {items.map((item) => (
        <li className="legend__item" key={item.label}>
          <span
            className={`legend__key legend__key--${item.shape ?? 'line'}`}
            style={{ color: item.color }}
            aria-hidden="true"
          />
          <span className="legend__label">{item.label}</span>
        </li>
      ))}
    </ul>
  );
}
