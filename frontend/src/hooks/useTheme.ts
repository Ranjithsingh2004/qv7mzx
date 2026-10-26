import { useCallback, useEffect, useState } from 'react';

export type ThemeChoice = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'windsight-theme';

function readStored(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored;
  } catch {
    /* private browsing or blocked storage: fall back to the OS setting */
  }
  return 'system';
}

/**
 * Theme preference, persisted per browser.
 *
 * `system` removes the attribute entirely so the OS media query in
 * `tokens.css` applies; an explicit choice stamps `data-theme`, which is
 * written to win over the media query in both directions.
 */
export function useTheme(): { choice: ThemeChoice; setChoice: (next: ThemeChoice) => void } {
  const [choice, setChoiceState] = useState<ThemeChoice>(readStored);

  useEffect(() => {
    const root = document.documentElement;
    if (choice === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', choice);
    try {
      localStorage.setItem(STORAGE_KEY, choice);
    } catch {
      /* preference simply will not persist */
    }
  }, [choice]);

  const setChoice = useCallback((next: ThemeChoice) => setChoiceState(next), []);
  return { choice, setChoice };
}
