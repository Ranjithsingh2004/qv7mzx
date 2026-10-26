import type { Analysis, Health } from '../api/types';
import type { ThemeChoice } from '../hooks/useTheme';
import { Badge } from './common/Badge';
import { londonDate } from '../lib/format';
import './Header.css';

const SECTIONS = [
  { id: 'overview', label: 'Overview' },
  { id: 'forecast-vs-actual', label: 'Forecast vs actual' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'error-analysis', label: 'Error analysis' },
  { id: 'detail', label: 'Period detail' },
  { id: 'decision-context', label: 'Using this' },
  { id: 'transparency', label: 'Data & method' },
];

export function Header({
  analysis,
  health,
  theme,
  onThemeChange,
}: {
  analysis: Analysis | null;
  health: Health | null;
  theme: ThemeChoice;
  onThemeChange: (next: ThemeChoice) => void;
}) {
  return (
    <header className="masthead">
      <div className="masthead__inner">
        <div className="masthead__brand">
          <span className="masthead__mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="28" height="28">
              <rect width="32" height="32" rx="7" fill="var(--series-actual)" opacity="0.14" />
              <path
                d="M5 20c4.2 0 6-8.5 10.5-8.5S21.8 20 27 20"
                fill="none"
                stroke="var(--series-actual)"
                strokeWidth="2.4"
                strokeLinecap="round"
              />
              <path
                d="M5 25.5c4.2 0 6-5.5 10.5-5.5s6.3 5.5 11.5 5.5"
                fill="none"
                stroke="var(--series-forecast)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="3.5 3"
              />
            </svg>
          </span>
          <div>
            <h1 className="masthead__title">Windsight</h1>
            <p className="masthead__tagline">
              Day-ahead wind forecast accuracy for GB power procurement
            </p>
          </div>
        </div>

        <div className="masthead__status">
          {/* The data-mode badge reflects the API's own declaration. There is
              no synthetic data path in this product, so it always reads live
              when an analysis has loaded, and shows nothing when none has. */}
          {analysis && (
            <Badge tone="info" glyph="●">
              {analysis.data_mode === 'live_elexon' ? 'Live Elexon BMRS data' : analysis.data_mode}
            </Badge>
          )}
          {health && health.upstream === 'reachable' && (
            <Badge tone="good" glyph="✔">
              Source API reachable
            </Badge>
          )}
          {health && health.upstream === 'unreachable' && (
            <Badge tone="critical" glyph="!">
              Source API unreachable
            </Badge>
          )}
          {analysis && (
            <span className="masthead__meta">
              Delivery {londonDate(analysis.delivery_from)} – {londonDate(analysis.delivery_to)}
            </span>
          )}
          <label className="masthead__theme">
            <span className="sr-only">Colour theme</span>
            <select
              value={theme}
              onChange={(event) => onThemeChange(event.target.value as ThemeChoice)}
              aria-label="Colour theme"
            >
              <option value="system">Theme: system</option>
              <option value="light">Theme: light</option>
              <option value="dark">Theme: dark</option>
            </select>
          </label>
        </div>
      </div>

      <nav className="masthead__nav" aria-label="Dashboard sections">
        <ul>
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a href={`#${section.id}`}>{section.label}</a>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
