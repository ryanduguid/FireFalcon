import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from pyfpa.au import drivers
from pyfpa.au.drivers import (
    DriverSeries,
    fetch_abs_series,
    fetch_rba_series,
    load_snapshot,
    save_snapshot,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(REPO / "scripts"))
import au_drivers_snapshot as snapshot  # noqa: E402


def _sample(url: str, headers=None, timeout: int = 60) -> bytes:
    """Serve the committed RBA table samples in place of a live download.

    Patched over `drivers._fetch`, so the script under test exercises the real
    parser and the real save path with no network dependency.
    """
    table = url.rsplit("/", 1)[-1].replace("-data.csv", "")
    return (FIXTURES / f"rba_{table}_sample.csv").read_bytes()


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


def test_fetch_rba_parses_the_committed_f1_sample(monkeypatch):
    monkeypatch.setattr(drivers, "_fetch", _sample)
    series = fetch_rba_series("cash_rate_target")
    assert series.series_id == "FIRMMCRTD"
    assert series.units == "Per cent"
    assert series.source_url.endswith("f1-data.csv")
    # The last dated row in a month wins; blank cells are skipped, never zeroed.
    assert series.data["2026-02"] == 3.85  # 27-Feb rise, not the 02-Feb 3.60
    assert series.data["2026-08"] == 4.35  # 27-Aug, since 28-Aug is blank
    assert "2026-04" not in series.data


def test_fetch_rba_selects_the_named_column_of_a_shared_table(monkeypatch):
    monkeypatch.setattr(drivers, "_fetch", _sample)
    aud_usd = fetch_rba_series("aud_usd")
    twi = fetch_rba_series("twi")
    # Both read f11.1; only the Series ID row separates them.
    assert (aud_usd.series_id, aud_usd.units) == ("FXRUSD", "USD")
    assert (twi.series_id, twi.units) == ("FXRTWI", "Index")
    assert aud_usd.data["2026-08"] == 0.7196
    assert twi.data["2026-08"] == 66.40


def _run_snapshot(monkeypatch, capsys, tmp_path, *args) -> tuple[int, dict]:
    """Drive the snapshot script in-process so no test shells out to the RBA."""
    monkeypatch.setattr(sys, "argv", ["au_drivers_snapshot.py", "--out", str(tmp_path), *args])
    code = snapshot.main()
    return code, json.loads(capsys.readouterr().out)


def test_snapshot_script_rba_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(drivers, "_fetch", _sample)
    code, report = _run_snapshot(monkeypatch, capsys, tmp_path, "--rba-only")
    assert code == 0, report
    assert not report["errors"]
    assert len(report["saved"]) == 3  # cash rate, aud/usd, twi
    for path in report["saved"]:
        loaded = load_snapshot(path)
        assert loaded.data, f"{loaded.name} snapshot has no data points"
        assert loaded.source_url.startswith("https://www.rba.gov.au")


def test_snapshot_script_abs_skipped_without_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ABS_API_KEY", raising=False)
    monkeypatch.setattr(drivers, "_fetch", _sample)
    code, report = _run_snapshot(monkeypatch, capsys, tmp_path)
    assert code == 0, report
    assert any(k.startswith("abs:") for k in report["skipped"])


def test_snapshot_script_reports_a_failed_fetch_as_exit_1(tmp_path, monkeypatch, capsys):
    def unreachable(url, headers=None, timeout: int = 60) -> bytes:
        raise OSError("network unreachable")

    monkeypatch.setattr(drivers, "_fetch", unreachable)
    code, report = _run_snapshot(monkeypatch, capsys, tmp_path, "--rba-only")
    assert code == 1
    assert set(report["errors"]) == {"rba:cash_rate_target", "rba:aud_usd", "rba:twi"}
    assert not report["saved"]


@pytest.mark.network
def test_live_rba_table_still_matches_the_committed_sample_layout():
    """Opt-in (`pytest -m network`): catches an RBA layout change.

    Deliberately outside the merge gate - an RBA outage must not fail an
    unrelated PR. Run it when refreshing the samples above.
    """
    series = fetch_rba_series("cash_rate_target")
    assert series.series_id == "FIRMMCRTD"
    assert series.units == "Per cent"
    assert len(series.data) > 100
