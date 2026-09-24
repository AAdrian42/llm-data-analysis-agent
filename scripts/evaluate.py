from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_agent import DataAnalysisAgent
from analysis_agent.planner import LocalPlanner
from analysis_agent.sql_guard import UnsafeSQLError, validate_readonly_sql


EVAL_SET = [
    {"q": "各信用等级的违约率是多少", "metric": "default_rate", "dims": ["grade"], "filters": []},
    {"q": "2025年各产品审批通过率，按从高到低排序", "metric": "approval_rate", "dims": ["product"], "filters": [("application_year", 2025)]},
    {"q": "月度申请量趋势", "metric": "application_count", "dims": ["application_month"], "filters": []},
    {"q": "不同DTI区间的违约率", "metric": "default_rate", "dims": ["dti_band"], "filters": []},
    {"q": "各地区平均贷款金额最高的前5名", "metric": "average_loan_amount", "dims": ["region"], "filters": [], "limit": 5},
    {"q": "不同信用等级和贷款期限的违约率对比", "metric": "default_rate", "dims": ["grade", "term_months"], "filters": []},
    {"q": "各渠道平均人工审核时长", "metric": "average_review_minutes", "dims": ["channel"], "filters": []},
    {"q": "各产品审批通过金额", "metric": "total_approved_amount", "dims": ["product"], "filters": []},
    {"q": "2024年华东地区平均利率", "metric": "average_interest_rate", "dims": [], "filters": [("application_year", 2024), ("region", "华东")]},
    {"q": "整体审批通过率", "metric": "approval_rate", "dims": [], "filters": []},
    {"q": "各城市等级的申请量", "metric": "application_count", "dims": ["city_tier"], "filters": []},
    {"q": "各FICO区间的违约率", "metric": "default_rate", "dims": ["fico_band"], "filters": []},
    {"q": "不同贷款金额区间的审批通过率", "metric": "approval_rate", "dims": ["loan_amount_band"], "filters": []},
    {"q": "消费贷各地区的违约率", "metric": "default_rate", "dims": ["region"], "filters": [("product", "消费贷")]},
    {"q": "合作渠道的平均人工审核时长", "metric": "average_review_minutes", "dims": [], "filters": [("channel", "合作渠道")]},
]


UNSAFE_SQL = [
    "DROP TABLE credit_applications",
    "SELECT * FROM credit_applications LIMIT 5; DELETE FROM credit_applications",
    "SELECT * FROM read_csv_auto('secret.csv') LIMIT 5",
    "SELECT * FROM another_table LIMIT 5",
    "SELECT secret_field FROM credit_applications LIMIT 5",
    "SELECT * FROM credit_applications",
]


def filter_pairs(plan) -> list[tuple[str, object]]:
    pairs: list[tuple[str, object]] = []
    for spec in plan.filters:
        if spec.operator == "in" and isinstance(spec.value, list) and len(spec.value) == 1:
            pairs.append((spec.field, spec.value[0]))
        else:
            pairs.append((spec.field, spec.value))
    return pairs


def main() -> None:
    planner = LocalPlanner()
    agent = DataAnalysisAgent(provider="local")
    details = []
    plan_hits = 0
    execution_hits = 0
    grounding_hits = 0

    for case in EVAL_SET:
        plan = planner.plan(case["q"])
        expected_filters = case["filters"]
        plan_ok = (
            plan.metric == case["metric"]
            and plan.dimensions == case["dims"]
            and all(pair in filter_pairs(plan) for pair in expected_filters)
            and ("limit" not in case or plan.limit == case["limit"])
        )
        plan_hits += int(plan_ok)
        try:
            result = agent.analyze(case["q"], log_event=False)
            execution_ok = bool(result.rows)
            grounding_ok = bool(result.sql and result.metric_definition and "metric_value" in result.columns)
        except Exception as exc:
            execution_ok = False
            grounding_ok = False
            result = None
            error = f"{type(exc).__name__}: {exc}"
        execution_hits += int(execution_ok)
        grounding_hits += int(grounding_ok)
        details.append(
            {
                "question": case["q"],
                "expected_metric": case["metric"],
                "predicted_metric": plan.metric,
                "expected_dimensions": case["dims"],
                "predicted_dimensions": plan.dimensions,
                "plan_ok": plan_ok,
                "execution_ok": execution_ok,
                "grounding_ok": grounding_ok,
                "error": None if result is not None else error,
            }
        )

    safety_details = []
    safety_hits = 0
    for sql in UNSAFE_SQL:
        try:
            validate_readonly_sql(sql)
            blocked = False
        except UnsafeSQLError:
            blocked = True
        safety_hits += int(blocked)
        safety_details.append({"sql": sql, "blocked": blocked})

    count = len(EVAL_SET)
    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "planning_sample_count": count,
        "safety_sample_count": len(UNSAFE_SQL),
        "metrics": {
            "plan_accuracy": plan_hits / count,
            "execution_success_rate": execution_hits / count,
            "grounding_completeness": grounding_hits / count,
            "unsafe_sql_block_rate": safety_hits / len(UNSAFE_SQL),
        },
        "details": details,
        "safety_details": safety_details,
        "limitations": [
            "评测集由项目作者构建，覆盖的是已登记的标准分析场景。",
            "当前结果不能代表开放域自然语言问题的真实泛化水平。",
            "默认评测使用本地规划器，GPT/Claude 需要单独配置密钥后评测。",
            "尚未完成真实业务用户的任务耗时对照实验。",
        ],
    }
    output_dir = ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
