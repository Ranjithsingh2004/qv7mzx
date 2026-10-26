"""Accuracy metric arithmetic, including the undefined cases."""

from __future__ import annotations

import math

import pytest

from app.analysis.metrics import compute_metrics


class TestKnownValues:
    """Hand-checked arithmetic on a tiny set of errors: +20, -10, -5."""

    @pytest.fixture
    def metrics(self):
        return compute_metrics([(100.0, 80.0), (120.0, 130.0), (90.0, 95.0)])

    def test_mae(self, metrics):
        assert metrics.mae_mw == pytest.approx((20 + 10 + 5) / 3)

    def test_rmse(self, metrics):
        assert metrics.rmse_mw == pytest.approx(math.sqrt((400 + 100 + 25) / 3))

    def test_bias_is_signed_mean_error(self, metrics):
        assert metrics.bias_mw == pytest.approx((20 - 10 - 5) / 3)

    def test_rmse_is_never_below_mae(self, metrics):
        assert metrics.rmse_mw >= metrics.mae_mw

    def test_mse_decomposes_into_bias_squared_plus_variance(self, metrics):
        mse = metrics.rmse_mw**2
        assert mse == pytest.approx(metrics.bias_mw**2 + metrics.error_sd_mw**2)
        assert metrics.bias_share_of_mse == pytest.approx(metrics.bias_mw**2 / mse)

    def test_over_and_under_counts(self, metrics):
        assert (metrics.hours_over_forecast, metrics.hours_under_forecast) == (1, 2)

    def test_mean_levels(self, metrics):
        assert metrics.mean_forecast_mw == pytest.approx(310 / 3)
        assert metrics.mean_actual_mw == pytest.approx(305 / 3)

    def test_wmape_is_total_error_over_total_actual(self, metrics):
        assert metrics.wmape_percent == pytest.approx(35 / 305 * 100)

    def test_max_abs_error(self, metrics):
        assert metrics.max_abs_error_mw == 20


class TestSignConvention:
    def test_positive_bias_means_over_forecast(self):
        # Forecast 120 against an actual of 100: the forecast ran high.
        metrics = compute_metrics([(120.0, 100.0)])
        assert metrics.bias_mw == 20
        assert metrics.hours_over_forecast == 1

    def test_negative_bias_means_under_forecast(self):
        metrics = compute_metrics([(80.0, 100.0)])
        assert metrics.bias_mw == -20
        assert metrics.hours_under_forecast == 1

    def test_a_perfect_forecast_scores_zero(self):
        metrics = compute_metrics([(100.0, 100.0), (50.0, 50.0)])
        assert metrics.mae_mw == 0
        assert metrics.rmse_mw == 0
        assert metrics.bias_mw == 0
        assert metrics.bias_share_of_mse is None  # 0/0 is not reported as a number


class TestMapePolicy:
    def test_excludes_actuals_at_or_below_the_floor(self):
        metrics = compute_metrics([(100.0, 100.0), (50.0, 10.0)], mape_floor_mw=50)
        assert metrics.mape_hours_included == 1
        assert metrics.mape_hours_excluded == 1
        assert metrics.mape_percent == pytest.approx(0.0)

    def test_is_none_when_every_hour_is_excluded(self):
        # Reporting 0% here would read as a perfect forecast.
        metrics = compute_metrics([(50.0, 1.0)], mape_floor_mw=100)
        assert metrics.mape_percent is None
        assert metrics.mape_hours_included == 0

    def test_wmape_survives_a_near_zero_hour_that_mape_cannot(self):
        metrics = compute_metrics([(10.0, 1.0), (1000.0, 1000.0)], mape_floor_mw=100)
        assert metrics.mape_percent == pytest.approx(0.0)
        assert metrics.wmape_percent == pytest.approx(9 / 1001 * 100)

    def test_zero_actual_does_not_raise(self):
        metrics = compute_metrics([(10.0, 0.0)], mape_floor_mw=0)
        assert metrics.mape_percent is None
        assert metrics.mae_mw == 10

    def test_floor_is_echoed_back(self):
        assert compute_metrics([(1.0, 1.0)], mape_floor_mw=42).mape_floor_mw == 42

    def test_negative_floor_is_rejected(self):
        with pytest.raises(ValueError, match="mape_floor_mw"):
            compute_metrics([(1.0, 1.0)], mape_floor_mw=-1)


class TestEmptyAndDegenerate:
    def test_no_matched_hours_yields_nulls_not_zeros(self):
        metrics = compute_metrics([])
        assert metrics.matched_hours == 0
        assert metrics.mae_mw is None
        assert metrics.rmse_mw is None
        assert metrics.bias_mw is None
        assert metrics.correlation is None

    def test_single_point_has_no_correlation(self):
        assert compute_metrics([(100.0, 90.0)]).correlation is None

    def test_constant_series_has_no_correlation(self):
        # Zero variance makes Pearson undefined rather than zero.
        assert compute_metrics([(100.0, 50.0), (100.0, 50.0)]).correlation is None

    def test_total_actual_of_zero_gives_no_wmape(self):
        assert compute_metrics([(10.0, 0.0), (5.0, 0.0)]).wmape_percent is None

    def test_perfect_correlation(self):
        pairs = [(10.0, 20.0), (20.0, 40.0), (30.0, 60.0)]
        assert compute_metrics(pairs).correlation == pytest.approx(1.0)

    def test_negative_actuals_are_handled(self):
        metrics = compute_metrics([(10.0, -5.0)], mape_floor_mw=0)
        assert metrics.mae_mw == 15
        assert metrics.mape_percent is None  # negative actual is below the floor
