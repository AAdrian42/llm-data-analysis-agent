from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from .models import AnalysisPlan, FilterSpec
from .semantic_layer import catalog_for_prompt


@dataclass
class PlanningOutput:
    plan: AnalysisPlan
    provider: str
    trace: list[dict[str, Any]]
    warnings: list[str]


METRIC_PATTERNS = [
    ("default_rate", ("违约率", "坏账率", "逾期率")),
    ("approval_rate", ("通过率", "审批率", "获批率")),
    ("approved_count", ("通过量", "获批量", "审批通过数")),
    ("total_approved_amount", ("通过金额", "放款金额", "审批金额")),
    ("average_review_minutes", ("审核时长", "处理时长", "审核时间")),
    ("average_interest_rate", ("平均利率", "利率均值")),
    ("average_dti", ("平均dti", "dti均值")),
    ("average_loan_amount", ("平均贷款金额", "平均申请金额", "贷款金额最高", "申请金额最高")),
    ("application_count", ("申请量", "申请数", "多少申请", "趋势")),
]


DIMENSION_PATTERNS = [
    ("application_month", ("月度", "每月", "月份", "月趋势", "最近12个月")),
    ("application_year", ("年度", "每年", "年份")),
    ("dti_band", ("dti区间", "dti 区间", "负债率区间")),
    ("fico_band", ("fico区间", "fico 区间", "信用分区间")),
    ("loan_amount_band", ("贷款金额区间", "金额区间")),
    ("grade", ("信用等级", "评级", "grade")),
    ("region", ("地区", "区域")),
    ("product", ("产品", "产品类型")),
    ("channel", ("渠道", "来源渠道")),
    ("term_months", ("贷款期限", "期限")),
    ("city_tier", ("城市等级", "城市级别")),
]


class LocalPlanner:
    def plan(self, question: str) -> AnalysisPlan:
        normalized = re.sub(r"\s+", "", question.lower())
        metric = self._metric(normalized)
        filters = self._filters(question)
        dimensions = self._dimensions(normalized)
        single_value_fields = {
            spec.field
            for spec in filters
            if spec.operator == "eq"
            or (spec.operator == "in" and isinstance(spec.value, list) and len(spec.value) == 1)
        }
        dimensions = [dimension for dimension in dimensions if dimension not in single_value_fields]
        limit = self._limit(normalized)
        if (
            any(dimension in {"application_month", "application_year"} for dimension in dimensions)
            and not re.search(r"(?:top|前)\d+", normalized, flags=re.IGNORECASE)
        ):
            limit = 120
        if len(dimensions) == 2 and not re.search(r"(?:top|前)\d+", normalized, flags=re.IGNORECASE):
            limit = 200
        sort = "asc" if any(word in normalized for word in ("从低到高", "升序", "最低")) else "desc"
        chart_type = self._chart_type(normalized, dimensions)
        return AnalysisPlan(
            metric=metric,
            dimensions=dimensions,
            filters=filters,
            sort=sort,
            limit=limit,
            chart_type=chart_type,
            rationale=f"识别指标 {metric}，按 {', '.join(dimensions) if dimensions else '整体'} 分析。",
        )

    @staticmethod
    def _metric(question: str) -> str:
        for metric, patterns in METRIC_PATTERNS:
            if any(pattern in question for pattern in patterns):
                return metric
        if "金额" in question and any(word in question for word in ("总", "合计")):
            return "total_approved_amount"
        return "application_count"

    @staticmethod
    def _dimensions(question: str) -> list[str]:
        dimensions: list[str] = []
        for dimension, patterns in DIMENSION_PATTERNS:
            if any(pattern in question for pattern in patterns):
                dimensions.append(dimension)
        if "趋势" in question and "application_month" not in dimensions:
            dimensions.insert(0, "application_month")
        return dimensions[:2]

    @staticmethod
    def _filters(question: str) -> list[FilterSpec]:
        filters: list[FilterSpec] = []
        years = re.findall(r"(20\d{2})\s*年?", question)
        if years:
            filters.append(FilterSpec(field="application_year", operator="in", value=sorted(set(map(int, years)))))

        for grade in "ABCDEFG":
            if re.search(fr"\b{grade}\s*级|{grade}级", question, flags=re.IGNORECASE):
                filters.append(FilterSpec(field="grade", operator="eq", value=grade))

        for value in ("消费贷", "经营贷", "教育贷", "装修贷"):
            if value in question:
                filters.append(FilterSpec(field="product", operator="eq", value=value))
        for value in ("华东", "华南", "华北", "华中", "西南", "西北", "东北"):
            if value in question:
                filters.append(FilterSpec(field="region", operator="eq", value=value))
        for value in ("App", "小程序", "网页", "合作渠道"):
            if value.lower() in question.lower():
                filters.append(FilterSpec(field="channel", operator="eq", value=value))

        term_match = re.search(r"(12|24|36|60)\s*个?月", question)
        if term_match and not any(word in question for word in ("不同", "各", "对比", "按")):
            filters.append(FilterSpec(field="term_months", operator="eq", value=int(term_match.group(1))))
        return filters

    @staticmethod
    def _limit(question: str) -> int:
        match = re.search(r"(?:top|前)(\d+)", question, flags=re.IGNORECASE)
        return min(int(match.group(1)), 50) if match else 20

    @staticmethod
    def _chart_type(question: str, dimensions: list[str]) -> str:
        if len(dimensions) == 2:
            return "heatmap"
        if dimensions and dimensions[0] in {"application_month", "application_year"}:
            return "line"
        if dimensions:
            return "bar"
        return "indicator"


class LLMPlanner:
    SYSTEM_PROMPT = (
        "你是数据分析规划器。只允许使用给定指标、维度和筛选字段。"
        "不要计算或编造结果；通过 submit_analysis_plan 工具提交结构化计划。"
        "rationale 只写简短映射说明，不输出隐含思维过程。"
    )

    def __init__(self, provider: str) -> None:
        self.provider = provider

    @staticmethod
    def _tool_schema() -> dict[str, Any]:
        schema = AnalysisPlan.model_json_schema()
        return {
            "name": "submit_analysis_plan",
            "description": "提交经过语义层约束的数据分析计划",
            "parameters": schema,
        }

    def plan(self, question: str) -> AnalysisPlan:
        catalog = json.dumps(catalog_for_prompt(), ensure_ascii=False)
        if self.provider == "openai":
            return self._openai(question, catalog)
        if self.provider == "anthropic":
            return self._anthropic(question, catalog)
        raise ValueError(f"Unsupported provider: {self.provider}")

    def _openai(self, question: str, catalog: str) -> AnalysisPlan:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        tool = self._tool_schema()
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"数据目录：{catalog}\n用户问题：{question}"},
            ],
            tools=[{"type": "function", "function": tool}],
            tool_choice={"type": "function", "function": {"name": tool["name"]}},
        )
        call = response.choices[0].message.tool_calls[0]
        return AnalysisPlan.model_validate_json(call.function.arguments)

    def _anthropic(self, question: str, catalog: str) -> AnalysisPlan:
        from anthropic import Anthropic

        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        tool = self._tool_schema()
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
            max_tokens=1000,
            temperature=0,
            system=self.SYSTEM_PROMPT,
            tools=[{"name": tool["name"], "description": tool["description"], "input_schema": tool["parameters"]}],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": f"数据目录：{catalog}\n用户问题：{question}"}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                return AnalysisPlan.model_validate(block.input)
        raise ValueError("Anthropic did not return submit_analysis_plan")


class PlannerRouter:
    def __init__(self, provider: str | None = None) -> None:
        self.requested_provider = (provider or os.getenv("ANALYTICS_LLM_PROVIDER", "local")).lower()
        self.local = LocalPlanner()

    def plan(self, question: str) -> PlanningOutput:
        trace = [{"node": "intent_input", "status": "ok", "detail": "接收自然语言问题"}]
        warnings: list[str] = []
        provider = self.requested_provider
        can_use = (
            provider == "openai" and bool(os.getenv("OPENAI_API_KEY"))
        ) or (
            provider == "anthropic" and bool(os.getenv("ANTHROPIC_API_KEY"))
        )
        if provider in {"openai", "anthropic"} and can_use:
            try:
                plan = LLMPlanner(provider).plan(question)
                trace.append({"node": "function_call", "status": "ok", "detail": f"{provider} 调用 submit_analysis_plan"})
                return PlanningOutput(plan, provider, trace, warnings)
            except Exception as exc:
                warnings.append(f"{provider} 规划失败，已回退本地规划器：{type(exc).__name__}")
        elif provider in {"openai", "anthropic"}:
            warnings.append(f"未配置 {provider} API Key，已使用本地规划器。")

        plan = self.local.plan(question)
        trace.append({"node": "local_planner", "status": "ok", "detail": "规则与语义词典生成 AnalysisPlan"})
        return PlanningOutput(plan, "local", trace, warnings)
