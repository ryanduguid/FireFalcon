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
import au_drivers_snapshot as snapshot


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


def test_concurrent_snapshots_keep_every_observation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    series = [_series(data={"2026-08": float(i)}) for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda item: save_snapshot(item, tmp_path), series))
    assert len(set(paths)) == 8
    assert {load_snapshot(path).data["2026-08"] for path in paths} == set(range(8))


def test_fetch_rba_unknown_series_rejected():
    with pytest.raises(ValueError, match="unknown RBA series"):
        fetch_rba_series("house_prices")


def test_fetch_abs_requires_key(monkeypatch):
    monkeypatch.delenv("ABS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ABS_API_KEY"):
        fetch_abs_series("cpi_monthly")


def test_fetch_abs_takes_no_key_argument(monkeypatch):
    # The key is host-environment only, so a caller must have no way to pass one.
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    with pytest.raises(TypeError):
        fetch_abs_series("wpi", api_key="synthetic-unused")  # type: ignore[call-arg]


def test_fetch_abs_unknown_dataflow_rejected(monkeypatch):
    monkeypatch.setenv("ABS_API_KEY", "test-key")
    with pytest.raises(ValueError, match="unknown ABS dataflow"):
        fetch_abs_series("made_up")


def test_abs_rejects_ambiguous_periods_in_either_order(monkeypatch):
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    rows = ["2026-Q1,AUS,4.0,Percent", "2026-Q1,NSW,3.0,Percent"]
    for ordered in (rows, rows[::-1]):
        raw = "TIME_PERIOD,REGION,OBS_VALUE,UNIT_MEASURE\n" + "\n".join(ordered)
        monkeypatch.setattr(drivers, "_fetch", lambda *args, raw=raw, **kwargs: raw.encode())
        with pytest.raises(ValueError, match="ambiguous|duplicate"):
            fetch_abs_series("wpi")


def test_abs_rejects_disjoint_series_even_with_partial_selection(monkeypatch):
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    raw = (
        b"TIME_PERIOD,REGION,INDUSTRY,OBS_VALUE,UNIT_MEASURE\n"
        b"2026-Q1,AUS,MINING,4.0,Percent\n2026-Q2,AUS,RETAIL,3.0,Percent\n"
    )
    monkeypatch.setattr(drivers, "_fetch", lambda *args, **kwargs: raw)
    for selection in (None, {"REGION": "AUS"}):
        with pytest.raises(ValueError, match="ambiguous"):
            fetch_abs_series("wpi", dimensions=selection)


def test_abs_allows_observation_status_changes_within_one_series(monkeypatch):
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    raw = (
        b"TIME_PERIOD,REGION,OBS_VALUE,OBS_STATUS\n"
        b"2026-Q1,AUS,4.0,F\n2026-Q2,AUS,3.0,P\n"
    )
    monkeypatch.setattr(drivers, "_fetch", lambda *args, **kwargs: raw)
    assert fetch_abs_series("wpi").data == {"2026Q1": 4.0, "2026Q2": 3.0}


def test_abs_explicit_selection_preserves_units_and_dimensions(tmp_path, monkeypatch):
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    raw = (
        "TIME_PERIOD,REGION,OBS_VALUE,UNIT_MEASURE\n"
        "2026-Q1,AUS,4.0,Percent\n2026-Q1,NSW,3.0,Percent\n"
        "2026-Q2,AUS,4.1,Percent\n"
    )
    monkeypatch.setattr(drivers, "_fetch", lambda *args, **kwargs: raw.encode())
    series = fetch_abs_series("wpi", dimensions={"REGION": "AUS"})
    assert series.data == {"2026Q1": 4.0, "2026Q2": 4.1}
    assert series.units == "Percent"
    assert series.dimensions == {"REGION": "AUS"}
    assert load_snapshot(save_snapshot(series, tmp_path)) == series


@pytest.mark.parametrize("dimensions", [{"REGION": "VIC"}, {"UNKNOWN": "AUS"}])
def test_abs_rejects_selection_without_observations(monkeypatch, dimensions):
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    raw = b"TIME_PERIOD,REGION,OBS_VALUE\n2026-Q1,AUS,4.0\n"
    monkeypatch.setattr(drivers, "_fetch", lambda *args, **kwargs: raw)
    with pytest.raises(ValueError, match="dimension|observations"):
        fetch_abs_series("wpi", dimensions=dimensions)


def test_fetch_rba_parses_the_committed_f1_sample(monkeypatch):
    monkeypatch.setattr(drivers, "_fetch", _sample)
    series = fetch_rba_series("cash_rate_target")
    assert series.series_id == "FIRMMCRTD"
    assert series.units == "Per cent"
    assert series.source_url.endswith("f1-data.csv")
    # The latest dated observation wins; blank cells are skipped, never zeroed.
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


@pytest.mark.parametrize("name", list(drivers.RBA_SERIES))
@pytest.mark.parametrize("order", ["reversed", "interleaved"])
def test_fetch_rba_is_independent_of_observation_order(name, order, monkeypatch, tmp_path):
    monkeypatch.setattr(drivers, "_fetch", _sample)
    expected = fetch_rba_series(name)
    table, _ = drivers.RBA_SERIES[name]
    lines = _sample(f"{drivers.RBA_BASE}/{table}").decode("utf-8-sig").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Series ID,")) + 1
    rows = lines[start:]
    rows = rows[::-1] if order == "reversed" else rows[1::2] + rows[::2]
    reordered = ("\n".join(lines[:start] + rows) + "\n").encode()
    monkeypatch.setattr(drivers, "_fetch", lambda url: reordered)

    actual = fetch_rba_series(name)

    assert list(actual.data.items()) == list(expected.data.items())
    reloaded = load_snapshot(save_snapshot(actual, tmp_path)).to_series()
    assert reloaded.index.is_monotonic_increasing
    assert reloaded.iloc[-1] == expected.to_series().iloc[-1]


@pytest.mark.parametrize("name", list(drivers.RBA_SERIES))
@pytest.mark.parametrize("duplicate", ["same", "formatted", "blank", "conflicting"])
def test_fetch_rba_duplicate_date_policy(name, duplicate, monkeypatch):
    monkeypatch.setattr(drivers, "_fetch", _sample)
    expected = fetch_rba_series(name)
    table, series_id = drivers.RBA_SERIES[name]
    lines = _sample(f"{drivers.RBA_BASE}/{table}").decode("utf-8-sig").splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("Series ID,"))
    col = lines[header].split(",").index(series_id)
    # The first date does not win its month, but a conflict must still be reported.
    row = lines[header + 1].split(",")
    if duplicate == "formatted":
        row[col] = f"{float(row[col]):.6f}"
    elif duplicate == "blank":
        row[col] = ""
    elif duplicate == "conflicting":
        row[col] = str(float(row[col]) + 1)
    payload = ("\n".join(lines + [",".join(row)]) + "\n").encode()
    monkeypatch.setattr(drivers, "_fetch", lambda url: payload)

    if duplicate == "conflicting":
        with pytest.raises(ValueError, match=f"{series_id} on 2026-02-02"):
            fetch_rba_series(name)
    else:
        assert list(fetch_rba_series(name).data.items()) == list(expected.data.items())


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


def test_abs_dataflow_ids_are_the_documented_indicator_api_ones():
    """F090: every key pointed at a Data API or discontinued id.

    Checked on 13 September 2026 against the dataflowId enum in the ABS
    Indicator API description (CPI_H, CPI_Q_H, LF_H, RT_H, WPI_H are listed;
    CPI_M, CPI, WPI, RT and LF are not) and the ABS Data API user guide
    updates, which record CPI_M/CPI_M_H ceasing in November 2025, quarterly CPI
    returning as CPI_Q_H in April 2026, and RT_H no longer being updated.
    """
    assert drivers.ABS_DATAFLOWS == {
        "cpi_monthly": "CPI_H",
        "cpi_quarterly": "CPI_Q_H",
        "wpi": "WPI_H",
        "retail_trade": "RT_H",
        "labour_force": "LF_H",
    }
    assert set(drivers.ABS_FREQUENCIES) == set(drivers.ABS_DATAFLOWS)
    assert all(identifier.endswith("_H") for identifier in drivers.ABS_DATAFLOWS.values())


def test_abs_rejects_a_frequency_the_key_does_not_promise(monkeypatch):
    # F090: cpi_quarterly accepted monthly observations and returned them under
    # the quarterly name.
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    raw = b"TIME_PERIOD,REGION,OBS_VALUE\n2026-01,AUS,4.0\n2026-02,AUS,4.1\n"
    monkeypatch.setattr(drivers, "_fetch", lambda *args, **kwargs: raw)
    with pytest.raises(ValueError, match="returned M observations"):
        fetch_abs_series("cpi_quarterly")
    # Control: the monthly key accepts the same observations.
    assert fetch_abs_series("cpi_monthly").frequency == "M"


def test_abs_rejects_a_single_observation_of_the_wrong_frequency(monkeypatch):
    # A quarterly response carrying one monthly period passed the aggregate
    # check and folded that month into an existing quarter.
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    raw = b"TIME_PERIOD,REGION,OBS_VALUE\n2026-Q1,AUS,4.0\n2026-02,AUS,4.1\n2026-Q2,AUS,4.2\n"
    monkeypatch.setattr(drivers, "_fetch", lambda *args, **kwargs: raw)
    with pytest.raises(ValueError, match="returned M observations"):
        fetch_abs_series("wpi")


def test_abs_dataflow_id_reaches_the_request_url(monkeypatch):
    monkeypatch.setenv("ABS_API_KEY", "synthetic-unused")
    seen = {}

    def capture(url, headers=None, timeout=60):
        seen["url"] = url
        return b"TIME_PERIOD,REGION,OBS_VALUE\n2026-Q1,AUS,4.0\n2026-Q2,AUS,4.1\n"

    monkeypatch.setattr(drivers, "_fetch", capture)
    series = fetch_abs_series("wpi")
    assert seen["url"].endswith("/data/WPI_H/csv")
    assert series.series_id == "WPI_H"
