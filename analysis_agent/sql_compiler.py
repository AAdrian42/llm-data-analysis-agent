from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .models import AnalysisPlan, FilterSpec
from .semantic_layer import DIMENSIONS, FILTERABLE_FIELDS, METRICS, TABLE_NAME


class PlanValidationError(ValueError):
    pass


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        value = value.isoformat()
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _filter_sql(spec: FilterSpec) -> str:
    if spec.field not in FILTERABLE_FIELDS:
        raise PlanValidationError(f"Filter field is not allowed: {spec.field}")
    field_expr = FILTERABLE_FIELDS[spec.field]
    if spec.operator == "eq":
        return f"{field_expr} = {_literal(spec.value)}"
    if spec.operator == "in":
        values = spec.value if isinstance(spec.value, list) else [spec.value]
        if not values:
            raise PlanValidationError("IN filter cannot be empty")
        return f"{field_expr} IN ({', '.join(_literal(value) for value in values)})"
    if spec.operator in {"gte", "lte"}:
        operator = ">=" if spec.operator == "gte" else "<="
        return f"{field_expr} {operator} {_literal(spec.value)}"
    if spec.operator == "between":
        if not isinstance(spec.value, list) or len(spec.value) != 2:
            raise PlanValidationError("BETWEEN filter requires two values")
        return f"{field_expr} BETWEEN {_literal(spec.value[0])} AND {_literal(spec.value[1])}"
    raise PlanValidationError(f"Unsupported operator: {spec.operator}")


def compile_plan(plan: AnalysisPlan) -> str:
    metric = METRICS[plan.metric]
    dimensions = [DIMENSIONS[name] for name in plan.dimensions]
    select_parts = [f"{dimension.expression} AS {dimension.name}" for dimension in dimensions]
    select_parts.append(f"{metric.expression} AS metric_value")
    select_parts.append("COUNT(*) AS sample_size")
    if plan.metric == "default_rate":
        select_parts.append(
            "SUM(CASE WHEN approved = 1 AND defaulted IS NOT NULL THEN 1 ELSE 0 END) "
            "AS metric_sample_size"
        )

    sql_lines = ["SELECT", "  " + ",\n  ".join(select_parts), f"FROM {TABLE_NAME}"]
    if plan.filters:
        sql_lines.extend(["WHERE", "  " + "\n  AND ".join(_filter_sql(spec) for spec in plan.filters)])
    if dimensions:
        sql_lines.append("GROUP BY " + ", ".join(str(index + 1) for index in range(len(dimensions))))
        if dimensions[0].name in {"application_month", "application_year"}:
            sql_lines.append("ORDER BY 1 ASC")
        elif plan.sort != "none":
            direction = "ASC" if plan.sort == "asc" else "DESC"
            sql_lines.append(f"ORDER BY metric_value {direction} NULLS LAST")
    sql_lines.append(f"LIMIT {plan.limit}")
    return "\n".join(sql_lines)

