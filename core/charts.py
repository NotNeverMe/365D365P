"""Plotly helpers so every dashboard looks consistent."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go

PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#4b5563"]


def theme(fig: go.Figure, *, title: str | None = None, yaxis_title: str | None = None, height: int = 460) -> go.Figure:
    """Apply the repo's house style to a figure and return it.

    The title sits at the very top of the figure and the legend sits just above
    the plot area, so the top margin is sized for whichever of the two are present.
    The legend gets room for two rows because eight series wrap.
    """
    has_legend = fig.layout.showlegend is not False and len(fig.data) > 1
    top = 16 + (36 if title else 0) + (48 if has_legend else 0)
    fig.update_layout(
        template="plotly_white",
        colorway=PALETTE,
        height=height,
        margin=dict(l=40, r=20, t=top, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        font=dict(family="Inter, system-ui, sans-serif", size=13),
    )
    if title:
        fig.update_layout(
            title=dict(text=title, x=0, xanchor="left", y=1, yref="container", yanchor="top", pad=dict(t=8), font=dict(size=16))
        )
    if yaxis_title:
        fig.update_yaxes(title_text=yaxis_title)
    return fig


def lines(df, x: str, y: str, color: str | None = None, **kwargs) -> go.Figure:
    """Themed line chart from a tidy frame."""
    title = kwargs.pop("title", None)
    yaxis_title = kwargs.pop("yaxis_title", None)
    return theme(px.line(df, x=x, y=y, color=color, **kwargs), title=title, yaxis_title=yaxis_title)


def bars(df, x: str, y: str, color: str | None = None, **kwargs) -> go.Figure:
    """Themed bar chart from a tidy frame."""
    title = kwargs.pop("title", None)
    yaxis_title = kwargs.pop("yaxis_title", None)
    fig = px.bar(df, x=x, y=y, color=color, **kwargs)
    fig.update_layout(hovermode="closest")
    return theme(fig, title=title, yaxis_title=yaxis_title)


def choropleth(df, iso3: str, value: str, *, title: str | None = None, **kwargs) -> go.Figure:
    """Themed world map keyed on ISO-3 codes."""
    fig = px.choropleth(df, locations=iso3, color=value, **kwargs)
    fig.update_layout(hovermode="closest", margin=dict(l=0, r=0, t=50 if title else 10, b=0))
    fig.update_geos(showframe=False, showcoastlines=False, projection_type="natural earth")
    return theme(fig, title=title, height=520)
