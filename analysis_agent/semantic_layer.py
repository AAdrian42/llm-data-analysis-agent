from __future__ import annotations

from .models import DimensionDefinition, MetricDefinition


TABLE_NAME = "credit_applications"


METRICS: dict[str, MetricDefinition] = {
    "application_count": MetricDefinition(
        name="application_count",
        label="申请量",
        expression="COUNT(*)",
        definition="申请记录总数，每条申请计为 1。",
        format_kind="integer",
    ),
    "approved_count": MetricDefinition(
        name="approved_count",
        label="审批通过量",
        expression="SUM(CASE WHEN approved = 1 THEN 1 ELSE 0 END)",
        definition="审批结果为通过的申请数量。",
        format_kind="integer",
    ),
    "approval_rate": MetricDefinition(
        name="approval_rate",
        label="审批通过率",
        expression="AVG(CAST(approved AS DOUBLE))",
        definition="审批通过申请数除以全部申请数。",
        format_kind="percentage",
    ),
    "default_rate": MetricDefinition(
        name="default_rate",
        label="违约率",
        expression="AVG(CASE WHEN approved = 1 AND defaulted IS NOT NULL THEN CAST(defaulted AS DOUBLE) END)",
        definition="已通过且标签已成熟的贷款中，发生违约的比例；拒绝申请不进入分母。",
        format_kind="percentage",
    ),
    "average_loan_amount": MetricDefinition(
        name="average_loan_amount",
        label="平均申请金额",
        expression="AVG(loan_amount)",
        definition="所有申请的贷款金额平均值。",
        format_kind="currency",
    ),
    "total_approved_amount": MetricDefinition(
        name="total_approved_amount",
        label="审批通过金额",
        expression="SUM(CASE WHEN approved = 1 THEN loan_amount ELSE 0 END)",
        definition="审批通过申请的贷款金额合计。",
        format_kind="currency",
    ),
    "average_interest_rate": MetricDefinition(
        name="average_interest_rate",
        label="平均年利率",
        expression="AVG(interest_rate)",
        definition="申请记录的平均年化利率。",
        format_kind="percentage_points",
    ),
    "average_dti": MetricDefinition(
        name="average_dti",
        label="平均 DTI",
        expression="AVG(dti)",
        definition="债务收入比 DTI 的平均值。",
        format_kind="decimal",
    ),
    "average_review_minutes": MetricDefinition(
        name="average_review_minutes",
        label="平均人工审核时长",
        expression="AVG(manual_review_minutes)",
        definition="进入人工审核流程的平均处理分钟数；未进入人工审核的记录为空，不进入分母。",
        format_kind="minutes",
    ),
}


DIMENSIONS: dict[str, DimensionDefinition] = {
    "application_month": DimensionDefinition(
        "application_month", "申请月份", "DATE_TRUNC('month', application_date)"
    ),
    "application_year": DimensionDefinition(
        "application_year", "申请年份", "EXTRACT(year FROM application_date)"
    ),
    "grade": DimensionDefinition("grade", "信用等级", "grade"),
    "region": DimensionDefinition("region", "地区", "region"),
    "product": DimensionDefinition("product", "产品", "product"),
    "channel": DimensionDefinition("channel", "渠道", "channel"),
    "term_months": DimensionDefinition("term_months", "贷款期限", "term_months"),
    "city_tier": DimensionDefinition("city_tier", "城市等级", "city_tier"),
    "dti_band": DimensionDefinition(
        "dti_band",
        "DTI 区间",
        "CASE WHEN dti < 10 THEN '<10' WHEN dti < 20 THEN '10-20' "
        "WHEN dti < 30 THEN '20-30' ELSE '>=30' END",
    ),
    "fico_band": DimensionDefinition(
        "fico_band",
        "FICO 区间",
        "CASE WHEN fico_score < 640 THEN '<640' WHEN fico_score < 680 THEN '640-679' "
        "WHEN fico_score < 720 THEN '680-719' ELSE '>=720' END",
    ),
    "loan_amount_band": DimensionDefinition(
        "loan_amount_band",
        "贷款金额区间",
        "CASE WHEN loan_amount < 10000 THEN '<1万' WHEN loan_amount < 20000 THEN '1-2万' "
        "WHEN loan_amount < 30000 THEN '2-3万' ELSE '>=3万' END",
    ),
}


RAW_COLUMNS = {
    "application_id",
    "application_date",
    "age",
    "region",
    "city_tier",
    "product",
    "channel",
    "grade",
    "term_months",
    "loan_amount",
    "annual_income",
    "dti",
    "fico_score",
    "interest_rate",
    "employment_length_years",
    "approved",
    "defaulted",
    "model_score",
    "manual_review_minutes",
}


FILTERABLE_FIELDS = {
    "application_year": "EXTRACT(year FROM application_date)",
    "application_month": "DATE_TRUNC('month', application_date)",
    "grade": "grade",
    "region": "region",
    "product": "product",
    "channel": "channel",
    "term_months": "term_months",
    "city_tier": "city_tier",
    "approved": "approved",
    "dti": "dti",
    "fico_score": "fico_score",
    "loan_amount": "loan_amount",
}


def catalog_for_prompt() -> dict:
    return {
        "table": TABLE_NAME,
        "metrics": {
            name: {"label": value.label, "definition": value.definition}
            for name, value in METRICS.items()
        },
        "dimensions": {name: value.label for name, value in DIMENSIONS.items()},
        "filterable_fields": sorted(FILTERABLE_FIELDS),
    }

