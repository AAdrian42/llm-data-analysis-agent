from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATABASE_PATH = DATA_DIR / "analytics_demo.duckdb"
MANIFEST_PATH = DATA_DIR / "manifest.json"
SEED = 20260924
ROW_COUNT = 100_000


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(values, -12, 12)))


def build_frame(row_count: int = ROW_COUNT, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = np.datetime64("2024-01-01")
    end = np.datetime64("2025-12-31")
    date_offsets = rng.integers(0, int((end - start).astype(int)) + 1, size=row_count)
    application_date = start + date_offsets.astype("timedelta64[D]")

    regions = rng.choice(
        ["华东", "华南", "华北", "华中", "西南", "西北", "东北"],
        size=row_count,
        p=[0.25, 0.18, 0.17, 0.14, 0.12, 0.07, 0.07],
    )
    products = rng.choice(
        ["消费贷", "经营贷", "教育贷", "装修贷"],
        size=row_count,
        p=[0.46, 0.25, 0.13, 0.16],
    )
    channels = rng.choice(
        ["App", "小程序", "网页", "合作渠道"],
        size=row_count,
        p=[0.52, 0.20, 0.12, 0.16],
    )
    city_tier = rng.choice(["一线", "新一线", "二线", "三线及以下"], size=row_count, p=[0.15, 0.24, 0.31, 0.30])
    age = np.clip(np.rint(rng.normal(36, 9, row_count)), 20, 65).astype(int)
    employment_years = np.clip(np.rint(rng.gamma(2.5, 2.2, row_count)), 0, 30).astype(int)
    annual_income = np.exp(rng.normal(math.log(110000), 0.52, row_count))
    annual_income *= np.where(city_tier == "一线", 1.32, np.where(city_tier == "新一线", 1.16, 1.0))
    annual_income = np.clip(np.rint(annual_income / 1000) * 1000, 24000, 1_000_000)

    base_risk = rng.normal(0, 1, row_count)
    dti = np.clip(17 + base_risk * 6.5 + rng.normal(0, 5, row_count), 0, 55)
    fico = np.clip(np.rint(700 - base_risk * 28 + rng.normal(0, 22, row_count)), 580, 820).astype(int)
    grade_index = np.digitize(base_risk + (dti - 18) / 28 - (fico - 690) / 110, [-1.2, -0.55, 0.05, 0.6, 1.15, 1.7])
    grade = np.array(list("ABCDEFG"))[grade_index]
    term_months = rng.choice([12, 24, 36, 60], size=row_count, p=[0.13, 0.19, 0.49, 0.19])

    product_multiplier = np.select(
        [products == "经营贷", products == "装修贷", products == "教育贷"],
        [1.45, 1.20, 0.82],
        default=1.0,
    )
    requested_ratio = np.clip(rng.beta(2.1, 5.8, row_count) * product_multiplier, 0.03, 0.72)
    loan_amount = np.clip(np.rint(annual_income * requested_ratio / 1000) * 1000, 3000, 200000)
    interest_rate = np.clip(5.2 + grade_index * 2.05 + (term_months == 60) * 1.1 + rng.normal(0, 1.0, row_count), 4.0, 26.0)

    loan_income_ratio = loan_amount / annual_income
    risk_logit = (
        -2.55
        + grade_index * 0.34
        + np.maximum(dti - 18, 0) * 0.028
        + np.maximum(680 - fico, 0) * 0.008
        + loan_income_ratio * 1.15
        + (term_months == 60) * 0.32
        + (products == "经营贷") * 0.13
        + (application_date >= np.datetime64("2025-07-01")) * 0.08
    )
    default_probability = sigmoid(risk_logit)
    model_score = np.clip(default_probability + rng.normal(0, 0.035, row_count), 0.005, 0.95)

    approval_logit = (
        2.1
        - model_score * 5.0
        - np.maximum(dti - 30, 0) * 0.04
        + np.maximum(fico - 680, 0) * 0.008
        - (loan_income_ratio > 0.5) * 0.55
        + (channels == "合作渠道") * 0.10
    )
    approval_probability = sigmoid(approval_logit)
    approved = (rng.random(row_count) < approval_probability).astype(int)
    defaulted = np.where(approved == 1, (rng.random(row_count) < default_probability).astype(float), np.nan)

    manual_flag = (model_score >= 0.14) & (model_score <= 0.42)
    channel_minutes = np.select(
        [channels == "合作渠道", channels == "网页", channels == "小程序"],
        [7.0, 3.0, 1.5],
        default=0.0,
    )
    review_minutes = np.where(
        manual_flag,
        np.clip(12 + model_score * 34 + channel_minutes + rng.normal(0, 5, row_count), 5, 60),
        np.nan,
    )

    frame = pd.DataFrame(
        {
            "application_id": np.arange(1, row_count + 1),
            "application_date": pd.to_datetime(application_date),
            "age": age,
            "region": regions,
            "city_tier": city_tier,
            "product": products,
            "channel": channels,
            "grade": grade,
            "term_months": term_months,
            "loan_amount": loan_amount.astype(float),
            "annual_income": annual_income.astype(float),
            "dti": np.round(dti, 2),
            "fico_score": fico,
            "interest_rate": np.round(interest_rate, 2),
            "employment_length_years": employment_years,
            "approved": approved,
            "defaulted": defaulted,
            "model_score": np.round(model_score, 5),
            "manual_review_minutes": np.round(review_minutes, 2),
        }
    )
    for column in ("region", "city_tier", "product", "channel", "grade"):
        frame[column] = frame[column].astype(object)
    return frame


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame = build_frame()
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    with duckdb.connect(str(DATABASE_PATH)) as connection:
        connection.register("source_frame", frame)
        connection.execute("CREATE TABLE credit_applications AS SELECT * FROM source_frame")
        connection.execute("CREATE INDEX idx_application_date ON credit_applications(application_date)")
        connection.execute("CREATE INDEX idx_grade ON credit_applications(grade)")
        summary = connection.execute(
            """
            SELECT COUNT(*) AS rows,
                   AVG(CAST(approved AS DOUBLE)) AS approval_rate,
                   AVG(CASE WHEN approved = 1 THEN defaulted END) AS default_rate,
                   MIN(application_date) AS date_start,
                   MAX(application_date) AS date_end
            FROM credit_applications
            """
        ).fetchone()

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "row_count": int(summary[0]),
        "column_count": len(frame.columns),
        "date_start": str(summary[3]),
        "date_end": str(summary[4]),
        "approval_rate": float(summary[1]),
        "default_rate_among_approved": float(summary[2]),
        "data_type": "synthetic_demo",
        "data_statement": "固定随机种子生成的合成信贷经营数据，不包含真实客户或京东内部数据。",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
