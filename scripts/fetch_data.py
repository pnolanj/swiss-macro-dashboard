"""Fault-tolerant, keyless macroeconomic data ingestion pipeline for Switzerland (CHE).

Fetches 7 primary macroeconomic series plus 2 historical SNB corridor series from
official public CSV endpoints (FRED and SNB), validates and normalizes schemas,
persists atomically with SHA-256 change detection, and writes structured audit logs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SERIES_DIR = DATA_DIR / "series"
METADATA_PATH = DATA_DIR / "refresh_metadata.json"
LOG_PATH = DATA_DIR / "refresh_log.csv"

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
SNB_CSV_URL = "https://data.snb.ch/api/cube/snboffzisa/data/csv/en"

REQUEST_TIMEOUT_SEC = 20
MAX_LOG_ROWS = 200
USER_AGENT = "SwitzerlandMacroMonitor/1.0 (Institutional Research; +https://github.com)"

LOG_COLUMNS = [
    "refresh_timestamp_utc",
    "refresh_timestamp_zurich",
    "trigger",
    "series_succeeded",
    "series_failed",
    "any_new_data",
    "status",
    "notes",
]

SERIES_SPECS: dict[str, dict[str, Any]] = {
    "gdp_real": {
        "name": "Real GDP",
        "provider": "fred",
        "series_id": "CLVMNACSCAB1GQCH",
        "source": "Eurostat via FRED",
        "frequency": "Quarterly",
        "units": "Millions of Chained 2010 Euros, Seasonally Adjusted",
        "source_url": "https://fred.stlouisfed.org/series/CLVMNACSCAB1GQCH",
        "primary": True,
    },
    "hicp_index": {
        "name": "Headline Inflation (HICP)",
        "provider": "fred",
        "series_id": "CP0000CHM086NEST",
        "source": "Eurostat via FRED",
        "frequency": "Monthly",
        "units": "Index 2025 = 100, Not Seasonally Adjusted",
        "source_url": "https://fred.stlouisfed.org/series/CP0000CHM086NEST",
        "primary": True,
    },
    "unemp_rate": {
        "name": "Unemployment Rate (Ages 15–74)",
        "provider": "fred",
        "series_id": "LRUN74TTCHQ156N",
        "source": "OECD via FRED",
        "frequency": "Quarterly",
        "units": "Percent of Labor Force, Not Seasonally Adjusted",
        "source_url": "https://fred.stlouisfed.org/series/LRUN74TTCHQ156N",
        "primary": True,
    },
    "snb_policy_rate": {
        "name": "SNB Official Policy Rate",
        "provider": "snb",
        "series_id": "snboffzisa (D0=LZ)",
        "snb_d0": "LZ",
        "source": "Swiss National Bank (data.snb.ch)",
        "frequency": "Monthly (End of Month)",
        "units": "Percent per annum",
        "source_url": "https://data.snb.ch/en/topics/snb/cube/snboffzisa?dimSel=D0(LZ)",
        "primary": True,
    },
    "snb_libor_low": {
        "name": "SNB 3M CHF Libor Target Range (Lower)",
        "provider": "snb",
        "series_id": "snboffzisa (D0=UG0)",
        "snb_d0": "UG0",
        "source": "Swiss National Bank (data.snb.ch)",
        "frequency": "Monthly (End of Month)",
        "units": "Percent per annum",
        "source_url": "https://data.snb.ch/en/topics/snb/cube/snboffzisa?dimSel=D0(UG0)",
        "primary": False,
    },
    "snb_libor_high": {
        "name": "SNB 3M CHF Libor Target Range (Upper)",
        "provider": "snb",
        "series_id": "snboffzisa (D0=OG0)",
        "snb_d0": "OG0",
        "source": "Swiss National Bank (data.snb.ch)",
        "frequency": "Monthly (End of Month)",
        "units": "Percent per annum",
        "source_url": "https://data.snb.ch/en/topics/snb/cube/snboffzisa?dimSel=D0(OG0)",
        "primary": False,
    },
    "rate_3m": {
        "name": "3-Month Interbank Rate",
        "provider": "fred",
        "series_id": "IR3TIB01CHM156N",
        "source": "OECD via FRED",
        "frequency": "Monthly",
        "units": "Percent per annum, Not Seasonally Adjusted",
        "source_url": "https://fred.stlouisfed.org/series/IR3TIB01CHM156N",
        "primary": True,
    },
    "yield_10y": {
        "name": "10-Year Swiss Government Bond Yield",
        "provider": "fred",
        "series_id": "IRLTLT01CHM156N",
        "source": "OECD via FRED",
        "frequency": "Monthly",
        "units": "Percent per annum, Not Seasonally Adjusted",
        "source_url": "https://fred.stlouisfed.org/series/IRLTLT01CHM156N",
        "primary": True,
    },
    "usd_chf": {
        "name": "USD/CHF Spot Exchange Rate",
        "provider": "fred",
        "series_id": "DEXSZUS",
        "source": "Board of Governors of the Federal Reserve System (H.10) via FRED",
        "frequency": "Daily (Business Days)",
        "units": "Swiss Francs per 1 U.S. Dollar (CHF/USD), Not Seasonally Adjusted",
        "source_url": "https://fred.stlouisfed.org/series/DEXSZUS",
        "primary": True,
    },
}


def build_http_session() -> requests.Session:
    """Create a shared HTTP session with retry and exponential backoff."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/csv,text/plain,*/*;q=0.8",
        }
    )
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _format_numeric(val: float) -> str:
    """Deterministic decimal string formatting without scientific notation."""
    if abs(val) < 1e-12:
        return "0"
    formatted = f"{val:.6f}".rstrip("0").rstrip(".")
    return formatted if formatted not in ("", "-0") else "0"


def _normalize_series_df(df: pd.DataFrame) -> pd.DataFrame:
    """Enforce strict (date, value) schema sorted ascending, deduplicated, finite."""
    out = df.copy()
    out["date"] = out["date"].astype(str).str.strip()
    # Normalize YYYY-MM to YYYY-MM-01 consistently
    out["date"] = out["date"].str.replace(
        r"^(\d{4}-\d{2})$", r"\1-01", regex=True
    )
    out["date"] = pd.to_datetime(out["date"], errors="coerce")

    out["value"] = (
        out["value"]
        .astype(str)
        .str.strip()
        .replace({"": np.nan, ".": np.nan, "NA": np.nan, "NaN": np.nan, "null": np.nan})
    )
    out["value"] = pd.to_numeric(out["value"], errors="coerce")

    out = out.dropna(subset=["date", "value"])
    out = out[np.isfinite(out["value"].to_numpy(dtype=float))]
    out = out.sort_values("date", ascending=True)
    out = out.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    if out.empty:
        raise ValueError("Parsed series contains zero valid numeric observations.")
    return out[["date", "value"]]


def fetch_fred_series(session: requests.Session, series_id: str) -> pd.DataFrame:
    """Fetch and parse a FRED CSV endpoint (handles both DATE and observation_date headers)."""
    url = FRED_CSV_URL.format(series_id=series_id)
    resp = session.get(url, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()

    raw_text = resp.content.decode("utf-8-sig", errors="replace")
    df = pd.read_csv(io.StringIO(raw_text), dtype=str)
    if df.shape[1] < 2:
        raise ValueError(f"FRED CSV for {series_id} has fewer than 2 columns.")

    df = df.iloc[:, [0, 1]].copy()
    df.columns = ["date", "value"]
    return _normalize_series_df(df)


def fetch_snb_cube(session: requests.Session) -> pd.DataFrame:
    """Fetch and parse the SNB snboffzisa semicolon-delimited CSV with dynamic header scan."""
    resp = session.get(SNB_CSV_URL, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()

    raw_text = resp.content.decode("utf-8-sig", errors="replace")
    lines = raw_text.splitlines()

    header_idx: int | None = None
    for idx, line in enumerate(lines):
        cleaned_tokens = [
            tok.strip().strip('"').strip("'").lstrip("\ufeff").lower()
            for tok in line.split(";")
        ]
        if "date" in cleaned_tokens and "value" in cleaned_tokens:
            header_idx = idx
            break

    if header_idx is None:
        raise ValueError("Unable to locate 'Date'/'Value' header row in SNB CSV payload.")

    csv_body = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(csv_body), sep=";", dtype=str)
    col_map: dict[str, str] = {}
    for col in df.columns:
        norm = str(col).strip().strip('"').strip("'").lstrip("\ufeff").lower()
        if norm == "date":
            col_map[col] = "date"
        elif norm == "d0":
            col_map[col] = "d0"
        elif norm == "value":
            col_map[col] = "value"

    df = df.rename(columns=col_map)
    required = {"date", "d0", "value"}
    if not required.issubset(df.columns):
        raise ValueError(f"SNB CSV missing expected columns {required - set(df.columns)}.")

    df["d0"] = df["d0"].astype(str).str.strip().str.strip('"')
    return df[["date", "d0", "value"]]


def extract_snb_series(cube_df: pd.DataFrame, d0_code: str) -> pd.DataFrame:
    """Filter an already-fetched SNB cube by D0 code and normalize to date,value."""
    sub = cube_df.loc[cube_df["d0"] == d0_code, ["date", "value"]].copy()
    if sub.empty:
        raise ValueError(f"No SNB observations found for D0={d0_code}.")
    return _normalize_series_df(sub)


def _serialize_series_csv(df: pd.DataFrame) -> str:
    """Serialize normalized DataFrame to deterministic LF-terminated CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["date", "value"])
    for date_str, val in zip(df["date"], df["value"]):
        writer.writerow([date_str, _format_numeric(float(val))])
    return buf.getvalue()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_write_bytes(target_path: Path, payload: bytes) -> None:
    """Write bytes to a sibling temporary file and atomically replace target_path."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.tmp")
    with open(tmp_path, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, target_path)


def _persist_series_atomic(series_key: str, df: pd.DataFrame) -> bool:
    """Persist series CSV atomically; return True iff file content changed."""
    target_path = SERIES_DIR / f"{series_key}.csv"
    new_bytes = _serialize_series_csv(df).encode("utf-8")
    new_hash = _sha256_bytes(new_bytes)

    old_hash: str | None = None
    if target_path.exists():
        old_hash = _sha256_bytes(target_path.read_bytes())

    data_changed = old_hash != new_hash
    if data_changed or not target_path.exists():
        _atomic_write_bytes(target_path, new_bytes)
    return data_changed


def _extract_stats_from_df(df: pd.DataFrame) -> dict[str, Any]:
    """Compute observation summary statistics from a normalized DataFrame."""
    latest_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) >= 2 else None
    return {
        "first_obs_date": str(df.iloc[0]["date"]),
        "latest_obs_date": str(latest_row["date"]),
        "latest_value": float(latest_row["value"]),
        "prev_obs_date": str(prev_row["date"]) if prev_row is not None else None,
        "prev_value": float(prev_row["value"]) if prev_row is not None else None,
        "row_count": int(len(df)),
    }


def _read_existing_series_stats(series_key: str) -> dict[str, Any]:
    """Read last-known-good CSV stats if a series fails during refresh."""
    path = SERIES_DIR / f"{series_key}.csv"
    if not path.exists():
        return {
            "first_obs_date": None,
            "latest_obs_date": None,
            "latest_value": None,
            "prev_obs_date": None,
            "prev_value": None,
            "row_count": 0,
        }
    try:
        existing_df = pd.read_csv(path)
        if existing_df.empty:
            raise ValueError("Empty existing CSV")
        return _extract_stats_from_df(existing_df)
    except Exception:
        return {
            "first_obs_date": None,
            "latest_obs_date": None,
            "latest_value": None,
            "prev_obs_date": None,
            "prev_value": None,
            "row_count": 0,
        }


def _load_existing_metadata() -> dict[str, Any]:
    if not METADATA_PATH.exists():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _append_refresh_log(row: dict[str, Any]) -> None:
    """Append one execution row to data/refresh_log.csv and cap at MAX_LOG_ROWS."""
    existing_rows: list[dict[str, str]] = []
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH, "r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for r in reader:
                    existing_rows.append({col: r.get(col, "") for col in LOG_COLUMNS})
        except Exception:
            existing_rows = []

    formatted_row = {col: str(row.get(col, "")) for col in LOG_COLUMNS}
    existing_rows.append(formatted_row)
    trimmed_rows = existing_rows[-MAX_LOG_ROWS:]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=LOG_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(trimmed_rows)
    _atomic_write_bytes(LOG_PATH, buf.getvalue().encode("utf-8"))


def _format_audit_table(metadata: dict[str, Any]) -> str:
    """Render a crisp ASCII audit table for stdout / GitHub Actions logs."""
    headers = ["Series Key", "Latest Obs Date", "Latest Value", "Rows", "Changed?", "Status"]
    rows: list[list[str]] = []

    for key, info in metadata["series"].items():
        latest_val = info.get("latest_value")
        val_str = f"{latest_val:.4f}" if isinstance(latest_val, (int, float)) else "N/A"
        rows.append(
            [
                key,
                str(info.get("latest_obs_date") or "N/A"),
                val_str,
                str(info.get("row_count", 0)),
                "Yes" if info.get("data_changed") else "No",
                str(info.get("status", "unknown")).upper(),
            ]
        )

    col_widths = [
        max(len(headers[i]), max((len(r[i]) for r in rows), default=0))
        for i in range(len(headers))
    ]
    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_line = "| " + " | ".join(headers[i].ljust(col_widths[i]) for i in range(len(headers))) + " |"

    lines = [
        "",
        f"SWITZERLAND MACRO REFRESH AUDIT  |  Trigger: {metadata['trigger']}",
        f"Attempt UTC: {metadata['last_attempt_utc']}  |  Zurich: {metadata['last_attempt_zurich']}",
        f"Succeeded: {metadata['series_succeeded']}  |  Failed: {metadata['series_failed']}  |  New Data: {metadata['any_new_data']}",
        sep,
        header_line,
        sep,
    ]
    for r in rows:
        aligned = [
            r[0].ljust(col_widths[0]),
            r[1].ljust(col_widths[1]),
            r[2].rjust(col_widths[2]),
            r[3].rjust(col_widths[3]),
            r[4].ljust(col_widths[4]),
            r[5].ljust(col_widths[5]),
        ]
        lines.append("| " + " | ".join(aligned) + " |")
    lines.append(sep)
    lines.append("")
    return "\n".join(lines)


def _current_timestamps() -> tuple[str, str]:
    now_utc = datetime.now(timezone.utc)
    utc_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        now_zurich = now_utc.astimezone(ZoneInfo("Europe/Zurich"))
        zurich_str = now_zurich.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        zurich_str = utc_str
    return utc_str, zurich_str


def run_refresh(trigger: str = "local_cli", print_table: bool = True) -> dict[str, Any]:
    """Execute full ingestion, atomic persistence, metadata generation, and audit logging."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SERIES_DIR.mkdir(parents=True, exist_ok=True)

    prev_metadata = _load_existing_metadata()
    session = build_http_session()

    attempt_utc, attempt_zurich = _current_timestamps()
    series_results: dict[str, dict[str, Any]] = {}
    series_succeeded = 0
    series_failed = 0
    any_new_data = False
    error_notes: list[str] = []

    # Fetch SNB cube once for all three SNB series (LZ, UG0, OG0)
    snb_cube_df: pd.DataFrame | None = None
    snb_cube_error: str | None = None
    try:
        snb_cube_df = fetch_snb_cube(session)
    except Exception as exc:
        snb_cube_error = f"SNB cube fetch failed: {exc}"

    for key, spec in SERIES_SPECS.items():
        base_entry: dict[str, Any] = {
            "name": spec["name"],
            "source": spec["source"],
            "series_id": spec["series_id"],
            "frequency": spec["frequency"],
            "units": spec["units"],
            "source_url": spec["source_url"],
            "primary": bool(spec["primary"]),
        }
        try:
            if spec["provider"] == "fred":
                df = fetch_fred_series(session, spec["series_id"])
            elif spec["provider"] == "snb":
                if snb_cube_df is None:
                    raise RuntimeError(snb_cube_error or "SNB cube unavailable")
                df = extract_snb_series(snb_cube_df, spec["snb_d0"])
            else:
                raise ValueError(f"Unsupported provider: {spec['provider']}")

            data_changed = _persist_series_atomic(key, df)
            stats = _extract_stats_from_df(df)
            series_results[key] = {
                **base_entry,
                **stats,
                "status": "ok",
                "error_message": None,
                "data_changed": data_changed,
            }
            series_succeeded += 1
            if data_changed:
                any_new_data = True

        except Exception as exc:
            err_msg = re.sub(r"\s+", " ", str(exc)).strip()
            fallback_stats = _read_existing_series_stats(key)
            series_results[key] = {
                **base_entry,
                **fallback_stats,
                "status": "error",
                "error_message": err_msg,
                "data_changed": False,
            }
            series_failed += 1
            error_notes.append(f"{key}: {err_msg}")

    all_ok = series_failed == 0
    if all_ok:
        last_success_utc = attempt_utc
        last_success_zurich = attempt_zurich
        run_status = "success"
    elif series_succeeded > 0:
        last_success_utc = prev_metadata.get("last_successful_refresh_utc") or attempt_utc
        last_success_zurich = prev_metadata.get("last_successful_refresh_zurich") or attempt_zurich
        run_status = "partial_failure"
    else:
        last_success_utc = prev_metadata.get("last_successful_refresh_utc") or "Never"
        last_success_zurich = prev_metadata.get("last_successful_refresh_zurich") or "Never"
        run_status = "failed"

    notes = (
        "All series refreshed cleanly; new observations persisted."
        if all_ok and any_new_data
        else "All series refreshed cleanly; no new upstream observations."
        if all_ok
        else "; ".join(error_notes)
    )

    metadata: dict[str, Any] = {
        "last_successful_refresh_utc": last_success_utc,
        "last_successful_refresh_zurich": last_success_zurich,
        "last_attempt_utc": attempt_utc,
        "last_attempt_zurich": attempt_zurich,
        "trigger": trigger,
        "status": run_status,
        "series_succeeded": series_succeeded,
        "series_failed": series_failed,
        "any_new_data": any_new_data,
        "series": series_results,
    }

    _atomic_write_bytes(
        METADATA_PATH,
        (json.dumps(metadata, indent=2, sort_keys=False) + "\n").encode("utf-8"),
    )

    _append_refresh_log(
        {
            "refresh_timestamp_utc": attempt_utc,
            "refresh_timestamp_zurich": attempt_zurich,
            "trigger": trigger,
            "series_succeeded": series_succeeded,
            "series_failed": series_failed,
            "any_new_data": any_new_data,
            "status": run_status,
            "notes": notes,
        }
    )

    if print_table:
        print(_format_audit_table(metadata))

    return metadata


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh Switzerland (CHE) macroeconomic CSV datasets from FRED and SNB."
    )
    parser.add_argument(
        "--trigger",
        choices=["github_actions", "manual_ui", "local_cli"],
        default="local_cli",
        help="Execution trigger label recorded in refresh_metadata.json and refresh_log.csv.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    result = run_refresh(trigger=args.trigger, print_table=True)
    return 0 if result["series_succeeded"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
