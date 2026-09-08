"""Create the local Superset database, datasets, charts, and dashboards."""

from __future__ import annotations

import http.cookiejar
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any, Protocol


def load_local_environment(path: Path = Path("superset/.env")) -> None:
    """Load simple KEY=VALUE settings without overriding the shell environment."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_environment()

BASE_URL = os.environ.get("SUPERSET_URL", "http://localhost:8088").rstrip("/")
USERNAME = os.environ.get("SUPERSET_ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("SUPERSET_ADMIN_PASSWORD")

DATABASE_NAME = "Game Analytics"
DATABASE_URI = "duckdb:////app/data/superset_analytics.duckdb"
DASHBOARDS = {
    "loading": {
        "title": "Launch Health · Loading",
        "slug": "technical-launch-loading-funnel",
        "uuid_name": "dashboard",
    },
    "ftue": {
        "title": "Launch Health · FTUE",
        "slug": "technical-launch-ftue",
        "uuid_name": "dashboard/ftue",
    },
}

# Shared visual system for both dashboards. The palette keeps meaning stable:
# teal is the primary journey colour, navy anchors headings, amber flags friction,
# and coral is reserved for loss/failure. System fonts avoid external requests.
COLOR_SCHEME = "technicalLaunch"
DASHBOARD_CSS = """
.dashboard-container,
.dashboard-content,
.grid-container {
  background: #f4f7fa !important;
  color: #183243;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.dashboard-component-chart-holder,
.dashboard-component-markdown {
  background: #ffffff !important;
  border: 1px solid #dce6ec !important;
  border-radius: 12px !important;
  box-shadow: 0 2px 8px rgba(18, 48, 71, 0.06) !important;
  overflow: hidden;
}

.dashboard-component-chart-holder:hover {
  border-color: #a9c8d3 !important;
  box-shadow: 0 5px 16px rgba(18, 48, 71, 0.10) !important;
}

.dashboard-component-chart-holder .chart-header {
  color: #183243;
  font-weight: 650;
  padding: 14px 16px 4px;
}

.dashboard-component-chart-holder .slice_container {
  padding: 0 10px 10px;
}

.dashboard-markdown {
  color: #415b6b;
  font-size: 14px;
  line-height: 1.55;
  padding: 16px 20px !important;
}

.dashboard-component-markdown:has(.ga-section) {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}

.dashboard-component-markdown:has(.ga-section) .dashboard-markdown {
  padding: 8px 4px 2px !important;
}

.ga-dashboard-hero {
  border-left: 5px solid #18a7a0;
  padding-left: 16px;
}

.ga-dashboard-hero h2 {
  color: #123047;
  font-size: 26px;
  letter-spacing: -0.02em;
  margin: 0 0 4px;
}

.ga-dashboard-hero p,
.ga-section p {
  color: #607382;
  margin: 0;
}

.ga-eyebrow {
  color: #15817c;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.10em;
  margin-bottom: 5px;
  text-transform: uppercase;
}

.ga-section h3 {
  color: #123047;
  font-size: 18px;
  margin: 0 0 2px;
}

.big-number .header-line,
.big-number .subheader-line {
  white-space: normal !important;
}

.big-number .subheader-line {
  color: #607382 !important;
  font-size: 14px !important;
  line-height: 1.35 !important;
}

table thead th {
  color: #415b6b !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em;
}

table tbody tr:hover td {
  background: #edf8f7 !important;
}
""".strip()

OBSOLETE_CHARTS = {
    "Sessions reaching each launch step",
    "Step conversion detail",
}

DATASETS = {
    "mart_launch_summary": "Launch summary",
    "mart_primary_funnel": "Primary loading funnel",
    "mart_branch_outcomes": "Conditional outcomes",
    "mart_segment_performance": "Platform and version performance",
    "mart_ftue_summary": "Focused FTUE summary",
}


class BinaryDownloadClient(Protocol):
    def download(self, path: str) -> bytes: ...


class SupersetClient:
    def __init__(self) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )
        self.token = ""
        self.csrf_token = ""

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if method != "GET" and self.csrf_token:
            headers["X-CSRFToken"] = self.csrf_token
        request = urllib.request.Request(
            f"{BASE_URL}{path}", data=body, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read().replace(b"\x00", b"")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            message = f"{method} {path} failed ({exc.code}): {detail}"
            raise RuntimeError(message) from exc
        return json.loads(raw) if raw else {}

    def authenticate(self) -> None:
        if not PASSWORD:
            raise RuntimeError(
                "SUPERSET_ADMIN_PASSWORD is required; copy "
                "superset/.env.example to superset/.env and set local credentials"
            )
        login = self.request(
            "POST",
            "/api/v1/security/login",
            {
                "username": USERNAME,
                "password": PASSWORD,
                "provider": "db",
                "refresh": True,
            },
        )
        self.token = login["access_token"]
        self.csrf_token = self.request(
            "GET", "/api/v1/security/csrf_token/"
        )["result"]

    def list_results(self, resource: str) -> list[dict[str, Any]]:
        response = self.request("GET", f"/api/v1/{resource}/?q=(page_size:100)")
        return response.get("result", [])

    def download(self, path: str) -> bytes:
        headers = {"Authorization": f"Bearer {self.token}"}
        request = urllib.request.Request(
            f"{BASE_URL}{path}", headers=headers, method="GET"
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            message = f"GET {path} failed ({exc.code}): {detail}"
            raise RuntimeError(message) from exc


def stable_uuid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"game-analytics/{name}"))


def ensure_database(client: SupersetClient) -> int:
    for database in client.list_results("database"):
        if database["database_name"] == DATABASE_NAME:
            return int(database["id"])
    response = client.request(
        "POST",
        "/api/v1/database/",
        {
            "database_name": DATABASE_NAME,
            "sqlalchemy_uri": DATABASE_URI,
            "configuration_method": "sqlalchemy_form",
            "expose_in_sqllab": True,
            "allow_dml": False,
            "allow_ctas": False,
            "allow_cvas": False,
            "allow_run_async": False,
            "extra": json.dumps(
                {"engine_params": {"connect_args": {"read_only": True}}}
            ),
            "uuid": stable_uuid("database"),
        },
    )
    return int(response.get("id") or response["result"]["id"])


def ensure_datasets(client: SupersetClient, database_id: int) -> dict[str, int]:
    existing = {
        item["table_name"]: int(item["id"])
        for item in client.list_results("dataset")
        if item.get("schema") == "analytics"
        and item.get("database", {}).get("id") == database_id
    }
    ids: dict[str, int] = {}
    for table_name in DATASETS:
        if table_name in existing:
            ids[table_name] = existing[table_name]
            client.request(
                "PUT", f"/api/v1/dataset/{ids[table_name]}/refresh"
            )
            continue
        try:
            response = client.request(
                "POST",
                "/api/v1/dataset/",
                {
                    "database": database_id,
                    "schema": "analytics",
                    "table_name": table_name,
                    "normalize_columns": True,
                    "uuid": stable_uuid(f"dataset/{table_name}"),
                },
            )
            ids[table_name] = int(response.get("id") or response["result"]["id"])
        except (json.JSONDecodeError, KeyError):
            # Some DuckDB reflections return a response containing null bytes;
            # the dataset is still committed, so retrieve its generated ID.
            refreshed = {
                item["table_name"]: int(item["id"])
                for item in client.list_results("dataset")
                if item.get("schema") == "analytics"
                and item.get("database", {}).get("id") == database_id
            }
            ids[table_name] = refreshed[table_name]
    return ids


def ensure_dashboard(client: SupersetClient, dashboard_key: str) -> int:
    definition = DASHBOARDS[dashboard_key]
    for dashboard in client.list_results("dashboard"):
        if dashboard.get("slug") == definition["slug"]:
            return int(dashboard["id"])
    response = client.request(
        "POST",
        "/api/v1/dashboard/",
        {
            "dashboard_title": definition["title"],
            "slug": definition["slug"],
            "published": True,
            "position_json": "{}",
            "json_metadata": json.dumps({"native_filter_configuration": []}),
            "uuid": stable_uuid(definition["uuid_name"]),
        },
    )
    return int(response.get("id") or response["result"]["id"])


def simple_metric(column_name: str, aggregate: str = "SUM") -> dict[str, Any]:
    return {
        "aggregate": aggregate,
        "column": {"column_name": column_name},
        "expressionType": "SIMPLE",
        "label": f"{aggregate}({column_name})",
    }


def simple_filter(subject: str, comparator: str) -> dict[str, Any]:
    return {
        "clause": "WHERE",
        "comparator": comparator,
        "expressionType": "SIMPLE",
        "operator": "==",
        "sqlExpression": None,
        "subject": subject,
    }


def chart_definitions(dataset_ids: dict[str, int]) -> list[dict[str, Any]]:
    ftue_id = dataset_ids["mart_ftue_summary"]
    summary_id = dataset_ids["mart_launch_summary"]
    funnel_id = dataset_ids["mart_primary_funnel"]
    branch_id = dataset_ids["mart_branch_outcomes"]
    segment_id = dataset_ids["mart_segment_performance"]
    return [
        {
            "name": "First-session game entry",
            "dashboard": "ftue",
            "dataset_id": ftue_id,
            "viz_type": "big_number_total",
            "params": {
                "datasource": f"{ftue_id}__table",
                "viz_type": "big_number_total",
                "metric": simple_metric("first_session_game_entry_rate", "MAX"),
                "subheader": "86 / 101 new players",
                "y_axis_format": ".1%",
                "color_scheme": COLOR_SCHEME,
                "adhoc_filters": [simple_filter("aggregation_level", "overall")],
                "time_range": "No filter",
            },
        },
        {
            "name": "First-session battle activation",
            "dashboard": "ftue",
            "dataset_id": ftue_id,
            "viz_type": "big_number_total",
            "params": {
                "datasource": f"{ftue_id}__table",
                "viz_type": "big_number_total",
                "metric": simple_metric("first_session_activation_rate", "MAX"),
                "subheader": "43 / 101 · 50.0% of entrants",
                "y_axis_format": ".1%",
                "color_scheme": COLOR_SCHEME,
                "adhoc_filters": [simple_filter("aggregation_level", "overall")],
                "time_range": "No filter",
            },
        },
        {
            "name": "Time to first battle",
            "dashboard": "ftue",
            "dataset_id": ftue_id,
            "viz_type": "big_number_total",
            "params": {
                "datasource": f"{ftue_id}__table",
                "viz_type": "big_number_total",
                "metric": simple_metric(
                    "median_time_to_first_battle_minutes", "MAX"
                ),
                "subheader": "Median minutes · P90 23.0 · n=43",
                "y_axis_format": ".1f",
                "color_scheme": COLOR_SCHEME,
                "adhoc_filters": [simple_filter("aggregation_level", "overall")],
                "time_range": "No filter",
            },
        },
        {
            "name": "D1 client retention",
            "dashboard": "ftue",
            "dataset_id": ftue_id,
            "viz_type": "big_number_total",
            "params": {
                "datasource": f"{ftue_id}__table",
                "viz_type": "big_number_total",
                "metric": simple_metric("d1_retention_rate", "MAX"),
                "subheader": "45 / 93 eligible installs",
                "y_axis_format": ".1%",
                "color_scheme": COLOR_SCHEME,
                "adhoc_filters": [simple_filter("aggregation_level", "overall")],
                "time_range": "No filter",
            },
        },
        {
            "name": "D1 retention by platform and client version",
            "dashboard": "ftue",
            "dataset_id": ftue_id,
            "viz_type": "table",
            "params": {
                "datasource": f"{ftue_id}__table",
                "viz_type": "table",
                "query_mode": "raw",
                "all_columns": [
                    "platform",
                    "client_version",
                    "d1_mature_installs",
                    "d1_returned_players",
                    "d1_retention_rate",
                ],
                "adhoc_filters": [
                    simple_filter("aggregation_level", "platform_version")
                ],
                "order_by_cols": [
                    '["platform", true]',
                    '["client_version", true]',
                ],
                "column_config": {
                    "d1_mature_installs": {
                        "d3NumberFormat": ",d",
                        "showCellBars": False,
                    },
                    "d1_returned_players": {
                        "d3NumberFormat": ",d",
                        "showCellBars": False,
                    },
                    "d1_retention_rate": {
                        "d3NumberFormat": ".1%",
                        "showCellBars": False,
                    },
                },
                "verbose_map": {
                    "platform": "Platform",
                    "client_version": "Version",
                    "d1_mature_installs": "Eligible installs",
                    "d1_returned_players": "Returned players",
                    "d1_retention_rate": "D1 retention",
                },
                "color_scheme": COLOR_SCHEME,
                "row_limit": 20,
                "page_length": 20,
                "time_range": "No filter",
            },
        },
        {
            "name": "Start to game conversion",
            "dashboard": "loading",
            "dataset_id": summary_id,
            "viz_type": "big_number_total",
            "params": {
                "datasource": f"{summary_id}__table",
                "viz_type": "big_number_total",
                "metric": simple_metric("conversion_rate", "MAX"),
                "subheader": "577 / 621 sessions reached the game",
                "y_axis_format": ".1%",
                "color_scheme": COLOR_SCHEME,
                "time_range": "No filter",
            },
        },
        {
            "name": "Median loading time",
            "dashboard": "loading",
            "dataset_id": summary_id,
            "viz_type": "big_number_total",
            "params": {
                "datasource": f"{summary_id}__table",
                "viz_type": "big_number_total",
                "metric": simple_metric("median_loading_seconds", "MAX"),
                "subheader": "Seconds · P90 156.2 · n=556",
                "y_axis_format": ".1f",
                "color_scheme": COLOR_SCHEME,
                "time_range": "No filter",
            },
        },
        {
            "name": "Primary loading funnel",
            "dashboard": "loading",
            "dataset_id": funnel_id,
            "viz_type": "funnel",
            "params": {
                "datasource": f"{funnel_id}__table",
                "viz_type": "funnel",
                "groupby": ["step_name"],
                # The mart already publishes the governed count at one row per
                # step. MAX consumes that value without re-summing the metric.
                "metric": simple_metric("sessions", "MAX"),
                "row_limit": 10,
                # The funnel is a process sequence, not a value ranking. The
                # zero-padded label is a stable presentation key for Superset,
                # while ECharts must preserve the returned row order.
                "sort_by_metric": False,
                "sort": "none",
                # Superset's native Ordering control. Keeping this in form_data
                # makes Explore/dashboard query regeneration retain ORDER BY.
                "order_by_cols": ['["step_name", true]'],
                "show_legend": False,
                "show_labels": True,
                "number_format": ",d",
                "color_scheme": COLOR_SCHEME,
                "series_colors": json.dumps(
                    {
                        "01 · Client start": "#176b87",
                        "02 · Config loaded": "#176b87",
                        "03 · Localization complete": "#176b87",
                        "04 · Maintenance check": "#176b87",
                        "05 · Data load started": "#f2b134",
                        "06 · Data load complete": "#18a7a0",
                        "07 · Ready to start": "#18a7a0",
                        "08 · Login started": "#18a7a0",
                        "09 · Login complete": "#18a7a0",
                        "10 · Game joined": "#18a7a0",
                    }
                ),
                "time_range": "No filter",
            },
        },
        {
            "name": "Primary funnel conversion from start",
            "dashboard": "loading",
            "dataset_id": funnel_id,
            "viz_type": "echarts_timeseries_bar",
            "params": {
                "datasource": f"{funnel_id}__table",
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "step_name",
                "metrics": [simple_metric("start_conversion_rate", "MAX")],
                "groupby": [],
                "orientation": "vertical",
                "row_limit": 10,
                "order_by_cols": ['["step_name", true]'],
                "x_axis_sort_series_type": "name",
                "x_axis_sort_series_ascending": True,
                "show_value": True,
                "show_legend": False,
                "rich_tooltip": True,
                "y_axis_format": ".1%",
                "x_axis_label_rotation": 45,
                "truncateYAxis": False,
                "color_scheme": COLOR_SCHEME,
                "time_range": "No filter",
            },
        },
        {
            "name": "Drop-off sessions by transition",
            "dashboard": "loading",
            "dataset_id": funnel_id,
            "viz_type": "echarts_timeseries_bar",
            "params": {
                "datasource": f"{funnel_id}__table",
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "step_name",
                "metrics": [simple_metric("drop_off_sessions", "MAX")],
                "groupby": [],
                "orientation": "horizontal",
                "row_limit": 10,
                "order_by_cols": ['["step_name", true]'],
                "x_axis_sort_series_type": "name",
                "x_axis_sort_series_ascending": True,
                "show_value": True,
                "show_legend": False,
                "rich_tooltip": True,
                "y_axis_format": ",d",
                "color_scheme": COLOR_SCHEME,
                "series_colors": json.dumps(
                    {"MAX(drop_off_sessions)": "#d98e2b"}
                ),
                "time_range": "No filter",
            },
        },
        {
            "name": "Conditional outcomes",
            "dashboard": "loading",
            "dataset_id": branch_id,
            "viz_type": "table",
            "params": {
                "datasource": f"{branch_id}__table",
                "viz_type": "table",
                "query_mode": "raw",
                "all_columns": [
                    "branch_order",
                    "branch_outcome",
                    "observed_sessions",
                    "continued_sessions",
                    "continuation_rate",
                ],
                "column_config": {
                    "branch_order": {"d3NumberFormat": "d", "showCellBars": False},
                    "observed_sessions": {
                        "d3NumberFormat": ",d",
                        "showCellBars": False,
                    },
                    "continued_sessions": {
                        "d3NumberFormat": ",d",
                        "showCellBars": False,
                    },
                    "continuation_rate": {
                        "d3NumberFormat": ".1%",
                        "showCellBars": False,
                    },
                },
                "verbose_map": {
                    "branch_order": "Order",
                    "branch_outcome": "Outcome",
                    "observed_sessions": "Observed",
                    "continued_sessions": "Continued",
                    "continuation_rate": "Continuation",
                },
                "color_scheme": COLOR_SCHEME,
                "order_by_cols": ['["branch_order", true]'],
                "row_limit": 20,
                "page_length": 20,
                "time_range": "No filter",
            },
        },
        {
            "name": "Platform and version performance",
            "dashboard": "loading",
            "dataset_id": segment_id,
            "viz_type": "table",
            "params": {
                "datasource": f"{segment_id}__table",
                "viz_type": "table",
                "query_mode": "raw",
                "all_columns": [
                    "platform",
                    "client_version",
                    "started_sessions",
                    "joined_sessions",
                    "conversion_rate",
                    "median_loading_seconds",
                    "p90_loading_seconds",
                ],
                "order_by_cols": ['["platform", true]', '["client_version", true]'],
                "column_config": {
                    "started_sessions": {"d3NumberFormat": ",d", "showCellBars": False},
                    "joined_sessions": {"d3NumberFormat": ",d", "showCellBars": False},
                    "conversion_rate": {"d3NumberFormat": ".1%", "showCellBars": False},
                    "median_loading_seconds": {
                        "d3NumberFormat": ".1f",
                        "showCellBars": False,
                    },
                    "p90_loading_seconds": {
                        "d3NumberFormat": ".1f",
                        "showCellBars": False,
                    },
                },
                "verbose_map": {
                    "platform": "Platform",
                    "client_version": "Version",
                    "started_sessions": "Starts",
                    "joined_sessions": "Game entries",
                    "conversion_rate": "Completion",
                    "median_loading_seconds": "Median load (sec)",
                    "p90_loading_seconds": "P90 load (sec)",
                },
                "color_scheme": COLOR_SCHEME,
                "row_limit": 20,
                "page_length": 20,
                "time_range": "No filter",
            },
        },
    ]


def chart_query_context(
    definition: dict[str, Any], chart_id: int
) -> str:
    params = {**definition["params"], "slice_id": chart_id}
    viz_type = definition["viz_type"]
    if viz_type == "table":
        columns = params["all_columns"]
        metrics: list[dict[str, Any]] = []
    elif viz_type == "funnel":
        columns = params["groupby"]
        metrics = [params["metric"]]
    elif viz_type == "echarts_timeseries_bar":
        columns = [params["x_axis"], *params.get("groupby", [])]
        metrics = params["metrics"]
    else:
        columns = []
        metrics = [params["metric"]]
    query: dict[str, Any] = {
        "time_range": "No filter",
        "filters": [
            {
                "col": item["subject"],
                "op": item["operator"],
                "val": item["comparator"],
            }
            for item in params.get("adhoc_filters", [])
            if item.get("expressionType") == "SIMPLE"
        ],
        "extras": {"having": "", "where": ""},
        "applied_time_extras": {},
        "columns": columns,
        "metrics": metrics,
        "annotation_layers": [],
        "row_limit": params.get("row_limit", 10_000),
        "series_limit": 0,
        "order_desc": params.get("order_desc", True),
        "url_params": {},
        "custom_params": {},
        "custom_form_data": {},
    }
    if "order_by_cols" in params:
        query["orderby"] = [json.loads(item) for item in params["order_by_cols"]]
    context = {
        "datasource": {"id": definition["dataset_id"], "type": "table"},
        "force": False,
        "queries": [query],
        "form_data": {
            **params,
            "force": False,
            "result_format": "json",
            "result_type": "full",
        },
        "result_format": "json",
        "result_type": "full",
    }
    return json.dumps(context, separators=(",", ":"))


def ensure_charts(
    client: SupersetClient,
    dataset_ids: dict[str, int],
    dashboard_ids: dict[str, int],
) -> list[dict[str, Any]]:
    existing_by_name: dict[str, dict[str, Any]] = {}
    existing_by_uuid: dict[str, dict[str, Any]] = {}
    for chart in client.list_results("chart"):
        full_chart = client.request("GET", f"/api/v1/chart/{chart['id']}")["result"]
        existing_by_name.setdefault(full_chart["slice_name"], full_chart)
        if full_chart.get("uuid"):
            existing_by_uuid[full_chart["uuid"]] = full_chart
    charts: list[dict[str, Any]] = []
    for definition in chart_definitions(dataset_ids):
        dashboard_id = dashboard_ids[definition["dashboard"]]
        chart_uuid = stable_uuid(f"chart/{definition['name']}")
        existing = existing_by_uuid.get(chart_uuid) or existing_by_name.get(
            definition["name"]
        )
        if existing:
            chart_id = int(existing["id"])
        else:
            response = client.request(
                "POST",
                "/api/v1/chart/",
                {
                    "slice_name": definition["name"],
                    "viz_type": definition["viz_type"],
                    "datasource_id": definition["dataset_id"],
                    "datasource_type": "table",
                    "dashboards": [dashboard_id],
                    "description": (
                        "Generated from tested dbt marts; excludes malformed, "
                        "duplicate, and out-of-window events where applicable."
                    ),
                    "params": json.dumps(definition["params"]),
                    "uuid": chart_uuid,
                },
            )
            chart_id = int(response.get("id") or response["result"]["id"])
        client.request(
            "PUT",
            f"/api/v1/chart/{chart_id}",
            {
                "slice_name": definition["name"],
                "viz_type": definition["viz_type"],
                "datasource_id": definition["dataset_id"],
                "datasource_type": "table",
                "dashboards": [dashboard_id],
                "description": (
                    "Generated from tested dbt marts; excludes malformed, duplicate, "
                    "and out-of-window events where applicable."
                ),
                "params": json.dumps(definition["params"]),
                "query_context": chart_query_context(definition, chart_id),
                "uuid": chart_uuid,
            },
        )
        charts.append(
            {
                "id": chart_id,
                "slice_name": definition["name"],
                "dashboard": definition["dashboard"],
                "uuid": chart_uuid,
            }
        )
    return charts


def remove_obsolete_charts(client: SupersetClient) -> None:
    """Remove chart objects retired from this source-controlled dashboard package."""
    for chart in client.list_results("chart"):
        if chart.get("slice_name") in OBSOLETE_CHARTS:
            client.request("DELETE", f"/api/v1/chart/{chart['id']}")


def dashboard_layout(
    charts: list[dict[str, Any]], dashboard_key: str
) -> str:
    chart_by_name = {
        chart["slice_name"]: chart
        for chart in charts
        if chart["dashboard"] == dashboard_key
    }
    if dashboard_key == "loading":
        markdown_rows = {
            1: (
                "MARKDOWN-LOADING",
                '<div class="ga-dashboard-hero">'
                '<div class="ga-eyebrow">Technical launch · 14-day snapshot</div>'
                "<h2>Loading health</h2>"
                "<p>Can players move reliably and quickly from client start "
                "to game entry?</p></div>",
            ),
            3: (
                "MARKDOWN-LOADING-JOURNEY",
                '<div class="ga-section"><h3>Journey health</h3>'
                "<p>Ordered completion across the mandatory ten-step launch "
                "path.</p></div>",
            ),
            5: (
                "MARKDOWN-LOADING-FRICTION",
                '<div class="ga-section"><h3>Where players get stuck</h3>'
                "<p>Drop-off volume and optional-path outcomes identify the "
                "highest-priority investigations.</p></div>",
            ),
            7: (
                "MARKDOWN-LOADING-SEGMENTS",
                '<div class="ga-section"><h3>Release health by segment</h3>'
                "<p>Platform and client-version cuts are directional where "
                "samples are small.</p></div>",
            ),
            9: (
                "MARKDOWN-LOADING-COVERAGE",
                '<div class="ga-note"><div class="ga-eyebrow">Coverage &amp; method</div>'
                "<strong>18,400 / 18,479</strong> physical event rows are "
                "metric-eligible after quality exclusions. Loading-time "
                "percentiles use <strong>556</strong> complete, coherently "
                "ordered sessions. Conditional outcomes are not mandatory "
                "funnel stages.</div>",
            ),
        }
        chart_rows = {
            2: ["Start to game conversion", "Median loading time"],
            4: ["Primary loading funnel", "Primary funnel conversion from start"],
            6: ["Drop-off sessions by transition", "Conditional outcomes"],
            8: ["Platform and version performance"],
        }
        row_heights = {2: 20, 4: 44, 6: 38, 8: 34}
        row_widths = {4: [7, 5], 6: [7, 5]}
        markdown_heights = {1: 11, 3: 7, 5: 7, 7: 7, 9: 11}
    elif dashboard_key == "ftue":
        markdown_rows = {
            1: (
                "MARKDOWN-FTUE",
                '<div class="ga-dashboard-hero">'
                '<div class="ga-eyebrow">Technical launch · new-player experience</div>'
                "<h2>FTUE health</h2>"
                "<p>Do new players enter the game, reach the core loop quickly, "
                "and choose to return?</p></div>",
            ),
            3: (
                "MARKDOWN-FTUE-COHORTS",
                '<div class="ga-section"><h3>D1 retention by release</h3>'
                "<p>Platform and version cohorts provide investigation signals, "
                "not statistically conclusive rankings.</p></div>",
            ),
            5: (
                "MARKDOWN-FTUE-COVERAGE",
                '<div class="ga-note"><div class="ga-eyebrow">Definition &amp; caveat</div>'
                "FTUE uses the first eligible launch per install and "
                "<code>BATTLE_STARTED</code> as activation. D1 retention is an "
                "eligible client start on the exact next UTC calendar day. "
                "Cohorts contain <strong>5–35 installs</strong>, so differences "
                "are directional. Unsupported tutorial and progression KPIs are "
                "intentionally excluded.</div>",
            ),
        }
        chart_rows = {
            2: [
                "First-session game entry",
                "First-session battle activation",
                "Time to first battle",
                "D1 client retention",
            ],
            4: ["D1 retention by platform and client version"],
        }
        row_heights = {2: 22, 4: 34}
        row_widths = {}
        markdown_heights = {1: 11, 3: 7, 5: 12}
    else:
        raise ValueError(f"Unknown dashboard key: {dashboard_key}")

    row_numbers = sorted({*markdown_rows, *chart_rows})
    positions: dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
        "GRID_ID": {
            "id": "GRID_ID",
            "type": "GRID",
            "children": [f"ROW-{number}" for number in row_numbers],
            "parents": ["ROOT_ID"],
        },
        "HEADER_ID": {
            "id": "HEADER_ID",
            "type": "HEADER",
            "meta": {"text": DASHBOARDS[dashboard_key]["title"]},
        },
    }

    for row_number, (component_id, code) in markdown_rows.items():
        row_id = f"ROW-{row_number}"
        positions[row_id] = {
            "id": row_id,
            "type": "ROW",
            "children": [component_id],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        positions[component_id] = {
            "id": component_id,
            "type": "MARKDOWN",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {
                "code": code,
                "height": markdown_heights[row_number],
                "width": 12,
            },
        }

    for row_number, chart_names in chart_rows.items():
        row_charts = [chart_by_name[name] for name in chart_names]
        row_id = f"ROW-{row_number}"
        chart_keys = [f"CHART-{chart['id']}" for chart in row_charts]
        positions[row_id] = {
            "id": row_id,
            "type": "ROW",
            "children": chart_keys,
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        widths = row_widths.get(
            row_number, [12 // len(row_charts)] * len(row_charts)
        )
        for chart, width in zip(row_charts, widths, strict=True):
            chart_key = f"CHART-{chart['id']}"
            positions[chart_key] = {
                "id": chart_key,
                "type": "CHART",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", row_id],
                "meta": {
                    "chartId": chart["id"],
                    "height": row_heights[row_number],
                    "sliceName": chart["slice_name"],
                    "uuid": chart.get("uuid"),
                    "width": width,
                },
            }
    return json.dumps(positions)


def export_dashboard(
    client: BinaryDownloadClient,
    dashboard_ids: list[int],
    output_path: Path = Path("outputs/superset_dashboard.zip"),
) -> Path:
    """Download a portable Superset dashboard bundle and verify it is a ZIP."""
    selected_ids = ",".join(str(dashboard_id) for dashboard_id in dashboard_ids)
    query = urllib.parse.urlencode({"q": f"!({selected_ids})"})
    payload = client.download(f"/api/v1/dashboard/export/?{query}")
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise RuntimeError("Superset dashboard export did not return a valid ZIP file")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return output_path


def configure() -> None:
    client = SupersetClient()
    client.authenticate()
    database_id = ensure_database(client)
    dataset_ids = ensure_datasets(client, database_id)
    dashboard_ids = {
        key: ensure_dashboard(client, key)
        for key in DASHBOARDS
    }
    remove_obsolete_charts(client)
    charts = ensure_charts(client, dataset_ids, dashboard_ids)
    for key, dashboard_id in dashboard_ids.items():
        definition = DASHBOARDS[key]
        client.request(
            "PUT",
            f"/api/v1/dashboard/{dashboard_id}",
            {
                "dashboard_title": definition["title"],
                "slug": definition["slug"],
                "position_json": dashboard_layout(charts, key),
                "css": DASHBOARD_CSS,
                "published": True,
                "json_metadata": json.dumps(
                    {
                        "native_filter_configuration": [],
                        "refresh_frequency": 0,
                        "timed_refresh_immune_slices": [],
                    }
                ),
            },
        )
        print(
            f"Superset dashboard ready: "
            f"{BASE_URL}/superset/dashboard/{definition['slug']}/"
        )
    export_path = export_dashboard(client, list(dashboard_ids.values()))
    print(f"Database ID: {database_id}; dashboard IDs: {dashboard_ids}")
    print(
        f"Datasets: {len(dataset_ids)}; charts: {len(charts)}; "
        f"dashboards: {len(dashboard_ids)}"
    )
    print(f"Portable dashboard export: {export_path}")


if __name__ == "__main__":
    try:
        configure()
    except (OSError, RuntimeError, KeyError, ValueError) as exc:
        print(f"Superset configuration failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
