"""HTTP surface: routes, response shapes, error bodies, CSV export.

Upstream Elexon calls are mocked from the JSON fixtures, so these exercise the
real routing, validation and serialisation paths with no network.
"""

from __future__ import annotations

import csv
import io

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import CSV_COLUMNS, app

FUELHH = "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream"
WINDFOR = "https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream"

#: The fixtures cover delivery days 2026-01-02..03, i.e. decisions on 01..02.
WINDOW = {"decision_from": "2026-01-01", "decision_to": "2026-01-02"}


@pytest.fixture
def client(fuelhh_rows, windfor_rows):
    """A TestClient whose upstream is served from fixtures."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FUELHH).mock(return_value=httpx.Response(200, json=fuelhh_rows))
        mock.get(WINDFOR).mock(return_value=httpx.Response(200, json=windfor_rows))
        with TestClient(app) as test_client:
            test_client.app.state.service.clear_cache()
            yield test_client


class TestHealth:
    def test_health_is_ok_without_touching_upstream(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["upstream"] == "not_probed"
        assert body["version"]
        assert "cache" in body

    def test_probe_reports_upstream_reachable(self, client):
        body = client.get("/api/health?probe=true").json()
        assert body["upstream"] == "reachable"

    @respx.mock
    def test_probe_reports_unreachable_without_failing_the_endpoint(self):
        respx.get(WINDFOR).mock(return_value=httpx.Response(503))
        with TestClient(app) as test_client:
            response = test_client.get("/api/health?probe=true")
        assert response.status_code == 200
        assert response.json()["upstream"] == "unreachable"


class TestMeta:
    def test_exposes_metric_definitions_and_assumptions(self, client):
        body = client.get("/api/meta").json()
        for metric in ("mae_mw", "rmse_mw", "bias_mw", "mape_percent", "wmape_percent"):
            assert metric in body["metric_definitions"]
        assert set(body["alignment_modes"]) == {"hourly_mean", "period_start"}
        assert body["datasets"]["actuals"]["name"] == "FUELHH"
        assert body["datasets"]["forecasts"]["name"] == "WINDFOR"
        assert "forecast - actual" in body["sign_convention"]
        # The cutoff assumption must be stated, not implied.
        assert any("09:00 Europe/London" in note for note in body["assumptions"])
        assert any("not a confirmed" in note for note in body["assumptions"])


class TestAnalysis:
    def test_returns_a_fully_matched_window(self, client):
        body = client.get("/api/analysis", params=WINDOW).json()
        assert body["data_mode"] == "live_elexon"
        assert body["delivery_from"] == "2026-01-02"
        assert body["delivery_to"] == "2026-01-03"
        assert body["coverage"]["expected_hours"] == 48
        assert body["coverage"]["matched_hours"] == 48
        assert body["metrics"]["matched_hours"] == 48
        assert len(body["records"]) == 48

    def test_cutoff_block_describes_the_assumption(self, client):
        cutoff = client.get("/api/analysis", params=WINDOW).json()["cutoff"]
        assert cutoff["time_of_day"] == "09:00"
        assert cutoff["days_before"] == 1
        assert cutoff["timezone"] == "Europe/London"
        assert cutoff["description"] == "09:00 Europe/London on D-1"

    def test_every_record_respects_its_cutoff(self, client):
        for record in client.get("/api/analysis", params=WINDOW).json()["records"]:
            assert record["forecast_publish_time"] <= record["decision_cutoff"]

    def test_records_carry_both_utc_and_london_timestamps(self, client):
        record = client.get("/api/analysis", params=WINDOW).json()["records"][0]
        assert record["target_start"].endswith("Z")
        assert "+0000" in record["target_start_london"]

    def test_error_equals_forecast_minus_actual(self, client):
        for record in client.get("/api/analysis", params=WINDOW).json()["records"]:
            assert record["error_mw"] == pytest.approx(record["forecast_mw"] - record["actual_mw"])

    def test_metrics_are_internally_consistent(self, client):
        metrics = client.get("/api/analysis", params=WINDOW).json()["metrics"]
        assert metrics["rmse_mw"] >= metrics["mae_mw"]
        assert metrics["mae_mw"] >= abs(metrics["bias_mw"])
        assert metrics["hours_over_forecast"] + metrics["hours_under_forecast"] <= 48

    def test_summaries_and_sources_are_present(self, client):
        body = client.get("/api/analysis", params=WINDOW).json()
        assert len(body["daily"]) == 2
        assert len(body["by_hour_of_day"]) == 24
        assert body["by_horizon"]
        assert body["sources"]["actuals"]["filter"] == "fuelType=WIND"
        assert body["sources"]["forecasts"]["dataset"] == "WINDFOR"
        assert body["data_quality"]["actuals"]["rows_accepted"] > 0

    def test_alignment_mode_is_honoured(self, client):
        body = client.get("/api/analysis", params={**WINDOW, "alignment": "period_start"}).json()
        assert body["alignment_mode"] == "period_start"
        assert all(len(r["settlement_periods"]) == 1 for r in body["records"])

    def test_a_later_cutoff_selects_a_later_vintage(self, client):
        early = client.get("/api/analysis", params={**WINDOW, "cutoff_time": "06:00"}).json()
        late = client.get("/api/analysis", params={**WINDOW, "cutoff_time": "23:00"}).json()
        assert (
            late["records"][0]["forecast_publish_time"]
            > early["records"][0]["forecast_publish_time"]
        )
        assert late["records"][0]["horizon_hours"] < early["records"][0]["horizon_hours"]

    def test_openapi_document_is_served(self, client):
        schema = client.get("/api/openapi.json").json()
        assert "/api/analysis" in schema["paths"]
        assert "/api/analysis/vintages" in schema["paths"]
        assert "/api/analysis/export.csv" in schema["paths"]

    def test_docs_page_is_served(self, client):
        assert client.get("/api/docs").status_code == 200


class TestVintagesEndpoint:
    def test_lists_vintages_with_exactly_one_selected(self, client):
        body = client.get(
            "/api/analysis/vintages",
            params={**WINDOW, "target": "2026-01-03T12:00:00Z"},
        ).json()
        assert body["target_start"] == "2026-01-03T12:00:00Z"
        assert body["decision_cutoff"] == "2026-01-02T09:00:00Z"
        assert len(body["vintages"]) > 1
        assert sum(1 for v in body["vintages"] if v["selected"]) == 1

    def test_the_selected_vintage_is_the_latest_eligible_one(self, client):
        vintages = client.get(
            "/api/analysis/vintages",
            params={**WINDOW, "target": "2026-01-03T12:00:00Z"},
        ).json()["vintages"]
        selected = next(v for v in vintages if v["selected"])
        eligible = [v for v in vintages if v["eligible"]]
        assert selected["publish_time"] == max(v["publish_time"] for v in eligible)
        assert all(not v["selected"] for v in vintages if not v["eligible"])

    def test_later_vintages_are_shown_but_marked_ineligible(self, client):
        """Showing the excluded vintages is how the rule is demonstrated."""
        vintages = client.get(
            "/api/analysis/vintages",
            params={**WINDOW, "target": "2026-01-03T12:00:00Z"},
        ).json()["vintages"]
        assert any(not v["eligible"] for v in vintages)

    def test_unknown_target_is_a_422_with_a_clear_message(self, client):
        response = client.get(
            "/api/analysis/vintages", params={**WINDOW, "target": "1999-01-01T00:00:00Z"}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_request"
        assert "no forecast vintages" in response.json()["message"]


class TestCutoffSweep:
    def test_evaluates_each_requested_cutoff(self, client):
        body = client.get(
            "/api/analysis/cutoff-sweep", params={**WINDOW, "cutoff_times": "06:00,12:00,23:00"}
        ).json()
        assert [row["cutoff_time"] for row in body["rows"]] == ["06:00", "12:00", "23:00"]
        assert all(row["matched_hours"] == 48 for row in body["rows"])

    def test_later_cutoffs_have_shorter_horizons(self, client):
        rows = client.get(
            "/api/analysis/cutoff-sweep", params={**WINDOW, "cutoff_times": "06:00,23:00"}
        ).json()["rows"]
        assert rows[0]["mean_horizon_hours"] > rows[1]["mean_horizon_hours"]

    def test_empty_cutoff_list_is_rejected(self, client):
        response = client.get(
            "/api/analysis/cutoff-sweep", params={**WINDOW, "cutoff_times": " , "}
        )
        assert response.status_code == 422

    def test_bad_cutoff_time_is_rejected(self, client):
        response = client.get(
            "/api/analysis/cutoff-sweep", params={**WINDOW, "cutoff_times": "06:00,99:99"}
        )
        assert response.status_code == 422


class TestCsvExport:
    def test_serves_a_csv_attachment(self, client):
        response = client.get("/api/analysis/export.csv", params=WINDOW)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert ".csv" in response.headers["content-disposition"]

    def test_header_and_row_count_match_the_analysis(self, client):
        response = client.get("/api/analysis/export.csv", params=WINDOW)
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == CSV_COLUMNS
        assert len(rows) == 1 + 48

    def test_values_agree_with_the_json_endpoint(self, client):
        """One analysis serves both, so the file and the screen cannot diverge."""
        expected = client.get("/api/analysis", params=WINDOW).json()["records"][0]
        rows = list(
            csv.DictReader(io.StringIO(client.get("/api/analysis/export.csv", params=WINDOW).text))
        )
        assert rows[0]["target_start_utc"] == expected["target_start"]
        assert rows[0]["status"] == expected["status"]
        assert float(rows[0]["actual_mw"]) == pytest.approx(expected["actual_mw"])
        assert float(rows[0]["forecast_mw"]) == pytest.approx(expected["forecast_mw"])
        assert float(rows[0]["error_mw"]) == pytest.approx(expected["error_mw"])
        assert rows[0]["forecast_publish_time_utc"] == expected["forecast_publish_time"]

    def test_filename_records_the_window_and_cutoff(self, client):
        disposition = client.get(
            "/api/analysis/export.csv", params={**WINDOW, "cutoff_time": "12:30"}
        ).headers["content-disposition"]
        assert "20260101-20260102" in disposition
        assert "cutoff1230" in disposition

    @respx.mock
    def test_unmatched_hours_appear_with_empty_values_not_zeros(self):
        """A gap must read as a gap in a spreadsheet, not as zero generation."""
        respx.get(FUELHH).mock(return_value=httpx.Response(200, json=[]))
        respx.get(WINDFOR).mock(return_value=httpx.Response(200, json=[]))
        with TestClient(app) as test_client:
            test_client.app.state.service.clear_cache()
            text = test_client.get("/api/analysis/export.csv", params=WINDOW).text
        rows = list(csv.DictReader(io.StringIO(text)))
        assert len(rows) == 48
        assert all(row["status"] == "no_forecast_published" for row in rows)
        assert all(row["actual_mw"] == "" and row["forecast_mw"] == "" for row in rows)
        assert all(row["error_mw"] == "" for row in rows)


class TestValidation:
    @pytest.mark.parametrize(
        "params,fragment",
        [
            ({"decision_from": "notadate"}, "yyyy-MM-dd"),
            ({"decision_from": "2026-01-10", "decision_to": "2026-01-01"}, "not be earlier"),
            ({"decision_from": "2020-01-01", "decision_to": "2026-01-01"}, "maximum"),
            ({"cutoff_time": "99:99"}, "out of range"),
            ({"cutoff_time": "noon"}, "HH:MM"),
            ({"alignment": "median"}, "alignment must be one of"),
            ({"cutoff_days_before": 99}, "less than or equal"),
            ({"mape_floor_mw": -5}, "greater than or equal"),
        ],
    )
    def test_bad_parameters_return_422_with_one_body_shape(self, client, params, fragment):
        response = client.get("/api/analysis", params=params)
        assert response.status_code == 422
        body = response.json()
        # Domain errors and FastAPI's own parameter errors share this shape.
        assert body["code"] == "invalid_request"
        assert fragment in body["message"]

    def test_upstream_failure_is_reported_as_502(self, fuelhh_rows):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(FUELHH).mock(return_value=httpx.Response(200, json=fuelhh_rows))
            mock.get(WINDFOR).mock(return_value=httpx.Response(503))
            with TestClient(app) as test_client:
                test_client.app.state.service.clear_cache()
                response = test_client.get("/api/analysis", params=WINDOW)
        assert response.status_code == 502
        assert response.json()["code"] == "upstream_unavailable"


class TestCaching:
    def test_repeated_identical_requests_hit_the_cache(self, client):
        client.get("/api/analysis", params=WINDOW)
        client.get("/api/analysis", params=WINDOW)
        stats = client.get("/api/health").json()["cache"]["analyses"]
        assert stats["hits"] >= 1

    def test_changing_the_cutoff_reuses_downloaded_data(self, client):
        client.get("/api/analysis", params=WINDOW)
        client.get("/api/analysis", params={**WINDOW, "cutoff_time": "12:00"})
        # Same fetch window, different analysis: the raw download is shared.
        assert client.get("/api/health").json()["cache"]["source_data"]["hits"] >= 1
