"""Payroll tax due dates for monthly lodgers, for the payroll settlement model.

`payroll_tax.yaml` holds each jurisdiction's rule, checked 29 September 2026 at
its revenue office. A month's tax is due on the 7th of the next month (the 21st
in the Northern Territory). June's goes into the annual return, due on 21 or 28
July. In NSW, Queensland and the ACT, December's is due on 14 January. Where the
revenue office moves a due date on a weekend or public holiday to the next
business day, this module moves weekend dates; public holidays are not
modelled, so a date on one comes out a day early. RevenueWA and SRO Tasmania
state no such rule for these returns, so their dates are not moved.

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


def payroll_tax_due_rule(jurisdiction: str) -> DueRule:
    """Due-date rule for a monthly lodger's payroll tax, for `due_rules["payroll_tax"]`."""
    rules = load_payroll_tax_data()["due_dates"]
    key = jurisdiction.strip().upper()
    if key not in rules:
        raise ValueError(f"unknown jurisdiction {jurisdiction!r}; expected one of {JURISDICTIONS}")
    rule = rules[key]

    def due(obligation: date) -> date:
        month = pd.Period(obligation, freq="M")
        require_payroll_tax_dates_reviewed(month.end_time.date())
        field = {6: "june_day", 12: "december_day"}.get(month.month, "monthly_day")
        following = month + 1
        result = date(following.year, following.month, rule.get(field, rule["monthly_day"]))
        if rule["next_business_day"]:
            result += timedelta(days={5: 2, 6: 1}.get(result.weekday(), 0))
        return result

    return due
