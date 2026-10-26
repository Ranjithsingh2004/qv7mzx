import type { ReactNode } from 'react';
import { ApiError } from '../../api/client';
import './States.css';

export function LoadingState({ label = 'Loading analysis…' }: { label?: string }) {
  return (
    <div className="state" role="status">
      <span className="state__spinner" aria-hidden="true" />
      <p className="state__title">{label}</p>
      <p className="state__body">
        Fetching wind outturn and every forecast vintage from Elexon BMRS.
      </p>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: ReactNode }) {
  return (
    <div className="state">
      <p className="state__title">{title}</p>
      <p className="state__body">{body}</p>
    </div>
  );
}

/**
 * A failure the user can act on.
 *
 * Invalid parameters and an unreachable upstream need different responses, so
 * the API's error code chooses the wording rather than showing one generic
 * message for both.
 */
export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const code = error instanceof ApiError ? error.code : 'unknown';
  const isInput = code === 'invalid_request';
  const title = isInput
    ? 'Those settings cannot produce an analysis'
    : code === 'upstream_unavailable'
      ? 'Elexon BMRS could not be reached'
      : 'Something went wrong';

  const guidance = isInput
    ? 'Adjust the controls above and the analysis will reload.'
    : code === 'upstream_unavailable'
      ? 'The source API did not respond. This is usually temporary — retrying often resolves it.'
      : 'Retrying may help. If it persists, the API may be unavailable.';

  return (
    <div className="state state--error" role="alert">
      <p className="state__title">{title}</p>
      <p className="state__body">{error.message}</p>
      <p className="state__body state__body--muted">{guidance}</p>
      {onRetry && !isInput && (
        <button type="button" className="state__retry" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
