"""PAYG withholding due dates for the payroll settlement model.

Taxation Administration Act 1953, Schedule 1, section 16-75 (checked 29
September 2026 on the ATO legal database):

- (2) a medium withholder pays a month's withholding by the 21st of the next
  month;
- (2A) a medium withholder that is a deferred BAS payer on that 21st pays by
  the 28th instead, and December's withholding by 28 February;
- (3) a small withholder pays a quarter's withholding by the 21st of the month
  after the quarter;
- (4) a small withholder that is a deferred BAS payer pays by 28 October,
  28 February, 28 April or 28 July.

A deferred BAS payer must notify the Commissioner of a BAS amount, does not
lodge monthly GST returns, and has BAS amounts other than medium or large
withholding and annual PAYG instalments (Income Tax Assessment Act 1997,
section 995-1). Its note gives the usual case: an entity that lodges quarterly
GST returns or pays GST by instalments. For a medium withholder the deferral
covers only the last month of each quarter: the ATO issues monthly statements
due on the 21st for the first two months and a quarterly statement due on the
28th for the third (ATO, "Activity statements", registered agent lodgment
program, last updated 1 July 2026).

The dates come from the activity statement rules in `gst_bas.yaml`, with their
weekend adjustment and reviewed_until horizon, so PAYG withholding and GST
share one source. Large withholders, who pay within days of each payday, are
refused. The category and deferred status are the ones that apply to the
entity; a forecast whose withholding grows past a threshold does not change
them.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from pyfpa.au.gst import monthly_activity_statement_due_date, quarterly_bas_due_date
from pyfpa.au.payroll_settlement import DueRule


def _quarter_end(payday: date) -> pd.Period:
    return pd.Period(payday, freq="Q-JUN").asfreq("M", how="end")


def _medium(payday: date) -> date:
    return monthly_activity_statement_due_date(pd.Period(payday, freq="M"))


def _medium_deferred(payday: date) -> date:
    month = pd.Period(payday, freq="M")
    if month == _quarter_end(payday):
        return quarterly_bas_due_date(month)
    return monthly_activity_statement_due_date(month)


def _small(payday: date) -> date:
    return monthly_activity_statement_due_date(_quarter_end(payday))


def _small_deferred(payday: date) -> date:
    return quarterly_bas_due_date(_quarter_end(payday))


def paygw_due_rule(withholder: str, *, deferred_bas_payer: bool) -> DueRule:
    """Due-date rule for PAYG withheld on a payday, for `due_rules["payg_withholding"]`.

    `withholder` is the entity's category, "small" or "medium"; see the module
    docstring for what makes it a deferred BAS payer.
    """
    if withholder == "large":
        raise ValueError("large withholders pay within days of each payday; that timing is not modelled")
    if withholder == "medium":
        return _medium_deferred if deferred_bas_payer else _medium
    if withholder == "small":
        return _small_deferred if deferred_bas_payer else _small
    raise ValueError(f"unknown withholder category {withholder!r}; use 'small' or 'medium'")
