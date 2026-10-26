import type { Analysis, Health, Meta } from '../../api/types';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { count, londonDate, londonDateTime, mw } from '../../lib/format';
import './sections.css';

/**
 * Provenance and method, stated on the page rather than only in the README.
 *
 * Everything here is read from the API response -- the dataset descriptions,
 * the normalisation counts and the assumptions list all come from the backend,
 * so the page cannot drift out of step with what the service actually did.
 */
export function TransparencySection({
  analysis,
  meta,
  health,
  refreshing,
}: {
  analysis: Analysis;
  meta: Meta | null;
  health: Health | null;
  refreshing: boolean;
}) {
  const quality = analysis.data_quality;

  return (
    <section className="section" id="transparency" aria-labelledby="transparency-heading">
      <div className="section__head">
        <h2 className="section__title" id="transparency-heading">
          Data &amp; method
        </h2>
        <p className="section__lede">
          Where every figure comes from, how the forecast was chosen, and what the analysis
          assumes.
        </p>
      </div>

      <div className="grid grid--two">
        <Card refreshing={refreshing} title="Sources retrieved for this analysis">
          <div className="section__badges">
            <Badge tone="info" glyph="●">
              {analysis.data_mode === 'live_elexon'
                ? 'Live Elexon BMRS data'
                : analysis.data_mode}
            </Badge>
            {health?.upstream === 'reachable' && (
              <Badge tone="good" glyph="✔">
                Source API reachable
              </Badge>
            )}
            {health?.upstream === 'unreachable' && (
              <Badge tone="critical" glyph="!">
                Source API unreachable
              </Badge>
            )}
          </div>

          {meta &&
            Object.entries(meta.datasets).map(([key, dataset]) => (
              <div key={key} className="source">
                <p className="source__name">
                  {dataset.name}
                  <span className="source__meta">
                    {dataset.resolution} · {dataset.units}
                  </span>
                </p>
                <p className="source__desc">{dataset.description}</p>
                <a className="source__link" href={dataset.documentation} target="_blank" rel="noreferrer noopener">
                  Elexon API documentation ↗
                </a>
              </div>
            ))}

          <dl className="kv">
            <div className="kv__row">
              <dt>Actuals query</dt>
              <dd className="tnum">
                {analysis.sources.actuals.dataset} · {analysis.sources.actuals.filter}
              </dd>
            </div>
            <div className="kv__row">
              <dt>Settlement dates fetched</dt>
              <dd className="tnum">
                {analysis.sources.actuals.settlement_date_from} →{' '}
                {analysis.sources.actuals.settlement_date_to}
              </dd>
            </div>
            <div className="kv__row">
              <dt>Forecast publications fetched</dt>
              <dd className="tnum">
                {londonDateTime(analysis.sources.forecasts.publish_time_from)} →{' '}
                {londonDateTime(analysis.sources.forecasts.publish_time_to)}
              </dd>
            </div>
            <div className="kv__row">
              <dt>Analysis generated</dt>
              <dd className="tnum">{londonDateTime(analysis.generated_at)} London</dd>
            </div>
          </dl>
        </Card>

        <Card refreshing={refreshing} title="Data quality on this fetch">
          <dl className="kv">
            <div className="kv__row">
              <dt>Actual rows received / accepted</dt>
              <dd className="tnum">
                {count(quality.actuals.rows_received)} / {count(quality.actuals.rows_accepted)}
              </dd>
            </div>
            <div className="kv__row">
              <dt>Actual rows dropped as malformed</dt>
              <dd className="tnum">{count(quality.actuals.rows_dropped_malformed)}</dd>
            </div>
            <div className="kv__row">
              <dt>Non-wind rows filtered out</dt>
              <dd className="tnum">{count(quality.actuals.rows_dropped_wrong_fuel)}</dd>
            </div>
            <div className="kv__row">
              <dt>Actual revisions collapsed</dt>
              <dd className="tnum">{count(quality.actuals.duplicates_collapsed)}</dd>
            </div>
            <div className="kv__row">
              <dt>Forecast rows received / accepted</dt>
              <dd className="tnum">
                {count(quality.forecasts.rows_received)} / {count(quality.forecasts.rows_accepted)}
              </dd>
            </div>
            <div className="kv__row">
              <dt>Forecast rows dropped as malformed</dt>
              <dd className="tnum">{count(quality.forecasts.rows_dropped_malformed)}</dd>
            </div>
            <div className="kv__row">
              <dt>Duplicate forecast vintages collapsed</dt>
              <dd className="tnum">{count(quality.forecasts.duplicates_collapsed)}</dd>
            </div>
          </dl>

          {quality.actuals.issues.length + quality.forecasts.issues.length > 0 ? (
            <>
              <p className="section__note">Issues encountered while normalising:</p>
              <ul className="section__list">
                {[...quality.actuals.issues, ...quality.forecasts.issues].map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </>
          ) : (
            <p className="section__note">
              No malformed rows, and no duplicate keys needing resolution, on this fetch.
            </p>
          )}

          <p className="section__note">
            Rows that cannot be parsed are dropped and counted rather than coerced to zero, so a
            bad upstream row reduces coverage visibly instead of biasing a metric silently.
          </p>
        </Card>
      </div>

      <Card refreshing={refreshing} title="How the forecast for each hour is chosen">
        <ol className="steps">
          <li>
            Take the target hour, and the London delivery day it falls on — day boundaries are
            resolved in <code>Europe/London</code>, so a delivery day is 23, 24 or 25 hours long
            across a clock change.
          </li>
          <li>
            Compute the decision cutoff for that delivery day:{' '}
            <strong>{analysis.cutoff.description}</strong>. In this window that runs from{' '}
            {londonDateTime(analysis.cutoff.earliest_cutoff_utc)} to{' '}
            {londonDateTime(analysis.cutoff.latest_cutoff_utc)} London.
          </li>
          <li>
            Gather every WINDFOR value published for that target hour — in this window{' '}
            {count(analysis.coverage.forecast_vintages_seen)} distinct publications were
            retrieved.
          </li>
          <li>
            Discard any published after the cutoff. A forecast published exactly at the cutoff is
            kept, since it was available to the decision.
          </li>
          <li>
            Take the most recent of what remains. If nothing remains, the hour is recorded as{' '}
            <code>no_eligible_forecast</code> and contributes to no metric.
          </li>
          <li>
            Match it to the actual for the same target hour:{' '}
            {analysis.alignment_description.toLowerCase()}.
          </li>
        </ol>
        <p className="section__note">
          The vintage inspector above applies this to a single hour and shows the excluded
          publications, so the rule can be checked rather than taken on trust.
        </p>
      </Card>

      <Card refreshing={refreshing} title="Assumptions and limitations">
        {meta ? (
          <ol className="steps">
            {meta.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ol>
        ) : (
          <p className="section__note">Assumptions could not be loaded from the API.</p>
        )}
        <dl className="kv">
          <div className="kv__row">
            <dt>Timezone handling</dt>
            <dd>
              UTC internally, Europe/London for every label and day boundary
            </dd>
          </div>
          <div className="kv__row">
            <dt>Sign convention</dt>
            <dd>{meta?.sign_convention ?? 'error = forecast − actual'}</dd>
          </div>
          <div className="kv__row">
            <dt>MAPE floor in force</dt>
            <dd className="tnum">{mw(analysis.mape_floor_mw)}</dd>
          </div>
          <div className="kv__row">
            <dt>Decision window</dt>
            <dd className="tnum">
              {londonDate(analysis.decision_from)} → {londonDate(analysis.decision_to)}
            </dd>
          </div>
          <div className="kv__row">
            <dt>Delivery window</dt>
            <dd className="tnum">
              {londonDate(analysis.delivery_from)} → {londonDate(analysis.delivery_to)}
            </dd>
          </div>
        </dl>
      </Card>
    </section>
  );
}
