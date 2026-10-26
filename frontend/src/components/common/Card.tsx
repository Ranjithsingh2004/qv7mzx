import type { ReactNode } from 'react';
import './Card.css';

interface CardProps {
  title?: string;
  /** Short supporting line under the title. */
  subtitle?: ReactNode;
  /** Controls or a legend aligned to the title row. */
  actions?: ReactNode;
  children: ReactNode;
  /** Reduced opacity while a refetch is in flight, holding the frame. */
  refreshing?: boolean;
  id?: string;
}

export function Card({ title, subtitle, actions, children, refreshing, id }: CardProps) {
  return (
    <section className="card" id={id} aria-busy={refreshing || undefined}>
      {(title || actions) && (
        <header className="card__head">
          <div className="card__heading">
            {title && <h3 className="card__title">{title}</h3>}
            {subtitle && <p className="card__subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="card__actions">{actions}</div>}
        </header>
      )}
      <div className={refreshing ? 'card__body card__body--refreshing' : 'card__body'}>
        {children}
      </div>
    </section>
  );
}
