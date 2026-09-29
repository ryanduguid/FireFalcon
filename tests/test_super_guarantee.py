"""Super guarantee due dates: Payday Super from 1 July 2026, quarterly dates before it.

Sources, checked 29 September 2026: the ATO's "Payment deadlines for Payday
Super" (last updated 10 August 2026: the fund must receive the contribution
within 7 business days after the payday, and a business day is any day but a
weekend or a public holiday for the whole of a state or territory) and
"Quarterly super payment due dates" (last updated 25 February 2026: 28 October,
28 January, 28 April and 28 July for earnings paid up to 30 June 2026, moved to
the next business day from a weekend or public holiday).
"""

from datetime import date, timedelta

import pandas as pd
import pytest
from paydaysuper.calendar import load_calendar

from pyfpa.au.payroll_settlement import monthly_settlement, settlement_events
from pyfpa.au.super_guarantee import super_due_rule


class _Calendar:
    """Weekends and the listed holidays are not business days; complete to coverage_until."""

    def __init__(self, holidays=(), coverage_until=date(2027, 8, 31)):
        self.holidays = set(holidays)
        self.coverage_until = coverage_until

    def add_business_days(self, d, n):
        while n:
            d += timedelta(days=1)
            if d.weekday() < 5 and d not in self.holidays:
                n -= 1
        return d

    def check_horizon(self, d):
        return f"{d.isoformat()} is beyond the calendar's coverage" if d > self.coverage_until else None


# Christmas Day 2026 is a Friday; Boxing Day falls on Saturday and is observed on Monday 28 December.
CHRISTMAS_2026 = (date(2026, 12, 25), date(2026, 12, 28), date(2027, 1, 1))


@pytest.mark.parametrize(
    ("payday", "holidays", "due"),
    [
        # The first Payday Super payday: Wednesday 1 July to Friday 10 July.
        (date(2026, 7, 1), (), date(2026, 7, 10)),
        # A holiday is not a business day: 13 October without it, 14 October with it.
        (date(2026, 10, 2), (), date(2026, 10, 13)),
        (date(2026, 10, 2), (date(2026, 10, 5),), date(2026, 10, 14)),
        (date(2026, 12, 24), CHRISTMAS_2026, date(2027, 1, 7)),
    ],
)
def test_payday_super_is_due_seven_business_days_after_the_payday(payday, holidays, due):
    assert super_due_rule(_Calendar(holidays))(payday) == due


@pytest.mark.parametrize(
    ("payday", "due"),
    [
        (date(2024, 8, 16), date(2024, 10, 28)),
        (date(2025, 11, 14), date(2026, 1, 28)),
        # 28 July 2024 is a Sunday.
        (date(2024, 6, 14), date(2024, 7, 29)),
        (date(2026, 6, 30), date(2026, 7, 28)),
    ],
)
def test_earnings_paid_before_1_july_2026_keep_the_quarterly_due_date(payday, due):
    assert super_due_rule(_Calendar())(payday) == due


def test_june_2026_super_is_still_owed_while_july_payday_super_falls_due():
    months = pd.period_range("2026-06", "2026-07", freq="M")
    payroll = pd.DataFrame(
        {"gross_wages": [10000.0, 10000.0], "bonuses": [0.0, 0.0], "super_guarantee": [1200.0, 1200.0],
         "payroll_tax": [0.0, 0.0], "workers_comp": [0.0, 0.0], "leave_provisions": [0.0, 0.0]},
        index=months,
    )
    events = settlement_events(
        payroll, [date(2026, 6, 26), date(2026, 7, 31)],
        payg_withholding_rate_assumption=0.0,
        due_rules={"super_guarantee": super_due_rule(_Calendar())},
    )
    assert [(e.obligation_date, e.due_date) for e in events if e.component == "super_guarantee"] == [
        (date(2026, 6, 26), date(2026, 7, 28)),
        (date(2026, 7, 31), date(2026, 8, 11)),
    ]
    table = monthly_settlement(events, months)
    assert table["super_guarantee_cash"].tolist() == [0.0, 1200.0]
    assert table["super_guarantee_closing"].tolist() == [1200.0, 1200.0]


def test_a_due_date_past_the_calendar_coverage_is_refused():
    rule = super_due_rule(_Calendar(coverage_until=date(2026, 7, 9)))
    with pytest.raises(ValueError, match="beyond the calendar's coverage"):
        rule(date(2026, 7, 1))


def test_both_horizons_include_their_last_day():
    # A due date on the calendar's last covered day, and a payday on reviewed_until.
    assert super_due_rule(_Calendar(coverage_until=date(2026, 7, 10)))(date(2026, 7, 1)) == date(2026, 7, 10)
    assert super_due_rule(_Calendar())(date(2027, 6, 30)) == date(2027, 7, 9)


def test_a_payday_after_the_reviewed_horizon_is_refused():
    with pytest.raises(ValueError, match="verified only to 2027-06-30"):
        super_due_rule(_Calendar())(date(2027, 7, 2))


def test_the_payday_super_checker_calendar_fits():
    # Labour Day, Monday 5 October 2026, is a public holiday for the whole of
    # NSW, the ACT and SA, so it is not a business day anywhere.
    assert super_due_rule(load_calendar())(date(2026, 10, 2)) == date(2026, 10, 14)
