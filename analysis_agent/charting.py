from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .models import AnalysisPlan
from .semantic_layer import DIMENSIONS, METRICS


PALETTE = ["#147d92", "#d97706", "#7c3aed", "#27865f", "#c2415d", "#59636f"]


def resolved_chart_type(plan: AnalysisPlan) -> str:
    if plan.chart_type != "auto":
        return plan.chart_type
    if len(plan.dimensions) == 2:
        return "heatmap"
    if plan.dimensions and plan.dimensions[0] in {"application_month", "application_year"}:
        return "line"
    if plan.dimensions:
        return "bar"
    return "indicator"


def build_chart(frame: pd.DataFrame, plan: AnalysisPlan) -> go.Figure | None:
    if frame.empty or "metric_value" not in frame:
        return None
    chart_type = resolved_chart_type(plan)
    metric = METRICS[plan.metric]
    display = frame.copy()
    if chart_type == "indicator":
        value = float(display.iloc[0]["metric_value"])
        suffix = "%" if metric.format_kind == "percentage" else ""
        shown_value = value * 100 if metric.format_kind == "percentage" else value
        figure = go.Figure(
            go.Indicator(
                mode="number",
                value=shown_value,
                number={"suffix": suffix, "valueformat": ".2f"},
                title={"text": metric.label},
            )
        )
    elif chart_type == "line":
        x_name = plan.dimensions[0]
        figure = px.line(
            display,
            x=x_name,
            y="metric_value",
            markers=True,
            labels={x_name: DIMENSIONS[x_name].label, "metric_value": metric.label},
            color_discrete_sequence=PALETTE,
        )
    elif chart_type == "heatmap" and len(plan.dimensions) == 2:
        x_name, y_name = plan.dimensions
        pivot = display.pivot(index=y_name, columns=x_name, values="metric_value")
        values = pivot.values * 100 if metric.format_kind == "percentage" else pivot.values
        figure = go.Figure(
            data=go.Heatmap(
                z=values,
                x=[str(value) for value in pivot.columns],
                y=[str(value) for value in pivot.index],
                colorscale=[[0, "#eef6f7"], [0.5, "#47a3b5"], [1, "#9f2d4b"]],
                colorbar={"title": metric.label},
                hovertemplate=f"{DIMENSIONS[x_name].label}: %{{x}}<br>{DIMENSIONS[y_name].label}: %{{y}}<br>{metric.label}: %{{z:.2f}}<extra></extra>",
            )
        )
        figure.update_xaxes(title=DIMENSIONS[x_name].label)
        figure.update_yaxes(title=DIMENSIONS[y_name].label)
    else:
        x_name = plan.dimensions[0]
        figure = px.bar(
            display,
            x=x_name,
            y="metric_value",
            labels={x_name: DIMENSIONS[x_name].label, "metric_value": metric.label},
            color=x_name,
            color_discrete_sequence=PALETTE,
        )
        figure.update_layout(showlegend=False)

    if metric.format_kind == "percentage" and chart_type not in {"indicator", "heatmap"}:
        figure.update_yaxes(tickformat=".1%")
    figure.update_layout(
        template="plotly_white",
        height=430,
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        font={"family": "Microsoft YaHei, Arial", "size": 13, "color": "#18212b"},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )
    return figure

