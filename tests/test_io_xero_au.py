import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pyfpa.io.xero_au import (
    detect_gst_inclusive,
    from_xero,
    read_xero_report,
)

FIXTURE_PL = Path(__file__).resolve().parent.parent / "pyfpa" / "io" / "fixtures" / "xero_pl_au.csv"
FIXTURE_BS = Path(__file__).resolve().parent.parent / "pyfpa" / "io" / "fixtures" / "xero_bs_au.csv"


def _cli(*args: str) -> dict:
    import json

    result = subprocess.run(
        [sys.executable, "-m", "pyfpa.cli", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    payload = json.loads(result.stdout)
    payload["_returncode"] = result.returncode
    return payload


def test_parse_pl_fixture():
    report = read_xero_report(FIXTURE_PL)
    assert len(report.rows) == 15
    sales = [r for r in report.rows if r.account == "Sales - Domestic"]
    assert len(sales) == 2  # split by tracking option
    assert {r.tracking_option for r in sales} == {"North", "South"}


def test_by_account_sums_tracking_splits():
    report = read_xero_report(FIXTURE_PL)
    totals = report.by_account()
    assert totals["Sales - Domestic"] == pytest.approx(99000.0)
    assert totals["Sales - GST Free"] == pytest.approx(12000.0)
    assert totals["Wages and Salaries"] == pytest.approx(-41600.0)


def test_by_tracking_groups_options():
    report = read_xero_report(FIXTURE_PL)
    splits = report.by_tracking()
    assert splits["North"]["Sales - Domestic"] == pytest.approx(58000.0)
    assert splits["South"]["Sales - Domestic"] == pytest.approx(41000.0)
    # Untracked overheads land under the (untracked) key.
    assert "(untracked)" in splits
    assert splits["(untracked)"]["Rent"] == pytest.approx(-6500.0)


def test_unmapped_tracking_subtracts_the_allowed_options():
    report = read_xero_report(FIXTURE_PL)
    # Nothing mapped yet: every option in the file is unmapped.
    assert report.unmapped_tracking() == ["North", "South"]
    # Mapped options drop out; the argument must actually be read.
    assert report.unmapped_tracking(["North"]) == ["South"]
    assert report.unmapped_tracking(["North", "South"]) == []
    # An allowed option that never appears in the file is not invented.
    assert report.unmapped_tracking(["North", "South", "West"]) == []


def test_from_xero_mirrors_adapter_shape():
    totals = from_xero()
    assert totals["Sales - Domestic"] == pytest.approx(99000.0)
    bs = from_xero(balance_sheet=True)
    assert bs["GST"] == pytest.approx(-2800.0)
    assert bs["PAYG Withholdings Payable"] == pytest.approx(-3900.0)


def test_sign_convention_preserved():
    report = read_xero_report(FIXTURE_PL)
    assert all(r.amount > 0 for r in report.rows if r.code in {"200", "201", "800"})
    assert all(
        r.amount < 0 for r in report.rows if r.code in {"400", "640", "642", "644", "646"}
    )


def test_gst_detector_with_control_total():
    report = read_xero_report(FIXTURE_PL)
    income = sum(r.amount for r in report.rows if r.amount > 0 and r.code != "800")
    assert detect_gst_inclusive(report, control_total=income) is False
    assert detect_gst_inclusive(report, control_total=income / 1.1) is True


def test_gst_detector_undetermined_without_control():
    report = read_xero_report(FIXTURE_PL)
    # Fixture amounts are ordinary trading totals; no strong signal either way.
    assert detect_gst_inclusive(report) in (False, None)


def test_empty_file_rejected(tmp_path):
    bad = tmp_path / "empty.csv"
    bad.write_text("Code,Account,Amount\n")
    with pytest.raises(ValueError, match="no rows"):
        read_xero_report(bad)


def test_end_to_end_lineage_pipeline(tmp_path):
    """Fixture -> init -> source-register -> mappings -> reconcile passes."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # Reconcile needs one row per account: aggregate tracking splits first,
    # per the recipe (step: reconcile before modelling).
    report = read_xero_report(FIXTURE_PL)
    with (data_dir / "xero_pl.csv").open("w") as f:
        f.write("Account,Amount\n")
        for account, amount in report.by_account().items():
            f.write(f'"{account}","{amount:.2f}"\n')
    root = tmp_path / "acme"
    root.mkdir()

    init = _cli("init", str(root), "--business-name", "Acme Pty Ltd")
    assert init["ok"] is True, init

    reg = _cli(
        "source-register", str(root),
        "--source-id", "xero-au",
        "--kind", "accounting_system",
        "--location", "../data/xero_pl.csv",
        "--entity", "Acme Pty Ltd",
        "--currency", "AUD",
        "--period", "2026-07",
        "--extraction-method", "Xero P&L CSV export, GST-exclusive, tracking aggregated",
    )
    assert reg["ok"] is True, reg

    for account in report.by_account():
        mapping = _cli(
            "mapping-register", str(root),
            "--source-id", "xero-au",
            "--source-value", account,
            "--target", f"model.{account.lower().replace(' ', '_').replace('&', 'and')}",
        )
        assert mapping["ok"] is True, (account, mapping)

    reconcile = _cli(
        "reconcile-source", str(root),
        "--source-id", "xero-au",
        "--account-column", "Account",
        "--amount-column", "Amount",
        "--allow-unmapped",
    )
    assert reconcile["ok"] is True, reconcile
    assert reconcile["data"]["passed"] is True


def test_reconcile_fails_on_unmapped_accounts(tmp_path):
    """Unmapped accounts must surface, not default."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURE_PL, data_dir / "xero_pl.csv")
    root = tmp_path / "acme"
    root.mkdir()
    _cli("init", str(root), "--business-name", "Acme Pty Ltd")
    _cli(
        "source-register", str(root),
        "--source-id", "xero-au",
        "--kind", "accounting_system",
        "--location", "../data/xero_pl.csv",
        "--entity", "Acme Pty Ltd",
        "--currency", "AUD",
        "--period", "2026-07",
        "--extraction-method", "Xero P&L CSV export, GST-exclusive",
    )
    reconcile = _cli(
        "reconcile-source", str(root),
        "--source-id", "xero-au",
        "--account-column", "Account",
        "--amount-column", "Amount",
    )
    assert reconcile["ok"] is False
    assert reconcile["error"]["type"] == "reconciliation_failed"
    assert reconcile["data"]["unmapped"]
