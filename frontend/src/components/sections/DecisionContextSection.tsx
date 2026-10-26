import { useMemo, useState } from 'react';
import type { Analysis } from '../../api/types';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { StatTile } from '../common/StatTile';
import { count, mw, signedMw } from '../../lib/format';
import './sections.css';

/** Central interval multipliers for a roughly normal error distribution. */
const COVERAGE_LEVELS = [
  { label: '80%', z: 1.2816 },
  { label: '90%', z: 1.6449 },
  { label: '95%', z: 1.96 },
];

/**
 * How to act on the measured error -- and, explicitly, what this dataset
 * cannot tell you.
 *
 * The challenge supplies national wind actuals and forecasts and nothing else.
 * There is no demand, no price, no thermal stack and no cost here, so this
 * section does not produce a procurement recommendation. The scenario tool
 * below is driven entirely by a number the user types in, and says so.
 */
export function DecisionContextSection({
  analysis,
  refreshing,
}: {
  analysis: Analysis;
  refreshing: boolean;
}) {
  const { metrics } = analysis;
  const [demandInput, setDemandInput] = useState('32000');

  const demand = Number(demandInput);
  const demandValid = Number.isFinite(demand) && demand > 0;

  // A single illustrative hour: the window's mean forecast level.
  const forecast = metrics.mean_forecast_mw;
  const bias = metrics.bias_mw;
  const sd = metrics.error_sd_mw;

  const scenario = useMemo(() => {
    if (!demandValid || forecast === null || bias === null || sd === null) return null;
    const naiveResidual = demand - forecast;
    // Removing the measured bias from the forecast gives the de-biased central
    // estimate; the spread around it is what remains uncertain.
    const debiasedResidual = demand - (forecast - bias);
    return {
      naiveResidual,
      debiasedResidual,
      bands: COVERAGE_LEVELS.map((level) => ({
        label: level.label,
        low: debiasedResidual - level.z * sd,
        high: debiasedResidual + level.z * sd,
        width: 2 * level.z * sd,
      })),
    };
  }, [demand, demandValid, forecast, bias, sd]);

  return (
    <section className="section" id="decision-context" aria-labelledby="context-heading">
      <div className="section__head">
        <h2 className="section__title" id="context-heading">
          Using this in a day-ahead decision
        </h2>
        <p className="section__lede">
          What the measured error means for a procurement position, and where this dataset stops.
        </p>
      </div>

      <div className="grid grid--two">
        <Card refreshing={refreshing} title="What the numbers imply">
          <ul className="section__list">
            <li>
              <strong>Size the exposure in volume terms.</strong> MAE of {mw(metrics.mae_mw)} is
              the typical gap between the forecast in hand at the cutoff and delivered wind. Any
              position built straight off the forecast carries roughly that much volume risk per
              hour before price is considered.
            </li>
            <li>
              <strong>Separate the correctable part from the uncertain part.</strong> Mean bias is{' '}
              {signedMw(metrics.bias_mw)} and the spread around it is {mw(metrics.error_sd_mw)}. A
              persistent offset can be allowed for in advance; the spread has to be carried or
              hedged.
            </li>
            <li>
              <strong>Check the direction.</strong>{' '}
              {count(metrics.hours_over_forecast)} of {count(metrics.matched_hours)} matched hours
              were over-forecast. Over-forecast wind means under-procured conventional cover,
              which is the direction that gets closed out in the balancing market.
            </li>
            <li>
              <strong>Decide how much lateness is worth.</strong> The cutoff comparison in the
              accuracy section prices the accuracy gained by deciding later, in MW.
            </li>
          </ul>
        </Card>

        <Card refreshing={refreshing} title="What this dataset cannot tell you">
          <div className="callout callout--caution">
            <p className="callout__title">Deliberately out of scope</p>
            <p className="callout__body">
              This product is built on national wind actuals and forecasts alone, which is the
              scope the brief sets. It therefore contains no consumer demand, no wholesale or
              balancing prices, no thermal availability and no procurement cost. It does not
              produce a buy or sell recommendation, and any figure resembling one would be
              invented rather than measured.
            </p>
          </div>
          <ul className="section__list">
            <li>
              Residual demand needs a demand forecast, which is not in scope. The scenario below
              takes one from you and labels it as such.
            </li>
            <li>
              Converting MW of error into money needs a price curve and an imbalance price. Both
              are out of scope.
            </li>
            <li>
              The error measured here is national. Portfolio-level exposure depends on the
              utility&rsquo;s own contracted position.
            </li>
          </ul>
        </Card>
      </div>

      <Card
        refreshing={refreshing}
        title="Optional scenario — residual demand from a demand figure you supply"
        subtitle="An illustration of how the measured error propagates. Not an output of the Elexon data."
        actions={
          <Badge tone="warning" glyph="!">
            Requires user-supplied demand
          </Badge>
        }
      >
        <div className="toolbar">
          <label className="field">
            <span className="field__label">Your expected demand for the hour (MW)</span>
            <input
              className="field__input"
              type="number"
              min={1}
              step={500}
              value={demandInput}
              onChange={(event) => setDemandInput(event.target.value)}
              aria-describedby="scenario-help"
            />
          </label>
          <p className="section__note" id="scenario-help">
            Compared against this window&rsquo;s mean forecast wind of {mw(forecast)} and its
            measured error distribution.
          </p>
        </div>

        {!demandValid && (
          <p className="section__note">Enter a positive demand figure to see the scenario.</p>
        )}

        {scenario && (
          <>
            <div className="grid grid--metrics">
              <StatTile
                label="Residual to procure, straight off the forecast"
                value={mw(scenario.naiveResidual)}
                detail="Your demand minus the forecast as published"
              />
              <StatTile
                label="Residual after removing measured bias"
                value={mw(scenario.debiasedResidual)}
                detail={`Adjusted for the ${signedMw(bias)} offset measured in this window`}
              />
              <StatTile
                label="Difference between the two"
                value={signedMw(scenario.debiasedResidual - scenario.naiveResidual)}
                tone={scenario.debiasedResidual >= scenario.naiveResidual ? 'over' : 'under'}
                detail="Volume the bias alone would have mis-stated"
              />
            </div>

            <table className="dtable" style={{ marginTop: 'var(--space-3)' }}>
              <caption className="sr-only">
                Residual demand intervals implied by the measured forecast error spread
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="dtable__th">
                    Coverage
                  </th>
                  <th scope="col" className="dtable__th dtable__th--num">
                    Residual demand range
                  </th>
                  <th scope="col" className="dtable__th dtable__th--num">
                    Range width
                  </th>
                </tr>
              </thead>
              <tbody>
                {scenario.bands.map((band) => (
                  <tr key={band.label}>
                    <td className="dtable__td">{band.label} of hours</td>
                    <td className="dtable__td dtable__td--num tnum">
                      {mw(band.low)} – {mw(band.high)}
                    </td>
                    <td className="dtable__td dtable__td--num tnum">{mw(band.width)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <p className="section__note">
              Intervals assume the forecast error is roughly normal around its mean, using the
              {' '}{mw(sd)} standard deviation measured over {count(metrics.matched_hours)} hours.
              That assumption is a simplification: wind forecast errors are skewed and
              serially correlated, so treat these as indicative width rather than a calibrated
              risk figure. The demand figure is yours, not Elexon&rsquo;s.
            </p>
          </>
        )}
      </Card>
    </section>
  );
}
