"""Payroll tax due dates for monthly lodgers, from each revenue office's published rules.

Sources, checked 29 September 2026: Revenue NSW key dates (last updated 10
September 2026); SRO Victoria monthly returns and annual reconciliation; the
Queensland Revenue Office due dates (last updated 5 August 2026); RevenueWA
payments; RevenueSA monthly returns and annual reconciliation; SRO Tasmania
returns; ACT Revenue Office lodging returns; and the NT Territory Revenue
Office payroll tax page. Weekend moves follow those pages, WA's Interpretation
Act 1984 s 61 (Saturday and Sunday are excluded days) and Tasmania's Acts
Interpretation Act 1931 s 29(3) (Sunday, not Saturday). The URLs are in
pyfpa/au/data/payroll_tax.yaml.
"""

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.payroll_settlement import monthly_settlement, settlement_events
from pyfpa.au.payroll_tax import payroll_tax_due_rule
from pyfpa.au.rates import JURISDICTIONS, load_payroll_tax_data


@pytest.mark.parametrize(
    ("jurisdiction", "month", "due"),
    [
        # Revenue NSW's published dates: weekends move, December is due on
        # 14 January, and June goes into the annual return on 28 July.
        ("NSW", "2026-10", date(2026, 11, 9)),
        ("NSW", "2026-12", date(2027, 1, 14)),
        ("NSW", "2027-01", date(2027, 2, 8)),
        ("NSW", "2027-06", date(2027, 7, 28)),
        ("VIC", "2026-07", date(2026, 8, 7)),
        ("VIC", "2026-12", date(2027, 1, 7)),
        ("VIC", "2027-06", date(2027, 7, 21)),
        ("QLD", "2026-12", date(2027, 1, 14)),
        ("QLD", "2027-05", date(2027, 6, 7)),
        ("QLD", "2027-06", date(2027, 7, 21)),
        # WA's Interpretation Act s 61 moves Sunday 7 March 2027.
        ("WA", "2027-02", date(2027, 3, 8)),
        ("WA", "2027-06", date(2027, 7, 21)),
        ("SA", "2026-06", date(2026, 7, 28)),
        ("SA", "2027-01", date(2027, 2, 8)),
        # RevenueSA's published date for December 2026.
        ("SA", "2026-12", date(2027, 1, 14)),
        ("TAS", "2026-09", date(2026, 10, 7)),
        # Tasmania moves Sunday 7 March 2027 but not Saturday 7 November 2026.
        ("TAS", "2027-02", date(2027, 3, 8)),
        ("TAS", "2026-10", date(2026, 11, 7)),
        ("TAS", "2027-06", date(2027, 7, 21)),
        ("ACT", "2026-10", date(2026, 11, 9)),
        ("ACT", "2026-12", date(2027, 1, 14)),
        ("ACT", "2027-06", date(2027, 7, 28)),
        # The Territory Revenue Office's own examples: 21 August 2026, and
        # Monday 23 November 2026 because 21 November is a Saturday.
        ("NT", "2026-07", date(2026, 8, 21)),
        ("NT", "2026-10", date(2026, 11, 23)),
        ("NT", "2026-12", date(2027, 1, 21)),
        ("NT", "2027-06", date(2027, 7, 21)),
    ],
)
def test_a_monthly_lodgers_tax_falls_due_on_the_published_date(jurisdiction, month, due):
    month_end = pd.Period(month, freq="M").end_time.date()
    assert payroll_tax_due_rule(jurisdiction)(month_end) == due


def test_public_holidays_are_not_modelled():
    # Revenue NSW publishes 9 June 2026 for May: 7 June is a Sunday and
    # Monday 8 June is the King's Birthday. The rule moves weekends only.
    assert payroll_tax_due_rule("NSW")(date(2026, 5, 31)) == date(2026, 6, 8)


def test_a_dated_rule_covers_only_its_own_month():
    # The dated 14 January 2027 leaves the months around December 2026 on the
    # standing rule, as RevenueSA's table has them: 7 December and 8 February.
    rule = payroll_tax_due_rule("SA")
    assert rule(date(2026, 11, 30)) == date(2026, 12, 7)
    assert rule(date(2027, 1, 31)) == date(2027, 2, 8)


def test_tasmania_moves_its_annual_return_from_either_weekend_day(monkeypatch):
    # 21 July 2029 is a Saturday. The monthly Saturday rule would leave it, but
    # SRO Tasmania's guide moves the annual return to the next working day. The
    # year is past the reviewed horizon, so the horizon check is set aside here.
    monkeypatch.setattr("pyfpa.au.payroll_tax.require_payroll_tax_dates_reviewed", lambda month_end: None)
    assert payroll_tax_due_rule("TAS")(date(2029, 6, 30)) == date(2029, 7, 23)


def test_every_jurisdiction_has_a_rule():
    assert sorted(load_payroll_tax_data()["due_dates"]) == sorted(JURISDICTIONS)


def test_an_unknown_jurisdiction_is_refused():
    with pytest.raises(ValueError, match="unknown jurisdiction"):
        payroll_tax_due_rule("NZ")


def test_a_month_after_the_reviewed_horizon_is_refused():
    with pytest.raises(ValueError, match="verified only to 2027-06-30"):
        payroll_tax_due_rule("VIC")(date(2027, 7, 31))


def test_june_tax_is_paid_with_the_annual_return_in_july():
    months = pd.period_range("2026-05", "2026-07", freq="M")
    zeros = [0.0, 0.0, 0.0]
    payroll = pd.DataFrame(
        {"gross_wages": zeros, "bonuses": zeros, "super_guarantee": zeros, "payroll_tax": [1000.0] * 3,
         "workers_comp": zeros, "leave_provisions": zeros},
        index=months,
    )
    events = settlement_events(
        payroll, [], payg_withholding_rate_assumption=0.0,
        due_rules={"payroll_tax": payroll_tax_due_rule("NSW")},
    )
    assert [e.due_date for e in events] == [date(2026, 6, 8), date(2026, 7, 28), date(2026, 8, 7)]
    table = monthly_settlement(events, months)
    assert table["payroll_tax_cash"].tolist() == [0.0, 1000.0, 1000.0]
    assert table["payroll_tax_closing"].tolist() == [1000.0, 1000.0, 1000.0]
