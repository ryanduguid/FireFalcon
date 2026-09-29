"""Payroll costs turned into dated settlement events, monthly cash and liabilities.

The payroll frame is written by hand for June to August 2026 so every expected
figure can be followed. Due-date rules are supplied by each test; this module
carries no statutory calendar of its own.
"""

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.payroll_settlement import (
    SettlementEvent,
    monthly_settlement,
    settlement_events,
    settlement_weekly_flows,
)

MONTHS = pd.period_range("2026-06", "2026-08", freq="M")
FRIDAYS = {
    "2026-06": [date(2026, 6, 5), date(2026, 6, 12), date(2026, 6, 19), date(2026, 6, 26)],
    "2026-07": [date(2026, 7, 3), date(2026, 7, 10), date(2026, 7, 17), date(2026, 7, 24), date(2026, 7, 31)],
    "2026-08": [date(2026, 8, 7), date(2026, 8, 14), date(2026, 8, 21), date(2026, 8, 28)],
}
PAYDAYS = [day for month in FRIDAYS.values() for day in month]


def _payroll(**overrides: list[float]) -> pd.DataFrame:
    columns = {
        "gross_wages": [4000.0, 5000.0, 4000.0],
        "bonuses": [0.0, 0.0, 0.0],
        "super_guarantee": [480.0, 600.0, 480.0],
        "payroll_tax": [1000.0, 1100.0, 1000.0],
        "workers_comp": [80.0, 100.0, 80.0],
        "leave_provisions": [300.0, 300.0, 300.0],
    }
    columns.update(overrides)
    return pd.DataFrame(columns, index=MONTHS)


def seventh_of_next_month(day: date) -> date:
    following = pd.Period(day, freq="M") + 1
    return date(following.year, following.month, 7)


def twenty_first_of_next_month(day: date) -> date:
    following = pd.Period(day, freq="M") + 1
    return date(following.year, following.month, 21)


def seven_days_later(day: date) -> date:
    return day + pd.Timedelta(days=7)


RULES = {
    "payg_withholding": twenty_first_of_next_month,
    "super_guarantee": seven_days_later,
    "payroll_tax": seventh_of_next_month,
    "workers_comp": seventh_of_next_month,
}


def _events(payroll=None, paydays=PAYDAYS, rules=RULES, rate=0.2, **kwargs):
    return settlement_events(
        _payroll() if payroll is None else payroll, paydays,
        payg_withholding_rate_assumption=rate, due_rules=rules, **kwargs,
    )


def _of(events, component, month=None):
    return [e for e in events if e.component == component and (month is None or str(e.source_period) == month)]


def test_gross_pay_is_split_equally_across_the_months_paydays():
    events = _events()
    # July: 5,000 over five Fridays is 1,000 a payday; 20% withheld.
    net = _of(events, "net_wages", "2026-07")
    withheld = _of(events, "payg_withholding", "2026-07")
    assert [e.amount for e in net] == pytest.approx([800.0] * 5)
    assert [e.amount for e in withheld] == pytest.approx([200.0] * 5)
    assert [e.obligation_date for e in net] == FRIDAYS["2026-07"]
    # Net wages leave on the payday itself.
    assert all(e.due_date == e.cash_date == e.obligation_date for e in net)
    # Super follows each payday: 600 over five paydays.
    assert [e.amount for e in _of(events, "super_guarantee", "2026-07")] == pytest.approx([120.0] * 5)


def test_monthly_costs_arise_at_month_end_and_leave_provisions_are_not_settled():
    events = _events()
    [tax] = _of(events, "payroll_tax", "2026-06")
    assert (tax.obligation_date, tax.due_date, tax.amount) == (date(2026, 6, 30), date(2026, 7, 7), 1000.0)
    assert not [e for e in events if e.component == "leave_provisions"]


def test_a_june_obligation_paid_in_july_is_a_june_liability():
    table = monthly_settlement(_events(), MONTHS)
    assert table.loc[MONTHS[0], "payroll_tax_obligations"] == pytest.approx(1000.0)
    assert table.loc[MONTHS[0], "payroll_tax_cash"] == pytest.approx(0.0)
    assert table.loc[MONTHS[0], "payroll_tax_closing"] == pytest.approx(1000.0)
    assert table.loc[MONTHS[1], "payroll_tax_cash"] == pytest.approx(1000.0)
    # August's tax is due 7 September, after the last month, so it stays owed.
    assert table.loc[MONTHS[2], "payroll_tax_closing"] == pytest.approx(1000.0)


def test_closing_liabilities_roll_forward_exactly_and_cash_adds_up_to_the_events():
    events = _events()
    table = monthly_settlement(events, MONTHS)
    for component in ("net_wages", "payg_withholding", "super_guarantee", "payroll_tax", "workers_comp"):
        previous = 0.0
        for month in MONTHS:
            row = table.loc[month]
            assert row[f"{component}_closing"] == pytest.approx(
                previous + row[f"{component}_obligations"] - row[f"{component}_cash"])
            previous = row[f"{component}_closing"]
    for month in MONTHS:
        dated = sum(e.amount for e in events if pd.Period(e.cash_date, freq="M") == month)
        assert table.loc[month, "total_cash"] == pytest.approx(dated)


def test_weekly_flows_hold_only_payments_inside_the_window():
    events = _events()
    # The window runs from Monday 29 June for 4 weeks, to Sunday 26 July.
    flows = settlement_weekly_flows(events, date(2026, 6, 29), weeks=4)
    in_window = [e for e in events if date(2026, 6, 29) <= e.cash_date <= date(2026, 7, 26)]
    assert sum(f.amount for f in flows) == pytest.approx(sum(e.amount for e in in_window))
    assert all(1 <= f.start_week <= 4 for f in flows)
    # July's first payday (Friday 3 July) is in week 1. The 31 July payday exists
    # but falls after the window, so the equal sums above prove it was left out.
    assert any(f.start_week == 1 and f.name.startswith("net_wages") for f in flows)
    assert [e for e in events if e.cash_date == date(2026, 7, 31)]


def test_paying_early_moves_only_the_cash_date():
    events = _events(pay_days_before_due={"payroll_tax": 2})
    [tax] = _of(events, "payroll_tax", "2026-06")
    assert (tax.due_date, tax.cash_date) == (date(2026, 7, 7), date(2026, 7, 5))


def test_obligations_before_the_first_month_open_the_liability():
    opening = SettlementEvent("payg_withholding", pd.Period("2026-05", freq="M"), date(2026, 5, 29),
                              date(2026, 6, 21), date(2026, 6, 21), 900.0)
    table = monthly_settlement([opening, *_events()], MONTHS)
    # 900 owed at the start, paid 21 June; June's own withholding (800) is due 21 July.
    assert table.loc[MONTHS[0], "payg_withholding_cash"] == pytest.approx(900.0)
    assert table.loc[MONTHS[0], "payg_withholding_closing"] == pytest.approx(800.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rules": {k: v for k, v in RULES.items() if k != "payroll_tax"}}, "payroll_tax has costs but no due rule"),
        ({"paydays": [d for d in PAYDAYS if d.month != 7]}, "2026-07 has payroll costs but no payday"),
        ({"paydays": [*PAYDAYS, date(2026, 9, 4)]}, "2026-09-04 falls outside the payroll months"),
        ({"paydays": [*PAYDAYS, PAYDAYS[0]]}, "repeated"),
        ({"rate": 1.0}, "payg_withholding_rate_assumption"),
        ({"rate": -0.1}, "payg_withholding_rate_assumption"),
        ({"rules": {**RULES, "payroll_tax": lambda d: d - pd.Timedelta(days=1)}}, "due before it arises"),
        ({"pay_days_before_due": {"payroll_tax": 40}}, "paid before it arises"),
        ({"rules": {**RULES, "overtime": seven_days_later}}, "unknown component"),
    ],
)
def test_settlement_refuses_what_it_cannot_place(kwargs, message):
    with pytest.raises(ValueError, match=message):
        _events(**kwargs)


def test_components_with_no_cost_need_no_rule():
    payroll = _payroll(workers_comp=[0.0, 0.0, 0.0])
    rules = {k: v for k, v in RULES.items() if k != "workers_comp"}
    assert not _of(_events(payroll=payroll, rules=rules), "workers_comp")
