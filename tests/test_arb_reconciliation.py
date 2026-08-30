"""Regression guards for the ARB Corporation public-company example.

Seams: source totals versus SOURCES.md, Phase A reproduction tolerance,
and the FY2025 holdout champion/challenger verdicts.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "arb"
sys.path.insert(0, str(EXAMPLE))


def test_source_csvs_match_appendix_4e_totals():
    import arb_model as am

    inc, bs, cf, seg = (
        am.income_statement(),
        am.balance_sheet(),
        am.cash_flow(),
        am.segment_table(),
    )
    assert float(inc.loc["net_sales", "FY2025"]) == 729_949_000.0
    assert float(inc.loc["net_sales", "FY2024"]) == 693_154_000.0
    assert float(inc.loc["cost_of_sales", "FY2025"]) == 315_721_000.0
    assert float(inc.loc["gross_profit", "FY2025"]) == 414_228_000.0
    assert float(inc.loc["ebit", "FY2025"]) == 136_144_000.0
    assert float(inc.loc["net_income", "FY2025"]) == 97_527_000.0
    assert float(bs.loc["cash", "FY2025"]) == 69_198_000.0
    assert float(bs.loc["inventory", "FY2025"]) == 249_061_000.0
    assert float(bs.loc["accounts_receivable", "FY2025"]) == 90_481_000.0
    assert float(bs.loc["accounts_payable", "FY2025"]) == 65_163_000.0
    assert float(cf.loc["capex", "FY2025"]) == 46_194_000.0
    assert float(cf.loc["depreciation_amortization", "FY2025"]) == 32_509_000.0
    sales = seg[seg.metric == "net_sales"].set_index("segment")
    assert float(sales.loc["Australian Aftermarket", "FY2025"]) == 403_281_000.0
    assert float(sales.loc["Exports", "FY2025"]) == 266_993_000.0
    assert float(sales.loc["Original Equipment", "FY2025"]) == 59_675_000.0
    assert (
        sales["FY2025"].sum()
        == pytest.approx(float(inc.loc["net_sales", "FY2025"]))
    )

    sources = (EXAMPLE / "data" / "SOURCES.md").read_text()
    assert "729,949" in sources
    assert "asxpdf/20250819/pdf/06n0z50mr65hhq.pdf" in sources
    assert "Materials and consumables used" in sources


def test_phase_a_reproduces_fy2025_operating_mechanics():
    import arb_model as am
    from pyfpa.analysis.reconcile import reconcile

    model = am.phase_a_model("FY2025", "FY2024")
    actual = am.phase_a_actual("FY2025", "FY2024")
    rec = reconcile(model, actual, tolerance=0.01)
    assert rec["within_tolerance"].all(), rec[["model", "actual", "variance_pct"]]
    assert abs(rec.loc["ebitda", "variance_pct"]) < 1e-9
    assert abs(rec.loc["operating_cash_flow_before_tax", "variance_pct"]) < 1e-6


def test_historical_holdout_rejects_uniform_export_rate():
    import arb_model as am

    uniform, export_led = am.historical_research_epochs()
    assert uniform.status == "discarded"
    assert uniform.evaluation.regression_guard_passed is False
    assert uniform.evaluation.promotion_eligible is False
    assert export_led.status == "proposed"
    assert export_led.evaluation.regression_guard_passed is True
    assert export_led.evaluation.promotion_eligible is True
    assert export_led.evaluation.objective_gain > 0.50
    for metric, champion in export_led.evaluation.champion_metrics.items():
        assert export_led.evaluation.challenger_metrics[metric] < champion


def test_forecast_is_coherent():
    import arb_model as am
    from pyfpa.analysis.segments import roll_up_segments

    forecast, segs = am.build_forecast()
    assert len(forecast) == 24
    fy26 = forecast.iloc[:12].sum()
    assert fy26["net_income"] > 0
    assert fy26["free_cash_flow"] > 0
    seg_sales = float(roll_up_segments(segs["FY2026"])["net_sales"])
    assert seg_sales == pytest.approx(float(fy26["revenue"]), rel=1e-9)


def test_tariff_thb_sensitivity_is_labeled_and_hurts_ebitda():
    import arb_model as am

    grid = am.cost_pressure_sensitivity()
    assert "Base" in grid.index
    assert "THB/tariff +150bps COGS" in grid.index
    stressed = float(grid.loc["THB/tariff +150bps COGS", "fy2026_ebitda"])
    base = float(grid.loc["Base", "fy2026_ebitda"])
    assert stressed < base - 1_000_000


def test_registered_challenger_resolves_to_a_committed_research_epoch():
    """MEMORY.md promises `research/` holds the epochs, and the registry needs them.

    Without the committed epoch the recorded `source_epoch` dangles, so the
    challenger can never be promoted however the human decides.
    """
    from pyfpa.research import (
        load_epochs,
        load_model_registry,
        load_research_objective,
        promote_challenger,
    )

    research = EXAMPLE / ".fpa" / "research"
    registry = load_model_registry(EXAMPLE / ".fpa" / "models" / "registry.yaml")
    epochs = {epoch.epoch_id: epoch for epoch in load_epochs(research)}
    assert set(epochs) == {
        "arb-fy2025-001-uniform-export-rate",
        "arb-fy2025-002-export-led-margin-pressure",
    }
    assert epochs["arb-fy2025-001-uniform-export-rate"].status == "discarded"

    challenger = registry.challengers[0]
    promoted = promote_challenger(
        registry,
        challenger_id=challenger.model_id,
        epoch=epochs[challenger.source_epoch],
        approved_by="reviewer",
        approved_at="2026-08-21",
        objective=load_research_objective(research / "objective.yaml"),
    )
    assert promoted.champion.model_id == challenger.model_id
    # The committed registry stays unpromoted; promotion needs a human.
    assert registry.promotions == []


def test_run_arb_regenerates_the_research_memory_it_claims_to(tmp_path):
    """MEMORY.md credits run_arb.py with the objective and the epochs."""
    import run_arb as runner

    committed = EXAMPLE / ".fpa" / "research"
    before = {path.name: path.read_text() for path in committed.glob("*.yaml")}
    runner.run_arb(tmp_path)
    written = {
        path.name: path.read_text()
        for path in (tmp_path / ".fpa" / "research").glob("*.yaml")
    }
    after = {path.name: path.read_text() for path in committed.glob("*.yaml")}
    assert set(written) == {
        "objective.yaml",
        "arb-fy2025-001-uniform-export-rate.epoch.yaml",
        "arb-fy2025-002-export-led-margin-pressure.epoch.yaml",
    }
    # The run stays inside output_dir, so re-running this guard cannot erase the
    # evidence it just caught.
    assert after == before
    assert written == before  # the committed memory is exactly what the run writes


def test_arb_pipeline_is_registered_for_agent_discovery():
    from pyfpa.memory.entrypoints import load_entrypoint_registry

    registry = load_entrypoint_registry(EXAMPLE / ".fpa" / "models" / "entrypoints.yaml")
    entrypoint = next(item for item in registry.entrypoints if item.name == "arb-pipeline")
    assert entrypoint.kind == "forecast"
    assert entrypoint.command == ["python3", "run_arb.py"]


def test_arb_income_statement_mapping_covers_every_source_row():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyfpa.cli",
            "reconcile-source",
            str(EXAMPLE),
            "--source-id",
            "arb-income-statement",
            "--account-column",
            "line",
            "--amount-column",
            "FY2025",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_arb_workspace_passes_agent_toolbelt_diagnostics():
    result = subprocess.run(
        [sys.executable, "-m", "pyfpa.cli", "doctor", str(EXAMPLE)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
