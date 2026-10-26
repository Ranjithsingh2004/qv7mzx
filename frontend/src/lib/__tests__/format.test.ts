import { describe, expect, it } from 'vitest';
import {
  count,
  decimal,
  deliveryDayLabel,
  hours,
  londonDate,
  londonDateTime,
  londonTime,
  londonZoneAbbrev,
  mw,
  mwTick,
  percent,
  ratioAsPercent,
  signedMw,
  signedPercent,
} from '../format';

describe('mw', () => {
  it('formats a generation level with thousands separators', () => {
    expect(mw(11284)).toBe('11,284 MW');
  });

  it('rounds to whole megawatts by default', () => {
    expect(mw(2038.913)).toBe('2,039 MW');
  });

  it.each([null, undefined, Number.NaN, Number.POSITIVE_INFINITY])(
    'renders an em dash rather than a number for %s',
    (value) => {
      // A missing value must never look like zero generation.
      expect(mw(value as number | null)).toBe('—');
    },
  );
});

describe('signedMw', () => {
  it('marks an over-forecast with a plus', () => {
    expect(signedMw(1747.9)).toBe('+1,748 MW');
  });

  it('marks an under-forecast with a true minus sign', () => {
    expect(signedMw(-301)).toBe('−301 MW');
  });

  it('leaves zero unsigned', () => {
    expect(signedMw(0)).toBe('0 MW');
  });

  it('renders a missing value as an em dash', () => {
    expect(signedMw(null)).toBe('—');
  });
});

describe('mwTick', () => {
  it.each([
    [0, '0'],
    [500, '500'],
    [5500, '5.5k'],
    [17000, '17k'],
    [-3500, '−3.5k'],
  ])('compacts %s to %s', (input, expected) => {
    expect(mwTick(input)).toBe(expected);
  });
});

describe('percentages', () => {
  it('formats a percentage to one decimal by default', () => {
    expect(percent(18.0699)).toBe('18.1%');
  });

  it('honours an explicit precision', () => {
    expect(percent(22.0449, 2)).toBe('22.04%');
  });

  it('signs a percentage', () => {
    expect(signedPercent(-3.25)).toBe('−3.3%');
  });

  it('converts a 0-1 ratio into a percentage', () => {
    expect(ratioAsPercent(0.487)).toBe('49%');
  });

  it('renders a missing ratio as an em dash', () => {
    expect(ratioAsPercent(null)).toBe('—');
  });
});

describe('decimal, hours and count', () => {
  it('formats a correlation to three places', () => {
    expect(decimal(0.9312345)).toBe('0.931');
  });

  it('formats a lead time', () => {
    expect(hours(16.5)).toBe('16.5 h');
  });

  it('separates thousands in a count', () => {
    expect(count(1488)).toBe('1,488');
  });
});

describe('London time rendering', () => {
  it('renders a winter instant at its UTC wall-clock time', () => {
    // January is GMT, so 18:00Z is 18:00 London.
    expect(londonTime('2026-01-15T18:00:00Z')).toBe('18:00');
  });

  it('shifts a summer instant into BST', () => {
    // July is BST (UTC+1), so 18:00Z is 19:00 London.
    expect(londonTime('2026-07-15T18:00:00Z')).toBe('19:00');
  });

  it('includes the day and month in a datetime label', () => {
    expect(londonDateTime('2026-01-15T18:00:00Z')).toBe('15 Jan 18:00');
  });

  it('rolls over to the next London day for a late-evening summer instant', () => {
    // 23:30Z on 1 July is 00:30 on 2 July in London.
    expect(londonDateTime('2026-07-01T23:30:00Z')).toBe('02 Jul 00:30');
  });

  it('reports the zone in force', () => {
    expect(londonZoneAbbrev('2026-01-15T12:00:00Z')).toBe('GMT');
    expect(londonZoneAbbrev('2026-07-15T12:00:00Z')).toBe('BST');
  });

  it('formats a plain yyyy-MM-dd without shifting the date', () => {
    expect(londonDate('2026-01-02')).toBe('02 Jan 2026');
  });

  it('labels a delivery day with its weekday', () => {
    expect(deliveryDayLabel('2026-01-02')).toBe('Fri 02 Jan');
  });
});
