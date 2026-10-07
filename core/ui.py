"""Streamlit helpers shared by the dashboards. Streamlit is imported lazily."""

from __future__ import annotations

import pandas as pd

DEFAULT_COMPARE = ["USA", "CHN", "IND", "GBR", "DEU", "JPN", "BRA"]


def page(title: str, caption: str, *, icon: str = "📊") -> None:
    """Configure the page and print the heading. Call first in every ``app.py``."""
    import streamlit as st

    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    st.title(title)
    st.caption(caption)


def country_picker(names: dict[str, str], default: list[str] | None = None, *, key: str = "countries", label: str = "Countries") -> list[str]:
    """Sidebar multiselect returning ISO-3 codes. ``names`` maps iso3 -> display name."""
    import streamlit as st

    wanted = [c for c in (default or DEFAULT_COMPARE) if c in names]
    chosen = st.sidebar.multiselect(
        label,
        options=sorted(names, key=lambda c: names[c]),
        default=wanted,
        format_func=lambda c: names.get(c, c),
        key=key,
    )
    return list(chosen)


def year_range(low: int, high: int, default: tuple[int, int] | None = None, *, key: str = "years") -> tuple[int, int]:
    """Sidebar range slider returning (first_year, last_year)."""
    import streamlit as st

    return st.sidebar.slider("Years", min_value=low, max_value=high, value=default or (low, high), key=key)


def download(df: pd.DataFrame, filename: str, *, label: str = "Download data (CSV)") -> None:
    """Offer ``df`` as a CSV download."""
    import streamlit as st

    st.download_button(label, df.to_csv(index=False).encode(), file_name=filename, mime="text/csv")


def sources(*lines: str) -> None:
    """Footer listing data sources and caveats."""
    import streamlit as st

    st.divider()
    st.caption("**Sources & caveats**  \n" + "  \n".join(lines))
