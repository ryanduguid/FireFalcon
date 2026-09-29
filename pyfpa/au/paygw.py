"""PAYG withholding due dates for the payroll settlement model.

Small withholders ($25,000 or less a year) pay quarterly and can arrange
monthly activity statements; medium withholders ($25,001 to $1 million) pay
monthly (ATO, "Paying and reporting PAYG withholding amounts for small and
medium withholders", checked 29 September 2026). The dates are the activity
statement due dates in `gst_bas.yaml`, including its weekend adjustment and
its reviewed_until horizon, so PAYG withholding and GST share one source.

Large withholders, who pay within days of each payday, and a medium withholder
reporting GST quarterly (a deferred BAS payer) are refused rather than
approximated. The category is the one the ATO has assigned; a forecast whose
withholding grows past a threshold does not change it.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from pyfpa.au.gst import monthly_activity_statement_due_date, quarterly_bas_due_date
from pyfpa.au.payroll_settlement import DueRule


def _monthly(payday: date) -> date:
    return monthly_activity_statement_due_date(pd.Period(payday, freq="M"))


def _quarterly(payday: date) -> date:
    quarter = pd.Period(payday, freq="Q-JUN")
    return quarterly_bas_due_date(quarter.asfreq("M", how="end"))


def paygw_due_rule(withholder: str, cycle: str) -> DueRule:
    """Due-date rule for PAYG withheld on a payday.

    `withholder` is "small" or "medium"; `cycle` is "monthly" or
    "quarterly_bas". Use the result as `due_rules["payg_withholding"]`.
    """
    if withholder == "large":
        raise ValueError("large withholders pay within days of each payday; that timing is not modelled")
    if withholder not in ("small", "medium"):
        raise ValueError(f"unknown withholder category {withholder!r}; use 'small' or 'medium'")
    if cycle not in ("monthly", "quarterly_bas"):
        raise ValueError(f"unknown activity statement cycle {cycle!r}; use 'monthly' or 'quarterly_bas'")
    if withholder == "medium" and cycle != "monthly":
        raise ValueError("medium withholders pay monthly; a deferred BAS payer arrangement is not modelled")
    return _monthly if cycle == "monthly" else _quarterly
