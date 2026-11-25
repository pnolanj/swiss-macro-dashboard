"""Switzerland Macroeconomic Monitor — Institutional Streamlit + Plotly Dashboard."""

from __future__ import annotations

import html
import io
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.fetch_data import (  # noqa: E402
    DATA_DIR,
    LOG_PATH,
    METADATA_PATH,
    SERIES_DIR,
    SERIES_SPECS,
    run_refresh,
)

# ---------------------------------------------------------------------------
# Institutional Design Tokens
# ---------------------------------------------------------------------------
NAVY = "#0A192F"
SLATE = "#475569"
STEEL = "#64748B"
ACCENT_BLUE = "#1D4ED8"
CRIMSON = "#B91C1C"
EMERALD = "#047857"
REF_GREY = "#94A3B8"
GRID_COLOR = "#F1F5F9"
BORDER_COLOR = "#E2E8F0"
CANVAS_BG = "#F8FAFC"
CARD_BG = "#FFFFFF"

TRIGGER_LABELS = {
    "github_actions": "GitHub Actions Scheduled",
    "manual_ui": "Manual Refresh",
    "local_cli": "Local CLI Refresh",
    "auto_init": "Initial Auto-Sync",
}

PLOTLY_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
}

# ---------------------------------------------------------------------------
# Page Configuration & CSS
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Switzerland Macro Monitor | Institutional Research",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_institutional_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #0F172A;
            background-color: #F8FAFC;
        }

        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2.5rem;
            max-width: 1560px;
        }

        /* Tabular numerals everywhere numbers appear */
        .mono, .kpi-value, .kpi-delta, .kpi-obs, .status-ts, .chart-badge, .meta-val, table {
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
        }

        /* Sidebar refinement */
        section[data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E2E8F0;
        }
        section[data-testid="stSidebar"] .block-container {
            padding-top: 1.25rem;
        }
        .sidebar-eyebrow {
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #64748B;
            margin-bottom: 0.4rem;
            margin-top: 0.8rem;
        }
        .sidebar-source-box {
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 4px;
            padding: 0.75rem 0.85rem;
            margin-top: 1rem;
            font-size: 0.75rem;
            line-height: 1.5;
            color: #475569;
        }
        .sidebar-source-box strong {
            color: #0A192F;
            font-weight: 600;
        }

        /* Executive Header Banner */
        .exec-banner {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-left: 4px solid #0A192F;
            border-radius: 4px;
            padding: 1.1rem 1.35rem;
            margin-bottom: 1rem;
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }
        .exec-left {
            max-width: 780px;
        }
        .exec-eyebrow {
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            color: #64748B;
            margin-bottom: 0.2rem;
        }
        .exec-title {
            font-size: 1.48rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #0A192F;
            line-height: 1.2;
            margin: 0;
        }
        .exec-subtitle {
            font-size: 0.85rem;
            color: #475569;
            margin-top: 0.3rem;
            line-height: 1.4;
        }
        .status-pill-bar {
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 4px;
            padding: 0.65rem 0.95rem;
            text-align: right;
            min-width: 285px;
        }
        .status-label-row {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 0.45rem;
            margin-bottom: 0.25rem;
        }
        .status-micro {
            font-size: 0.65rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #64748B;
        }
        .trigger-badge {
            font-size: 0.64rem;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: #0A192F;
            background: #E2E8F0;
            padding: 0.12rem 0.45rem;
            border-radius: 3px;
        }
        .trigger-badge.warn {
            color: #B91C1C;
            background: #FEE2E2;
        }
        .status-ts {
            font-size: 0.76rem;
            font-weight: 600;
            color: #0A192F;
            line-height: 1.45;
        }
        .status-ts-sub {
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
            font-size: 0.71rem;
            color: #475569;
        }

        /* Executive 6-Column KPI Grid */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 0.75rem;
            margin-bottom: 1.15rem;
        }
        @media (max-width: 1280px) {
            .kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        }
        @media (max-width: 720px) {
            .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        .kpi-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 4px;
            padding: 0.8rem 0.9rem 0.7rem 0.9rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 112px;
        }
        .kpi-label {
            font-size: 0.67rem;
            font-weight: 700;
            letter-spacing: 0.07em;
            text-transform: uppercase;
            color: #64748B;
            line-height: 1.3;
        }
        .kpi-value {
            font-size: 1.4rem;
            font-weight: 700;
            color: #0A192F;
            letter-spacing: -0.02em;
            margin-top: 0.25rem;
            line-height: 1.15;
        }
        .kpi-delta {
            font-size: 0.72rem;
            font-weight: 500;
            margin-top: 0.22rem;
            color: #475569;
        }
        .kpi-delta.pos { color: #047857; }
        .kpi-delta.neg { color: #B91C1C; }
        .kpi-delta.neu { color: #475569; }
        .kpi-obs {
            margin-top: 0.5rem;
            padding-top: 0.42rem;
            border-top: 1px solid #F1F5F9;
            font-size: 0.68rem;
            color: #64748B;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .kpi-obs strong {
            color: #0F172A;
            font-weight: 600;
        }

        /* Institutional Chart Panels (wrapping st.container(border=True)) */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0 !important;
            border-radius: 4px !important;
            padding: 0.85rem 1rem 0.7rem 1rem !important;
            box-shadow: none !important;
        }
        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.75rem;
            margin-bottom: 0.25rem;
            padding-bottom: 0.45rem;
            border-bottom: 1px solid #F1F5F9;
        }
        .chart-title {
            font-size: 0.94rem;
            font-weight: 700;
            color: #0A192F;
            letter-spacing: -0.01em;
            line-height: 1.25;
        }
        .chart-sub {
            font-size: 0.74rem;
            color: #64748B;
            margin-top: 0.1rem;
        }
        .chart-badge {
            font-size: 0.78rem;
            font-weight: 600;
            color: #0A192F;
            background: #F1F5F9;
            border: 1px solid #E2E8F0;
            border-radius: 3px;
            padding: 0.18rem 0.5rem;
            white-space: nowrap;
        }
        .chart-badge.alert {
            color: #B91C1C;
            background: #FEF2F2;
            border-color: #FECACA;
        }

        /* Mandatory Chart Metadata Footer */
        .chart-meta-footer {
            margin-top: 0.2rem;
            padding-top: 0.55rem;
            border-top: 1px solid #E2E8F0;
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.28rem 0.85rem;
            font-size: 0.7rem;
            line-height: 1.35;
            color: #475569;
        }
        .meta-item {
            display: flex;
            flex-wrap: wrap;
            gap: 0.25rem;
        }
        .meta-key {
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-size: 0.63rem;
            color: #64748B;
            margin-top: 0.04rem;
        }
        .meta-val {
            font-family: 'Inter', sans-serif;
            font-size: 0.7rem;
            color: #334155;
        }
        .meta-obs-highlight {
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
            font-weight: 700;
            color: #0A192F;
        }
        .meta-span-2 {
            grid-column: span 2;
        }

        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.25rem;
            border-bottom: 1px solid #E2E8F0;
            margin-bottom: 1rem;
        }
        .stTabs [data-baseweb="tab"] {
            height: 2.35rem;
            padding: 0 1rem;
            font-size: 0.82rem;
            font-weight: 600;
            color: #64748B;
            background-color: transparent;
            border-radius: 4px 4px 0 0;
        }
        .stTabs [aria-selected="true"] {
            color: #0A192F !important;
            border-bottom: 2px solid #0A192F !important;
            background-color: #FFFFFF !important;
        }

        /* Institutional section heading */
        .section-head {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #0A192F;
            padding-bottom: 0.35rem;
            border-bottom: 1px solid #E2E8F0;
            margin: 0.4rem 0 0.75rem 0;
        }
        .info-callout {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-left: 3px solid #1D4ED8;
            border-radius: 4px;
            padding: 0.7rem 0.9rem;
            font-size: 0.8rem;
            color: #334155;
            margin: 0.65rem 0 1rem 0;
            line-height: 1.45;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Data Loading & Compute-Before-Slice Pipeline
# ---------------------------------------------------------------------------
def ensure_initialized() -> None:
    """Auto-run ingestion once if data/refresh_metadata.json is missing on first boot."""
    if not METADATA_PATH.exists():
        with st.spinner("Initializing Swiss macroeconomic dataset from FRED and SNB..."):
            run_refresh(trigger="auto_init", print_table=False)


def get_metadata_mtime() -> float:
    return METADATA_PATH.stat().st_mtime if METADATA_PATH.exists() else 0.0


@st.cache_data(ttl=300, show_spinner=False)
def load_macro_bundle(meta_mtime: float) -> dict[str, Any]:
    """Load metadata, raw CSVs, refresh log, and compute ALL transforms on FULL history."""
    _ = meta_mtime  # cache key dependency
    metadata: dict[str, Any] = {}
    if METADATA_PATH.exists():
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    raw_series: dict[str, pd.DataFrame] = {}
    for key in SERIES_SPECS:
        path = SERIES_DIR / f"{key}.csv"
        if path.exists():
            df = pd.read_csv(path)
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df.dropna(subset=["date", "value"]).sort_values("date").reset_index(drop=True)
            raw_series[key] = df
        else:
            raw_series[key] = pd.DataFrame(columns=["date", "value"])

    # Compute-before-slice transformations on FULL series
    # 1. Real GDP (Quarterly)
    gdp = raw_series["gdp_real"].copy()
    gdp["gdp_yoy"] = (gdp["value"] / gdp["value"].shift(4) - 1.0) * 100.0
    gdp["gdp_qoq"] = (gdp["value"] / gdp["value"].shift(1) - 1.0) * 100.0

    # 2. HICP (Monthly)
    hicp = raw_series["hicp_index"].copy()
    hicp["hicp_yoy"] = (hicp["value"] / hicp["value"].shift(12) - 1.0) * 100.0

    # 3. Unemployment (Quarterly)
    unemp = raw_series["unemp_rate"].copy()
    unemp["unemp_ma4"] = unemp["value"].rolling(4, min_periods=4).mean()

    # 4. SNB Policy Rate & Historical Corridor (Monthly)
    snb_policy = raw_series["snb_policy_rate"].copy()
    snb_low = raw_series["snb_libor_low"].copy().rename(columns={"value": "libor_low"})
    snb_high = raw_series["snb_libor_high"].copy().rename(columns={"value": "libor_high"})
    snb_corridor = pd.merge(snb_low, snb_high, on="date", how="inner").sort_values("date")

    # 5. Yield Curve (Monthly inner join)
    r3m = raw_series["rate_3m"].copy().rename(columns={"value": "rate_3m"})
    y10 = raw_series["yield_10y"].copy().rename(columns={"value": "yield_10y"})
    rates = pd.merge(r3m, y10, on="date", how="inner").sort_values("date").reset_index(drop=True)
    rates["spread_bps"] = (rates["yield_10y"] - rates["rate_3m"]) * 100.0

    # 6. USD/CHF (Daily)
    fx = raw_series["usd_chf"].copy()
    fx["ma_30d"] = fx["value"].rolling(30, min_periods=15).mean()

    # Refresh Log
    if LOG_PATH.exists():
        log_df = pd.read_csv(LOG_PATH)
    else:
        log_df = pd.DataFrame(
            columns=[
                "refresh_timestamp_utc",
                "refresh_timestamp_zurich",
                "trigger",
                "series_succeeded",
                "series_failed",
                "any_new_data",
                "status",
                "notes",
            ]
        )

    # Global min/max years across primary datasets
    all_dates = pd.concat(
        [df["date"] for k, df in raw_series.items() if not df.empty],
        ignore_index=True,
    ) if any(not df.empty for df in raw_series.values()) else pd.Series(dtype="datetime64[ns]")

    min_year = int(all_dates.min().year) if not all_dates.empty else 2000
    max_year = int(all_dates.max().year) if not all_dates.empty else datetime.utcnow().year
    max_date = pd.Timestamp(all_dates.max()) if not all_dates.empty else pd.Timestamp.utcnow().tz_localize(None)

    return {
        "metadata": metadata,
        "raw": raw_series,
        "gdp": gdp,
        "hicp": hicp,
        "unemp": unemp,
        "snb_policy": snb_policy,
        "snb_corridor": snb_corridor,
        "rates": rates,
        "fx": fx,
        "log_df": log_df,
        "min_year": min_year,
        "max_year": max_year,
        "max_date": max_date,
    }


@st.cache_data(ttl=300, show_spinner=False)
def export_df_csv_bytes(df: pd.DataFrame) -> bytes:
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out.to_csv(index=False).encode("utf-8")


@st.cache_data(ttl=300, show_spinner=False)
def build_zip_bundle(meta_mtime: float) -> bytes:
    """Create an in-memory ZIP archive containing all series CSVs and refresh_metadata.json."""
    _ = meta_mtime
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for key in SERIES_SPECS:
            path = SERIES_DIR / f"{key}.csv"
            if path.exists():
                zf.write(path, arcname=f"series/{key}.csv")
        if METADATA_PATH.exists():
            zf.write(METADATA_PATH, arcname="refresh_metadata.json")
        if LOG_PATH.exists():
            zf.write(LOG_PATH, arcname="refresh_log.csv")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Formatting & Filtering Helpers
# ---------------------------------------------------------------------------
def fmt_obs_date(dt: pd.Timestamp | str | None, freq: str) -> str:
    if dt is None or pd.isna(dt):
        return "N/A"
    ts = pd.Timestamp(dt)
    f_low = freq.lower()
    if "quarter" in f_low:
        q = (ts.month - 1) // 3 + 1
        return f"Q{q} {ts.year}"
    if "month" in f_low:
        return ts.strftime("%b %Y")
    return ts.strftime("%Y-%m-%d")


def slice_by_dates(df: pd.DataFrame, start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> pd.DataFrame:
    if df.empty:
        return df
    return df.loc[(df["date"] >= start_dt) & (df["date"] <= end_dt)].copy()


def apply_institutional_layout(
    fig: go.Figure,
    height: int = 335,
    y_title: str | None = None,
    y_suffix: str = "",
    y_tickformat: str | None = None,
) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=46, r=18, t=34, b=32),
        plot_bgcolor=CARD_BG,
        paper_bgcolor=CARD_BG,
        font=dict(family="Inter, sans-serif", size=11, color=SLATE),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=NAVY,
            bordercolor=NAVY,
            font=dict(family="JetBrains Mono, monospace", size=11, color="#FFFFFF"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(255,255,255,0)",
            font=dict(size=10.5, color=SLATE),
            itemwidth=30,
        ),
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor=BORDER_COLOR,
        linewidth=1,
        tickfont=dict(family="JetBrains Mono, monospace", size=10, color=STEEL),
        zeroline=False,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=GRID_COLOR,
        gridwidth=1,
        linecolor="rgba(0,0,0,0)",
        tickfont=dict(family="JetBrains Mono, monospace", size=10, color=STEEL),
        ticksuffix=y_suffix,
        tickformat=y_tickformat,
        title_text=y_title,
        title_font=dict(size=10.5, color=STEEL),
        zeroline=False,
    )
    return fig


def add_empty_state(fig: go.Figure, message: str = "No observations in selected sample period.") -> go.Figure:
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(family="Inter, sans-serif", size=12, color=STEEL),
    )
    return fig


def render_chart_header(title: str, subtitle: str, badge_text: str, alert: bool = False) -> None:
    badge_cls = "chart-badge alert" if alert else "chart-badge"
    st.markdown(
        f"""
        <div class="chart-header">
            <div>
                <div class="chart-title">{html.escape(title)}</div>
                <div class="chart-sub">{html.escape(subtitle)}</div>
            </div>
            <div class="{badge_cls}">{html.escape(badge_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chart_footer(
    units: str,
    transformation: str,
    frequency: str,
    source_id: str,
    latest_obs: str,
) -> None:
    st.markdown(
        f"""
        <div class="chart-meta-footer">
            <div class="meta-item"><span class="meta-key">Units:</span> <span class="meta-val">{html.escape(units)}</span></div>
            <div class="meta-item"><span class="meta-key">Frequency:</span> <span class="meta-val">{html.escape(frequency)}</span></div>
            <div class="meta-item meta-span-2"><span class="meta-key">Transformation:</span> <span class="meta-val">{html.escape(transformation)}</span></div>
            <div class="meta-item"><span class="meta-key">Source / ID:</span> <span class="meta-val">{html.escape(source_id)}</span></div>
            <div class="meta-item"><span class="meta-key">Latest Obs.:</span> <span class="meta-obs-highlight">{html.escape(latest_obs)}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Chart Builders (6 Institutional Figures)
# ---------------------------------------------------------------------------
def build_gdp_chart(df: pd.DataFrame, metric_mode: str) -> go.Figure:
    is_yoy = metric_mode == "YoY % Growth"
    col = "gdp_yoy" if is_yoy else "gdp_qoq"
    sub = df.dropna(subset=[col])

    fig = go.Figure()
    if sub.empty:
        return apply_institutional_layout(add_empty_state(fig), y_suffix="%")

    colors = [NAVY if v >= 0 else CRIMSON for v in sub[col]]
    fig.add_trace(
        go.Bar(
            x=sub["date"],
            y=sub[col],
            name=metric_mode,
            marker_color=colors,
            hovertemplate=f"{metric_mode}: %{{y:+.2f}}%<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color=REF_GREY, line_width=1)
    apply_institutional_layout(fig, y_suffix="%")
    fig.update_layout(showlegend=False)
    return fig


def build_hicp_chart(df: pd.DataFrame, view_mode: str) -> go.Figure:
    is_yoy = view_mode == "YoY % Inflation"
    col = "hicp_yoy" if is_yoy else "value"
    sub = df.dropna(subset=[col])

    fig = go.Figure()
    if sub.empty:
        return apply_institutional_layout(add_empty_state(fig), y_suffix="%" if is_yoy else "")

    if is_yoy:
        fig.add_hrect(
            y0=0.0,
            y1=2.0,
            fillcolor="rgba(16, 185, 129, 0.08)",
            line_width=0,
            layer="below",
        )
        fig.add_hline(y=0.0, line_color=REF_GREY, line_width=1)
        fig.add_hline(y=2.0, line_color="rgba(4, 120, 87, 0.35)", line_width=1, line_dash="dot")
        fig.add_annotation(
            x=1.0,
            y=2.0,
            xref="paper",
            yref="y",
            xanchor="right",
            yanchor="bottom",
            text="SNB Price Stability Range (0%–2%)",
            showarrow=False,
            font=dict(family="Inter, sans-serif", size=9.5, color=EMERALD),
            bgcolor="rgba(255,255,255,0.75)",
        )

    fig.add_trace(
        go.Scatter(
            x=sub["date"],
            y=sub[col],
            mode="lines",
            name="HICP YoY %" if is_yoy else "HICP Index (2025=100)",
            line=dict(color=NAVY, width=2.4),
            hovertemplate=(
                "HICP YoY: %{y:+.2f}%<extra></extra>"
                if is_yoy
                else "HICP Index: %{y:.2f}<extra></extra>"
            ),
        )
    )
    apply_institutional_layout(fig, y_suffix="%" if is_yoy else "")
    return fig


def build_unemp_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_institutional_layout(add_empty_state(fig), y_suffix="%")

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["value"],
            mode="lines+markers",
            name="Quarterly Rate (NSA)",
            line=dict(color=REF_GREY, width=1.6),
            marker=dict(size=4.5, color=REF_GREY),
            hovertemplate="Quarterly Rate: %{y:.2f}%<extra></extra>",
        )
    )
    ma_sub = df.dropna(subset=["unemp_ma4"])
    if not ma_sub.empty:
        fig.add_trace(
            go.Scatter(
                x=ma_sub["date"],
                y=ma_sub["unemp_ma4"],
                mode="lines",
                name="4-Quarter Moving Avg.",
                line=dict(color=NAVY, width=2.5),
                hovertemplate="4Q Moving Avg: %{y:.2f}%<extra></extra>",
            )
        )
    apply_institutional_layout(fig, y_suffix="%")
    return fig


def build_snb_policy_chart(
    policy_df: pd.DataFrame,
    corridor_df: pd.DataFrame,
    start_dt: pd.Timestamp,
    end_dt: pd.Timestamp,
) -> go.Figure:
    fig = go.Figure()
    if policy_df.empty and corridor_df.empty:
        return apply_institutional_layout(add_empty_state(fig), y_suffix="%")

    if not corridor_df.empty:
        fig.add_trace(
            go.Scatter(
                x=corridor_df["date"],
                y=corridor_df["libor_high"],
                mode="lines",
                line=dict(color="rgba(100, 116, 139, 0.45)", width=1, shape="hv"),
                name="3M CHF Libor Target Range (Pre-Jun 2019)",
                legendgroup="corridor",
                hovertemplate="Libor Upper Bound: %{y:.2f}%<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=corridor_df["date"],
                y=corridor_df["libor_low"],
                mode="lines",
                fill="tonexty",
                fillcolor="rgba(100, 116, 139, 0.16)",
                line=dict(color="rgba(100, 116, 139, 0.45)", width=1, shape="hv"),
                name="3M CHF Libor Lower",
                legendgroup="corridor",
                showlegend=False,
                hovertemplate="Libor Lower Bound: %{y:.2f}%<extra></extra>",
            )
        )

    if not policy_df.empty:
        fig.add_trace(
            go.Scatter(
                x=policy_df["date"],
                y=policy_df["value"],
                mode="lines",
                name="SNB Official Policy Rate (LZ)",
                line=dict(color=CRIMSON, width=2.5, shape="hv"),
                hovertemplate="SNB Policy Rate: %{y:.2f}%<extra></extra>",
            )
        )

    fig.add_hline(y=0.0, line_color=REF_GREY, line_width=1)

    regime_dt = pd.Timestamp("2019-06-13")
    if start_dt <= regime_dt <= end_dt:
        fig.add_shape(
            type="line",
            x0="2019-06-13",
            x1="2019-06-13",
            y0=0,
            y1=1,
            xref="x",
            yref="paper",
            line=dict(color=STEEL, width=1.1, dash="dot"),
        )
        fig.add_annotation(
            x="2019-06-13",
            y=0.98,
            xref="x",
            yref="paper",
            text="SNB Policy Rate Introduced",
            showarrow=False,
            xanchor="left",
            yanchor="top",
            xshift=5,
            font=dict(family="Inter, sans-serif", size=9.5, color=SLATE),
            bgcolor="rgba(255,255,255,0.85)",
        )

    apply_institutional_layout(fig, y_suffix="%")
    return fig


def build_yield_curve_chart(df: pd.DataFrame, view_mode: str) -> go.Figure:
    show_spread = view_mode == "Rates (3M & 10Y) + 10Y–3M Spread"
    if df.empty:
        fig = go.Figure()
        return apply_institutional_layout(add_empty_state(fig), y_suffix="%")

    if show_spread:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.09,
            row_heights=[0.68, 0.32],
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["yield_10y"],
                mode="lines",
                name="10Y Gov. Yield",
                line=dict(color=NAVY, width=2.3),
                hovertemplate="10Y Yield: %{y:.2f}%<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["rate_3m"],
                mode="lines",
                name="3M Interbank Rate",
                line=dict(color=ACCENT_BLUE, width=2.0, dash="dash"),
                hovertemplate="3M Rate: %{y:.2f}%<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_hline(y=0.0, line_color=REF_GREY, line_width=0.9, row=1, col=1)

        spread_colors = [EMERALD if v >= 0 else CRIMSON for v in df["spread_bps"]]
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=df["spread_bps"],
                name="10Y–3M Spread (bps)",
                marker_color=spread_colors,
                opacity=0.88,
                hovertemplate="10Y–3M Spread: %{y:+.0f} bps<extra></extra>",
            ),
            row=2,
            col=1,
        )
        fig.add_hline(y=0.0, line_color=REF_GREY, line_width=0.9, row=2, col=1)

        apply_institutional_layout(fig, height=345)
        fig.update_yaxes(ticksuffix="%", row=1, col=1)
        fig.update_yaxes(ticksuffix=" bps", tickfont=dict(size=9.5), row=2, col=1)
        fig.update_xaxes(showgrid=False, linecolor=BORDER_COLOR, row=1, col=1)
        fig.update_xaxes(showgrid=False, linecolor=BORDER_COLOR, row=2, col=1)
        return fig

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["yield_10y"],
            mode="lines",
            name="10Y Gov. Yield",
            line=dict(color=NAVY, width=2.3),
            hovertemplate="10Y Yield: %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["rate_3m"],
            mode="lines",
            name="3M Interbank Rate",
            line=dict(color=ACCENT_BLUE, width=2.0, dash="dash"),
            hovertemplate="3M Rate: %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_hline(y=0.0, line_color=REF_GREY, line_width=1)
    apply_institutional_layout(fig, height=345, y_suffix="%")
    return fig


def build_fx_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_institutional_layout(add_empty_state(fig), height=345)

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["value"],
            mode="lines",
            name="USD/CHF Daily Spot",
            line=dict(color=ACCENT_BLUE, width=1.4),
            opacity=0.85,
            hovertemplate="Spot: %{y:.4f} CHF/USD<extra></extra>",
        )
    )
    ma_sub = df.dropna(subset=["ma_30d"])
    if not ma_sub.empty:
        fig.add_trace(
            go.Scatter(
                x=ma_sub["date"],
                y=ma_sub["ma_30d"],
                mode="lines",
                name="30-Trading-Day MA",
                line=dict(color=NAVY, width=2.3),
                hovertemplate="30D MA: %{y:.4f} CHF/USD<extra></extra>",
            )
        )

    fig.add_annotation(
        x=0.99,
        y=0.98,
        xref="paper",
        yref="paper",
        xanchor="right",
        yanchor="top",
        text="Quotation: CHF per 1 USD (Down = CHF Appreciation)",
        showarrow=False,
        font=dict(family="Inter, sans-serif", size=9.5, color=SLATE),
        bgcolor="rgba(248, 250, 252, 0.92)",
        bordercolor=BORDER_COLOR,
        borderwidth=1,
        borderpad=4,
    )
    apply_institutional_layout(fig, height=345, y_tickformat=".3f")
    return fig


# ---------------------------------------------------------------------------
# Executive Header & KPI Strip
# ---------------------------------------------------------------------------
def render_header(metadata: dict[str, Any]) -> None:
    utc_ts = metadata.get("last_successful_refresh_utc", "Not yet refreshed")
    zurich_ts = metadata.get("last_successful_refresh_zurich", "N/A")
    trigger_raw = metadata.get("trigger", "local_cli")
    trigger_label = TRIGGER_LABELS.get(trigger_raw, trigger_raw)
    failed = int(metadata.get("series_failed", 0))
    badge_cls = "trigger-badge warn" if failed > 0 else "trigger-badge"
    status_suffix = f" ({failed} ERR)" if failed > 0 else ""

    st.markdown(
        f"""
        <div class="exec-banner">
            <div class="exec-left">
                <div class="exec-eyebrow">SOVEREIGN MACROECONOMIC INTELLIGENCE &nbsp;|&nbsp; SWITZERLAND (CHE)</div>
                <h1 class="exec-title">Swiss Macroeconomic Monitor</h1>
                <div class="exec-subtitle">
                    Navigating low inflation, near-zero policy rates, and Swiss franc strength without sacrificing real output growth or labor-market stability.
                </div>
            </div>
            <div class="status-pill-bar">
                <div class="status-label-row">
                    <span class="status-micro">Last Successful Refresh</span>
                    <span class="{badge_cls}">{html.escape(trigger_label + status_suffix)}</span>
                </div>
                <div class="status-ts">{html.escape(str(utc_ts))}</div>
                <div class="status-ts-sub">Zurich: {html.escape(str(zurich_ts))}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_strip(bundle: dict[str, Any]) -> None:
    cards: list[dict[str, str]] = []

    # 1. Real GDP Growth (YoY %)
    gdp_yoy = bundle["gdp"].dropna(subset=["gdp_yoy"])
    if not gdp_yoy.empty:
        latest = gdp_yoy.iloc[-1]
        prev = gdp_yoy.iloc[-2] if len(gdp_yoy) >= 2 else None
        qoq_val = latest["gdp_qoq"]
        delta_pp = (latest["gdp_yoy"] - prev["gdp_yoy"]) if prev is not None else np.nan
        qoq_txt = f"QoQ {qoq_val:+.2f}%" if pd.notna(qoq_val) else ""
        delta_txt = f"{delta_pp:+.2f} pp vs. prior | {qoq_txt}" if pd.notna(delta_pp) else qoq_txt
        cls = "pos" if latest["gdp_yoy"] > 0 else "neg" if latest["gdp_yoy"] < 0 else "neu"
        cards.append(
            {
                "label": "Real GDP Growth (YoY)",
                "value": f"{latest['gdp_yoy']:+.2f}%",
                "delta": delta_txt,
                "cls": cls,
                "obs": fmt_obs_date(latest["date"], "Quarterly"),
            }
        )
    else:
        cards.append({"label": "Real GDP Growth (YoY)", "value": "N/A", "delta": "—", "cls": "neu", "obs": "N/A"})

    # 2. Headline HICP Inflation (YoY %)
    hicp_yoy = bundle["hicp"].dropna(subset=["hicp_yoy"])
    if not hicp_yoy.empty:
        latest = hicp_yoy.iloc[-1]
        prev = hicp_yoy.iloc[-2] if len(hicp_yoy) >= 2 else None
        mom_pp = (latest["hicp_yoy"] - prev["hicp_yoy"]) if prev is not None else np.nan
        delta_txt = f"{mom_pp:+.2f} pp MoM ({mom_pp * 100:+.0f} bps)" if pd.notna(mom_pp) else "—"
        in_band = 0.0 <= latest["hicp_yoy"] <= 2.0
        cls = "pos" if in_band else "neg"
        cards.append(
            {
                "label": "Headline HICP (YoY)",
                "value": f"{latest['hicp_yoy']:+.2f}%",
                "delta": delta_txt,
                "cls": cls,
                "obs": fmt_obs_date(latest["date"], "Monthly"),
            }
        )
    else:
        cards.append({"label": "Headline HICP (YoY)", "value": "N/A", "delta": "—", "cls": "neu", "obs": "N/A"})

    # 3. Unemployment Rate (Ages 15-74)
    unemp = bundle["unemp"]
    if not unemp.empty:
        latest = unemp.iloc[-1]
        prev = unemp.iloc[-2] if len(unemp) >= 2 else None
        diff = (latest["value"] - prev["value"]) if prev is not None else np.nan
        delta_txt = f"{diff:+.2f} pp vs. prior Q" if pd.notna(diff) else "—"
        cls = "neg" if (pd.notna(diff) and diff > 0.05) else "pos" if (pd.notna(diff) and diff < -0.05) else "neu"
        cards.append(
            {
                "label": "Unemployment (15–74)",
                "value": f"{latest['value']:.2f}%",
                "delta": delta_txt,
                "cls": cls,
                "obs": fmt_obs_date(latest["date"], "Quarterly"),
            }
        )
    else:
        cards.append({"label": "Unemployment (15–74)", "value": "N/A", "delta": "—", "cls": "neu", "obs": "N/A"})

    # 4. SNB Policy Rate
    snb = bundle["snb_policy"]
    if not snb.empty:
        latest = snb.iloc[-1]
        prev = snb.iloc[-2] if len(snb) >= 2 else None
        diff_bps = (latest["value"] - prev["value"]) * 100.0 if prev is not None else np.nan
        delta_txt = (
            f"{diff_bps:+.0f} bps vs. prior mo."
            if pd.notna(diff_bps) and abs(diff_bps) >= 0.5
            else "Unchanged (0 bps)"
        )
        cls = "neg" if latest["value"] < 0 else "neu"
        cards.append(
            {
                "label": "SNB Policy Rate",
                "value": f"{latest['value']:.2f}%",
                "delta": delta_txt,
                "cls": cls,
                "obs": fmt_obs_date(latest["date"], "Monthly"),
            }
        )
    else:
        cards.append({"label": "SNB Policy Rate", "value": "N/A", "delta": "—", "cls": "neu", "obs": "N/A"})

    # 5. 10Y-3M Yield Spread
    rates = bundle["rates"]
    if not rates.empty:
        latest = rates.iloc[-1]
        spread = latest["spread_bps"]
        y10 = latest["yield_10y"]
        cls = "pos" if spread >= 0 else "neg"
        cards.append(
            {
                "label": "10Y–3M Yield Spread",
                "value": f"{spread:+.0f} bps",
                "delta": f"10Y: {y10:.2f}% | 3M: {latest['rate_3m']:.2f}%",
                "cls": cls,
                "obs": fmt_obs_date(latest["date"], "Monthly"),
            }
        )
    else:
        cards.append({"label": "10Y–3M Yield Spread", "value": "N/A", "delta": "—", "cls": "neu", "obs": "N/A"})

    # 6. USD/CHF Spot Rate
    fx = bundle["fx"]
    if not fx.empty:
        latest = fx.iloc[-1]
        lookback_idx = max(0, len(fx) - 22)  # ~30 calendar days (~21 trading days)
        ref_val = fx.iloc[lookback_idx]["value"]
        chg_pct = ((latest["value"] / ref_val) - 1.0) * 100.0 if ref_val else np.nan
        delta_txt = f"30D: {chg_pct:+.2f}% (CHF/USD)" if pd.notna(chg_pct) else "—"
        cards.append(
            {
                "label": "USD/CHF Spot Rate",
                "value": f"{latest['value']:.4f}",
                "delta": delta_txt,
                "cls": "neu",
                "obs": fmt_obs_date(latest["date"], "Daily"),
            }
        )
    else:
        cards.append({"label": "USD/CHF Spot Rate", "value": "N/A", "delta": "—", "cls": "neu", "obs": "N/A"})

    card_html = []
    for c in cards:
        card_html.append(
            f"""
            <div class="kpi-card">
                <div>
                    <div class="kpi-label">{html.escape(c['label'])}</div>
                    <div class="kpi-value">{html.escape(c['value'])}</div>
                    <div class="kpi-delta {c['cls']}">{html.escape(c['delta'])}</div>
                </div>
                <div class="kpi-obs">
                    <span>Obs:</span>
                    <strong>{html.escape(c['obs'])}</strong>
                </div>
            </div>
            """
        )

    st.markdown(f'<div class="kpi-grid">{"".join(card_html)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar Controls
# ---------------------------------------------------------------------------
def render_sidebar(bundle: dict[str, Any]) -> dict[str, Any]:
    with st.sidebar:
        st.markdown('<div class="sidebar-eyebrow">Sample Period</div>', unsafe_allow_html=True)
        preset = st.radio(
            "Sample Period",
            options=[
                "2015–Present (Default)",
                "Last 5 Years",
                "Last 10 Years",
                "Full Available History",
                "Custom Year Range",
            ],
            index=0,
            label_visibility="collapsed",
        )

        min_year = bundle["min_year"]
        max_year = bundle["max_year"]
        max_date = bundle["max_date"]

        if preset == "2015–Present (Default)":
            start_dt = pd.Timestamp("2015-01-01")
            end_dt = max_date
        elif preset == "Last 5 Years":
            start_dt = max_date - pd.DateOffset(years=5)
            end_dt = max_date
        elif preset == "Last 10 Years":
            start_dt = max_date - pd.DateOffset(years=10)
            end_dt = max_date
        elif preset == "Full Available History":
            start_dt = pd.Timestamp(min_year, 1, 1)
            end_dt = max_date
        else:
            years = list(range(min_year, max_year + 1))
            default_start = 2015 if 2015 in years else years[0]
            start_year = st.selectbox(
                "Start Year",
                options=years,
                index=years.index(default_start),
            )
            valid_end_years = [y for y in years if y >= start_year]
            end_year = st.selectbox(
                "End Year",
                options=valid_end_years,
                index=len(valid_end_years) - 1,
            )
            start_dt = pd.Timestamp(start_year, 1, 1)
            end_dt = pd.Timestamp(end_year, 12, 31)

        st.markdown('<div class="sidebar-eyebrow">Analytical Views</div>', unsafe_allow_html=True)
        gdp_metric = st.radio(
            "Real GDP Metric",
            options=["YoY % Growth", "QoQ % Growth"],
            index=0,
        )
        inflation_view = st.radio(
            "Inflation View",
            options=["YoY % Inflation", "HICP Index (2025 = 100)"],
            index=0,
        )
        yield_view = st.radio(
            "Yield Curve View",
            options=["Rates (3M & 10Y) + 10Y–3M Spread", "Rates Only"],
            index=0,
        )

        st.markdown('<div class="sidebar-eyebrow">Live Ingestion</div>', unsafe_allow_html=True)
        if st.button("Run Live Data Refresh", use_container_width=True, type="primary"):
            with st.spinner("Refreshing primary series from FRED and SNB..."):
                result = run_refresh(trigger="manual_ui", print_table=False)
            st.cache_data.clear()
            new_flag = "new source data detected" if result.get("any_new_data") else "no new upstream releases"
            st.session_state["refresh_toast"] = (
                f"Refresh complete ({result.get('last_attempt_utc')}) — "
                f"{result.get('series_succeeded')}/{result.get('series_succeeded', 0) + result.get('series_failed', 0)} "
                f"series OK; {new_flag}."
            )
            st.rerun()

        st.markdown(
            """
            <div class="sidebar-source-box">
                <strong>Primary Data Providers</strong><br/>
                SNB (data.snb.ch) · Eurostat / FRED<br/>
                OECD / FRED · Federal Reserve H.10 / FRED<br/><br/>
                <strong>Automation Cadence</strong><br/>
                GitHub Actions: Daily 12:00 UTC (13:00 CET)<br/>
                Keyless public CSV ingestion with atomic commits.
            </div>
            """,
            unsafe_allow_html=True,
        )

    return {
        "preset": preset,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "gdp_metric": gdp_metric,
        "inflation_view": inflation_view,
        "yield_view": yield_view,
    }


# ---------------------------------------------------------------------------
# Tab 1 — Executive Macro Dashboard
# ---------------------------------------------------------------------------
def render_tab_dashboard(bundle: dict[str, Any], cfg: dict[str, Any]) -> None:
    start_dt, end_dt = cfg["start_dt"], cfg["end_dt"]

    gdp_slice = slice_by_dates(bundle["gdp"], start_dt, end_dt)
    hicp_slice = slice_by_dates(bundle["hicp"], start_dt, end_dt)
    unemp_slice = slice_by_dates(bundle["unemp"], start_dt, end_dt)
    snb_pol_slice = slice_by_dates(bundle["snb_policy"], start_dt, end_dt)
    snb_cor_slice = slice_by_dates(bundle["snb_corridor"], start_dt, end_dt)
    rates_slice = slice_by_dates(bundle["rates"], start_dt, end_dt)
    fx_slice = slice_by_dates(bundle["fx"], start_dt, end_dt)

    # Row 1: Real GDP | Headline Inflation
    r1_left, r1_right = st.columns(2, gap="medium")

    with r1_left:
        with st.container(border=True):
            is_yoy = cfg["gdp_metric"] == "YoY % Growth"
            col = "gdp_yoy" if is_yoy else "gdp_qoq"
            valid_gdp = bundle["gdp"].dropna(subset=[col])
            latest_val = valid_gdp.iloc[-1][col] if not valid_gdp.empty else np.nan
            latest_obs = fmt_obs_date(valid_gdp.iloc[-1]["date"], "Quarterly") if not valid_gdp.empty else "N/A"
            badge = f"{latest_val:+.2f}%" if pd.notna(latest_val) else "N/A"

            render_chart_header(
                title="Real GDP Growth",
                subtitle=f"Chained-volume output expansion ({cfg['gdp_metric']})",
                badge_text=badge,
                alert=bool(pd.notna(latest_val) and latest_val < 0),
            )
            st.plotly_chart(
                build_gdp_chart(gdp_slice, cfg["gdp_metric"]),
                use_container_width=True,
                config=PLOTLY_CONFIG,
            )
            render_chart_footer(
                units="Percent (%) from Millions of Chained 2010 EUR (SA)",
                transformation=(
                    "YoY % = (X_t / X_{t-4} - 1) × 100"
                    if is_yoy
                    else "QoQ % = (X_t / X_{t-1} - 1) × 100"
                ),
                frequency="Quarterly",
                source_id="Eurostat via FRED (CLVMNACSCAB1GQCH)",
                latest_obs=latest_obs,
            )

    with r1_right:
        with st.container(border=True):
            is_yoy = cfg["inflation_view"] == "YoY % Inflation"
            col = "hicp_yoy" if is_yoy else "value"
            valid_hicp = bundle["hicp"].dropna(subset=[col])
            latest_val = valid_hicp.iloc[-1][col] if not valid_hicp.empty else np.nan
            latest_obs = fmt_obs_date(valid_hicp.iloc[-1]["date"], "Monthly") if not valid_hicp.empty else "N/A"
            badge = (
                f"{latest_val:+.2f}%"
                if (is_yoy and pd.notna(latest_val))
                else f"{latest_val:.2f}"
                if pd.notna(latest_val)
                else "N/A"
            )

            render_chart_header(
                title="Headline Inflation (HICP)",
                subtitle="Harmonised Index of Consumer Prices vs. SNB 0%–2% stability band"
                if is_yoy
                else "Harmonised Index of Consumer Prices — Raw Index Level",
                badge_text=badge,
                alert=bool(is_yoy and pd.notna(latest_val) and (latest_val < 0 or latest_val > 2.0)),
            )
            st.plotly_chart(
                build_hicp_chart(hicp_slice, cfg["inflation_view"]),
                use_container_width=True,
                config=PLOTLY_CONFIG,
            )
            render_chart_footer(
                units="Percent (%) YoY" if is_yoy else "Index (2025 = 100), NSA",
                transformation=(
                    "YoY % = (X_t / X_{t-12} - 1) × 100"
                    if is_yoy
                    else "None — Raw Level (Index 2025 = 100)"
                ),
                frequency="Monthly",
                source_id="Eurostat via FRED (CP0000CHM086NEST)",
                latest_obs=latest_obs,
            )

    # Row 2: Unemployment Rate | SNB Policy Rate
    r2_left, r2_right = st.columns(2, gap="medium")

    with r2_left:
        with st.container(border=True):
            valid_u = bundle["unemp"]
            latest_val = valid_u.iloc[-1]["value"] if not valid_u.empty else np.nan
            latest_obs = fmt_obs_date(valid_u.iloc[-1]["date"], "Quarterly") if not valid_u.empty else "N/A"
            badge = f"{latest_val:.2f}%" if pd.notna(latest_val) else "N/A"

            render_chart_header(
                title="Unemployment Rate (Ages 15–74)",
                subtitle="Quarterly labor-force rate with 4-quarter trend smoother",
                badge_text=badge,
            )
            st.plotly_chart(
                build_unemp_chart(unemp_slice),
                use_container_width=True,
                config=PLOTLY_CONFIG,
            )
            render_chart_footer(
                units="Percent of Labor Force (NSA)",
                transformation="Raw Level + 4-Quarter Trailing Moving Average",
                frequency="Quarterly",
                source_id="OECD via FRED (LRUN74TTCHQ156N)",
                latest_obs=latest_obs,
            )

    with r2_right:
        with st.container(border=True):
            valid_snb = bundle["snb_policy"]
            latest_val = valid_snb.iloc[-1]["value"] if not valid_snb.empty else np.nan
            latest_obs = fmt_obs_date(valid_snb.iloc[-1]["date"], "Monthly") if not valid_snb.empty else "N/A"
            badge = f"{latest_val:.2f}%" if pd.notna(latest_val) else "N/A"

            render_chart_header(
                title="SNB Monetary Policy Rate",
                subtitle="Official Policy Rate (Jun 2019–Present) & pre-2019 3M Libor target corridor",
                badge_text=badge,
                alert=bool(pd.notna(latest_val) and latest_val < 0),
            )
            st.plotly_chart(
                build_snb_policy_chart(snb_pol_slice, snb_cor_slice, start_dt, end_dt),
                use_container_width=True,
                config=PLOTLY_CONFIG,
            )
            render_chart_footer(
                units="Percent per annum (End of Month)",
                transformation="None — Raw Policy Rate (LZ) & Target Bounds (UG0–OG0)",
                frequency="Monthly (End of Month)",
                source_id="Swiss National Bank (snboffzisa: LZ, UG0, OG0)",
                latest_obs=latest_obs,
            )

    # Row 3: Swiss Interest Rates & Spread | USD/CHF Spot Rate
    r3_left, r3_right = st.columns(2, gap="medium")

    with r3_left:
        with st.container(border=True):
            valid_rates = bundle["rates"]
            latest_spread = valid_rates.iloc[-1]["spread_bps"] if not valid_rates.empty else np.nan
            latest_obs = fmt_obs_date(valid_rates.iloc[-1]["date"], "Monthly") if not valid_rates.empty else "N/A"
            badge = f"{latest_spread:+.0f} bps" if pd.notna(latest_spread) else "N/A"

            render_chart_header(
                title="Swiss Interest Rates & Yield Curve Spread",
                subtitle="10-Year sovereign yield, 3-month interbank rate, and term spread",
                badge_text=badge,
                alert=bool(pd.notna(latest_spread) and latest_spread < 0),
            )
            st.plotly_chart(
                build_yield_curve_chart(rates_slice, cfg["yield_view"]),
                use_container_width=True,
                config=PLOTLY_CONFIG,
            )
            render_chart_footer(
                units="Rates: % p.a. (NSA) | Spread: Basis Points (bps)",
                transformation="Spread (bps) = (Yield_10Y - Rate_3M) × 100 on matched monthly dates",
                frequency="Monthly",
                source_id="OECD via FRED (IRLTLT01CHM156N, IR3TIB01CHM156N)",
                latest_obs=latest_obs,
            )

    with r3_right:
        with st.container(border=True):
            valid_fx = bundle["fx"]
            latest_val = valid_fx.iloc[-1]["value"] if not valid_fx.empty else np.nan
            latest_obs = fmt_obs_date(valid_fx.iloc[-1]["date"], "Daily") if not valid_fx.empty else "N/A"
            badge = f"{latest_val:.4f} CHF/USD" if pd.notna(latest_val) else "N/A"

            render_chart_header(
                title="USD/CHF Spot Exchange Rate",
                subtitle="Daily noon buying rate in New York with 30-trading-day moving average",
                badge_text=badge,
            )
            st.plotly_chart(
                build_fx_chart(fx_slice),
                use_container_width=True,
                config=PLOTLY_CONFIG,
            )
            render_chart_footer(
                units="CHF per 1 USD (Down = CHF Appreciation), NSA",
                transformation="Raw Daily Spot + 30-Trading-Day Moving Average",
                frequency="Daily (Business Days)",
                source_id="Federal Reserve Board H.10 via FRED (DEXSZUS)",
                latest_obs=latest_obs,
            )


# ---------------------------------------------------------------------------
# Tab 2 — Data Explorer & Export
# ---------------------------------------------------------------------------
def render_tab_explorer(bundle: dict[str, Any], cfg: dict[str, Any], meta_mtime: float) -> None:
    st.markdown('<div class="section-head">Series Inspector & Institutional Data Export</div>', unsafe_allow_html=True)

    explorer_options = {
        "Real GDP (Quarterly — Raw, YoY %, QoQ %)": ("gdp", "gdp_real", "Quarterly"),
        "Headline Inflation / HICP (Monthly — Index, YoY %)": ("hicp", "hicp_index", "Monthly"),
        "Unemployment Rate Ages 15–74 (Quarterly — Raw, 4Q MA)": ("unemp", "unemp_rate", "Quarterly"),
        "SNB Official Policy Rate (Monthly — LZ)": ("snb_policy", "snb_policy_rate", "Monthly"),
        "Swiss Yield Curve & 10Y–3M Spread (Monthly)": ("rates", "yield_10y", "Monthly"),
        "USD/CHF Spot Exchange Rate (Daily — Spot, 30D MA)": ("fx", "usd_chf", "Daily"),
        "SNB Historical 3M Libor Corridor (Monthly — UG0/OG0)": ("snb_corridor", "snb_libor_low", "Monthly"),
    }

    c1, c2, c3 = st.columns([3.2, 1.4, 1.6], gap="medium")
    with c1:
        selected_label = st.selectbox("Select Indicator Dataset", list(explorer_options.keys()))
    with c2:
        scope = st.radio(
            "Row Scope",
            options=["Filtered Sample", "Full History"],
            horizontal=True,
        )
    with c3:
        st.markdown("<div style='height: 1.55rem;'></div>", unsafe_allow_html=True)
        zip_bytes = build_zip_bundle(meta_mtime)
        st.download_button(
            label="Download Full Swiss Macro Bundle (.ZIP)",
            data=zip_bytes,
            file_name="switzerland_macro_bundle.zip",
            mime="application/zip",
            use_container_width=True,
        )

    df_key, spec_key, _ = explorer_options[selected_label]
    full_df = bundle[df_key].copy()
    display_df = (
        slice_by_dates(full_df, cfg["start_dt"], cfg["end_dt"])
        if scope == "Filtered Sample"
        else full_df
    )

    # Rename columns cleanly for institutional display
    rename_map = {
        "date": "Date",
        "value": "Raw Value",
        "gdp_yoy": "GDP YoY (%)",
        "gdp_qoq": "GDP QoQ (%)",
        "hicp_yoy": "HICP YoY (%)",
        "unemp_ma4": "4Q Moving Avg (%)",
        "rate_3m": "3M Interbank (%)",
        "yield_10y": "10Y Sovereign Yield (%)",
        "spread_bps": "10Y–3M Spread (bps)",
        "ma_30d": "30-Trading-Day MA",
        "libor_low": "3M Libor Lower (%)",
        "libor_high": "3M Libor Upper (%)",
    }

    csv_bytes = export_df_csv_bytes(display_df)
    table_df = display_df.sort_values("date", ascending=False).rename(columns=rename_map)

    col_cfg: dict[str, Any] = {
        "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
        "Raw Value": st.column_config.NumberColumn("Raw Value", format="%.4f"),
        "GDP YoY (%)": st.column_config.NumberColumn("GDP YoY (%)", format="%.2f%%"),
        "GDP QoQ (%)": st.column_config.NumberColumn("GDP QoQ (%)", format="%.2f%%"),
        "HICP YoY (%)": st.column_config.NumberColumn("HICP YoY (%)", format="%.2f%%"),
        "4Q Moving Avg (%)": st.column_config.NumberColumn("4Q Moving Avg (%)", format="%.2f%%"),
        "3M Interbank (%)": st.column_config.NumberColumn("3M Interbank (%)", format="%.2f%%"),
        "10Y Sovereign Yield (%)": st.column_config.NumberColumn("10Y Sovereign Yield (%)", format="%.2f%%"),
        "10Y–3M Spread (bps)": st.column_config.NumberColumn("10Y–3M Spread (bps)", format="%+.1f"),
        "30-Trading-Day MA": st.column_config.NumberColumn("30-Trading-Day MA", format="%.4f"),
        "3M Libor Lower (%)": st.column_config.NumberColumn("3M Libor Lower (%)", format="%.2f%%"),
        "3M Libor Upper (%)": st.column_config.NumberColumn("3M Libor Upper (%)", format="%.2f%%"),
    }

    dl_col, info_col = st.columns([1.6, 4.4])
    with dl_col:
        st.download_button(
            label="Download Selected Series (.CSV)",
            data=csv_bytes,
            file_name=f"che_{spec_key}_{scope.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with info_col:
        st.caption(
            f"Showing {len(table_df):,} observations sorted newest-first. "
            "CSV downloads are exported in ascending chronological ISO date order."
        )

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        height=470,
        column_config={k: v for k, v in col_cfg.items() if k in table_df.columns},
    )


# ---------------------------------------------------------------------------
# Tab 3 — Verification & Refresh Log
# ---------------------------------------------------------------------------
def _build_verification_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    meta_series = bundle["metadata"].get("series", {})
    rows: list[dict[str, Any]] = []

    def _latest_transformed(key: str) -> str:
        if key == "gdp_real":
            sub = bundle["gdp"].dropna(subset=["gdp_yoy"])
            return f"{sub.iloc[-1]['gdp_yoy']:+.2f}% YoY" if not sub.empty else "N/A"
        if key == "hicp_index":
            sub = bundle["hicp"].dropna(subset=["hicp_yoy"])
            return f"{sub.iloc[-1]['hicp_yoy']:+.2f}% YoY" if not sub.empty else "N/A"
        if key == "unemp_rate":
            sub = bundle["unemp"].dropna(subset=["unemp_ma4"])
            return f"{sub.iloc[-1]['unemp_ma4']:.2f}% (4Q MA)" if not sub.empty else "N/A"
        if key == "snb_policy_rate":
            return "Raw Level (No Transform)"
        if key in ("rate_3m", "yield_10y"):
            sub = bundle["rates"]
            return f"{sub.iloc[-1]['spread_bps']:+.0f} bps (10Y–3M)" if not sub.empty else "N/A"
        if key == "usd_chf":
            sub = bundle["fx"].dropna(subset=["ma_30d"])
            return f"{sub.iloc[-1]['ma_30d']:.4f} (30D MA)" if not sub.empty else "N/A"
        return "—"

    for key, spec in SERIES_SPECS.items():
        if not spec.get("primary", False):
            continue
        m = meta_series.get(key, {})
        raw_val = m.get("latest_value")
        raw_fmt = f"{raw_val:,.4f}" if isinstance(raw_val, (int, float)) else "N/A"
        rows.append(
            {
                "Indicator": spec["name"],
                "Primary Source": spec["source"],
                "Series ID": spec["series_id"],
                "Frequency": spec["frequency"],
                "Latest Obs. Date": str(m.get("latest_obs_date") or "N/A"),
                "Latest Raw Value": raw_fmt,
                "Latest Transformed Value": _latest_transformed(key),
                "Primary Source URL": spec["source_url"],
            }
        )
    return rows


def _build_verification_markdown(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    lines = [
        "# Switzerland (CHE) Macroeconomic Monitor — Primary Source Verification Log",
        "",
        f"- **Last Successful Refresh (UTC):** {metadata.get('last_successful_refresh_utc', 'N/A')}",
        f"- **Last Successful Refresh (Zurich):** {metadata.get('last_successful_refresh_zurich', 'N/A')}",
        f"- **Trigger:** {metadata.get('trigger', 'N/A')}",
        "",
        "| Indicator | Primary Source | Series ID | Frequency | Latest Obs. Date | Dashboard Raw Value | Dashboard Transformed Value | Official Source URL | Spot-Check Match? |",
        "|---|---|---|---|---|---:|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['Indicator']} | {r['Primary Source']} | `{r['Series ID']}` | "
            f"{r['Frequency']} | `{r['Latest Obs. Date']}` | {r['Latest Raw Value']} | "
            f"{r['Latest Transformed Value']} | [Verify]({r['Primary Source URL']}) | [ ] Confirmed |"
        )
    lines.append("")
    return "\n".join(lines)


def render_tab_verification(bundle: dict[str, Any]) -> None:
    # Section 1 — Primary Source Observation Audit Table
    st.markdown(
        '<div class="section-head">Section 1 — Primary Source Observation Audit Table (7 Core Series)</div>',
        unsafe_allow_html=True,
    )
    audit_rows = _build_verification_rows(bundle)
    audit_df = pd.DataFrame(audit_rows)

    st.dataframe(
        audit_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Primary Source URL": st.column_config.LinkColumn(
                "Verification Link",
                display_text="Verify Source",
            ),
            "Latest Obs. Date": st.column_config.TextColumn("Latest Obs. Date"),
        },
    )

    md_template = _build_verification_markdown(audit_rows, bundle["metadata"])
    st.download_button(
        label="Download Verification Template (.MD)",
        data=md_template.encode("utf-8"),
        file_name="switzerland_source_verification.md",
        mime="text/markdown",
    )

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

    # Section 2 — Automated Refresh Execution Log
    st.markdown(
        '<div class="section-head">Section 2 — Automated Refresh Execution Log</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="info-callout">
            <strong>Audit Interpretation:</strong> A refresh entry with <code>status = success</code> and
            <code>any_new_data = False</code> confirms healthy automated pipeline execution when primary
            statistical agencies (SNB, Eurostat, OECD, Federal Reserve) have not yet published a newer observation
            since the preceding run.
        </div>
        """,
        unsafe_allow_html=True,
    )

    log_df = bundle["log_df"].copy()
    if not log_df.empty:
        log_display = log_df.iloc[::-1].reset_index(drop=True)
        st.dataframe(
            log_display,
            use_container_width=True,
            hide_index=True,
            height=280,
            column_config={
                "refresh_timestamp_utc": st.column_config.TextColumn("UTC Timestamp"),
                "refresh_timestamp_zurich": st.column_config.TextColumn("Zurich Timestamp"),
                "trigger": st.column_config.TextColumn("Trigger"),
                "series_succeeded": st.column_config.NumberColumn("Succeeded", format="%d"),
                "series_failed": st.column_config.NumberColumn("Failed", format="%d"),
                "any_new_data": st.column_config.CheckboxColumn("New Data?"),
                "status": st.column_config.TextColumn("Status"),
                "notes": st.column_config.TextColumn("Audit Notes"),
            },
        )
    else:
        st.info("No refresh log entries found yet.")

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

    # Section 3 — Methodology & Transformation Equations
    st.markdown(
        '<div class="section-head">Section 3 — Methodology & Transformation Equations</div>',
        unsafe_allow_html=True,
    )
    m_left, m_right = st.columns(2, gap="medium")
    with m_left:
        st.markdown("**1. Real GDP Growth (Quarterly — Compute-Before-Slice)**")
        st.latex(r"\text{GDP YoY}_t = \left(\frac{Y_t}{Y_{t-4}} - 1\right) \times 100 \qquad \text{GDP QoQ}_t = \left(\frac{Y_t}{Y_{t-1}} - 1\right) \times 100")

        st.markdown("**2. Headline HICP Inflation (Monthly)**")
        st.latex(r"\pi_t^{\text{YoY}} = \left(\frac{\text{HICP}_t}{\text{HICP}_{t-12}} - 1\right) \times 100")

        st.markdown("**3. Unemployment Trend Smoother (Quarterly, Ages 15–74)**")
        st.latex(r"\overline{U}_t^{(4Q)} = \frac{1}{4}\sum_{k=0}^{3} U_{t-k}")

    with m_right:
        st.markdown("**4. Sovereign Term Spread (Monthly, Matched Dates)**")
        st.latex(r"\text{Spread}_t\ (\text{bps}) = \left(y_t^{10\text{Y}} - r_t^{3\text{M}}\right) \times 100")

        st.markdown("**5. USD/CHF Moving Average & Quotation Convention**")
        st.latex(r"\overline{\text{FX}}_t^{(30\text{D})} = \frac{1}{30}\sum_{k=0}^{29} \text{FX}_{t-k}")
        st.caption(
            "Convention: DEXSZUS is quoted as Swiss Francs per 1 U.S. Dollar (CHF/USD). "
            "A declining series reflects Swiss franc appreciation against the U.S. dollar."
        )

        st.markdown("**6. SNB Policy Regime Transition (June 13, 2019)**")
        st.caption(
            "Prior to June 2019, the SNB steered monetary policy via a target range for the 3-month CHF Libor "
            "(SNB cube snboffzisa dimensions UG0 and OG0). Effective June 13, 2019, the SNB replaced the Libor "
            "corridor with a single official SNB Policy Rate (dimension LZ)."
        )


# ---------------------------------------------------------------------------
# Main Application Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    inject_institutional_css()
    ensure_initialized()

    if "refresh_toast" in st.session_state:
        st.toast(st.session_state.pop("refresh_toast"))

    meta_mtime = get_metadata_mtime()
    bundle = load_macro_bundle(meta_mtime)

    cfg = render_sidebar(bundle)
    render_header(bundle["metadata"])
    render_kpi_strip(bundle)

    tab_dash, tab_explorer, tab_verify = st.tabs(
        [
            "Executive Macro Dashboard",
            "Data Explorer & Export",
            "Verification & Refresh Log",
        ]
    )

    with tab_dash:
        render_tab_dashboard(bundle, cfg)
    with tab_explorer:
        render_tab_explorer(bundle, cfg, meta_mtime)
    with tab_verify:
        render_tab_verification(bundle)


if __name__ == "__main__":
    main()
