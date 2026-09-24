from __future__ import annotations

from pathlib import Path

import pytest

from analysis_agent import DataAnalysisAgent
from analysis_agent.planner import LocalPlanner
from analysis_agent.sql_guard import UnsafeSQLError, validate_readonly_sql


ROOT = Path(__file__).resolve().parents[1]


def test_planner_maps_metric_dimension_and_filter() -> None:
    plan = LocalPlanner().plan("2025年各产品的审批通过率")
    assert plan.metric == "approval_rate"
    assert plan.dimensions == ["product"]
    assert plan.filters[0].field == "application_year"
    assert 2025 in plan.filters[0].value


def test_time_series_plan_does_not_truncate_two_year_window() -> None:
    plan = LocalPlanner().plan("月度申请量趋势")
    assert plan.dimensions == ["application_month"]
    assert plan.limit == 120


def test_two_dimension_plan_preserves_complete_cross_table() -> None:
    plan = LocalPlanner().plan("不同信用等级和贷款期限的违约率对比")
    assert plan.dimensions == ["grade", "term_months"]
    assert plan.limit == 200


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE credit_applications",
        "SELECT * FROM credit_applications LIMIT 5; DELETE FROM credit_applications",
        "SELECT * FROM read_csv_auto('private.csv') LIMIT 5",
        "SELECT secret FROM credit_applications LIMIT 5",
        "SELECT * FROM credit_applications",
    ],
)
def test_sql_guard_blocks_unsafe_queries(sql: str) -> None:
    with pytest.raises(UnsafeSQLError):
        validate_readonly_sql(sql)


def test_agent_executes_grounded_analysis() -> None:
    agent = DataAnalysisAgent(provider="local", audit_path=ROOT / "data" / "audit" / "test_events.jsonl")
    result = agent.analyze("各信用等级的违约率是多少", log_event=False)
    assert result.plan.metric == "default_rate"
    assert result.plan.dimensions == ["grade"]
    assert len(result.rows) == 7
    assert "metric_value" in result.columns
    assert "拒绝申请不进入分母" in result.metric_definition
    assert all("grade" in row for row in result.rows)


def test_agent_uses_readonly_sql_with_limit() -> None:
    agent = DataAnalysisAgent(provider="local", audit_path=ROOT / "data" / "audit" / "test_events.jsonl")
    result = agent.analyze("2025年各产品审批通过率", log_event=False)
    assert result.sql.startswith("SELECT")
    assert "LIMIT" in result.sql
    assert "2025" in result.sql
