"""Render worked decisions from the existing Ridgeline weekly scenarios."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyfpa

HERE = Path(__file__).resolve().parent
METRICS = {
    "min_cash": {"unit": "model currency units", "period": "configured weekly horizon",
                 "formula": "minimum of weekly ending_cash; excludes opening cash"},
    "min_week": {"unit": "one-based forecast week", "period": "configured weekly horizon",
                 "formula": "first week at min_cash"},
    "first_negative_week": {"unit": "one-based forecast week or null", "period": "configured weekly horizon",
                            "formula": "first week where ending_cash < 0"},
    "ending_cash": {"unit": "model currency units", "period": "final configured forecast week",
                    "formula": "ending_cash in the last weekly frame row"},
    "ending_cash_change": {"unit": "model currency units", "period": "final configured forecast week",
                           "formula": "scenario ending_cash minus baseline ending_cash"},
}


def decision_pack(config=None, scenarios=None):
    config = pyfpa.load_cash13_config(HERE / "cash13.yaml") if config is None else config
    scenarios = pyfpa.load_cash13_scenarios(HERE / "scenarios.yaml") if scenarios is None else scenarios
    names = [scenario.name for scenario in scenarios]
    if len(names) != len(set(names)) or "base" in names:
        raise ValueError("Scenario names must be unique and cannot be 'base'.")
    configurations = [("base", config)] + [(scenario.name, pyfpa.apply_scenario(config, scenario)) for scenario in scenarios]
    rows = []
    baseline_ending = None
    for name, changed in configurations:
        frame = pyfpa.cash13_forecast(changed)
        metrics = pyfpa.runway_summary(frame)
        ending = float(frame["ending_cash"].iloc[-1])
        if baseline_ending is None:
            baseline_ending = ending
        scenario = next((value for value in scenarios if value.name == name), None)
        assumptions = {} if scenario is None else scenario.model_dump(mode="json", exclude={"name"})
        outside = [{"name": flow.name, "amount": flow.amount, "week": flow.start_week}
                   for flow in changed.receipts if flow.recurrence == "once" and flow.start_week > config.weeks]
        rows.append({"scenario": name, **metrics, "ending_cash": ending,
                     "ending_cash_change": ending - baseline_ending,
                     "changed_assumptions": assumptions, "one_off_receipts_beyond_horizon": outside})
    return {"horizon_weeks": config.weeks, "opening_cash": config.opening_cash,
            "metrics": METRICS, "scenarios": rows,
            "boundary": "Weekly raw cash in model currency units. No calendar start, funding approval, automatic draw or intraweek timing is supplied."}


def briefing(pack):
    lines = ["# Ridgeline weekly cash decisions", "",
             f"Opening cash: {pack['opening_cash']:,.2f} model currency units. Horizon: {pack['horizon_weeks']} forecast weeks.", "",
             "| Scenario | Trough | Trough week | First negative week | Ending cash | Change vs base |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in pack["scenarios"]:
        first = row["first_negative_week"] if row["first_negative_week"] is not None else "none"
        lines.append(f"| {row['scenario']} | {row['min_cash']:,.2f} | {row['min_week']} | {first} | "
                     f"{row['ending_cash']:,.2f} | {row['ending_cash_change']:,.2f} |")
    for row in pack["scenarios"]:
        lines += ["", f"## {row['scenario']}", ""]
        assumptions = row["changed_assumptions"]
        if not assumptions:
            lines.append("Use the baseline amounts and receipt timing in cash13.yaml.")
        for side in ("receipts", "disbursements"):
            for change in assumptions.get(side, []):
                if change["amount_factor"] != 1:
                    lines.append(f"{change['name']}: use {change['amount_factor'] * 100:g}% of each baseline {side[:-1]} amount.")
                if change["delay_weeks"]:
                    lines.append(f"{change['name']}: delay every named {side[:-1]} by {change['delay_weeks']} forecast weeks.")
        for side in ("add_receipts", "add_disbursements"):
            for flow in assumptions.get(side, []):
                recurrence = "every two weeks" if flow["recurrence"] == "biweekly" else flow["recurrence"]
                lines.append(f"Add {flow['name']}: {flow['amount']:,.2f} model currency units, {recurrence}, from forecast week {flow['start_week']}.")
        lines += ["",
                  f"The trough is {row['min_cash']:,.2f} in forecast week {row['min_week']}. "
                  + ("Ending cash does not cross below zero in the horizon."
                     if row["first_negative_week"] is None else
                     f"First forecast week with negative ending cash: {row['first_negative_week']}."),
                  f"Ending cash changes by {row['ending_cash_change']:,.2f} from the baseline. "
                  "Review receipt timing and available liquidity before accepting this plan."]
        for flow in row["one_off_receipts_beyond_horizon"]:
            lines.append(f"Receipt {flow['name']} of {flow['amount']:,.2f} falls in week {flow['week']}, beyond the horizon; it is not cancelled.")
    lines += ["", "## Metric dictionary", "", "| Metric | Unit | Period | Formula |", "|---|---|---|---|"]
    for name, definition in pack["metrics"].items():
        lines.append(f"| {name} | {definition['unit']} | {definition['period']} | {definition['formula']} |")
    lines += ["", pack["boundary"], ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new directory for the fabricated decision pack")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    pack = decision_pack()
    (args.output / "decisions.json").write_text(json.dumps(pack, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "decisions.md").write_text(briefing(pack), encoding="utf-8")
    print("RIDGELINE DECISIONS WRITTEN")
