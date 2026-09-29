"""PAYG withholding due dates from the withholder category and activity statement cycle.

Sources, checked 29 September 2026: the ATO's "Paying and reporting PAYG
withholding amounts for small and medium withholders" (small withholders pay
quarterly, medium withholders monthly) and "Due dates for lodging and paying
your BAS" (monthly due on the 21st of the following month; quarterly on 28
October, 28 February, 28 April and 28 July; a weekend or public holiday moves
the date to the next business day, and this pack models weekends only).
"""

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.gst import BasCycle, GstAssumptions, bas_schedule, monthly_gst
from pyfpa.au.paygw import paygw_due_rule
from pyfpa.au.payroll_settlement import settlement_events


@pytest.mark.parametrize(
    ("withholder", "cycle", "payday", "due"),
    [
        ("medium", "monthly", date(2026, 7, 17), date(2026, 8, 21)),
        # 21 November 2026 is a Saturday.
        ("medium", "monthly", date(2026, 10, 30), date(2026, 11, 23)),
        ("small", "monthly", date(2026, 7, 17), date(2026, 8, 21)),
        ("small", "quarterly_bas", date(2026, 8, 14), date(2026, 10, 28)),
        ("small", "quarterly_bas", date(2026, 9, 30), date(2026, 10, 28)),
        # The December quarter is due 28 February, a Sunday in 2027.
        ("small", "quarterly_bas", date(2026, 11, 13), date(2027, 3, 1)),
        ("small", "quarterly_bas", date(2027, 6, 25), date(2027, 7, 28)),
    ],
)
def test_the_due_date_follows_the_activity_statement(withholder, cycle, payday, due):
    assert paygw_due_rule(withholder, cycle)(payday) == due


@pytest.mark.parametrize(
    ("withholder", "cycle", "message"),
    [
        ("large", "monthly", "large withholders"),
        ("medium", "quarterly_bas", "medium withholders pay monthly"),
        ("small", "annual", "cycle"),
        ("tiny", "monthly", "withholder"),
    ],
)
def test_unsupported_arrangements_are_refused(withholder, cycle, message):
    with pytest.raises(ValueError, match=message):
        paygw_due_rule(withholder, cycle)


def test_a_payday_after_the_reviewed_horizon_is_refused():
    rule = paygw_due_rule("medium", "monthly")
    with pytest.raises(ValueError, match="verified only to 2027-06-30"):
        rule(date(2027, 7, 2))


def test_the_bas_schedule_shares_the_horizon():
    months = pd.period_range("2027-04", "2027-09", freq="M")
    revenue = pd.Series([1000.0] * 6, index=months)
    purchases = pd.Series([0.0] * 6, index=months)
    frame = monthly_gst(revenue, purchases)
    with pytest.raises(ValueError, match="verified only to 2027-06-30"):
        bas_schedule(frame["net_gst"], GstAssumptions(bas_cycle=BasCycle.QUARTERLY))


def test_june_withholding_is_owed_at_30_june_and_paid_on_21_july():
    months = pd.period_range("2026-06", "2026-07", freq="M")
    payroll = pd.DataFrame(
        {"gross_wages": [4000.0, 4000.0], "bonuses": [0.0, 0.0], "super_guarantee": [0.0, 0.0],
         "payroll_tax": [0.0, 0.0], "workers_comp": [0.0, 0.0], "leave_provisions": [0.0, 0.0]},
        index=months,
    )
    events = settlement_events(
        payroll, [date(2026, 6, 26), date(2026, 7, 31)],
        payg_withholding_rate_assumption=0.25,
        due_rules={"payg_withholding": paygw_due_rule("medium", "monthly")},
    )
    june = [e for e in events if e.component == "payg_withholding" and str(e.source_period) == "2026-06"]
    assert [(e.obligation_date, e.due_date, e.amount) for e in june] == [(date(2026, 6, 26), date(2026, 7, 21), 1000.0)]
