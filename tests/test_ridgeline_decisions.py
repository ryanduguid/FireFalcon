from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock

import pyfpa
from pyfpa import Cash13Config, Scenario, WeeklyFlow

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ridgeline_decisions", ROOT / "examples/ridgeline/decisions.py")
assert spec is not None and spec.loader is not None
decisions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decisions)


def test_ridgeline_decisions_have_exact_weekly_results_and_one_frame_per_scenario() -> None:
    with mock.patch.object(pyfpa, "cash13_forecast", wraps=pyfpa.cash13_forecast) as forecast:
        pack = decisions.decision_pack()
    assert forecast.call_count == len(pack["scenarios"])
    assert [(r["min_cash"], r["min_week"], r["first_negative_week"], r["ending_cash"], r["ending_cash_change"])
            for r in pack["scenarios"]] == [
        (-146000.0, 7, 3, 16000.0, 0.0), (-266000.0, 7, 3, -104000.0, -120000.0),
        (-199200.0, 7, 3, -82800.0, -98800.0), (-164000.0, 7, 3, -29000.0, -45000.0)]
    assert pack["scenarios"][1]["one_off_receipts_beyond_horizon"] == [
        {"name": "Wholesale AR collection", "amount": 120000.0, "week": 14}]
    assert "ending_cash_dec" not in pack["metrics"]
    assert pack["metrics"]["ending_cash"]["unit"] == "model currency units"


def test_briefing_uses_the_result_and_does_not_cache_scenario_numbers() -> None:
    pack = decisions.decision_pack()
    pack["scenarios"][1]["min_cash"] = -123456.0
    pack["scenarios"][1]["first_negative_week"] = 4
    text = decisions.briefing(pack)
    assert "-123,456.00" in text
    assert "First forecast week with negative ending cash: 4." in text
    assert "-266,000.00" not in text
    assert "beyond the horizon; it is not cancelled" in text


def test_zero_is_not_negative_and_repeated_minimum_uses_first_week() -> None:
    cfg = Cash13Config(opening_cash=0.0, weeks=3, receipts=[WeeklyFlow(name="Sales", amount=5.0, start_week=3)])
    row = decisions.decision_pack(cfg, [Scenario(name="same")])["scenarios"][0]
    assert row["min_cash"] == 0.0
    assert row["min_week"] == 1
    assert row["first_negative_week"] is None
