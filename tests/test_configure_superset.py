from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

from configure_superset import (
    COLOR_SCHEME,
    DASHBOARD_CSS,
    chart_definitions,
    chart_query_context,
    dashboard_layout,
    export_dashboard,
)


def test_dashboards_share_a_single_visual_system() -> None:
    assert COLOR_SCHEME == "technicalLaunch"
    assert "font-family: Inter" in DASHBOARD_CSS
    assert "#f4f7fa" in DASHBOARD_CSS
    assert "#18a7a0" in DASHBOARD_CSS

    dataset_ids = {
        "mart_launch_summary": 2,
        "mart_primary_funnel": 3,
        "mart_branch_outcomes": 4,
        "mart_segment_performance": 5,
        "mart_ftue_summary": 6,
    }
    for definition in chart_definitions(dataset_ids):
        assert definition["params"]["color_scheme"] == COLOR_SCHEME


def test_primary_funnel_preserves_business_step_order() -> None:
    dataset_ids = {
        "mart_launch_summary": 2,
        "mart_primary_funnel": 3,
        "mart_branch_outcomes": 4,
        "mart_segment_performance": 5,
        "mart_ftue_summary": 6,
    }
    definition = next(
        item
        for item in chart_definitions(dataset_ids)
        if item["name"] == "Primary loading funnel"
    )

    assert definition["params"]["sort_by_metric"] is False
    assert definition["params"]["sort"] == "none"
    assert definition["params"]["metric"]["aggregate"] == "MAX"
    assert definition["params"]["order_by_cols"] == ['["step_name", true]']

    context = json.loads(chart_query_context(definition, chart_id=3))
    assert context["queries"][0]["orderby"] == [["step_name", True]]


def test_table_ordering_columns_are_selected() -> None:
    dataset_ids = {
        "mart_launch_summary": 2,
        "mart_primary_funnel": 3,
        "mart_branch_outcomes": 4,
        "mart_segment_performance": 5,
        "mart_ftue_summary": 6,
    }

    for definition in chart_definitions(dataset_ids):
        params = definition["params"]
        if definition["viz_type"] != "table":
            continue
        selected = set(params["all_columns"])
        ordered = {json.loads(item)[0] for item in params.get("order_by_cols", [])}
        assert ordered <= selected


def test_funnel_bar_charts_use_governed_metrics_and_step_order() -> None:
    dataset_ids = {
        "mart_launch_summary": 2,
        "mart_primary_funnel": 3,
        "mart_branch_outcomes": 4,
        "mart_segment_performance": 5,
        "mart_ftue_summary": 6,
    }
    definitions = {
        item["name"]: item
        for item in chart_definitions(dataset_ids)
        if item["viz_type"] == "echarts_timeseries_bar"
    }

    assert set(definitions) == {
        "Primary funnel conversion from start",
        "Drop-off sessions by transition",
    }
    expected_columns = {
        "Primary funnel conversion from start": "start_conversion_rate",
        "Drop-off sessions by transition": "drop_off_sessions",
    }
    for name, definition in definitions.items():
        params = definition["params"]
        assert params["x_axis"] == "step_name"
        assert params["order_by_cols"] == ['["step_name", true]']
        assert params["metrics"][0]["aggregate"] == "MAX"
        assert params["metrics"][0]["column"]["column_name"] == expected_columns[name]

        context = json.loads(chart_query_context(definition, chart_id=10))
        assert context["queries"][0]["columns"] == ["step_name"]
        assert context["queries"][0]["orderby"] == [["step_name", True]]

    conversion = definitions["Primary funnel conversion from start"]["params"]
    assert conversion["orientation"] == "vertical"
    assert conversion["y_axis_format"] == ".1%"


def test_dashboard_layout_separates_loading_from_ftue() -> None:
    dataset_ids = {
        "mart_launch_summary": 2,
        "mart_primary_funnel": 3,
        "mart_branch_outcomes": 4,
        "mart_segment_performance": 5,
        "mart_ftue_summary": 6,
    }
    charts = [
        {
            "id": index,
            "slice_name": definition["name"],
            "dashboard": definition["dashboard"],
            "uuid": f"chart-{index}",
        }
        for index, definition in enumerate(chart_definitions(dataset_ids), start=1)
    ]

    loading = dashboard_layout(charts, "loading")
    ftue = dashboard_layout(charts, "ftue")

    assert "Primary loading funnel" in loading
    assert "First-session game entry" not in loading
    assert "First-session game entry" in ftue
    assert "D1 retention by platform and client version" in ftue
    assert "Primary loading funnel" not in ftue

    ftue_positions = json.loads(ftue)
    ftue_kpi_row = ftue_positions["ROW-2"]
    assert len(ftue_kpi_row["children"]) == 4
    assert {
        ftue_positions[chart_id]["meta"]["width"]
        for chart_id in ftue_kpi_row["children"]
    } == {3}

    loading_positions = json.loads(loading)
    journey_row = loading_positions["ROW-4"]
    assert [
        loading_positions[chart_id]["meta"]["width"]
        for chart_id in journey_row["children"]
    ] == [7, 5]


def test_ftue_charts_filter_the_canonical_metric_grain() -> None:
    dataset_ids = {
        "mart_launch_summary": 2,
        "mart_primary_funnel": 3,
        "mart_branch_outcomes": 4,
        "mart_segment_performance": 5,
        "mart_ftue_summary": 6,
    }
    definitions = {
        item["name"]: item
        for item in chart_definitions(dataset_ids)
        if item["dashboard"] == "ftue"
    }

    for name in (
        "First-session game entry",
        "First-session battle activation",
        "Time to first battle",
        "D1 client retention",
    ):
        context = json.loads(chart_query_context(definitions[name], chart_id=10))
        assert context["queries"][0]["filters"] == [
            {"col": "aggregation_level", "op": "==", "val": "overall"}
        ]

    table = definitions["D1 retention by platform and client version"]
    context = json.loads(chart_query_context(table, chart_id=11))
    assert context["queries"][0]["filters"] == [
        {
            "col": "aggregation_level",
            "op": "==",
            "val": "platform_version",
        }
    ]


def test_export_dashboard_writes_valid_portable_bundle(tmp_path: Path) -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dashboard_export/dashboard.yaml", "dashboard_title: Test")

    class StubClient:
        requested_path = ""

        def download(self, path: str) -> bytes:
            self.requested_path = path
            return buffer.getvalue()

    client = StubClient()
    output_path = tmp_path / "dashboard.zip"

    result = export_dashboard(
        client, dashboard_ids=[17, 23], output_path=output_path
    )

    assert result == output_path
    assert zipfile.is_zipfile(output_path)
    assert client.requested_path == "/api/v1/dashboard/export/?q=%21%2817%2C23%29"


def test_export_dashboard_rejects_non_zip_response(tmp_path: Path) -> None:
    class StubClient:
        def download(self, path: str) -> bytes:
            return b'{"message": "not an export"}'

    output_path = tmp_path / "dashboard.zip"

    try:
        export_dashboard(StubClient(), [17], output_path)
    except RuntimeError as exc:
        assert "valid ZIP" in str(exc)
    else:
        raise AssertionError("Expected an invalid export response to fail")

    assert not output_path.exists()
