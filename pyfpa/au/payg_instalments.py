"""PAYG instalments for quarterly payers.

Taxation Administration Act 1953, Schedule 1 (checked 29 September 2026 on the
ATO legal database):

- s 45-61: a quarter's instalment is due by the 21st of the month after the
  quarter, or for a deferred BAS payer by the 28th (the December quarter's by
  28 February). The dates come from the activity statement rules in
  `gst_bas.yaml`, with their weekend move and reviewed_until horizon.
- s 45-110: on the instalment income basis, the instalment is the applicable
  instalment rate times the quarter's instalment income. Otherwise the ATO
  notifies an amount (the GDP-adjusted notional tax basis).

Monthly and annual payers, the two-instalment option and a head company's
dates are not modelled. Instalment income here is whatever series the caller
passes, such as GST-exclusive revenue as a proxy for ordinary income.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from pyfpa.au.gst import monthly_activity_statement_due_date, quarterly_bas_due_date


def payg_instalment_schedule(
    instalment_income: pd.Series,
    *,
    deferred_bas_payer: bool,
    rate: float | None = None,
    quarterly_amount: float | None = None,
) -> pd.DataFrame:
    """Instalments by quarter: columns quarter, due_date, amount.

    Pass either `rate` (the instalment rate, applied to each quarter's
    instalment income) or `quarterly_amount` (the amount the ATO notified).
    `instalment_income` is monthly with a PeriodIndex and must start at the
    beginning of an income-year quarter; a last quarter it does not finish is
    left out, because its instalment is not yet known.
    """
    if (rate is None) == (quarterly_amount is None):
        raise ValueError("give either rate or quarterly_amount")
    if rate is not None and not 0 <= rate <= 1:
        raise ValueError("rate must be between 0 and 1")
    if quarterly_amount is not None and quarterly_amount < 0:
        raise ValueError("quarterly_amount must be 0 or more")
    index = instalment_income.index
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != "M" or not len(index):
        raise ValueError("instalment_income needs a monthly PeriodIndex")
    if index[0].month % 3 != 1:
        raise ValueError("instalment_income must start at the beginning of a quarter (July, October, January or April)")
    rows = []
    for quarter, income in instalment_income.groupby(index.asfreq("Q-JUN")):
        quarter_end = quarter.asfreq("M", how="end")
        if quarter_end > index.max():
            continue
        due = quarterly_bas_due_date(quarter_end) if deferred_bas_payer else (
            monthly_activity_statement_due_date(quarter_end))
        amount = rate * float(income.sum()) if rate is not None else float(quarterly_amount or 0.0)
        rows.append({"quarter": str(quarter), "due_date": due, "amount": amount})
    return pd.DataFrame(rows, columns=["quarter", "due_date", "amount"])


def payments_by_month(schedule: pd.DataFrame) -> dict[str, float]:
    """Total instalments by the month they fall due, keyed "YYYY-MM", as income_tax.payments takes them."""
    totals: dict[str, float] = defaultdict(float)
    for due, amount in zip(schedule["due_date"], schedule["amount"], strict=True):
        totals[str(pd.Period(due, freq="M"))] += float(amount)
    return dict(totals)
