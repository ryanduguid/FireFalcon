import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from pyfpa.au.drivers import (
    DriverSeries,
    fetch_abs_series,
    fetch_rba_series,
    load_snapshot,
    save_snapshot,
)

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "au_drivers_snapshot.py"


def _series(name="cash_rate_target", data=None, **overrides):
    kwargs = {
        "name": name,
        "source": "rba",
        "source_url": "https://www.rba.gov.au/statistics/tables/csv/f1-data.csv",
        "series_id": "FIRMMCRTD",
        "retrieved": pd.Timestamp("2026-08-20").date(),
        "units": "Per cent",
        "frequency": "M",
        "data": data or {"2026-06": 4.10, "2026-07": 4.35, "2026-08": 4.35},
        **overrides,
    }
    return DriverSeries(**kwargs)


def test_to_series_builds_monthly_period_index():
    series = _series().to_series()
    assert isinstance(series.index, pd.PeriodIndex)
    assert series.index.freqstr == "M"
    assert series.loc[pd.Period("2026-08", freq="M")] == 4.35


def test_to_series_quarterly_frequency():
    series = _series(
        name="wpi", source="abs", frequency="Q",
        data={"2026Q1": 0.9, "2026Q2": 0.8},
    ).to_series()
    assert series.index.freqstr.startswith("Q")


def test_snapshot_round_trip(tmp_path):
    original = _series()
    path = save_snapshot(original, tmp_path)
    assert path.name == "rba_cash_rate_target_2026-08-20.json"
    loaded = load_snapshot(path)
    assert loaded == original
    assert loaded.source_url.endswith("f1-data.csv")


def test_snapshot_never_overwrites(tmp_path):
    first = save_snapshot(_series(), tmp_path)
    second = save_snapshot(_series(), tmp_path)
    assert first != second
    assert first.exists() and second.exists()


def test_fetch_rba_unknown_series_rejected():
    with pytest.raises(ValueError, match="unknown RBA series"):
        fetch_rba_series("house_prices")


def test_fetch_abs_requires_key(monkeypatch):
    monkeypatch.delenv("ABS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ABS_API_KEY"):
        fetch_abs_series("cpi_monthly")


def test_fetch_abs_unknown_dataflow_rejected(monkeypatch):
    monkeypatch.setenv("ABS_API_KEY", "test-key")
    with pytest.raises(ValueError, match="unknown ABS dataflow"):
        fetch_abs_series("made_up")


def test_snapshot_script_rba_only(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path), "--rba-only"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert len(report["saved"]) == 3  # cash rate, aud/usd, twi
    for path in report["saved"]:
        loaded = load_snapshot(path)
        assert loaded.data, f"{loaded.name} snapshot has no data points"
        assert loaded.source_url.startswith("https://www.rba.gov.au")


def test_snapshot_script_abs_skipped_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ABS_API_KEY", raising=False)
    env = {k: v for k, v in __import__("os").environ.items() if k != "ABS_API_KEY"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert any(k.startswith("abs:") for k in report["skipped"])
