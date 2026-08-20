"""Run the Harbour Light Pty Ltd synthetic Australian example.

Usage:
    python3 examples/harbour-light/run_harbour.py
Writes a briefing, live-formula workbook, and 13-week cash forecast.
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

import harbour_model as hm
import pyfpa
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.io.reporting import to_briefing_md


_TITLE = "Harbour Light Pty Ltd"


def run_harbour(output_dir: str | Path) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    monthly = hm.monthly_forecast()
    cash13 = pyfpa.cash13_forecast(hm.cash13_config())
    runway = pyfpa.runway_summary(cash13)
    briefing = to_briefing_md(monthly, title=_TITLE, runway=runway)
    (out / "briefing.md").write_text(briefing)
    model_to_excel(hm.entity_config(), out / "model.xlsx")
    return {
        "revenue_total": round(monthly["revenue"].sum()),
        "ebitda_total": round(monthly["ebitda"].sum()),
        "net_income_total": round(monthly["net_income"].sum()),
        "ending_cash_jun": round(monthly["ending_cash"].iloc[-1]),
        "runway_min_cash": round(runway["min_cash"]),
        "runway_min_week": runway["min_week"],
        "runway_first_negative_week": runway["first_negative_week"],
    }


if __name__ == "__main__":
    figures = run_harbour(HERE / "output")
    print("Wrote briefing.md + model.xlsx to examples/harbour-light/output/")
    for key, value in figures.items():
        print(f"  {key}: {value}")
