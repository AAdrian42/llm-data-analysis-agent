from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import plotly.graph_objects as go

from .models import AnalysisPlan
from .semantic_layer import DIMENSIONS, METRICS


PALETTE = ["#147d92", "#d97706", "#7c3aed", "#27865f", "#c2415d", "#59636f"]


def build_static_chart(frame: pd.DataFrame, plan: AnalysisPlan) -> bytes | None:
    if frame.empty or "metric_value" not in frame:
        return None
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.figure import Figure
    from matplotlib.font_manager import FontProperties
    from matplotlib.text import Text
    from matplotlib.ticker import PercentFormatter, StrMethodFormatter

    font = FontProperties(
        fname=str(Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansSC.ttf")
    )
    chart_type = resolved_chart_type(plan)
    metric = METRICS[plan.metric]
    figure = Figure(figsize=(9, 4.3), dpi=140, facecolor="white", layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    values = pd.to_numeric(frame["metric_value"], errors="coerce").to_numpy()
    if chart_type == "indicator":
        from .tools import format_metric

        axes.axis("off")
        axes.text(0.5, 0.6, format_metric(values[0], plan.metric), ha="center", va="center",
                  fontsize=36, color=PALETTE[0], transform=axes.transAxes)
        axes.text(0.5, 0.35, metric.label, ha="center", fontsize=16, transform=axes.transAxes)
    elif chart_type == "heatmap" and len(plan.dimensions) == 2:
        x_name, y_name = plan.dimensions
        pivot = frame.pivot(index=y_name, columns=x_name, values="metric_value")
        color_map = LinearSegmentedColormap.from_list("risk", ["#eef6f7", "#47a3b5", "#9f2d4b"])
        image = axes.imshow(pivot.to_numpy(dtype=float), aspect="auto", cmap=color_map)
        axes.set_xticks(range(len(pivot.columns)), [str(v) for v in pivot.columns])
        axes.set_yticks(range(len(pivot.index)), [str(v) for v in pivot.index])
        axes.set_xlabel(DIMENSIONS[x_name].label)
        axes.set_ylabel(DIMENSIONS[y_name].label)
        colorbar = figure.colorbar(image, ax=axes)
        colorbar.set_label(metric.label)
        if metric.format_kind == "percentage":
            colorbar.ax.yaxis.set_major_formatter(PercentFormatter(1))
        for row in range(len(pivot.index)):
            for col in range(len(pivot.columns)):
                value = pivot.iloc[row, col]
                if pd.notna(value):
                    label = f"{value:.1%}" if metric.format_kind == "percentage" else f"{value:,.1f}"
                    axes.text(col, row, label, ha="center", va="center", fontsize=10, color="#17212b")
    else:
        x_name = plan.dimensions[0]
        labels = [str(v) for v in frame[x_name]]
        positions = np.arange(len(labels))
        if chart_type == "line":
            axes.plot(positions, values, color=PALETTE[0], marker="o", markersize=4, linewidth=2)
        else:
            axes.bar(positions, values, color=[PALETTE[i % len(PALETTE)] for i in positions], width=0.65)
        step = max(1, int(np.ceil(len(labels) / 12)))
        ticks = positions[::step]
        axes.set_xticks(ticks, [labels[i] for i in ticks], rotation=35 if len(labels) > 8 else 0)
        axes.set_xlabel(DIMENSIONS[x_name].label)
        axes.set_ylabel(metric.label)
        axes.set_axisbelow(True)
        axes.grid(axis="y", color="#e2e8ed", linewidth=0.7)
        axes.spines[["top", "right"]].set_visible(False)
        axes.tick_params(colors="#17212b")
        if metric.format_kind == "percentage":
            axes.yaxis.set_major_formatter(PercentFormatter(1))
        else:
            axes.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    for text in figure.findobj(Text):
        size = text.get_fontsize()
        text.set_fontproperties(font)
        text.set_fontsize(size)
    buffer = BytesIO()
    figure.savefig(buffer, format="png", facecolor="white")
    return buffer.getvalue()


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
    # Load the chart library only when there is a result to plot.
    import plotly.express as px
    import plotly.graph_objects as go

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

