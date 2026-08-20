"""Australian economic driver adapters.

Official-source series for revenue, wage, financing and sensitivity
models. Two mechanisms:

- **RBA statistical tables** (no key): cash rate target (F1) and
  exchange rates (F11.1) as CSV downloads. Snapshot to disk with
  provenance metadata so a forecast stays reproducible after the RBA
  revises or republishes a series.
- **ABS Indicator API** (key required): CPI, WPI, retail trade, labour
  force and other headline releases. Key comes from the host
  environment variable ``ABS_API_KEY`` (request one from
  api.data@abs.gov.au); never committed.

Both parse into a common ``DriverSeries``: a monthly or quarterly
pandas Series carrying provenance (source_url, retrieved date, series
id). Snapshots are the auditable record; re-fetching replaces nothing
without an explicit new snapshot file.
"""

from __future__ import annotations

import io
import json
import os
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

RBA_BASE = "https://www.rba.gov.au/statistics/tables/csv"
ABS_BASE = "https://indicator.api.abs.gov.au/v1"

# RBA table F1 (interest rates) / F11.1 (exchange rates) series ids,
# read from the tables' own "Series ID" metadata rows.
RBA_SERIES = {
    "cash_rate_target": ("f1-data.csv", "FIRMMCRTD"),
    "aud_usd": ("f11.1-data.csv", "FXRUSD"),
    "twi": ("f11.1-data.csv", "FXRTWI"),
}

# ABS Indicator API dataflow identifiers for the headline series useful
# in FP&A driver models. Keys map to ABS dataflow ids.
ABS_DATAFLOWS = {
    "cpi_monthly": "CPI_M",
    "cpi_quarterly": "CPI_H",
    "wpi": "WPI",
    "retail_trade": "RT",
    "labour_force": "LF",
}

_UA = "FireFalcon-au (github.com/ryanduguid/FireFalcon)"


class DriverSeries(BaseModel):
    """One fetched series with provenance."""

    name: str
    source: str  # 'rba' | 'abs'
    source_url: str
    series_id: str
    retrieved: date
    units: str = ""
    frequency: str = ""
    data: dict[str, float] = Field(default_factory=dict)  # {period: value}

    def to_series(self) -> pd.Series:
        """Series indexed by PeriodIndex (M or Q as recorded)."""
        freq = "Q" if self.frequency.startswith("Q") else "M"
        idx = pd.PeriodIndex(list(self.data), freq=freq)
        return pd.Series(list(self.data.values()), index=idx, name=self.name)


def _fetch(url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_rba_series(name: str) -> DriverSeries:
    """Fetch one RBA driver series by its key in ``RBA_SERIES``."""
    if name not in RBA_SERIES:
        raise ValueError(f"unknown RBA series {name!r}; expected one of {sorted(RBA_SERIES)}")
    table_csv, series_id = RBA_SERIES[name]
    url = f"{RBA_BASE}/{table_csv}"
    raw = _fetch(url).decode("utf-8-sig")
    lines = raw.splitlines()
    # First line is a ragged table title; the machine-readable block
    # starts at the 'Title' metadata row and includes the metadata rows
    # (Description, Frequency, Units, Source, Publication date,
    # 'Series ID') followed by dd-Mon-yyyy data rows.
    start = next(i for i, line in enumerate(lines) if line.startswith("Title,"))
    frame = pd.read_csv(io.StringIO("\n".join(lines[start:])), header=None, dtype=str)

    header_row = frame.index[frame[0] == "Series ID"]
    if header_row.empty:
        raise ValueError(f"no 'Series ID' metadata row in {table_csv}")
    ids = frame.loc[header_row[0]]
    try:
        col = ids[ids == series_id].index[0]
    except IndexError as e:
        raise ValueError(f"series id {series_id} not present in {table_csv}") from e

    units = ""
    freq = ""
    units_row = frame.index[frame[0] == "Units"]
    if not units_row.empty:
        units = str(frame.loc[units_row[0], col])
    freq_row = frame.index[frame[0] == "Frequency"]
    if not freq_row.empty:
        freq = str(frame.loc[freq_row[0], col])

    data: dict[str, float] = {}
    for i in range(header_row[0] + 1, len(frame)):
        raw_date = str(frame.iloc[i, 0]).strip()
        raw_val = str(frame.iloc[i, col]).strip()
        if not raw_date or raw_date == "nan" or raw_val in ("", "nan"):
            continue
        try:
            period = pd.Period(pd.Timestamp(raw_date), freq="M")
            data[str(period)] = float(raw_val)
        except (ValueError, TypeError):
            continue

    return DriverSeries(
        name=name,
        source="rba",
        source_url=url,
        series_id=series_id,
        retrieved=date.today(),
        units=units,
        frequency="M",
        data=data,
    )


def fetch_abs_series(name: str, api_key: str | None = None) -> DriverSeries:
    """Fetch one ABS Indicator API dataflow as a DriverSeries.

    Key resolution: explicit `api_key` argument, else ``ABS_API_KEY``
    environment variable. Raises RuntimeError when neither exists.
    """
    if name not in ABS_DATAFLOWS:
        raise ValueError(f"unknown ABS dataflow {name!r}; expected one of {sorted(ABS_DATAFLOWS)}")
    key = api_key or os.environ.get("ABS_API_KEY")
    if not key:
        raise RuntimeError(
            "ABS Indicator API requires a key: set ABS_API_KEY in the host "
            "environment (request from api.data@abs.gov.au). Never commit it."
        )
    dataflow = ABS_DATAFLOWS[name]
    url = f"{ABS_BASE}/data/{dataflow}/csv"
    raw = _fetch(url, headers={"x-api-key": key}).decode("utf-8-sig")
    frame = pd.read_csv(io.StringIO(raw), dtype=str)

    # SDMX-CSV shape varies per dataflow; locate the time + observation
    # columns by their standard names.
    time_col = next((c for c in frame.columns if c.upper() in ("TIME_PERIOD", "TIME")), None)
    obs_col = next((c for c in frame.columns if c.upper() == "OBS_VALUE"), None)
    if time_col is None or obs_col is None:
        raise ValueError(
            f"unexpected SDMX-CSV shape for {dataflow}: columns {list(frame.columns)}"
        )
    data: dict[str, float] = {}
    for _, row in frame.iterrows():
        period_raw = str(row[time_col]).strip()
        value_raw = str(row[obs_col]).strip()
        if not period_raw or value_raw in ("", "nan"):
            continue
        try:
            freq = "Q" if "Q" in period_raw else "M"
            data[str(pd.Period(period_raw, freq=freq))] = float(value_raw)
        except (ValueError, TypeError):
            continue
    frequency = "Q" if any("Q" in k for k in data) else "M"

    return DriverSeries(
        name=name,
        source="abs",
        source_url=url,
        series_id=dataflow,
        retrieved=date.today(),
        frequency=frequency,
        data=data,
    )


def save_snapshot(series: DriverSeries, directory: str | Path) -> Path:
    """Persist a series snapshot with provenance as JSON.

    Filename: ``<source>_<name>_<retrieved>.json``. Never overwrites an
    existing snapshot; the same day re-fetch appends a counter.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    base = f"{series.source}_{series.name}_{series.retrieved.isoformat()}"
    path = directory / f"{base}.json"
    counter = 1
    while path.exists():
        path = directory / f"{base}_{counter}.json"
        counter += 1
    path.write_text(json.dumps(series.model_dump(mode="json"), indent=2))
    return path


def load_snapshot(path: str | Path) -> DriverSeries:
    """Reload a snapshot, preserving its recorded retrieved date."""
    return DriverSeries.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
