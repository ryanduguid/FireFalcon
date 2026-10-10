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
from datetime import UTC, date, datetime
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

# ABS Indicator API dataflow identifiers for the headline series useful in FP&A
# driver models, with the frequency each key promises. Indicator API ids carry
# the _H suffix; the unsuffixed forms (CPI, WPI, RT, LF) belong to the separate
# Data API. Checked against the dataflowId enum in the ABS Indicator API
# description and the ABS Data API user guide updates on 13 September 2026:
# https://raw.githubusercontent.com/apigovau/api-descriptions/master/abs/indicator.openapi.yaml
# https://www.abs.gov.au/statistics/application-programming-interfaces-apis/data-api-user-guide/updates
#
# CPI_H became monthly in November 2025, when CPI_M and CPI_M_H ceased;
# quarterly CPI returned as CPI_Q_H in April 2026. Retail Trade ceased with the
# June 2025 period: RT_H is history, not a live driver. The Monthly Household
# Spending Indicator (HSI_M_H) is the ABS replacement publication, but it
# measures household spending rather than retail turnover, so it is not mapped
# here as a substitute.
ABS_DATAFLOWS = {
    "cpi_monthly": "CPI_H",
    "cpi_quarterly": "CPI_Q_H",
    "wpi": "WPI_H",
    "retail_trade": "RT_H",
    "labour_force": "LF_H",
}

# Expected observation frequency per key, so a monthly dataflow cannot be
# returned under a quarterly name (or the reverse).
ABS_FREQUENCIES = {
    "cpi_monthly": "M",
    "cpi_quarterly": "Q",
    "wpi": "Q",
    "retail_trade": "M",
    "labour_force": "M",
}

# Retail Trade, Australia ceased with the June 2025 period and RT_H is no longer
# updated: treat retail_trade as history, and assess the Monthly Household Spending
# Indicator separately, since it measures a different concept.

_UA = "au-fpa-pack (github.com/ryanduguid/au-fpa-pack)"


class DriverSeries(BaseModel):
    """One fetched series with provenance."""

    name: str
    source: str  # 'rba' | 'abs'
    source_url: str
    series_id: str
    retrieved: date  # UTC fetch date, so provenance does not vary by machine
    units: str = ""
    frequency: str = ""
    dimensions: dict[str, str] = Field(default_factory=dict)
    data: dict[str, float] = Field(default_factory=dict)  # {period: value}

    def to_series(self) -> pd.Series:
        """Series indexed by PeriodIndex (M or Q as recorded)."""
        freq = "Q" if self.frequency.startswith("Q") else "M"
        idx = pd.PeriodIndex(list(self.data), freq=freq)
        return pd.Series(list(self.data.values()), index=idx, name=self.name)


def _fetch(url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body: bytes = resp.read()
    return body


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
    units_row = frame.index[frame[0] == "Units"]
    if not units_row.empty:
        units = str(frame.loc[units_row[0], col])

    observations: dict[date, float] = {}
    for i in range(header_row[0] + 1, len(frame)):
        raw_date = str(frame.iloc[i, 0]).strip()
        raw_val = str(frame.iloc[i, col]).strip()
        if not raw_date or raw_date == "nan" or raw_val in ("", "nan"):
            continue
        try:
            source_date = pd.Timestamp(raw_date).date()
            value = float(raw_val)
        except (ValueError, TypeError):
            continue

        if source_date in observations and observations[source_date] != value:
            raise ValueError(
                f"conflicting observations for {series_id} on {source_date.isoformat()}"
            )
        observations[source_date] = value

    data: dict[str, float] = {}
    for source_date in sorted(observations):
        data[str(pd.Period(source_date, freq="M"))] = observations[source_date]

    return DriverSeries(
        name=name,
        source="rba",
        source_url=url,
        series_id=series_id,
        retrieved=datetime.now(tz=UTC).date(),
        units=units,
        frequency="M",
        data=data,
    )


def fetch_abs_series(
    name: str, *, dimensions: dict[str, str] | None = None,
) -> DriverSeries:
    """Fetch one ABS Indicator API dataflow as a DriverSeries.

    The key comes from ``ABS_API_KEY`` in the host environment and nowhere else,
    as skills/fpa-au-drivers/SKILL.md requires: no key handling in code, full
    stop. There is deliberately no argument for it, so no caller can route a
    credential through source or configuration. Raises RuntimeError when it is
    unset. Filter dimension columns explicitly when a dataflow contains multiple
    series. Duplicate periods are rejected, never resolved by row order.
    """
    if name not in ABS_DATAFLOWS:
        raise ValueError(f"unknown ABS dataflow {name!r}; expected one of {sorted(ABS_DATAFLOWS)}")
    key = os.environ.get("ABS_API_KEY")
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
    selection = dict(dimensions or {})
    for column, dimension_value in selection.items():
        if column not in frame.columns or column in (time_col, obs_col):
            raise ValueError(f"unknown ABS dimension {column!r}")
        frame = frame.loc[frame[column] == dimension_value]
    unit_col = next((c for c in frame.columns if c.upper() in ("UNIT_MEASURE", "UNIT")), None)
    units = frame[unit_col].dropna().unique().tolist() if unit_col else []
    if len(units) > 1:
        raise ValueError("ambiguous ABS units; select a single series with dimensions")
    # Observation attributes may change over time within one series.
    dimension_columns = [
        column for column in frame.columns
        if column != time_col and not column.upper().startswith("OBS_")
    ]
    if dimension_columns and len(frame[dimension_columns].drop_duplicates()) > 1:
        raise ValueError("ambiguous ABS dimensions; select a single series with dimensions")
    # Every observation must carry the frequency the key promises. Judging the
    # aggregate let a quarterly response smuggle in a monthly period, which
    # to_series() then folded into the same quarter as a duplicate.
    expected_frequency = ABS_FREQUENCIES[name]
    data: dict[str, float] = {}
    for _, row in frame.iterrows():
        period_raw = str(row[time_col]).strip()
        value_raw = str(row[obs_col]).strip()
        if not period_raw or value_raw in ("", "nan"):
            continue
        freq = "Q" if "Q" in period_raw else "M"
        if freq != expected_frequency:
            raise ValueError(
                f"ABS dataflow {dataflow} returned {freq} observations for {name!r}, "
                f"which is {expected_frequency}: the dataflow's frequency has changed"
            )
        try:
            period = str(pd.Period(period_raw, freq=freq))
            value = float(value_raw)
        except (ValueError, TypeError):
            continue
        if period in data:
            raise ValueError(f"duplicate ABS period {period}: select a single series with dimensions")
        data[period] = value
    if not data:
        raise ValueError("no ABS observations match the selected dimensions")
    frequency = expected_frequency

    return DriverSeries(
        name=name,
        source="abs",
        source_url=url,
        series_id=dataflow,
        retrieved=datetime.now(tz=UTC).date(),
        units=str(units[0]) if units else "",
        dimensions=selection,
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
    while True:
        try:
            with path.open("x", encoding="utf-8") as output:
                output.write(json.dumps(series.model_dump(mode="json"), indent=2))
            break
        except FileExistsError:
            path = directory / f"{base}_{counter}.json"
            counter += 1
    return path


def load_snapshot(path: str | Path) -> DriverSeries:
    """Reload a snapshot, preserving its recorded retrieved date."""
    return DriverSeries.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
