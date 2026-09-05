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


# The layout Xero exports from Reports, observed on the Demo Company (AU)
# on 5 September 2026 and saved as CSV: title rows, a header carrying
# "Account", section rows without amounts, "Total <section>" subtotals,
# derived rows, natural-balance amounts and a comparative column.
FIXTURE_PL_EXPORT = FIXTURE_PL.with_name("xero_pl_au_export.csv")
FIXTURE_BS_EXPORT = FIXTURE_BS.with_name("xero_bs_au_export.csv")


def test_report_layout_pl_loads_posting_accounts_with_normalised_signs():
    report = read_xero_report(FIXTURE_PL_EXPORT)
    accounts = report.by_account()
    for label in (
        "Trading Income",
        "Total Trading Income",
        "Gross Profit",
        "Operating Expenses",
        "Total Operating Expenses",
        "Net Profit",
    ):
        assert label not in accounts
    assert len(report.rows) == 7
    assert accounts["Sales"] == pytest.approx(27500.0)
    assert accounts["Interest Income"] == pytest.approx(97.05)
    # Xero exports expenses positive; the module convention is negative.
    assert accounts["Purchases"] == pytest.approx(-760.0)
    assert accounts["Wages and Salaries"] == pytest.approx(-13400.0)
    # A credit sitting in an expense section flips the other way.
    assert accounts["Freight & Courier"] == pytest.approx(9.09)
    # Only the reported period is read; the comparative column is ignored.
    assert accounts["Rent"] == pytest.approx(-1075.0)
    # The GST detector still sees income as income.
    assert detect_gst_inclusive(report, control_total=27500.0 + 97.05) is False


def test_report_layout_bs_reads_account_from_column_b():
    bs = read_xero_report(FIXTURE_BS_EXPORT).by_account()
    assert bs["Business Bank Account"] == pytest.approx(85420.0)
    assert bs["Less Accumulated Depreciation"] == pytest.approx(-12000.0)
    assert bs["GST"] == pytest.approx(-2800.0)
    assert bs["Business Loan"] == pytest.approx(-60000.0)
    assert bs["Retained Earnings"] == pytest.approx(-37400.0)
    for label in (
        "Assets",
        "Bank",
        "Total Bank",
        "Total Assets",
        "Net Assets",
        "Liabilities",
        "Current Liabilities",
        "Equity",
        "Total Equity",
    ):
        assert label not in bs
    assert len(bs) == 10


def test_report_layout_splits_a_shown_account_code(tmp_path):
    p = tmp_path / "pl.csv"
    p.write_text(
        "Profit and Loss\nOrg\nFor the month ended 31 August 2026\n\n"
        "Account,Aug 2026\n\n"
        "Trading Income\nSales (200),100.00\nTotal Trading Income,100.00\n\n"
        "Operating Expenses\nRent (Sydney),40.00\nRent (469),60.00\n"
        "Total Operating Expenses,100.00\n\nNet Profit,0\n"
    )
    rows = read_xero_report(p).rows
    assert [(r.code, r.account, r.amount) for r in rows] == [
        ("200", "Sales", 100.0),
        ("", "Rent (Sydney)", -40.0),
        ("469", "Rent", -60.0),
    ]


def test_report_layout_without_a_period_column_is_refused(tmp_path):
    p = tmp_path / "pl.csv"
    p.write_text("Profit and Loss\nOrg\n\nAccount\nSales,1\n")
    with pytest.raises(ValueError, match="period column"):
        read_xero_report(p)


def test_unrecognised_layout_names_the_columns_it_wanted(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("Name,Value\nSales,1\n")
    with pytest.raises(ValueError, match="'Account'"):
        read_xero_report(p)
