import { useMemo } from 'react';
import type { Analysis, AnalysisParams, Meta } from '../../api/types';
import { fetchCutoffSweep } from '../../api/client';
import { useAsync } from '../../hooks/useAsync';
import { MaeBarChart, type MaeDatum } from '../charts/MaeBarChart';
import { Card } from '../common/Card';
import { ErrorState, LoadingState } from '../common/States';
import { StatTile } from '../common/StatTile';
import { count, decimal, mw, percent, ratioAsPercent, signedMw } from '../../lib/format';
import './sections.css';

const SWEEP_CUTOFFS = ['06:00', '09:00', '12:00', '17:00', '23:00'];

/** Metrics shown as definition rows, so nothing on the page is unexplained. */
const SHOWN_DEFINITIONS = [
  'mae_mw',
  'rmse_mw',
  'bias_mw',
  'error_sd_mw',
  'bias_share_of_mse',
  'mape_percent',
  'wmape_percent',
  'correlation',
] as const;

export function AccuracySection({
  analysis,
  params,
  meta,
  refreshing,
}: {
  analysis: Analysis;
  params: AnalysisParams;
  meta: Meta | null;
  refreshing: boolean;
}) {
  const { metrics } = analysis;
  const definitions = meta?.metric_definitions ?? {};

  const sweep = useAsync((signal) => fetchCutoffSweep(params, SWEEP_CUTOFFS, signal), [params]);

  const sweepData = useMemo<MaeDatum[]>(
    () =>
      (sweep.data?.rows ?? []).map((row) => ({
        key: row.cutoff_time,
        label: row.cutoff_time,
        mae: row.mae_mw,
        rmse: row.rmse_mw,
        bias: row.bias_mw,
        hours: row.matched_hours,
        meanHorizon: row.mean_horizon_hours,
        detail: row.cutoff_description,
      })),
    [sweep.data],
  );

  const biasShare = metrics.bias_share_of_mse;

  return (
    <section className="section" id="accuracy" aria-labelledby="accuracy-heading">
      <div className="section__head">
        <h2 className="section__title" id="accuracy-heading">
          Forecast accuracy
        </h2>
        <p className="section__lede">
          Every metric is computed from the {count(metrics.matched_hours)} hours that have both a
          cutoff-eligible forecast and a measured actual. Unmatched hours are excluded, never
          treated as zero error. Sign convention: {meta?.sign_convention ?? 'error = forecast − actual'}.
        </p>
      </div>

      <Card refreshing={refreshing} title="Accuracy metrics">
        <div className="grid grid--metrics">
          <StatTile
            label="MAE"
            value={mw(metrics.mae_mw)}
            hint={definitions.mae_mw}
            detail={`${percent(metrics.normalised_mae_percent)} of mean actual`}
          />
          <StatTile label="RMSE" value={mw(metrics.rmse_mw)} hint={definitions.rmse_mw} />
          <StatTile
            label="Mean bias"
            value={signedMw(metrics.bias_mw)}
            tone={(metrics.bias_mw ?? 0) >= 0 ? 'over' : 'under'}
            hint={definitions.bias_mw}
            detail={`${count(metrics.hours_over_forecast)} hours over, ${count(
              metrics.hours_under_forecast,
            )} under`}
          />
          <StatTile
            label="Error spread (SD)"
            value={mw(metrics.error_sd_mw)}
            hint={definitions.error_sd_mw}
          />
          <StatTile
            label="wMAPE"
            value={percent(metrics.wmape_percent)}
            hint={definitions.wmape_percent}
            detail="Defined for every matched hour"
          />
          <StatTile
            label="MAPE"
            value={percent(metrics.mape_percent, 2)}
            hint={definitions.mape_percent}
            detail={
              metrics.mape_hours_excluded > 0
                ? `${count(metrics.mape_hours_excluded)} hours excluded below ${mw(
                    metrics.mape_floor_mw,
                  )}`
                : `All ${count(metrics.mape_hours_included)} hours above the ${mw(
                    metrics.mape_floor_mw,
                  )} floor`
            }
          />
          <StatTile
            label="Correlation"
            value={decimal(metrics.correlation)}
            hint={definitions.correlation}
            detail="Shape tracking, ignoring bias"
          />
          <StatTile
            label="Worst single hour"
            value={mw(metrics.max_abs_error_mw)}
            hint={definitions.max_abs_error_mw}
          />
        </div>
      </Card>

      <div className="grid grid--two">
        <Card
          refreshing={refreshing}
          title="How much of the error is systematic?"
          subtitle="Mean squared error splits exactly into a bias component and a dispersion component."
        >
          <div className="grid grid--stats">
            <StatTile
              label="From systematic bias"
              value={ratioAsPercent(biasShare)}
              hint={definitions.bias_share_of_mse}
              detail={`A stable ${signedMw(metrics.bias_mw)} offset`}
            />
            <StatTile
              label="From random dispersion"
              value={ratioAsPercent(biasShare === null ? null : 1 - biasShare)}
              detail={`${mw(metrics.error_sd_mw)} standard deviation`}
            />
          </div>
          <div className="callout">
            <p className="callout__title">Operational reading</p>
            <p className="callout__body">
              {biasShare !== null && biasShare > 0.3 ? (
                <>
                  A large share of this window&rsquo;s squared error is a persistent offset rather
                  than random noise. An offset of that kind is correctable — it can be allowed for
                  in the position before the auction. The remaining{' '}
                  {mw(metrics.error_sd_mw)} of dispersion is the genuinely uncertain part and is
                  what a volume hedge has to cover. Before correcting for it, confirm the scope
                  caveat in Data &amp; method: part of a persistent level difference between these
                  two datasets may not be forecast error at all.
                </>
              ) : (
                <>
                  Most of this window&rsquo;s squared error is dispersion rather than a stable
                  offset, so there is little to gain from a bias correction. The exposure is
                  genuine weather uncertainty and has to be carried or hedged.
                </>
              )}
            </p>
          </div>
        </Card>

        <Card
          refreshing={refreshing}
          title="What a later decision would be worth"
          subtitle="The same outturn, judged against whatever forecast each cutoff would have allowed."
        >
          {sweep.loading && <LoadingState label="Evaluating cutoffs…" />}
          {sweep.error && <ErrorState error={sweep.error} onRetry={sweep.reload} />}
          {sweep.data && (
            <>
              <MaeBarChart
                data={sweepData}
                xLabel={`Cutoff time on D-${params.cutoffDaysBefore} (London)`}
                height={230}
                description={
                  'Column chart of mean absolute error in megawatts for each candidate decision ' +
                  'cutoff time, with the mean forecast lead time for each.'
                }
              />
              <p className="section__note">
                Each column re-runs the whole analysis at a different deadline. Later cutoffs use
                fresher forecasts and shorter lead times, so the gap between the first and last
                column is the accuracy a desk buys by deciding later — information to weigh
                against liquidity and process constraints, which this dataset cannot speak to.
              </p>
            </>
          )}
        </Card>
      </div>

      <Card
        refreshing={refreshing}
        title="Metric definitions"
        subtitle="Exactly as the API documents them, so the dashboard and the API cannot disagree."
      >
        <dl className="defs">
          {SHOWN_DEFINITIONS.filter((key) => definitions[key]).map((key) => (
            <div key={key}>
              <dt className="defs__term">{key}</dt>
              <dd className="defs__desc">{definitions[key]}</dd>
            </div>
          ))}
        </dl>
      </Card>
    </section>
  );
}
