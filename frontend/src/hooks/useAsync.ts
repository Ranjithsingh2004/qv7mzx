import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  /** True only on the first load; a refetch keeps the previous render. */
  loading: boolean;
  /** True while re-fetching with data already on screen. */
  refreshing: boolean;
  reload: () => void;
}

/**
 * Run an async loader, keeping the previous result visible while the next one
 * is in flight.
 *
 * Holding the last render at reduced opacity rather than dropping to a
 * skeleton is deliberate: the dashboard's controls change often, and a
 * flashing layout makes comparisons between settings much harder to read.
 *
 * In-flight requests are aborted when inputs change or the component
 * unmounts, so a slow earlier response can never overwrite a newer one.
 */
export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(true);
  const [nonce, setNonce] = useState(0);
  const hasData = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    setPending(true);
    loader(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        hasData.current = true;
        setData(result);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (cause instanceof DOMException && cause.name === 'AbortError') return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (!controller.signal.aborted) setPending(false);
      });
    return () => controller.abort();
    // `loader` is recreated on every render by design; `deps` is the contract.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return {
    data,
    error,
    loading: pending && !hasData.current,
    refreshing: pending && hasData.current,
    reload,
  };
}
