"""Super guarantee due dates for the payroll settlement model.

The date is when the employee's fund must receive the contribution, from the
rules in `super_guarantee.yaml` (checked 29 September 2026 against the ATO):

- earnings paid from 1 July 2026 fall under Payday Super: within 7 business
  days after the payday, the usual period in Superannuation Guarantee
  (Administration) Act 1992, s 6(1);
- earnings paid before then keep the quarterly dates, 28 October, 28 January,
  28 April and 28 July, moved to the next business day from a weekend or public
  holiday. June 2026 pay is therefore due on 28 July 2026, while July's first
  Payday Super contributions are falling due.

Only the usual period is modelled. The longer periods for a first contribution
to a new fund, out-of-cycle payments, exceptional circumstances and overlapping
due dates can only make a due date later, so these are the earliest dates the
law allows.

Receipt by the fund is not payment by the employer: a clearing house needs
time to process, so set `pay_days_before_due` in `settlement_events` for it.

Business days come from the calendar passed in, which must count a day as a
business day unless it is a weekend or a public holiday for the whole of a
state or territory (s 6(1)). payday-super-checker's calendar does:
`paydaysuper.calendar.load_calendar()`. A due date past the calendar's
coverage, or a payday past the data file's reviewed_until, is refused.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from pyfpa.au.payroll_settlement import DueRule
from pyfpa.au.rates import load_super_guarantee_data, require_super_dates_reviewed


class BusinessCalendar(Protocol):
    def add_business_days(self, d: date, n: int) -> date:
        """The n-th business day after d, not counting d."""
        ...

    def check_horizon(self, d: date) -> str | None:
        """A message when d is past the dates the calendar is complete to, else None."""
        ...


def super_due_rule(calendar: BusinessCalendar) -> DueRule:
    """Due-date rule for super guarantee on a payday, for `due_rules["super_guarantee"]`."""
    data = load_super_guarantee_data()
    payday_super_from: date = data["payday_super_from"]
    usual_period = int(data["usual_period_business_days"])
    quarterly_due = data["quarterly_due"]

    def rule(payday: date) -> date:
        require_super_dates_reviewed(payday)
        if payday >= payday_super_from:
            due = calendar.add_business_days(payday, usual_period)
        else:
            quarter_end = pd.Period(payday, freq="Q-JUN").asfreq("M", how="end")
            day = quarterly_due[f"{quarter_end.month:02d}"]
            year = quarter_end.year + (1 if day["month"] < quarter_end.month else 0)
            # The first business day on or after the quarterly date.
            due = calendar.add_business_days(date(year, day["month"], day["day"]) - timedelta(days=1), 1)
        problem = calendar.check_horizon(due)
        if problem:
            raise ValueError(problem)
        return due

    return rule
