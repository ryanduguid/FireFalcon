"""PAYG instalments for quarterly payers.

Taxation Administration Act 1953, Schedule 1 (checked 29 September 2026 on the
ATO legal database):

- s 45-61: a quarter's instalment is due by the 21st of the month after the
  quarter, or for a deferred BAS payer by the 28th (the December quarter's by
  28 February). The dates come from the activity statement rules in
  `gst_bas.yaml`, with their weekend move and reviewed_until horizon.
- s 45-110: on the instalment income basis, the instalment is the applicable
  instalment rate times the quarter's instalment income.
- s 45-112: otherwise the Commissioner works out and notifies the amount for
  each quarter (the GDP-adjusted notional tax basis).

Instalment income is gross business and investment income excluding GST.
GST-exclusive sales revenue will do only when it is all of an entity's material
instalment income; otherwise pass the full series. Monthly and annual payers,
the two-instalment option and a head company's dates are not modelled.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping

import pandas as pd

from pyfpa.au.gst import (
    _validate_monthly_series,
    monthly_activity_statement_due_date,
    quarterly_bas_due_date,
)


def payg_instalment_schedule(
    instalment_income: pd.Series,
    *,
    deferred_bas_payer: bool,
    rate: float | None = None,
    notified_amounts: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Instalments by quarter: columns quarter, due_date, amount.

    Pass either `rate`, the instalment rate assumed for every quarter and
    applied to each quarter's instalment income, or `notified_amounts`, the
    amount notified for each quarter keyed by the quarter's last month
    ("2026-09"). `instalment_income` is monthly with a PeriodIndex, runs without
    gaps or repeats from the start of an income-year quarter, and holds finite
    amounts; a last quarter it does not finish is left out, because its
    instalment is not yet known. Each notified amount must be finite and 0 or
    more, and must belong to a quarter the schedule includes.
    """
    if (rate is None) == (notified_amounts is None):
        raise ValueError("give either rate or notified_amounts")
    if rate is not None and not 0 <= rate <= 1:
        raise ValueError("rate must be between 0 and 1")
    _validate_monthly_series(instalment_income)
    amounts: Mapping[str, float] = notified_amounts or {}
    index = instalment_income.index
    if not len(index) or index[0].month % 3 != 1:
        raise ValueError("instalment_income must start at the beginning of a quarter (July, October, January or April)")
    rows = []
    scheduled: set[str] = set()
    for quarter, income in instalment_income.groupby(index.asfreq("Q-JUN")):
        quarter_end = quarter.asfreq("M", how="end")
        if quarter_end > index.max():
            continue
        due = quarterly_bas_due_date(quarter_end) if deferred_bas_payer else (
            monthly_activity_statement_due_date(quarter_end))
        if rate is not None:
            amount = rate * float(income.sum())
        else:
            if str(quarter_end) not in amounts:
                raise ValueError(f"notified_amounts has no amount for the quarter ending {quarter_end}")
            amount = float(amounts[str(quarter_end)])
            if not math.isfinite(amount) or amount < 0:
                raise ValueError(
                    f"the notified amount for the quarter ending {quarter_end} must be a finite amount of 0 or more")
        rows.append({"quarter": str(quarter), "due_date": due, "amount": amount})
        scheduled.add(str(quarter_end))
    # An amount for a quarter the schedule leaves out, past the series or not
    # finished by it, would otherwise vanish without a word.
    unused = sorted(set(amounts) - scheduled)
    if unused:
        raise ValueError("notified_amounts names quarters that instalment_income does not finish: "
                         + ", ".join(unused))
    return pd.DataFrame(rows, columns=["quarter", "due_date", "amount"])


def payments_by_month(schedule: pd.DataFrame) -> dict[str, float]:
    """Total instalments by the month they fall due, keyed "YYYY-MM", as income_tax.payments takes them."""
    totals: dict[str, float] = defaultdict(float)
    for due, amount in zip(schedule["due_date"], schedule["amount"], strict=True):
        totals[str(pd.Period(due, freq="M"))] += float(amount)
    return dict(totals)
