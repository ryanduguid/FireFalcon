"""PAYG withholding due dates under Taxation Administration Act 1953, Schedule 1, section 16-75.

Sources, checked 29 September 2026: section 16-75 on the ATO legal database;
the deferred BAS payer definition in Income Tax Assessment Act 1997, section
995-1; the ATO's "Activity statements" page for the registered agent lodgment
program (last updated 1 July 2026: a medium withholder with a quarterly
obligation gets monthly statements due on the 21st for the first two months of
a quarter and a quarterly statement due on the 28th for the third); and "Due
dates for lodging and paying your BAS" (a weekend or public holiday moves the
date to the next business day, and this pack models weekends only).
"""

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.gst import BasCycle, GstAssumptions, bas_schedule, monthly_gst
from pyfpa.au.paygw import paygw_due_rule
from pyfpa.au.payroll_settlement import monthly_settlement, settlement_events


@pytest.mark.parametrize(
    ("withholder", "deferred", "payday", "due"),
    [
        # (2): the 21st of the next month, in every month of the quarter.
        ("medium", False, date(2026, 7, 17), date(2026, 8, 21)),
        ("medium", False, date(2026, 9, 25), date(2026, 10, 21)),
        # 21 November 2026 is a Saturday.
        ("medium", False, date(2026, 10, 30), date(2026, 11, 23)),
        # (2A): a deferred BAS payer's third month moves to the 28th; the first
        # two stay on the 21st.
        ("medium", True, date(2026, 8, 14), date(2026, 9, 21)),
        ("medium", True, date(2026, 9, 25), date(2026, 10, 28)),
        # December's withholding is due 28 February, a Sunday in 2027.
        ("medium", True, date(2026, 12, 18), date(2027, 3, 1)),
        # (3): the 21st of the month after the quarter.
        ("small", False, date(2026, 8, 14), date(2026, 10, 21)),
        ("small", False, date(2026, 11, 13), date(2027, 1, 21)),
        # (4): 28 October, 28 February, 28 April or 28 July.
        ("small", True, date(2026, 8, 14), date(2026, 10, 28)),
        ("small", True, date(2026, 9, 30), date(2026, 10, 28)),
        ("small", True, date(2026, 11, 13), date(2027, 3, 1)),
        ("small", True, date(2027, 2, 12), date(2027, 4, 28)),
        ("small", True, date(2027, 6, 25), date(2027, 7, 28)),
    ],
)
def test_the_due_date_follows_section_16_75(withholder, deferred, payday, due):
    assert paygw_due_rule(withholder, deferred_bas_payer=deferred)(payday) == due


@pytest.mark.parametrize(
    ("withholder", "message"),
    [("large", "large withholders"), ("tiny", "unknown withholder category")],
)
def test_unsupported_withholders_are_refused(withholder, message):
    with pytest.raises(ValueError, match=message):
        paygw_due_rule(withholder, deferred_bas_payer=False)


def test_a_payday_after_the_reviewed_horizon_is_refused():
    rule = paygw_due_rule("medium", deferred_bas_payer=False)
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
        due_rules={"payg_withholding": paygw_due_rule("medium", deferred_bas_payer=False)},
    )
    june = [e for e in events if e.component == "payg_withholding" and str(e.source_period) == "2026-06"]
    assert [(e.obligation_date, e.due_date, e.amount) for e in june] == [(date(2026, 6, 26), date(2026, 7, 21), 1000.0)]
    assert monthly_settlement(events, months).loc[months[0], "payg_withholding_closing"] == 1000.0
