from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .audit import AuditLogger
from .charting import resolved_chart_type
from .models import AgentResult, AnalysisPlan
from .planner import PlannerRouter
from .semantic_layer import DIMENSIONS, FILTERABLE_FIELDS, METRICS
from .sql_compiler import PlanValidationError, compile_plan
from .sql_guard import UnsafeSQLError, validate_readonly_sql
from .tools import AnalyticsTools, format_metric


class AgentExecutionError(RuntimeError):
    pass


class DataAnalysisAgent:
    def __init__(
        self,
        database_path: str | Path | None = None,
        provider: str | None = None,
        audit_path: str | Path | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        self.database_path = Path(database_path or root / "data" / "analytics_demo.duckdb")
        self.planner = PlannerRouter(provider)
        self.tools = AnalyticsTools(self.database_path)
        self.audit = AuditLogger(
            audit_path
            or os.getenv("ANALYTICS_AUDIT_PATH", str(root / "data" / "audit" / "agent_events.jsonl"))
        )

    def analyze(self, question: str, log_event: bool = True) -> AgentResult:
        started = time.perf_counter()
        question = question.strip()
        if not question:
            raise AgentExecutionError("请输入需要分析的问题。")

        planning = self.planner.plan(question)
        trace = list(planning.trace)
        warnings = list(planning.warnings)
        plan = planning.plan

        self._validate_plan(plan)
        trace.append(
            {
                "node": "semantic_validation",
                "status": "ok",
                "detail": f"指标 {plan.metric}、维度 {plan.dimensions or ['整体']} 通过白名单校验",
            }
        )

        try:
            sql = compile_plan(plan)
        except PlanValidationError as exc:
            raise AgentExecutionError(f"分析计划无法编译：{exc}") from exc
        trace.append({"node": "sql_compiler", "status": "ok", "detail": "AnalysisPlan 已转换为确定性 SQL"})

        try:
            validate_readonly_sql(sql)
        except UnsafeSQLError as exc:
            raise AgentExecutionError(f"SQL 安全校验失败：{exc}") from exc
        trace.append({"node": "sql_guard", "status": "ok", "detail": "只读、单语句、表字段和 LIMIT 校验通过"})

        try:
            frame = self.tools.run_sql(sql)
        except Exception as exc:
            raise AgentExecutionError(f"查询执行失败：{type(exc).__name__}: {exc}") from exc
        trace.append(
            {"node": "duckdb_query", "status": "ok", "detail": f"DuckDB 返回 {len(frame)} 行结果"}
        )

        quality_warnings = self.tools.pandas_quality_check(frame, plan)
        warnings.extend(quality_warnings)
        trace.append(
            {
                "node": "pandas_quality",
                "status": "warning" if quality_warnings else "ok",
                "detail": "Pandas 完成空值、样本量和数值有效性检查",
            }
        )

        chart_type = resolved_chart_type(plan)
        trace.append(
            {"node": "chart_router", "status": "ok", "detail": f"选择 {chart_type} 可视化"}
        )
        summary = self._summarize(frame, plan)
        rows = self._serializable_rows(frame)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        result = AgentResult(
            question=question,
            plan=plan,
            sql=sql,
            rows=rows,
            columns=list(frame.columns),
            summary=summary,
            metric_definition=METRICS[plan.metric].definition,
            chart_type=chart_type,
            warnings=warnings,
            trace=trace,
            provider=planning.provider,
            elapsed_ms=elapsed_ms,
        )
        if log_event:
            self.audit.write(
                {
                    "question": question,
                    "provider": planning.provider,
                    "metric": plan.metric,
                    "dimensions": plan.dimensions,
                    "row_count": len(frame),
                    "warning_count": len(warnings),
                    "elapsed_ms": elapsed_ms,
                    "status": "success",
                }
            )
        return result

    @staticmethod
    def _validate_plan(plan: AnalysisPlan) -> None:
        if plan.metric not in METRICS:
            raise AgentExecutionError(f"指标不在语义层：{plan.metric}")
        invalid_dimensions = [name for name in plan.dimensions if name not in DIMENSIONS]
        if invalid_dimensions:
            raise AgentExecutionError(f"维度不在语义层：{invalid_dimensions}")
        invalid_filters = [spec.field for spec in plan.filters if spec.field not in FILTERABLE_FIELDS]
        if invalid_filters:
            raise AgentExecutionError(f"筛选字段不允许：{invalid_filters}")

    @staticmethod
    def _summarize(frame: pd.DataFrame, plan: AnalysisPlan) -> str:
        metric = METRICS[plan.metric]
        if frame.empty:
            return "当前筛选条件下没有可用数据。"
        valid = frame.dropna(subset=["metric_value"]).copy()
        if valid.empty:
            return f"当前筛选条件下，{metric.label}没有有效分母或有效数值。"
        if not plan.dimensions:
            value = float(valid.iloc[0]["metric_value"])
            sample = int(valid.iloc[0].get("metric_sample_size", valid.iloc[0].get("sample_size", 0)))
            return f"{metric.label}为 {format_metric(value, plan.metric)}，有效样本量为 {sample:,}。"

        if plan.dimensions[0] in {"application_month", "application_year"} and len(plan.dimensions) == 1:
            ordered = valid.sort_values(plan.dimensions[0])
            first = float(ordered.iloc[0]["metric_value"])
            last = float(ordered.iloc[-1]["metric_value"])
            delta = last - first
            direction = "上升" if delta > 0 else "下降" if delta < 0 else "基本持平"
            return (
                f"{metric.label}从 {format_metric(first, plan.metric)} 变化到 "
                f"{format_metric(last, plan.metric)}，整体{direction}。"
            )

        best = valid.loc[valid["metric_value"].idxmax()]
        worst = valid.loc[valid["metric_value"].idxmin()]
        best_group = " / ".join(str(best[name]) for name in plan.dimensions)
        worst_group = " / ".join(str(worst[name]) for name in plan.dimensions)
        return (
            f"{metric.label}最高的是 {best_group}，为 {format_metric(float(best['metric_value']), plan.metric)}；"
            f"最低的是 {worst_group}，为 {format_metric(float(worst['metric_value']), plan.metric)}。"
        )

    @staticmethod
    def _serializable_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
        normalized = frame.copy()
        for column in normalized.columns:
            if pd.api.types.is_datetime64_any_dtype(normalized[column]):
                normalized[column] = normalized[column].dt.strftime("%Y-%m-%d")
        normalized = normalized.astype(object).where(pd.notna(normalized), None)
        return normalized.to_dict(orient="records")

