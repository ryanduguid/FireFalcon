"""Payroll tax due dates for monthly lodgers, for the payroll settlement model.

`payroll_tax.yaml` holds each jurisdiction's rule, checked 29 September 2026 at
its revenue office. A month's tax is due on the 7th of the next month (the 21st
in the Northern Territory). June's goes into the annual return, due on 21 or 28
July. In NSW, Queensland and the ACT, December's is due on 14 January; for SA
the data holds RevenueSA's published 14 January 2027 for December 2026 only,
because its Christmas extensions are discretionary. A due date on a weekend
moves to the next day, except that Tasmania moves a monthly date from a Sunday
but not a Saturday (Acts Interpretation Act 1931 (Tas) s 29(3)); its annual
return moves from either weekend day, as SRO Tasmania's employer guide says.
Public holidays are not modelled, so a date on one comes out a day early.

The forecast's monthly payroll tax is an annualised estimate, so the annual
return has no adjustment to time: June's amount is paid on the annual return's
due date. Annual, quarterly and half-yearly lodgers pay later than these dates
and are not modelled. One jurisdiction's dates apply to the whole payroll_tax
column, which sums every jurisdiction, so an employer in several needs a
forecast for each to time each one's tax.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from pyfpa.au.payroll_settlement import DueRule
from pyfpa.au.rates import (
    JURISDICTIONS,
    load_payroll_tax_data,
    require_payroll_tax_dates_reviewed,
)

_WEEKEND = {"Saturday": 5, "Sunday": 6}


def payroll_tax_due_rule(jurisdiction: str) -> DueRule:
    """Due-date rule for a monthly lodger's payroll tax, for `due_rules["payroll_tax"]`."""
    rules = load_payroll_tax_data()["due_dates"]
    key = jurisdiction.strip().upper()
    if key not in rules:
        raise ValueError(f"unknown jurisdiction {jurisdiction!r}; expected one of {JURISDICTIONS}")
    rule = rules[key]
    moved = {_WEEKEND[day] for day in rule["weekend_days_moved"]}
    june_moved = {_WEEKEND[day] for day in rule.get("june_weekend_days_moved", rule["weekend_days_moved"])}

    def due(obligation: date) -> date:
        month = pd.Period(obligation, freq="M")
        require_payroll_tax_dates_reviewed(month.end_time.date())
        published: date | None = rule.get("dated", {}).get(str(month))
        if published:
            return published
        field = {6: "june_day", 12: "december_day"}.get(month.month, "monthly_day")
        following = month + 1
        result = date(following.year, following.month, rule.get(field, rule["monthly_day"]))
        while result.weekday() in (june_moved if month.month == 6 else moved):
            result += timedelta(days=1)
        return result

    return due
