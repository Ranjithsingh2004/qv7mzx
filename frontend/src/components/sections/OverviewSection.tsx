import type { Analysis, Meta } from '../../api/types';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { StatTile } from '../common/StatTile';
import { count, londonDate, mw, percent, signedMw } from '../../lib/format';
import './sections.css';

/**
 * The opening read: how accurate the day-ahead forecast was, how complete the
 * analysis is, and what the decision rule was.
 *
 * MAE is the single hero figure for the view -- it is in megawatts, the same
 * unit as the volume being procured, so it answers "how far out are we
 * typically?" directly.
 */
export function OverviewSection({
  analysis,
  meta,
  refreshing,
}: {
  analysis: Analysis;
  meta: Meta | null;
  refreshing: boolean;
}) {
  const { metrics, coverage, cutoff } = analysis;
  const definitions = meta?.metric_definitions ?? {};
  const biasTone = (metrics.bias_mw ?? 0) >= 0 ? 'over' : 'under';
  const fullCoverage = coverage.matched_percent >= 99.995;

  return (
    <section className="section" id="overview" aria-labelledby="overview-heading">
      <div className="section__head">
        <h2 className="section__title" id="overview-heading">
          Overview
        </h2>
        <p className="section__lede">
          Purchase decisions taken {londonDate(analysis.decision_from)} –{' '}
          {londonDate(analysis.decision_to)}, procuring for delivery{' '}
          {londonDate(analysis.delivery_from)} – {londonDate(analysis.delivery_to)}. Each hour is
          judged against the most recent wind forecast published by{' '}
          <strong>{cutoff.description}</strong>.
        </p>
      </div>

      <div className="grid grid--hero">
        <Card refreshing={refreshing}>
          <StatTile
            size="hero"
            label="Mean absolute error of the day-ahead forecast"
            value={mw(metrics.mae_mw)}
            hint={definitions.mae_mw}
            detail={
              <>
                {percent(metrics.normalised_mae_percent)} of mean actual generation (
                {mw(metrics.mean_actual_mw)}) across {count(metrics.matched_hours)} matched hours
              </>
            }
          />
          <p className="section__note">
            On an average hour in this window, the forecast the desk had at the cutoff differed
            from measured wind outturn by {mw(metrics.mae_mw)}. That is the volume the
            procurement position was exposed to before any price effect.
          </p>
        </Card>

        <Card refreshing={refreshing} title="Headline accuracy">
          <div className="grid grid--stats">
            <StatTile
              label="RMSE"
              value={mw(metrics.rmse_mw)}
              hint={definitions.rmse_mw}
              detail="Penalises the large misses"
            />
            <StatTile
              label="Mean bias"
              value={signedMw(metrics.bias_mw)}
              tone={biasTone}
              hint={definitions.bias_mw}
              detail={biasTone === 'over' ? 'Forecast ran high' : 'Forecast ran low'}
            />
            <StatTile
              label="Error spread"
              value={mw(metrics.error_sd_mw)}
              hint={definitions.error_sd_mw}
              detail="Once bias is removed"
            />
            <StatTile
              label="wMAPE"
              value={percent(metrics.wmape_percent)}
              hint={definitions.wmape_percent}
              detail="Total error over total outturn"
            />
          </div>
        </Card>
      </div>

      <div className="grid grid--three">
        <Card refreshing={refreshing} title="Data availability">
          <dl className="kv">
            <div className="kv__row">
              <dt>Delivery days</dt>
              <dd className="tnum">{count(coverage.delivery_days)}</dd>
            </div>
            <div className="kv__row">
              <dt>Target hours in window</dt>
              <dd className="tnum">{count(coverage.expected_hours)}</dd>
            </div>
            <div className="kv__row">
              <dt>Hours with eligible forecast</dt>
              <dd className="tnum">{count(coverage.hours_with_forecast)}</dd>
            </div>
            <div className="kv__row">
              <dt>Hours with actual outturn</dt>
              <dd className="tnum">{count(coverage.hours_with_actual)}</dd>
            </div>
            <div className="kv__row">
              <dt>Half-hourly actuals used</dt>
              <dd className="tnum">
                {count(coverage.actual_settlement_periods)} of{' '}
                {count(coverage.expected_settlement_periods)}
              </dd>
            </div>
            <div className="kv__row">
              <dt>Forecast vintages retrieved</dt>
              <dd className="tnum">{count(coverage.forecast_vintages_seen)}</dd>
            </div>
          </dl>
        </Card>

        <Card refreshing={refreshing} title="Matched settlement periods">
          <StatTile
            label="Hours contributing to every metric"
            value={count(coverage.matched_hours)}
            detail={`${percent(coverage.matched_percent)} of the ${count(
              coverage.expected_hours,
            )} hours in the delivery window`}
          />
          <div className="coverage">
            <div
              className="coverage__track"
              role="img"
              aria-label={`${percent(coverage.matched_percent)} of target hours matched`}
            >
              <div
                className="coverage__fill"
                style={{ width: `${Math.min(100, coverage.matched_percent)}%` }}
              />
            </div>
            <ul className="section__list">
              {coverage.hours_missing_forecast > 0 && (
                <li>
                  {count(coverage.hours_missing_forecast)} hours had no forecast available by the
                  cutoff
                </li>
              )}
              {coverage.hours_missing_actual > 0 && (
                <li>{count(coverage.hours_missing_actual)} hours had no actual outturn published</li>
              )}
              {coverage.hours_partial_actual > 0 && (
                <li>
                  {count(coverage.hours_partial_actual)} hours were backed by one settlement period
                  instead of two
                </li>
              )}
              {fullCoverage && coverage.hours_partial_actual === 0 && (
                <li>
                  Every hour in the window has both a cutoff-eligible forecast and a complete
                  actual. No gaps to account for.
                </li>
              )}
            </ul>
          </div>
        </Card>

        <Card refreshing={refreshing} title="Source status">
          <div className="section__badges">
            <Badge tone="info" glyph="●">
              {analysis.data_mode === 'live_elexon' ? 'Live Elexon BMRS' : analysis.data_mode}
            </Badge>
            <Badge tone="neutral">FUELHH · fuelType=WIND</Badge>
            <Badge tone="neutral">WINDFOR</Badge>
          </div>
          <ul className="section__list">
            <li>
              Actuals: {count(analysis.sources.actuals.records)} half-hourly records, settlement
              dates {analysis.sources.actuals.settlement_date_from} to{' '}
              {analysis.sources.actuals.settlement_date_to}.
            </li>
            <li>
              Forecasts: {count(analysis.sources.forecasts.records)} values across{' '}
              {count(coverage.forecast_vintages_seen)} publications.
            </li>
            <li>
              Every figure on this page is computed from those responses. This product has no
              synthetic or demo data path.
            </li>
          </ul>
          <p className="section__note">
            Known limitation: Elexon does not document FUELHH wind outturn and the WINDFOR forecast
            as covering an identical set of wind assets, so part of the measured bias may be a
            scope difference rather than forecast skill. See Data &amp; method.
          </p>
        </Card>
      </div>
    </section>
  );
}
