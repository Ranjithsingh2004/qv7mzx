/**
 * Display formatting.
 *
 * Centralised so that MW values, percentages and timestamps are rendered
 * identically everywhere -- including the CSV header labels and the chart
 * tooltips, which is where inconsistency usually shows up first.
 */

const MW = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
const MW_PRECISE = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** A generation or error level in MW, e.g. `11,284 MW`. */
export function mw(value: number | null | undefined, options?: { precise?: boolean }): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const formatter = options?.precise ? MW_PRECISE : MW;
  return `${formatter.format(value)} MW`;
}

/** A signed MW value, so the direction of a bias reads at a glance. */
export function signedMw(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${MW.format(Math.abs(value))} MW`;
}

/** Compact MW for axis ticks: 0 / 5k / 10k. */
export function mwTick(value: number): string {
  if (value === 0) return '0';
  const abs = Math.abs(value);
  const sign = value < 0 ? '−' : '';
  if (abs >= 1000) {
    const thousands = abs / 1000;
    const text = thousands >= 10 ? thousands.toFixed(0) : thousands.toFixed(1).replace(/\.0$/, '');
    return `${sign}${text}k`;
  }
  return `${sign}${MW.format(abs)}`;
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${value.toFixed(digits)}%`;
}

export function signedPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

export function ratioAsPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function decimal(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return value.toFixed(digits);
}

export function hours(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${value.toFixed(digits)} h`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-GB').format(value);
}

/**
 * Timestamps are always labelled with their zone.
 *
 * The API returns UTC (`...Z`) plus a pre-computed London rendering, so the
 * frontend never re-derives a timezone and can never disagree with the
 * backend about a DST boundary.
 */
const LONDON_DATETIME = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/London',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const LONDON_TIME = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/London',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const LONDON_DATE = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/London',
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});

/** `15 Jan 18:00` in London local time. */
export function londonDateTime(iso: string): string {
  return LONDON_DATETIME.format(new Date(iso)).replace(',', '');
}

/** `18:00` in London local time. */
export function londonTime(iso: string): string {
  return LONDON_TIME.format(new Date(iso));
}

/** `15 Jan 2026`, from either an ISO instant or a plain `yyyy-MM-dd`. */
export function londonDate(value: string): string {
  const date = value.length === 10 ? new Date(`${value}T12:00:00Z`) : new Date(value);
  return LONDON_DATE.format(date);
}

/** Whether London is on BST at an instant, so labels can say which. */
export function londonZoneAbbrev(iso: string): 'GMT' | 'BST' {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    timeZoneName: 'short',
  }).formatToParts(new Date(iso));
  const name = parts.find((part) => part.type === 'timeZoneName')?.value ?? 'GMT';
  return name.includes('BST') ? 'BST' : 'GMT';
}

/** `Thu 15 Jan` for a `yyyy-MM-dd` delivery date. */
export function deliveryDayLabel(date: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    weekday: 'short',
    day: '2-digit',
    month: 'short',
  }).format(new Date(`${date}T12:00:00Z`));
}
