"""ARB Corporation worked example - full pipeline.

Phase A reproduces FY2025 operating mechanics from actual drivers.
Phase B replays two FY2025 champion/challenger holdout epochs.
Phase C forecasts FY2026-FY2027 from the August 2025 4E view.
Phase D labels a Thai Baht / US-tariff COGS sensitivity.

Run:  python3 examples/arb/run_arb.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import arb_model as am
from pyfpa.analysis.reconcile import reconcile
from pyfpa.io.reporting import to_briefing_md

OUT = HERE / "output"


def phase_a() -> str:
    model = am.phase_a_model("FY2025", "FY2024")
    actual = am.phase_a_actual("FY2025", "FY2024")
    rec = reconcile(model, actual, tolerance=0.01)
    lines = [
        "# Phase A - FY2025 actual-driver reproduction",
        "",
        "The engine is driven with ARB's reported sales mix, materials/sales COGS,",
        "working-capital days, D&A and PPE capex. EBITDA is EBIT + D&A.",
        "Gross profit is sales minus materials (ARB does not print GP).",
        "",
        "| Line | Model | Actual | Variance |",
        "|---|--:|--:|--:|",
    ]
    for line, row in rec.iterrows():
        lines.append(
            f"| {line} | {row['model']:,.0f} | {row['actual']:,.0f} | "
            f"{row['variance_pct'] * 100:+.2f}% |"
        )
    lines += [
        "",
        "This validates operating arithmetic, not forecast skill. Target-year",
        "drivers are inputs. Tax, franking, associates, and acquisitions sit",
        "outside the engine.",
        "",
    ]
    return "\n".join(lines)


def phase_b() -> str:
    epochs = am.historical_research_epochs()
    lines = [
        "# Phase B - FY2025 historical holdout research",
        "",
        "The champion is a flat FY2024 run rate. FY2025 is held out.",
        "Working-capital days are not a holdout metric: AR barely moved while",
        "sales grew, and H2 destocking is a management action.",
        "",
        "| Epoch | Hypothesis | Status | Objective gain |",
        "|---|---|---|--:|",
    ]
    for epoch in epochs:
        lines.append(
            f"| {epoch.epoch_id} | {epoch.hypothesis} | {epoch.status} | "
            f"{epoch.evaluation.objective_gain * 100:+.1f}% |"
        )
    uniform, export_led = epochs
    lines += [
        "",
        "## What the loop learned",
        "",
        "- **Uniform 16.4 percent growth was discarded.** Export growth is not a",
        "  company-wide rate. Applying it to Australian aftermarket overstates",
        f"  revenue error from {uniform.evaluation.champion_metrics['revenue_error'] * 100:.1f}%",
        f"  to {uniform.evaluation.challenger_metrics['revenue_error'] * 100:.1f}%.",
        "- **Export-led volume plus 150bps margin compression is proposed.**",
        "  It stays unpromoted until a human accepts the cost-pressure hypothesis.",
        "",
        "| Metric | Flat FY2024 champion | Export-led challenger |",
        "|---|--:|--:|",
    ]
    labels = {
        "revenue_error": "Revenue error",
        "gross_profit_error": "Gross profit error",
        "ebitda_error": "EBITDA error",
    }
    for metric, label in labels.items():
        lines.append(
            f"| {label} | "
            f"{export_led.evaluation.champion_metrics[metric] * 100:.1f}% | "
            f"{export_led.evaluation.challenger_metrics[metric] * 100:.1f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def phase_c() -> str:
    forecast, segs = am.build_forecast()
    fy26 = forecast.iloc[:12]
    briefing = to_briefing_md(fy26, title="ARB Corporation FY2026 forecast")
    extra = [
        "",
        "## Channel mix (FY2026)",
        "",
        "| Channel | Net sales |",
        "|---|--:|",
    ]
    for segment in segs["FY2026"]:
        extra.append(f"| {segment.name} | ${segment.net_sales:,.0f} |")
    extra += [
        "",
        "Assumptions are in `arb_model.FORECAST`. This is the August 2025 4E",
        "view, not a later refresh. Property capex is stepped down because the",
        "board said FY2026 property investment would be significantly lower.",
        "",
    ]
    return briefing + "\n".join(extra)


def phase_d() -> str:
    grid = am.cost_pressure_sensitivity()
    lines = [
        "# Phase D - Thai Baht / US tariff sensitivity",
        "",
        "Labeled sensitivity, not a kernel FX or customs engine. Adds 150bps",
        "to FY2026 COGS versus the base forecast.",
        "",
        "| Scenario | FY2026 EBITDA | FY2026 FCF |",
        "|---|--:|--:|",
    ]
    for name, row in grid.iterrows():
        lines.append(
            f"| {name} | ${row['fy2026_ebitda']:,.0f} | ${row['fy2026_fcf']:,.0f} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_arb(output_dir: str | Path | None = None) -> dict:
    out = Path(output_dir) if output_dir is not None else OUT
    out.mkdir(parents=True, exist_ok=True)
    (out / "reconciliation.md").write_text(phase_a())
    (out / "historical-holdout.md").write_text(phase_b())
    (out / "forecast-briefing.md").write_text(phase_c())
    (out / "sensitivity.md").write_text(phase_d())
    forecast, _ = am.build_forecast()
    return {
        "fy2026_revenue": round(float(forecast.iloc[:12]["revenue"].sum())),
        "fy2026_net_income": round(float(forecast.iloc[:12]["net_income"].sum())),
    }


if __name__ == "__main__":
    figures = run_arb()
    print("Wrote Phase A-D markdown to examples/arb/output/")
    for key, value in figures.items():
        print(f"  {key}: {value}")
