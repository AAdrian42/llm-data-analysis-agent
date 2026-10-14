from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from analysis_agent import DataAnalysisAgent
from analysis_agent.agent import AgentExecutionError
from analysis_agent.charting import build_chart, build_static_chart
from analysis_agent.models import AnalysisPlan
from analysis_agent.semantic_layer import DIMENSIONS, METRICS


ROOT = Path(__file__).resolve().parent
st.set_page_config(
    page_title="LLM 数据分析 Agent",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stApp { background: #f4f6f8; color: #17212b; }
      .block-container { max-width: 1480px; padding-top: 1.3rem; }
      h1, h2, h3 { letter-spacing: 0; }
      [data-testid="stSidebar"] { background: #e8eef2; }
      [data-testid="stSidebar"] * { color: #17212b; }
      [data-testid="stSidebar"] div[data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #cbd5dd; border-radius: 6px;
      }
      [data-testid="stTextArea"] textarea,
      [data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #17212b !important;
        -webkit-text-fill-color: #17212b !important; caret-color: #147d92;
      }
      [data-testid="stTextArea"] textarea::placeholder {
        color: #59636f !important; -webkit-text-fill-color: #59636f !important;
      }
      [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        background-color: #ffffff !important; color: #17212b !important;
        border-color: #cbd5dd;
      }
      [data-testid="stSelectbox"] [data-baseweb="select"] * {
        color: #17212b !important;
      }
      [role="listbox"], [role="option"] {
        background-color: #ffffff; color: #17212b;
      }
      [role="option"]:hover { background-color: #edf7f8; }
      [data-testid="stTextArea"]:focus-within > div { border-color: #147d92; }
      [data-testid="stMetric"] * { color: #17212b; }
      div[data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #d9e0e6; border-radius: 6px; padding: 12px;
      }
      div[data-testid="stExpander"] {
        background: #ffffff; border: 1px solid #d9e0e6; border-radius: 6px;
      }
      .boundary-note {
        border-left: 4px solid #147d92; background: #edf7f8; padding: 12px 14px; margin: 8px 0 16px;
      }
      .summary-box {
        background: #ffffff; border: 1px solid #d9e0e6; border-left: 4px solid #d97706;
        border-radius: 6px; padding: 15px 16px; margin: 10px 0 16px;
      }
      @media (max-width: 1050px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
          min-width: 160px; flex: 1 1 160px;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


EXAMPLES = [
    "各信用等级的违约率是多少？",
    "2025年各产品审批通过率，按从高到低排序。",
    "月度申请量趋势。",
    "不同DTI区间的违约率。",
    "各地区平均贷款金额最高的前5名。",
    "不同信用等级和贷款期限的违约率对比。",
    "各渠道平均人工审核时长。",
]


def ensure_artifacts() -> tuple[dict, dict | None]:
    database = ROOT / "data" / "analytics_demo.duckdb"
    manifest_path = ROOT / "data" / "manifest.json"
    if not database.exists() or not manifest_path.exists():
        st.error("演示数据库尚未生成，请先运行：python scripts/build_demo_data.py")
        st.stop()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_path = ROOT / "reports" / "evaluation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    return manifest, report


@st.cache_resource
def get_agent(provider: str) -> DataAnalysisAgent:
    return DataAnalysisAgent(provider=provider)


@st.cache_data(show_spinner=False, max_entries=64)
def get_chart_image(rows: list[dict], plan: dict) -> bytes | None:
    return build_static_chart(pd.DataFrame(rows), AnalysisPlan.model_validate(plan))


manifest, evaluation = ensure_artifacts()

with st.sidebar:
    st.title("分析控制台")
    provider_label = st.selectbox("规划模式", ["本地规划器", "OpenAI Function Calling", "Claude Function Calling"])
    provider_map = {
        "本地规划器": "local",
        "OpenAI Function Calling": "openai",
        "Claude Function Calling": "anthropic",
    }
    provider = provider_map[provider_label]
    st.divider()
    st.metric("演示数据", f"{manifest['row_count']:,} 行")
    st.metric("字段数量", manifest["column_count"])
    st.metric("数据范围", "2024-2025")
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        st.warning("未配置 OpenAI API Key，将自动回退本地规划器。")
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        st.warning("未配置 Anthropic API Key，将自动回退本地规划器。")
    st.divider()
    st.caption("演示数据全部为合成数据，不包含真实客户或企业内部数据。")

agent = get_agent(provider)

st.title("LLM 数据分析 Agent")
st.markdown(
    '<div class="boundary-note">自然语言负责表达需求，实际数字由受控 SQL 和 Pandas 工具计算；所有结果均可查看口径、SQL 与执行轨迹。</div>',
    unsafe_allow_html=True,
)

analysis_tab, catalog_tab, evaluation_tab = st.tabs(["自助分析", "指标与数据字典", "评测与安全"])

with analysis_tab:
    input_col, status_col = st.columns([1.35, 0.65], gap="large")
    with input_col:
        example = st.selectbox("常用分析问题", EXAMPLES)
        question = st.text_area("分析问题", value=example, height=95)
        analyze_clicked = st.button("开始分析", type="primary", width="stretch")
    with status_col:
        st.subheader("执行原则")
        st.write("指标口径由语义层统一维护")
        st.write("SQL 仅允许只读白名单查询")
        st.write("结果经过 Pandas 质量检查")
        st.write("事实摘要仅引用实际查询结果")

    if analyze_clicked:
        try:
            st.session_state["analysis_result"] = agent.analyze(question)
            st.session_state.pop("analysis_error", None)
        except AgentExecutionError as exc:
            st.session_state["analysis_error"] = str(exc)
            st.session_state.pop("analysis_result", None)

    if "analysis_error" in st.session_state:
        st.error(st.session_state["analysis_error"])

    result = st.session_state.get("analysis_result")
    if result is not None:
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("规划模式", result.provider)
        r2.metric("结果行数", len(result.rows))
        r3.metric("响应耗时", f"{result.elapsed_ms:.0f} ms")
        r4.metric("图表类型", result.chart_type)
        st.markdown(f'<div class="summary-box"><strong>分析结论</strong><br>{result.summary}</div>', unsafe_allow_html=True)

        if result.warnings:
            st.warning("；".join(result.warnings))

        frame = pd.DataFrame(result.rows)
        chart_col, detail_col = st.columns([1.25, 0.75], gap="large")
        with chart_col:
            st.subheader("自动图表")
            chart_image = get_chart_image(result.rows, result.plan.model_dump())
            chart_mode = st.segmented_control("图表模式", ["标准图", "交互图"], default="标准图")
            if chart_mode == "交互图":
                figure = build_chart(frame, result.plan)
                if figure is not None:
                    st.plotly_chart(figure, width="stretch", config={"displaylogo": False})
            elif chart_image is not None:
                st.image(chart_image, width="stretch")
            if chart_image is not None:
                st.download_button("下载图表 PNG", data=chart_image, file_name="analysis_chart.png",
                                   mime="image/png", icon=":material/download:")
        with detail_col:
            st.subheader("分析口径")
            st.write(result.metric_definition)
            st.caption(f"指标：{METRICS[result.plan.metric].label}")
            dimensions = [DIMENSIONS[name].label for name in result.plan.dimensions]
            st.caption("维度：" + ("、".join(dimensions) if dimensions else "整体"))
            st.caption("数据类型：合成演示数据")

        st.subheader("查询结果")
        st.dataframe(frame, width="stretch", hide_index=True)
        st.download_button(
            "导出当前结果 CSV",
            data=frame.to_csv(index=False).encode("utf-8-sig"),
            file_name="analysis_result.csv",
            mime="text/csv",
            width="content",
        )

        with st.expander("查看结构化分析计划"):
            st.json(result.plan.model_dump())
        with st.expander("查看实际执行 SQL"):
            st.code(result.sql, language="sql")
        with st.expander("查看工具执行轨迹"):
            trace_frame = pd.DataFrame(result.trace)
            st.dataframe(trace_frame, width="stretch", hide_index=True)
            st.caption("这里展示可审计的节点状态，不展示模型私有思维过程。")
    else:
        st.info("选择示例或输入业务问题后开始分析。")

with catalog_tab:
    st.subheader("指标口径")
    metric_frame = pd.DataFrame(
        [
            {
                "指标代码": metric.name,
                "显示名称": metric.label,
                "业务定义": metric.definition,
                "展示格式": metric.format_kind,
            }
            for metric in METRICS.values()
        ]
    )
    st.dataframe(metric_frame, width="stretch", hide_index=True)

    st.subheader("分析维度")
    dimension_frame = pd.DataFrame(
        [{"维度代码": value.name, "显示名称": value.label} for value in DIMENSIONS.values()]
    )
    st.dataframe(dimension_frame, width="stretch", hide_index=True)

    st.subheader("演示数据声明")
    st.write(manifest["data_statement"])
    st.json({key: value for key, value in manifest.items() if key != "data_statement"})

with evaluation_tab:
    if evaluation is None:
        st.info("运行 python scripts/evaluate.py 后显示评测结果。")
    else:
        st.subheader("离线评测")
        metrics = evaluation["metrics"]
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("计划准确率", f"{metrics['plan_accuracy']:.1%}")
        e2.metric("执行成功率", f"{metrics['execution_success_rate']:.1%}")
        e3.metric("依据完整率", f"{metrics['grounding_completeness']:.1%}")
        e4.metric("危险SQL拦截率", f"{metrics['unsafe_sql_block_rate']:.1%}")
        st.caption(
            f"规划题 {evaluation['planning_sample_count']} 条，安全测试 {evaluation['safety_sample_count']} 条。"
        )
        with st.expander("查看规划评测明细"):
            st.dataframe(pd.DataFrame(evaluation["details"]), width="stretch", hide_index=True)
        with st.expander("查看SQL安全测试"):
            st.dataframe(pd.DataFrame(evaluation["safety_details"]), width="stretch", hide_index=True)
        st.subheader("评测边界")
        for limitation in evaluation["limitations"]:
            st.write(f"- {limitation}")
