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
  each quarter (the GDP-adjusted notional tax basis); a notice given after
  the quarter ends makes the instalment due by the 21st day after the notice
  (s 45-112(3)), moved past a weekend like the other dates.

Instalment income is gross business and investment income excluding GST, so no
month is negative. GST-exclusive sales revenue will do only when it is all of
an entity's material instalment income; otherwise pass the full series.
Monthly and annual payers, the two-instalment option, a head company's dates
and a change of deferred BAS payer status during the schedule are not modelled.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, timedelta
from typing import NamedTuple

import pandas as pd

from pyfpa.au.gst import (
    _next_business_day,
    _validate_monthly_series,
    monthly_activity_statement_due_date,
    quarterly_bas_due_date,
)


class NotifiedAmount(NamedTuple):
    """An instalment the Commissioner notified, and the day the notice was given."""

    amount: float
    notified_on: date


def payg_instalment_schedule(
    instalment_income: pd.Series,
    *,
    deferred_bas_payer: bool,
    rate: float | None = None,
    notified_amounts: Mapping[str, NotifiedAmount] | None = None,
) -> pd.DataFrame:
    """Instalments by quarter: columns quarter, due_date, amount.

    Pass either `rate`, the instalment rate assumed for every quarter and
    applied to each quarter's instalment income, or `notified_amounts`, a
    `NotifiedAmount` for each quarter keyed by the quarter's last month
    ("2026-09"). `instalment_income` is monthly with a PeriodIndex, covers each
    month once without gaps from the start of an income-year quarter, and holds
    finite amounts of 0 or more; a last quarter it does not finish is left out,
    because its instalment is not yet known. Each notified amount must be finite
    and 0 or more, and must belong to a quarter the schedule includes.
    """
    if (rate is None) == (notified_amounts is None):
        raise ValueError("give either rate or notified_amounts")
    if rate is not None and not 0 <= rate <= 1:
        raise ValueError("rate must be between 0 and 1")
    _validate_monthly_series(instalment_income)
    if (instalment_income < 0).any():
        raise ValueError("instalment_income is gross income, so no month can be negative")
    notices: Mapping[str, NotifiedAmount] = notified_amounts or {}
    if any(not isinstance(notice, NotifiedAmount) for notice in notices.values()):
        raise TypeError("each notified amount must be a NotifiedAmount(amount, notified_on)")
    index = instalment_income.index
    # The earliest month, not the first row: a shuffled index must not pass a
    # quarter that starts mid-way.
    if not len(index) or index.min().month % 3 != 1:
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
            if str(quarter_end) not in notices:
                raise ValueError(f"notified_amounts has no amount for the quarter ending {quarter_end}")
            notice = notices[str(quarter_end)]
            amount = float(notice.amount)
            if not math.isfinite(amount) or amount < 0:
                raise ValueError(
                    f"the notified amount for the quarter ending {quarter_end} must be a finite amount of 0 or more")
            if notice.notified_on > quarter_end.end_time.date():
                due = _next_business_day(notice.notified_on + timedelta(days=21))
        rows.append({"quarter": str(quarter), "due_date": due, "amount": amount})
        scheduled.add(str(quarter_end))
    # An amount for a quarter the schedule leaves out, past the series or not
    # finished by it, would otherwise vanish without a word.
    unused = sorted(set(notices) - scheduled)
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
