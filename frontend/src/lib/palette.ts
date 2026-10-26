/**
 * Chart colours read from the CSS custom properties in `tokens.css`.
 *
 * Recharts needs concrete colour strings rather than `var(...)` for some
 * props (notably SVG gradients and computed fills), so the tokens are
 * resolved from the document once per theme change. Reading them here rather
 * than duplicating hex values keeps a single source of truth, so a token edit
 * cannot leave the charts behind.
 */

import { useEffect, useState } from 'react';

export interface ChartPalette {
  actual: string;
  forecast: string;
  third: string;
  over: string;
  under: string;
  grid: string;
  axis: string;
  surface: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
}

const TOKENS: Record<keyof ChartPalette, string> = {
  actual: '--series-actual',
  forecast: '--series-forecast',
  third: '--series-third',
  over: '--diverge-over',
  under: '--diverge-under',
  grid: '--grid',
  axis: '--axis',
  surface: '--surface-1',
  textPrimary: '--text-primary',
  textSecondary: '--text-secondary',
  textMuted: '--text-muted',
};

const FALLBACK: ChartPalette = {
  actual: '#2a78d6',
  forecast: '#eb6834',
  third: '#1baf7a',
  over: '#e34948',
  under: '#2a78d6',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  surface: '#fcfcfb',
  textPrimary: '#0b0b0b',
  textSecondary: '#52514e',
  textMuted: '#898781',
};

function read(): ChartPalette {
  if (typeof window === 'undefined') return FALLBACK;
  const computed = getComputedStyle(document.documentElement);
  const entries = Object.entries(TOKENS).map(([key, token]) => {
    const value = computed.getPropertyValue(token).trim();
    return [key, value || FALLBACK[key as keyof ChartPalette]] as const;
  });
  return Object.fromEntries(entries) as unknown as ChartPalette;
}

/** The resolved chart palette, refreshed when the theme changes. */
export function useChartPalette(): ChartPalette {
  const [palette, setPalette] = useState<ChartPalette>(read);

  useEffect(() => {
    const refresh = () => setPalette(read());
    refresh();

    // The in-app toggle flips `data-theme`; the OS setting fires on the query.
    const observer = new MutationObserver(refresh);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', refresh);

    return () => {
      observer.disconnect();
      media.removeEventListener('change', refresh);
    };
  }, []);

  return palette;
}
