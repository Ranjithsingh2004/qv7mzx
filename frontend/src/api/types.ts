/** Response types mirroring the FastAPI schemas in `backend/app/schemas.py`. */

export interface Metrics {
  matched_hours: number;
  mae_mw: number | null;
  rmse_mw: number | null;
  bias_mw: number | null;
  error_sd_mw: number | null;
  bias_share_of_mse: number | null;
  mape_percent: number | null;
  mape_hours_included: number;
  mape_hours_excluded: number;
  mape_floor_mw: number;
  wmape_percent: number | null;
  normalised_mae_percent: number | null;
  correlation: number | null;
  max_abs_error_mw: number | null;
  mean_actual_mw: number | null;
  mean_forecast_mw: number | null;
  hours_over_forecast: number;
  hours_under_forecast: number;
}

export interface Coverage {
  delivery_days: number;
  expected_hours: number;
  hours_with_forecast: number;
  hours_with_actual: number;
  matched_hours: number;
  matched_percent: number;
  hours_missing_forecast: number;
  hours_missing_actual: number;
  hours_partial_actual: number;
  expected_settlement_periods: number;
  actual_settlement_periods: number;
  forecast_vintages_seen: number;
}

export type RecordStatus =
  | 'matched'
  | 'no_eligible_forecast'
  | 'no_forecast_published'
  | 'no_actual';

export interface PeriodRecord {
  target_start: string;
  target_start_london: string;
  delivery_date: string;
  decision_cutoff: string;
  status: RecordStatus;
  actual_mw: number | null;
  actual_partial: boolean;
  settlement_periods: number[];
  forecast_mw: number | null;
  forecast_publish_time: string | null;
  horizon_hours: number | null;
  error_mw: number | null;
  vintages_available: number;
  vintages_eligible: number;
}

export interface DailySummary {
  delivery_date: string;
  hours: number;
  matched_hours: number;
  unmatched_hours: number;
  mean_actual_mw: number | null;
  mean_forecast_mw: number | null;
  mae_mw: number | null;
  bias_mw: number | null;
  max_abs_error_mw: number | null;
}

export interface HorizonBucket {
  horizon_from_hours: number;
  horizon_to_hours: number;
  matched_hours: number;
  mae_mw: number | null;
  bias_mw: number | null;
}

export interface HourOfDayBucket {
  hour_of_day: number;
  matched_hours: number;
  mae_mw: number | null;
  bias_mw: number | null;
  mean_actual_mw: number | null;
}

export interface CutoffInfo {
  time_of_day: string;
  days_before: number;
  timezone: string;
  description: string;
  earliest_cutoff_utc: string;
  latest_cutoff_utc: string;
}

export interface SourceInfo {
  actuals: {
    dataset: string;
    filter: string;
    settlement_date_from: string;
    settlement_date_to: string;
    records: number;
  };
  forecasts: {
    dataset: string;
    publish_time_from: string;
    publish_time_to: string;
    records: number;
  };
}

export interface NormaliseSummary {
  rows_received: number;
  rows_accepted: number;
  rows_dropped_malformed: number;
  rows_dropped_wrong_fuel: number;
  duplicates_collapsed: number;
  issues: string[];
}

export interface Analysis {
  data_mode: string;
  decision_from: string;
  decision_to: string;
  delivery_from: string;
  delivery_to: string;
  cutoff: CutoffInfo;
  alignment_mode: AlignmentMode;
  alignment_description: string;
  mape_floor_mw: number;
  metrics: Metrics;
  coverage: Coverage;
  daily: DailySummary[];
  by_horizon: HorizonBucket[];
  by_hour_of_day: HourOfDayBucket[];
  records: PeriodRecord[];
  sources: SourceInfo;
  data_quality: { actuals: NormaliseSummary; forecasts: NormaliseSummary };
  generated_at: string;
}

export interface Vintage {
  publish_time: string;
  generation: number;
  horizon_hours: number;
  eligible: boolean;
  selected: boolean;
}

export interface VintageResponse {
  target_start: string;
  target_start_london: string;
  decision_cutoff: string;
  cutoff_description: string;
  vintages: Vintage[];
}

export interface CutoffSweepRow {
  cutoff_time: string;
  cutoff_description: string;
  matched_hours: number;
  mae_mw: number | null;
  rmse_mw: number | null;
  bias_mw: number | null;
  error_sd_mw: number | null;
  wmape_percent: number | null;
  mean_horizon_hours: number | null;
}

export interface CutoffSweepResponse {
  decision_from: string;
  decision_to: string;
  alignment_mode: string;
  rows: CutoffSweepRow[];
}

export interface Meta {
  metric_definitions: Record<string, string>;
  alignment_modes: Record<string, string>;
  datasets: Record<
    string,
    { name: string; description: string; resolution: string; units: string; documentation: string }
  >;
  defaults: Record<string, string | number>;
  assumptions: string[];
  sign_convention: string;
}

export interface Health {
  status: string;
  service: string;
  version: string;
  time_utc: string;
  upstream: 'reachable' | 'unreachable' | 'not_probed';
  cache: Record<string, unknown>;
}

export type AlignmentMode = 'hourly_mean' | 'period_start';

/** The parameter set every endpoint is scoped by. */
export interface AnalysisParams {
  decisionFrom: string;
  decisionTo: string;
  cutoffTime: string;
  cutoffDaysBefore: number;
  alignment: AlignmentMode;
  mapeFloorMw: number;
}
