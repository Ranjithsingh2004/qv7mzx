# Methodology

How Windsight turns two Elexon datasets into a defensible statement about
day-ahead wind forecast accuracy, and what it deliberately does not claim.

## 1. The question

A GB utility's day-ahead desk must commit to a procurement position before
gate closure on the day before delivery. At that moment the only wind
information it has is a forecast. The question this product answers is:

> **How wrong was the forecast that was actually on the desk at the moment of
> the decision?**

That is a different question from "how wrong was the forecast", and the
difference is the whole point. Forecasts are revised continuously; some of
those revisions arrive after the decision was made. Comparing outturn against
the latest revision measures hindsight, not the decision.

## 2. Sources

Both are public Elexon BMRS Insights API datasets. No API key exists for them
and none is used.

| | Actuals | Forecasts |
|---|---|---|
| Dataset | `FUELHH` | `WINDFOR` |
| Filter | `fuelType=WIND` | — |
| Endpoint | `/datasets/FUELHH/stream` | `/datasets/WINDFOR/stream` |
| Resolution | 30 minutes (settlement periods) | 60 minutes |
| Units | MW, averaged over the period | MW |
| Query by | `settlementDateFrom` / `settlementDateTo` | `publishDateTimeFrom` / `publishDateTimeTo` |
| Key fields | `startTime`, `settlementDate`, `settlementPeriod`, `generation` | `startTime`, `publishTime`, `generation` |

Observed behaviour, confirmed against the live API rather than assumed:

- `FUELHH` and `WINDFOR` stream endpoints return a bare JSON array with no
  pagination envelope. A month of either is a single request.
- `FUELHH` rejects settlement-date and publish-date filters used together, so
  only the settlement-date form is sent.
- `FUELHH` carries `publishTime` roughly 30 minutes after `startTime`; it is a
  publication stamp, not the target period.
- `WINDFOR` publishes about eight vintages a day (commonly 02:30, 04:30,
  07:30, 09:30, 11:30, 15:30, 18:30 and 22:30 UTC), each covering roughly a
  73-hour window of hourly target periods.
- That cadence is **not** guaranteed. January 2026 contains an off-schedule
  publication at `2026-01-15T12:25:00Z`. Vintage selection therefore compares
  instants and never assumes fixed publication slots.
- A `WINDFOR` vintage also covers target hours in the recent past, so lead
  times in the raw feed range from about −25 h to +66 h.

## 3. Time handling

- Every timestamp crossing a module boundary is timezone-aware and in **UTC**.
  Naive datetimes are rejected rather than assumed.
- A **delivery day** is a calendar day in `Europe/London`, because that is what
  a GB settlement date means and how a trader thinks. Day boundaries are
  computed in London and converted to UTC.
- London days are 23, 24 or 25 hours long across clock changes, giving 46, 48
  or 50 settlement periods. The analysis iterates UTC hours between
  London-resolved day boundaries, so transition days come out with the right
  number of periods rather than being padded to 24.
- The UI labels every timestamp with its zone and shows the London rendering
  the API computed, so the frontend never re-derives a timezone and cannot
  disagree with the backend about a DST boundary.

## 4. The decision cutoff

For a delivery day *D*, the cutoff is a wall-clock time in `Europe/London` on
day *D − n*:

```
cutoff(D) = cutoff_time, Europe/London, on day D − cutoff_days_before
```

**Default: 09:00 Europe/London on D−1.**

> This is a documented product assumption, not a confirmed market rule. GB
> day-ahead auctions close mid-morning on D−1, so 09:00 sits ahead of gate
> closure and every forecast it admits was genuinely available beforehand. The
> challenge does not specify an operational cutoff. Both the time and the
> number of days are configurable in the UI and the API, and the cutoff
> comparison shows how the answer moves as the deadline moves.

Because the cutoff is a *wall-clock* London time, it tracks BST correctly:
09:00 London is 09:00 UTC in January and 08:00 UTC in July.

## 5. Forecast-vintage selection

For each target hour *T* on delivery day *D*:

1. Gather every `WINDFOR` value whose `startTime` equals *T*. Vintages are kept
   separate — they are never merged or averaged.
2. Discard any whose `publishTime` is **after** `cutoff(D)`. The comparison is
   inclusive: a forecast published exactly at the deadline was available.
3. Of what remains, take the one with the **latest** `publishTime`.
4. If nothing remains, the hour is recorded as `no_eligible_forecast` and
   contributes to no metric. It is never backfilled with a later forecast.

`no_eligible_forecast` (vintages existed, all too late) is reported separately
from `no_forecast_published` (none existed at all), because the two mean
different things about the data.

The UI's **vintage inspector** applies this to a single hour and renders the
excluded publications explicitly, so the rule can be checked rather than
trusted.

## 6. Aligning half-hourly actuals to hourly forecasts

The datasets do not share a resolution: outturn is half-hourly, forecasts are
hourly. Comparison happens on the hourly grid, and the actuals are reduced onto
it. Two reductions are offered, because the choice is a judgement:

- **`hourly_mean`** (default) — the mean of the settlement periods inside the
  hour. Uses every observation; the natural like-for-like against an hourly
  figure.
- **`period_start`** — only the settlement period beginning exactly on the
  hour. Discards half the actuals but involves no aggregation.

Neither invents data. An hour with no actual stays unmatched; an hour backed by
one period instead of two is flagged `actual_partial` and counted, rather than
silently averaged as though complete.

Over January 2026 the two reductions give MAE 2,038.9 MW and 2,022.5 MW
respectively — a 0.8% difference, so the headline does not hinge on the choice.

## 7. Metrics

Computed from **matched hours only** — an hour needs both a cutoff-eligible
forecast and an actual. Unmatched hours are counted and surfaced, never treated
as zero error.

**Sign convention: `error = forecast − actual`.** A positive error means wind
was over-forecast, and a desk trusting it would have under-procured.

| Metric | Definition |
|---|---|
| MAE | `mean(|error|)` — average miss, in the units of the traded volume |
| RMSE | `sqrt(mean(error²))` — penalises large misses |
| Bias | `mean(error)` — the signed, systematic component |
| Error SD | standard deviation of error about its own mean |
| Bias share of MSE | `bias² / MSE` — how much of the squared error is systematic |
| MAPE | `mean(|error| / actual)` over hours above the MAPE floor |
| wMAPE | `sum(|error|) / sum(actual)` |
| Normalised MAE | MAE as a percentage of mean actual |
| Correlation | Pearson *r* between forecast and actual |

**MAPE policy.** MAPE is undefined at zero and unstable near it. It is computed
only over matched hours whose actual exceeds the **MAPE floor** (100 MW by
default, configurable), and the included and excluded counts are always
reported. **wMAPE** is reported alongside because it is defined for every
matched hour, and is the percentage figure to prefer.

**Undefined is reported as `null`, never as zero.** An empty window returns
`matched_hours: 0` with null metrics; correlation is null for fewer than two
points or a constant series. Zero would read as a perfect forecast.

**MSE decomposition.** `MSE = bias² + variance`, exactly. Splitting the error
this way separates the part that could be corrected in advance from the part
that is irreducible and must be hedged.

## 8. Data quality

- Rows that cannot be parsed are **dropped and counted**, never coerced to
  zero, so a bad upstream row reduces visible coverage instead of silently
  biasing a metric. The counts appear in the UI.
- `fuelType=WIND` is applied both in the upstream query and again during
  normalisation, so the guarantee holds even if a request is built differently.
  A row with no `fuelType` is dropped rather than assumed to be wind.
- Duplicate actuals for one settlement period are treated as revisions: the
  later `publishTime` wins.
- Duplicate `(publishTime, startTime)` forecast rows are collapsed. Distinct
  vintages are never collapsed — doing so would destroy the cutoff logic.
- Negative generation is kept: wind farms can legitimately net-consume.

## 9. Results for January 2026

Decisions 1–31 January 2026, delivering 2 January – 1 February, at the default
09:00 London D−1 cutoff and `hourly_mean` alignment. 744 target hours, 100%
matched, 1,488 settlement periods, 280 forecast vintages retrieved.

| Metric | Value |
|---|---|
| MAE | 2,038.9 MW |
| RMSE | 2,504.8 MW |
| Mean bias | **+1,747.9 MW** |
| Error SD | 1,794.1 MW |
| Bias share of MSE | 48.7% |
| wMAPE | 18.07% |
| MAPE (floor 100 MW) | 22.04% |
| Correlation | 0.931 |
| Largest single-hour error | 6,870 MW |
| Hours over / under forecast | 632 / 112 |
| Mean actual wind | 11,284 MW |

Two things stand out.

**The forecast tracks shape well but sits high.** Correlation of 0.931 says the
day's profile is predicted well. Yet 632 of 744 hours were over-forecast, and
27 of 31 delivery days had a positive mean bias. Nearly half the squared error
(48.7%) is a stable offset rather than random dispersion.

**Deciding later helps, and the gain is measurable.** Re-running the same
analysis at later cutoffs:

| Cutoff (D−1, London) | MAE | RMSE | Mean lead time |
|---|---|---|---|
| 06:00 | 2,016.1 MW | 2,521.5 MW | 31.0 h |
| 09:00 (default) | 2,038.9 MW | 2,504.8 MW | 28.0 h |
| 12:00 | 1,901.0 MW | 2,359.1 MW | 24.1 h |
| 17:00 | 1,873.5 MW | 2,326.6 MW | 20.0 h |
| 23:00 | 1,825.0 MW | 2,277.5 MW | 13.0 h |

## 10. The most important caveat

**A persistent level difference between these two series is not necessarily
forecast error.**

Elexon does not document `FUELHH` wind outturn and the `WINDFOR` forecast as
covering an identical set of wind assets. `FUELHH` reflects metered generation;
a forecast produced for system operation may cover a wider fleet. If the two
describe different populations, part of the +1,748 MW bias is a **scope
difference**, not forecaster skill.

This cannot be resolved from the two datasets the challenge permits, and
Windsight does not pretend otherwise. The figures are reported as measured, the
caveat is shown in the product next to them, and the decomposition into bias
and dispersion is presented precisely so a reader can see how much of the
headline rests on the part in question. The dispersion component
(1,794 MW SD) is unaffected by any constant offset and is the more robust
measure of genuine forecast uncertainty.

## 11. Out of scope, by design

The challenge supplies national wind actuals and forecasts and nothing else.
Windsight therefore contains **no** demand, prices, thermal availability,
procurement cost or buy/sell recommendation. Any such figure would be invented
rather than measured.

The residual-demand panel is an explicitly labelled scenario driven by a demand
number **the user types in**. It propagates the measured error distribution
through that input and says so on screen. It is not an output of the Elexon
data.
