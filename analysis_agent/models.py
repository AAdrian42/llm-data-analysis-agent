from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


MetricName = Literal[
    "application_count",
    "approved_count",
    "approval_rate",
    "default_rate",
    "average_loan_amount",
    "total_approved_amount",
    "average_interest_rate",
    "average_dti",
    "average_review_minutes",
]

DimensionName = Literal[
    "application_month",
    "application_year",
    "grade",
    "region",
    "product",
    "channel",
    "term_months",
    "city_tier",
    "dti_band",
    "fico_band",
    "loan_amount_band",
]


class FilterSpec(BaseModel):
    field: str
    operator: Literal["eq", "in", "gte", "lte", "between"] = "eq"
    value: Any


class AnalysisPlan(BaseModel):
    metric: MetricName
    dimensions: list[DimensionName] = Field(default_factory=list, max_length=2)
    filters: list[FilterSpec] = Field(default_factory=list, max_length=8)
    sort: Literal["asc", "desc", "none"] = "desc"
    limit: int = Field(default=20, ge=1, le=200)
    chart_type: Literal["auto", "indicator", "bar", "line", "heatmap", "table"] = "auto"
    rationale: str = ""

    @field_validator("dimensions")
    @classmethod
    def unique_dimensions(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    label: str
    expression: str
    definition: str
    format_kind: str


@dataclass(frozen=True)
class DimensionDefinition:
    name: str
    label: str
    expression: str


@dataclass
class AgentResult:
    question: str
    plan: AnalysisPlan
    sql: str
    rows: list[dict[str, Any]]
    columns: list[str]
    summary: str
    metric_definition: str
    chart_type: str
    warnings: list[str]
    trace: list[dict[str, Any]]
    provider: str
    elapsed_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "plan": self.plan.model_dump(),
            "sql": self.sql,
            "rows": self.rows,
            "columns": self.columns,
            "summary": self.summary,
            "metric_definition": self.metric_definition,
            "chart_type": self.chart_type,
            "warnings": self.warnings,
            "trace": self.trace,
            "provider": self.provider,
            "elapsed_ms": self.elapsed_ms,
        }

