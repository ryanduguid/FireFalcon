import json
import shutil
from pathlib import Path

import pytest

from pyfpa.io.xero_au import (
    detect_gst_inclusive,
    read_xero_report,
)

FIXTURE_PL = Path(__file__).resolve().parent.parent / "pyfpa" / "io" / "fixtures" / "xero_pl_au.csv"
FIXTURE_BS = Path(__file__).resolve().parent.parent / "pyfpa" / "io" / "fixtures" / "xero_bs_au.csv"


@pytest.fixture
def cli(run_cli):
    """Run `openfpa` in this process, as conftest's run_cli does, and return its JSON."""

    def _call(*args: str) -> dict:
        result = run_cli(*args)
        payload = json.loads(result.stdout)
        payload["_returncode"] = result.returncode
        return payload

    return _call


def test_parse_pl_fixture():
    report = read_xero_report(FIXTURE_PL)
    assert len(report.rows) == 15
    sales = [r for r in report.rows if r.account == "Sales - Domestic"]
    assert len(sales) == 2  # split by tracking option
    assert {r.tracking_option for r in sales} == {"North", "South"}


def test_blank_account_amount_does_not_reset_cost_section_sign(tmp_path):
    source = tmp_path / "report.csv"
    source.write_text("Account,Jul 2026\nIncome,\nSales,100\nOperating Expenses,\nEmpty Account,\nRent,20\n", encoding="utf-8")
    assert read_xero_report(source).by_account() == {"Sales": 100, "Rent": -20}


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
    assert detect_gst_inclusive(report) is None


@pytest.mark.parametrize("control", [None, 0.0, -1.0, float("nan"), float("inf")])
def test_gst_detector_does_not_infer_basis_from_round_amounts(tmp_path, control):
    path = tmp_path / "sales.csv"
    path.write_text("Code,Account,Amount\n200,Sales,1100\n")
    report = read_xero_report(path)
    assert detect_gst_inclusive(report, control_total=control) is None
    assert detect_gst_inclusive(report, control_total=1000.0) is True
    assert detect_gst_inclusive(report, control_total=1100.0) is False


@pytest.mark.parametrize("row", ["Sales", "Sales,NaN", "Sales,inf", "Sales,-inf", "Sales,1e309"])
def test_xero_flat_report_rejects_missing_or_nonfinite_amounts(tmp_path, row):
    path = tmp_path / "invalid.csv"
    path.write_text(f"Account,Amount\n{row}\n")
    with pytest.raises(ValueError, match="amount"):
        read_xero_report(path)


def test_empty_file_rejected(tmp_path):
    bad = tmp_path / "empty.csv"
    bad.write_text("Code,Account,Amount\n")
    with pytest.raises(ValueError, match="no rows"):
        read_xero_report(bad)


def test_end_to_end_lineage_pipeline(tmp_path, cli):
    """Fixture -> init -> source-register -> mappings -> reconcile reports a difference.

    Every account is mapped, so nothing is unmapped, but no expected totals were
    supplied: reconcile must report that rather than pass on mappings alone.
    """
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

    init = cli("init", str(root), "--business-name", "Acme Pty Ltd")
    assert init["ok"] is True, init

    reg = cli(
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
        mapping = cli(
            "mapping-register", str(root),
            "--source-id", "xero-au",
            "--source-value", account,
            "--target", f"model.{account.lower().replace(' ', '_').replace('&', 'and')}",
        )
        assert mapping["ok"] is True, (account, mapping)

    reconcile = cli(
        "reconcile-source", str(root),
        "--source-id", "xero-au",
        "--account-column", "Account",
        "--amount-column", "Amount",
        "--allow-unmapped",
    )
    assert reconcile["ok"] is False, reconcile
    assert reconcile["data"]["unmapped"] == []
    assert reconcile["data"]["expected_provided"] is False
    assert reconcile["data"]["passed"] is False


def test_reconcile_fails_on_unmapped_accounts(tmp_path, cli):
    """Unmapped accounts must surface, not default."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURE_PL, data_dir / "xero_pl.csv")
    root = tmp_path / "acme"
    root.mkdir()
    cli("init", str(root), "--business-name", "Acme Pty Ltd")
    cli(
        "source-register", str(root),
        "--source-id", "xero-au",
        "--kind", "accounting_system",
        "--location", "../data/xero_pl.csv",
        "--entity", "Acme Pty Ltd",
        "--currency", "AUD",
        "--period", "2026-07",
        "--extraction-method", "Xero P&L CSV export, GST-exclusive",
    )
    reconcile = cli(
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


@pytest.mark.parametrize(
    "columns", ["Eastside,North,Unassigned", "2026,North,Unassigned"]
)
def test_tracking_comparison_is_not_read_as_one_period(tmp_path, columns):
    """Fabricated amounts in the Compare Region layout observed 13 September 2026."""
    source = tmp_path / "tracking.csv"
    source.write_text(
        "Profit and Loss,,,\nFabricated Company,,,\n"
        "For the year ended 30 June 2027,,,\n,,,\n"
        f"Account,{columns}\nTrading Income,,,\nSales,120,80,50\n"
        "Total Trading Income,120,80,50\nOperating Expenses,,,\n"
        "Rent,40,20,10\nNet Profit,80,60,40\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Tracking Option"):
        read_xero_report(source)


@pytest.mark.parametrize("period", ["2026", "Sept 2026", "September 2026", "30 June 2026"])
def test_report_period_headers_keep_the_first_period(tmp_path, period):
    source = tmp_path / "period.csv"
    source.write_text(
        f"Profit and Loss\nFabricated Company\nAccount,{period},2025\n"
        "Trading Income,,\nSales,120,999\nOperating Expenses,,\nRent,40,888\n",
        encoding="utf-8",
    )
    assert read_xero_report(source).by_account() == {"Sales": 120, "Rent": -40}


@pytest.mark.parametrize("first_option", ["Eastside", "2026"])
def test_explicit_tracking_comparison_preserves_every_option(tmp_path, first_option):
    source = tmp_path / "tracking.csv"
    source.write_text(
        "Profit and Loss,,,\nFabricated Company,,,\n"
        f"Account,{first_option},North,Unassigned\nTrading Income,,,\n"
        "Sales (200),120,80,50\nTotal Trading Income,120,80,50\n"
        "Cost of Sales,,,\nPurchases (310),10,-5,\nGross Profit,110,85,50\n"
        "Operating Expenses,,,\nRent,40,20,10\nNet Profit,70,65,40\n",
        encoding="utf-8-sig",
    )
    report = read_xero_report(source, tracking_comparison=True)
    assert report.by_tracking() == {
        first_option: {"Sales": 120, "Purchases": -10, "Rent": -40},
        "North": {"Sales": 80, "Purchases": 5, "Rent": -20},
        "(untracked)": {"Sales": 50, "Purchases": 0, "Rent": -10},
    }
    assert report.by_account() == {"Sales": 250, "Purchases": -5, "Rent": -70}
    assert sum(report.by_account().values()) == 175
    assert [row.code for row in report.rows if row.account == "Sales"] == ["200"] * 3


@pytest.mark.parametrize(
    "columns", ["North,north", "North,", "North,Total", "North,(untracked)"]
)
def test_tracking_comparison_refuses_ambiguous_headers(tmp_path, columns):
    source = tmp_path / "ambiguous.csv"
    source.write_text(f"Profit and Loss\nAccount,{columns}\nSales,120,80\n")
    with pytest.raises(ValueError, match="tracking columns"):
        read_xero_report(source, tracking_comparison=True)


@pytest.mark.parametrize("amounts", ["", "120", "120,80,99", "120,TBC", "120,NaN"])
@pytest.mark.parametrize("account", ["Sales", "Income"])
def test_tracking_comparison_refuses_missing_extra_or_bad_amounts(tmp_path, amounts, account):
    source = tmp_path / "bad.csv"
    source.write_text(f"Profit and Loss\nAccount,Eastside,North\n{account},{amounts}\n")
    with pytest.raises(ValueError):
        read_xero_report(source, tracking_comparison=True)


def test_tracking_comparison_refuses_full_width_posting_without_amounts(tmp_path):
    source = tmp_path / "blank-posting.csv"
    source.write_text(
        "Profit and Loss\nAccount,Eastside,North\nTrading Income,,\n"
        "Other income,10,20\nSales,,\n"
    )
    with pytest.raises(ValueError, match="has no amounts"):
        read_xero_report(source, tracking_comparison=True)


def test_tracking_comparison_mode_refuses_other_layouts(tmp_path):
    source = tmp_path / "flat.csv"
    source.write_text("Account,Amount,Tracking Option\nSales,120,North\n")
    with pytest.raises(ValueError, match="P&L report layout"):
        read_xero_report(source, tracking_comparison=True)
    with pytest.raises(ValueError, match="P&L report layout"):
        read_xero_report(FIXTURE_BS_EXPORT, tracking_comparison=True)


def test_unrecognised_layout_names_the_columns_it_wanted(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("Name,Value\nSales,1\n")
    with pytest.raises(ValueError, match="'Account'"):
        read_xero_report(p)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Code,Account,Amount\n200,Sales,1,234.56\n400,Rent,500.00\n", "extra fields in Xero CSV row 2"),
        ("Code,Account,Amount\n200,Sales,1000.00\n\n260,,250.00\n", "missing account in Xero CSV row 4"),
        ("Code,Account,Amount,Amount\n200,Sales,1000.00,0\n", "duplicate Xero CSV columns"),
        ("Code,Account,Amount,\n200,Sales,1000.00,\n", "unnamed Xero CSV columns"),
    ],
)
def test_xero_flat_layout_refuses_what_read_pl_csv_refuses(tmp_path, text, message):
    """Each of these used to read silently: Sales as 1.0, the 250.00 dropped, the last Amount column kept."""
    path = tmp_path / "flat.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        read_xero_report(path)


REPORT_HEAD = "Profit and Loss\nProbe Pty Ltd\nFor the month ended 31 July 2026\n\nAccount,Jul 2026\n"


def test_a_posting_account_named_total_is_refused_not_dropped(tmp_path):
    path = tmp_path / "pl.csv"
    path.write_text(
        REPORT_HEAD + "Trading Income,\nSales,10000.00\nTotal Trading Income,10000.00\n"
        "Operating Expenses,\nRent,2000.00\nTotal Tools Hire,750.00\n"
        "Total Operating Expenses,2750.00\nNet Profit,7250.00\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="'Total Tools Hire' reads as a subtotal"):
        read_xero_report(path)


def test_subtotals_of_less_headings_and_both_export_layouts_still_read(tmp_path):
    path = tmp_path / "pl.csv"
    path.write_text(
        REPORT_HEAD + "Income,\nSales,10000.00\nTotal Income,10000.00\n"
        "Less Operating Expenses,\nRent,2000.00\nTotal Operating Expenses,2000.00\nNet Profit,8000.00\n",
        encoding="utf-8",
    )
    assert read_xero_report(path).by_account() == {"Sales": 10000.0, "Rent": -2000.0}
    for fixture in ("xero_pl_au_export.csv", "xero_bs_au_export.csv", "xero_pl_au.csv", "xero_bs_au.csv"):
        assert read_xero_report(FIXTURE_PL.parent / fixture).rows
