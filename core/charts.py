"""Plotly helpers so every dashboard looks consistent."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go

PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#4b5563"]


def theme(fig: go.Figure, *, title: str | None = None, yaxis_title: str | None = None, height: int = 460) -> go.Figure:
    """Apply the repo's house style to a figure and return it."""
    fig.update_layout(
        template="plotly_white",
        colorway=PALETTE,
        height=height,
        margin=dict(l=40, r=20, t=60 if title else 30, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        font=dict(family="Inter, system-ui, sans-serif", size=13),
    )
    if title:
        fig.update_layout(title=dict(text=title, x=0))
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
