"""Regression guards for the Harbour Light synthetic Australian example.

Seams: Xero fixture mapping, quarterly BAS cash dates, and live-formula
workbook verification against the engine.
"""
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "harbour-light"
sys.path.insert(0, str(EXAMPLE))

pytest.importorskip("formulas")


def test_xero_mapping_annualises_tracking_channels():
    import harbour_model as hm

    channels = {channel.name: channel for channel in hm.channels_from_xero()}
    assert channels["North"].annual_revenue == pytest.approx(840_000.0)
    assert channels["South"].annual_revenue == pytest.approx(492_000.0)
    assert channels["North"].cogs_pct == pytest.approx(31_000.0 / 70_000.0)
    assert channels["South"].cogs_pct == pytest.approx(19_000.0 / 41_000.0)
    assert hm.taxable_sales_pct() == pytest.approx(99_000.0 / 111_000.0)


def test_payroll_gross_wages_tie_to_xero_wages_line():
    import harbour_model as hm

    payroll = hm.payroll_frame()
    assert payroll["gross_wages"].iloc[0] == pytest.approx(41_600.0)
    assert payroll["super_guarantee"].iloc[0] == pytest.approx(4_992.0)
    # Synthetic Xero has $1,300 payroll tax; VIC wages sit under the $1m
    # threshold, so the kernel is the statutory source and pays nil.
    assert payroll["payroll_tax"].sum() == pytest.approx(0.0)


def test_quarterly_bas_dates_match_ato_fy2027_cycle():
    import harbour_model as hm

    schedule = hm.bas_settlement()
    assert schedule["due_date"].tolist() == [
        date(2026, 10, 28),
        date(2027, 2, 28),
        date(2027, 4, 28),
        date(2027, 7, 28),
    ]
    receipts, disbursements = hm.gst_cash13_flows()
    assert receipts == []
    assert len(disbursements) == 1
    assert disbursements[0].start_week == 4
    assert disbursements[0].name == "BAS 2027Q1"


def test_fy_summary_labels_harbour_months_as_fy2027():
    import harbour_model as hm
    from pyfpa.au import fy_summary

    monthly = hm.monthly_forecast()
    quarters = fy_summary(monthly[["revenue"]], by="quarter")
    assert list(quarters.index) == [
        "Q1 FY2027",
        "Q2 FY2027",
        "Q3 FY2027",
        "Q4 FY2027",
    ]
    assert quarters["revenue"].sum() == pytest.approx(1_332_000.0)


def test_verified_excel_matches_engine(tmp_path):
    import harbour_model as hm
    from pyfpa.excel.model_workbook import model_to_excel
    from pyfpa.excel.verify import verify_workbook
    from pyfpa.models.cashflow import cashflow_from_config

    cfg = hm.entity_config()
    path = tmp_path / "harbour-model.xlsx"
    model_to_excel(cfg, path)
    report = verify_workbook(path, cashflow_from_config(cfg))
    assert report.passed, report.failures


def test_run_harbour_writes_artifacts(tmp_path):
    import run_harbour as runner

    result = runner.run_harbour(tmp_path)
    assert (tmp_path / "briefing.md").exists()
    assert (tmp_path / "model.xlsx").exists()
    assert result["revenue_total"] == 1_332_000
    text = (tmp_path / "briefing.md").read_text()
    assert "# Harbour Light Pty Ltd" in text
    assert "13-Week" in text


def test_harbour_pipeline_is_registered_for_agent_discovery():
    from pyfpa.memory.entrypoints import load_entrypoint_registry

    registry = load_entrypoint_registry(EXAMPLE / ".fpa" / "models" / "entrypoints.yaml")
    entrypoint = next(item for item in registry.entrypoints if item.name == "harbour-light-pipeline")
    assert entrypoint.kind == "forecast"
    assert entrypoint.command == ["python3", "run_harbour.py"]


def test_harbour_pl_mapping_covers_every_source_row():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyfpa.cli",
            "reconcile-source",
            str(EXAMPLE),
            "--source-id",
            "xero-pl",
            "--account-column",
            "Account",
            "--amount-column",
            "Amount",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_harbour_workspace_passes_agent_toolbelt_diagnostics():
    result = subprocess.run(
        [sys.executable, "-m", "pyfpa.cli", "doctor", str(EXAMPLE)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
