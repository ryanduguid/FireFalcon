"""Tie every figure in the Lumbridge briefing to the schedule or input it reports.

The generator computes the briefing's two tables, but several sentences carry
figures as written text. A model change that moved a schedule would leave
those sentences stale while the tables regenerated, and nothing would fail.
Each named figure below is read from the committed briefing and compared with
exactly one source: a committed on-time schedule (`monthly.csv`,
`daily-cash.csv`, `results.json`), an input file under `data/`, or, for the
45-day-late case that no committed schedule records, the example's own
forecast run with that delay. A separate test proves the committed files
regenerate unchanged from the inputs.
"""

from __future__ import annotations

import json
import re
import runpy
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pandas as pd
import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "lumbridge-services"
OUTPUT = EXAMPLE / "output"
DATA = EXAMPLE / "data"
GENERATOR = EXAMPLE / "models" / "generated" / "lumbridge.py"
MONEY = r"\(?\$-?[\d,]+(?:\.\d{2})?\)?"


def money(text: str) -> float:
    """'$1,234.50', '$-11,960.00' or '($25,160)' as a signed number."""
    negative = text.startswith("(") or "-" in text
    value = float(re.sub(r"[^\d.]", "", text))
    return -value if negative else value


def day_month(stamp: pd.Timestamp) -> str:
    return f"{stamp.day} {stamp.strftime('%B')}"


@cache
def sources() -> dict:
    monthly = pd.read_csv(OUTPUT / "monthly.csv", index_col=0)
    daily = pd.read_csv(OUTPUT / "daily-cash.csv", index_col="date", parse_dates=["date"])["ending_cash"]
    results = json.loads((OUTPUT / "results.json").read_text(encoding="utf-8"))
    assumptions = json.loads((DATA / "assumptions.json").read_text(encoding="utf-8"))
    opening = pd.read_csv(DATA / "xero_bs.csv").set_index("Account")["Amount"]
    invoices = pd.read_csv(DATA / "invoices.csv", parse_dates=["receipt_date"]).set_index("id")
    late = runpy.run_path(str(GENERATOR))["forecast"](delay_days=45)
    late_daily = late["daily"]["ending_cash"]
    delayed = invoices.loc[assumptions["delay_invoice"]]
    return {
        "monthly": monthly, "daily": daily, "results": results, "assumptions": assumptions,
        "opening": opening, "delayed": delayed, "late_monthly": late["monthly"], "late_daily": late_daily,
    }


def comparison_rows() -> dict[str, tuple[float, float]]:
    s = sources()
    m, lm, r = s["monthly"], s["late_monthly"], s["results"]
    return {
        "Quarter revenue": (r["quarter_revenue"], lm["Revenue"].sum()),
        "Quarter profit before tax": (r["quarter_profit_before_tax"], lm["Profit before tax"].sum()),
        "October closing cash": (m["Closing cash"].iloc[0], lm["Closing cash"].iloc[0]),
        "Minimum daily cash": (r["minimum_daily_cash"], s["late_daily"].min()),
        "December closing cash": (r["december_cash"], lm["Closing cash"].iloc[-1]),
    }


def prose_figures() -> list[tuple[str, str, Callable[[], tuple]]]:
    """(name, pattern with one group per figure, expected values in group order)."""
    s = sources()
    m, a, late_daily = s["monthly"], s["assumptions"], s["late_daily"]
    trough = -late_daily.min()
    return [
        ("base-case profit", rf"The base case earns ({MONEY}) before income tax",
         lambda: (s["results"]["quarter_profit_before_tax"],)),
        ("table delay", r"This monthly table uses a (\d+)-day receipt delay",
         lambda: (s["results"]["delay_days"],)),
        ("opening GST", rf"October includes ({MONEY}) of opening GST",
         lambda: (-s["opening"]["GST"],)),
        ("October instalment", rf"and a ({MONEY}) income tax instalment",
         lambda: (m["Income tax instalment"].iloc[0],)),
        ("first overdrawn day", r"The late case first becomes negative on (\d{1,2} \w+)",
         lambda: (day_month(late_daily[late_daily < 0].index[0]),)),
        ("trough", rf"reaches ({MONEY}) on (\d{{1,2}} \w+)",
         lambda: (late_daily.min(), day_month(late_daily.idxmin()))),
        ("delayed receipt date", r"the delayed receipt arrives on (\d{1,2} \w+)",
         lambda: (day_month(s["delayed"]["receipt_date"] + pd.Timedelta(days=45)),)),
        ("December payables",
         rf"At 31 December, ({MONEY}) GST, ({MONEY}) PAYG withholding and ({MONEY}) supplier invoices remain payable",
         lambda: (m["GST payable"].iloc[-1], m["PAYG withholding payable"].iloc[-1], m["Supplier payables"].iloc[-1])),
        ("loan balance", rf"The loan balance is ({MONEY})",
         lambda: (-s["opening"]["Business Loan"] - m["Loan principal paid"].sum(),)),
        ("leave provisions", rf"the quarter adds ({MONEY}) of unused leave provisions",
         lambda: (m["Leave provision"].sum(),)),
        ("delayed receipt", rf"Confirm the ({MONEY}) OPEN-V receipt date",
         lambda: (s["delayed"]["net"] + s["delayed"]["gst"],)),
        ("trough funding", rf"The 45-day delay needs ({MONEY}) of additional cash at the trough",
         lambda: (trough,)),
        ("buffer funding", rf"or ({MONEY}) to preserve the assumed ({MONEY}) buffer",
         lambda: (trough + a["minimum_cash_buffer"], a["minimum_cash_buffer"])),
        ("run-rate revenue", rf"held at September's fabricated ({MONEY}) monthly run rate",
         lambda: (m["Revenue"].iloc[0],)),
        ("run-rate profit", rf"monthly pre-tax profit remains ({MONEY})",
         lambda: (m["Profit before tax"].iloc[0],)),
    ]


def _same(found: str, expected: float | int | str) -> bool:
    if isinstance(expected, str):
        return found == expected
    if re.fullmatch(r"\d+", found):
        return int(found) == expected
    return bool(money(found) == pytest.approx(float(expected), abs=0.005))


def briefing_mismatches(text: str) -> list[str]:
    """Every named figure that is missing, repeated or different from its source."""
    problems = []
    table = re.findall(rf"^\| ([A-Za-z ]+) \| ({MONEY}) \| ({MONEY}) \|$", text, re.MULTILINE)
    for label, pair in comparison_rows().items():
        rows = [(on_time, late) for name, on_time, late in table if name == label]
        if len(rows) != 1:
            problems.append(f"comparison row {label!r} appears {len(rows)} times")
            continue
        for column, value, source in zip(("on time", "late"), rows[0], pair, strict=True):
            if not _same(value, source):
                problems.append(f"{label} ({column}): briefing {value}, source {source:,.2f}")
    monthly = sources()["monthly"]
    for month, row in monthly.iterrows():
        pattern = rf"^\| {re.escape(str(month))} \| ({MONEY}) \| ({MONEY}) \| ({MONEY}) \|$"
        found = re.findall(pattern, text, re.MULTILINE)
        if len(found) != 1:
            problems.append(f"monthly review row {month} appears {len(found)} times")
            continue
        for value, column in zip(found[0], ("Revenue", "Profit before tax", "Closing cash"), strict=True):
            if not _same(value, row[column]):
                problems.append(f"{month} {column}: briefing {value}, source {row[column]:,.2f}")
    for name, pattern, expected_values in prose_figures():
        found = re.findall(pattern, text)
        if len(found) != 1:
            problems.append(f"{name}: pattern matched {len(found)} times")
            continue
        values = found[0] if isinstance(found[0], tuple) else (found[0],)
        for value, source in zip(values, expected_values(), strict=True):
            if not _same(value, source):
                problems.append(f"{name}: briefing {value}, source {source}")
    return problems


def committed_briefing() -> str:
    return (OUTPUT / "briefing.md").read_text(encoding="utf-8")


def test_every_briefing_figure_matches_its_one_source():
    assert briefing_mismatches(committed_briefing()) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("October includes $12,600 of opening GST", "October includes $12,500 of opening GST"),
        ("| Minimum daily cash | $16,800.00 |", "| Minimum daily cash | $16,700.00 |"),
        ("The loan balance is $17,000", "The loan balance is $18,000"),
        ("reaches ($25,160) on 6 November", "reaches ($25,160) on 7 November"),
    ],
)
def test_a_changed_figure_is_reported(old, new):
    text = committed_briefing()
    assert old in text
    assert briefing_mismatches(text.replace(old, new, 1))


def test_a_missing_or_repeated_figure_is_reported():
    text = committed_briefing()
    sentence = "The loan balance is $17,000"
    assert any("loan balance: pattern matched 0" in p for p in briefing_mismatches(text.replace(sentence, "The loan balance is unchanged")))
    assert any("loan balance: pattern matched 2" in p for p in briefing_mismatches(text + "\n" + sentence + ".\n"))


def test_rewording_prose_that_carries_no_figure_is_not_reported():
    text = committed_briefing()
    old = "Treat the Grand Exchange collection date as an assumption until the customer confirms it."
    assert old in text
    assert briefing_mismatches(text.replace(old, "Confirm the Grand Exchange collection date with the customer.")) == []


def test_the_committed_outputs_regenerate_unchanged(tmp_path):
    runpy.run_path(str(GENERATOR))["run"](tmp_path)
    for name in ("briefing.md", "monthly.csv", "cash13.csv", "daily-cash.csv", "results.json"):
        committed = (OUTPUT / name).read_bytes().replace(b"\r\n", b"\n")
        regenerated = (tmp_path / name).read_bytes().replace(b"\r\n", b"\n")
        assert regenerated == committed, name
