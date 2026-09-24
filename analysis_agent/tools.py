from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from .models import AnalysisPlan
from .semantic_layer import METRICS, TABLE_NAME, catalog_for_prompt
from .sql_guard import validate_readonly_sql


class AnalyticsTools:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        if not self.database_path.exists():
            raise FileNotFoundError(f"Demo database not found: {self.database_path}")

    def describe_dataset(self) -> dict[str, Any]:
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            row_count = connection.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
            date_range = connection.execute(
                f"SELECT MIN(application_date), MAX(application_date) FROM {TABLE_NAME}"
            ).fetchone()
        return {
            **catalog_for_prompt(),
            "row_count": int(row_count),
            "date_start": str(date_range[0]),
            "date_end": str(date_range[1]),
            "data_type": "synthetic_demo",
        }

    def run_sql(self, sql: str) -> pd.DataFrame:
        safe_sql = validate_readonly_sql(sql)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            connection.execute("SET threads = 2")
            return connection.execute(safe_sql).fetch_df()

    @staticmethod
    def pandas_quality_check(frame: pd.DataFrame, plan: AnalysisPlan) -> list[str]:
        warnings: list[str] = []
        if frame.empty:
            return ["查询没有返回数据，请检查筛选条件或时间范围。"]
        if "metric_value" not in frame.columns:
            warnings.append("结果缺少 metric_value，无法生成标准指标图表。")
            return warnings
        missing_ratio = float(frame["metric_value"].isna().mean())
        if missing_ratio > 0:
            warnings.append(f"指标结果有 {missing_ratio:.1%} 的空值，通常表示分母没有有效样本。")
        numeric = pd.to_numeric(frame["metric_value"], errors="coerce")
        if np.isinf(numeric.fillna(0)).any():
            warnings.append("指标结果存在无穷值，已阻止直接解读。")
        sample_column = "metric_sample_size" if "metric_sample_size" in frame.columns else "sample_size"
        if sample_column in frame.columns and (frame[sample_column] < 50).any():
            warnings.append("部分分组有效样本少于 50，结论可能不稳定。")
        if len(frame) >= plan.limit:
            warnings.append(f"结果已按计划限制为前 {plan.limit} 行。")
        return warnings

    @staticmethod
    def profile_result(frame: pd.DataFrame) -> dict[str, Any]:
        return {
            "row_count": int(len(frame)),
            "columns": list(frame.columns),
            "null_counts": {column: int(value) for column, value in frame.isna().sum().items()},
        }


def format_metric(value: float, metric_name: str) -> str:
    metric = METRICS[metric_name]
    if pd.isna(value):
        return "无有效值"
    if metric.format_kind == "percentage":
        return f"{value:.2%}"
    if metric.format_kind == "percentage_points":
        return f"{value:.2f}%"
    if metric.format_kind == "currency":
        return f"{value:,.0f} 元"
    if metric.format_kind == "integer":
        return f"{value:,.0f}"
    if metric.format_kind == "minutes":
        return f"{value:.1f} 分钟"
    return f"{value:.2f}"

