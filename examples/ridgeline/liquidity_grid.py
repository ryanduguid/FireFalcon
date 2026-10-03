"""Compare 12 fabricated weekly cash constraints using the existing engine."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pyfpa
from pyfpa.cash13.scenarios import FlowChange, Scenario

HERE = Path(__file__).resolve().parent


def opening_buffer(config, floor=0.0):
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not math.isfinite(floor):
        raise ValueError("The weekly ending-cash floor must be finite.")
    frame = pyfpa.cash13_forecast(config)
    metrics = pyfpa.runway_summary(frame)
    minimum = float(metrics["min_cash"])
    buffer = max(0.0, floor - minimum)
    if not all(math.isfinite(value) for value in (minimum, buffer, config.opening_cash + buffer)):
        raise ValueError("The calculated opening buffer must be finite.")
    buffered = pyfpa.cash13_forecast(config.model_copy(update={"opening_cash": config.opening_cash + buffer}))
    return {"unbuffered": {**metrics, "ending_cash": float(frame["ending_cash"].iloc[-1])},
            "meets_floor_without_buffer": minimum >= floor,
            "additional_opening_buffer": buffer,
            "buffered_opening_cash": config.opening_cash + buffer,
            "buffered": {**pyfpa.runway_summary(buffered),
                         "ending_cash": float(buffered["ending_cash"].iloc[-1])}}


def liquidity_grid(floor=0.0, delays=range(6)):
    delays = tuple(delays)
    if len(delays) != 6 or set(delays) != set(range(6)) or any(type(x) is not int for x in delays):
        raise ValueError("The grid requires the six distinct delay values from 0 to 5.")
    config = pyfpa.load_cash13_config(HERE / "cash13.yaml")
    hires = next(scenario for scenario in pyfpa.load_cash13_scenarios(HERE / "scenarios.yaml")
                 if scenario.name == "Hire two staff from week 5")
    cells = []
    for delay in delays:
        for hiring in (False, True):
            scenario = Scenario(name=f"delay-{delay}-hire-{int(hiring)}",
                                receipts=[FlowChange(name="Wholesale AR collection", delay_weeks=delay)],
                                add_disbursements=hires.add_disbursements if hiring else [])
            changed = pyfpa.apply_scenario(config, scenario)
            cells.append({"delay_weeks": delay, "hiring_package": hiring,
                          **opening_buffer(changed, floor),
                          "one_off_receipts_beyond_horizon": [
                              {"name": flow.name, "amount": flow.amount, "week": flow.start_week}
                              for flow in changed.receipts
                              if flow.recurrence == "once" and flow.start_week > config.weeks]})
    return {"floor": floor, "horizon_weeks": config.weeks, "opening_cash": config.opening_cash,
            "liquidity_fields": {
                "additional_opening_buffer": "max(0, floor minus minimum weekly ending cash), in model currency units",
                "meets_floor_without_buffer": "all weekly ending cash meets the floor; excludes opening cash and intraweek timing",
                "buffered": "a full rerun with the additional opening buffer; no receipts or payments changed"},
            "cells": cells,
            "boundary": "The zero floor is a fabricated demonstration, not an approved liquidity policy. "
                        "An opening buffer is counterfactual cash, not available funding. "
                        "This finite grid does not establish an optimum, intraweek solvency or financing approval."}


def briefing(pack):
    lines = ["# Ridgeline weekly cash constraints", "",
             f"Weekly ending-cash floor: {pack['floor']:,.2f} model currency units. Horizon: {pack['horizon_weeks']} weeks.", "",
             "| Delay weeks | Hiring package | Unbuffered trough | Additional opening buffer | Rerun trough |",
             "|---:|---|---:|---:|---:|"]
    for cell in pack["cells"]:
        lines.append(f"| {cell['delay_weeks']} | {'on' if cell['hiring_package'] else 'off'} | "
                     f"{cell['unbuffered']['min_cash']:,.2f} | {cell['additional_opening_buffer']:,.2f} | "
                     f"{cell['buffered']['min_cash']:,.2f} |")
    lines += ["", "At a five-week delay, the second wholesale collection moves to week 14, "
              "beyond the 13-week horizon. It remains a receipt assumption.", "", pack["boundary"], ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True, help="new directory for the fabricated grid")
    args = parser.parse_args()
    pack = liquidity_grid(args.floor)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "liquidity.json").write_text(json.dumps(pack, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "liquidity.md").write_text(briefing(pack), encoding="utf-8")
    print("CASH CONSTRAINTS QUALIFIED")


if __name__ == "__main__":
    main()
