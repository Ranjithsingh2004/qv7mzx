import { useId, useState } from 'react';
import './InfoHint.css';

interface InfoHintProps {
  label: string;
  text: string;
}

/**
 * A metric definition revealed on demand.
 *
 * Toggled by click and reachable by keyboard rather than hover-only, so the
 * definitions are available on touch devices too. The text is always rendered
 * from a string prop, never as markup.
 */
export function InfoHint({ label, text }: InfoHintProps) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className="hint">
      <button
        type="button"
        className="hint__trigger"
        aria-label={label}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
      >
        <span aria-hidden="true">?</span>
      </button>
      {open && (
        <span className="hint__bubble" id={id} role="note">
          {text}
        </span>
      )}
    </span>
  );
}
