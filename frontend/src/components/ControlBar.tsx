import type { AlignmentMode, AnalysisParams } from '../api/types';
import './ControlBar.css';

interface Preset {
  label: string;
  from: string;
  to: string;
}

/**
 * The challenge scopes the work to purchase decisions taken in January 2026,
 * which is why that is the default and the first preset. The shorter presets
 * are for drilling into a week or a single day without typing dates.
 */
const PRESETS: Preset[] = [
  { label: 'January 2026 (full month)', from: '2026-01-01', to: '2026-01-31' },
  { label: 'First week', from: '2026-01-01', to: '2026-01-07' },
  { label: 'Mid-month week', from: '2026-01-12', to: '2026-01-18' },
  { label: 'Final week', from: '2026-01-25', to: '2026-01-31' },
];

const CUTOFF_TIMES = ['06:00', '07:00', '08:00', '09:00', '10:00', '12:00', '17:00', '23:00'];

/**
 * Every control that scopes the dashboard, in one row above the content.
 *
 * Filters scope everything below them, so each chart, statistic and table
 * re-renders against the same slice and the numbers always agree.
 */
export function ControlBar({
  params,
  onChange,
  alignmentModes,
  disabled,
}: {
  params: AnalysisParams;
  onChange: (next: Partial<AnalysisParams>) => void;
  alignmentModes: Record<string, string>;
  disabled?: boolean;
}) {
  const activePreset = PRESETS.find(
    (preset) => preset.from === params.decisionFrom && preset.to === params.decisionTo,
  );

  return (
    <form
      className="controls"
      aria-label="Analysis settings"
      onSubmit={(event) => event.preventDefault()}
    >
      <fieldset className="controls__group controls__group--wide" disabled={disabled}>
        <legend className="controls__legend">Decision window</legend>
        <div className="controls__presets" role="group" aria-label="Decision window presets">
          {PRESETS.map((preset) => {
            const active = activePreset?.label === preset.label;
            return (
              <button
                key={preset.label}
                type="button"
                className={active ? 'chip chip--active' : 'chip'}
                aria-pressed={active}
                onClick={() => onChange({ decisionFrom: preset.from, decisionTo: preset.to })}
              >
                {active && (
                  <span className="chip__check" aria-hidden="true">
                    ✔
                  </span>
                )}
                {preset.label}
              </button>
            );
          })}
        </div>
        <div className="controls__dates">
          <label className="field field--inline">
            <span className="field__label">From</span>
            <input
              className="field__input"
              type="date"
              value={params.decisionFrom}
              max={params.decisionTo}
              onChange={(event) => onChange({ decisionFrom: event.target.value })}
            />
          </label>
          <label className="field field--inline">
            <span className="field__label">To</span>
            <input
              className="field__input"
              type="date"
              value={params.decisionTo}
              min={params.decisionFrom}
              onChange={(event) => onChange({ decisionTo: event.target.value })}
            />
          </label>
        </div>
      </fieldset>

      <fieldset className="controls__group" disabled={disabled}>
        <legend className="controls__legend">Decision cutoff</legend>
        <div className="controls__row">
          <label className="field">
            <span className="field__label">Time (Europe/London)</span>
            <select
              className="field__input"
              value={params.cutoffTime}
              onChange={(event) => onChange({ cutoffTime: event.target.value })}
            >
              {CUTOFF_TIMES.map((time) => (
                <option key={time} value={time}>
                  {time}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field__label">Days before delivery</span>
            <select
              className="field__input"
              value={params.cutoffDaysBefore}
              onChange={(event) => onChange({ cutoffDaysBefore: Number(event.target.value) })}
            >
              <option value={0}>0 — same day</option>
              <option value={1}>1 — day-ahead</option>
              <option value={2}>2 — two days ahead</option>
            </select>
          </label>
        </div>
        <p className="controls__note">
          Only forecasts published at or before this moment are used. Default 09:00 on D-1 is a
          documented assumption, not a market rule.
        </p>
      </fieldset>

      <fieldset className="controls__group" disabled={disabled}>
        <legend className="controls__legend">Method</legend>
        <div className="controls__row">
          <label className="field">
            <span className="field__label">Actual alignment</span>
            <select
              className="field__input"
              value={params.alignment}
              onChange={(event) => onChange({ alignment: event.target.value as AlignmentMode })}
            >
              {Object.entries(alignmentModes).map(([value, description]) => (
                <option key={value} value={value} title={description}>
                  {value === 'hourly_mean' ? 'Hourly mean of periods' : 'Period starting on hour'}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field__label">MAPE floor</span>
            <select
              className="field__input"
              value={params.mapeFloorMw}
              onChange={(event) => onChange({ mapeFloorMw: Number(event.target.value) })}
            >
              <option value={0}>0 MW — include all</option>
              <option value={100}>100 MW</option>
              <option value={500}>500 MW</option>
              <option value={1000}>1,000 MW</option>
            </select>
          </label>
        </div>
      </fieldset>
    </form>
  );
}
