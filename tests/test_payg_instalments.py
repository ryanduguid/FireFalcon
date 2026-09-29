"""PAYG instalments for quarterly payers, under Taxation Administration Act 1953, Schedule 1.

Sources, checked 29 September 2026 on the ATO legal database: section 45-61
(a quarter's instalment is due by the 21st of the month after the quarter; a
deferred BAS payer's by the 28th, or 28 February for the December quarter) and
section 45-110 (on the instalment income basis, the instalment is the
applicable instalment rate times the quarter's instalment income). A weekend
moves the date to the Monday, as the pack's BAS dates do.
"""

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.payg_instalments import payg_instalment_schedule, payments_by_month

INCOME = pd.Series(1000.0, index=pd.period_range("2026-07", periods=6, freq="M"))


@pytest.mark.parametrize(
    ("deferred", "dates"),
    [
        (False, [date(2026, 10, 21), date(2027, 1, 21)]),
        # 28 February 2027 is a Sunday.
        (True, [date(2026, 10, 28), date(2027, 3, 1)]),
    ],
)
def test_the_rate_method_takes_the_rate_of_each_quarters_income(deferred, dates):
    schedule = payg_instalment_schedule(INCOME, deferred_bas_payer=deferred, rate=0.05)
    assert schedule["quarter"].tolist() == ["2027Q1", "2027Q2"]
    assert schedule["due_date"].tolist() == dates
    assert schedule["amount"].tolist() == [150.0, 150.0]


def test_the_amount_method_pays_the_notified_amount_each_quarter():
    schedule = payg_instalment_schedule(INCOME, deferred_bas_payer=True, quarterly_amount=400.0)
    assert schedule["amount"].tolist() == [400.0, 400.0]


def test_a_quarter_the_series_has_not_finished_is_left_out():
    schedule = payg_instalment_schedule(INCOME.iloc[:5], deferred_bas_payer=False, rate=0.05)
    assert schedule["quarter"].tolist() == ["2027Q1"]


def test_payments_by_month_is_ready_for_the_income_year_tax_schedule():
    schedule = payg_instalment_schedule(INCOME, deferred_bas_payer=True, rate=0.05)
    assert payments_by_month(schedule) == {"2026-10": 150.0, "2027-03": 150.0}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rate": 0.05, "quarterly_amount": 400.0}, "either rate or quarterly_amount"),
        ({}, "either rate or quarterly_amount"),
        ({"rate": 1.5}, "rate"),
        ({"quarterly_amount": -1.0}, "quarterly_amount"),
    ],
)
def test_the_method_must_be_stated_once(kwargs, message):
    with pytest.raises(ValueError, match=message):
        payg_instalment_schedule(INCOME, deferred_bas_payer=False, **kwargs)


def test_income_must_start_at_a_quarter():
    with pytest.raises(ValueError, match="start at the beginning of a quarter"):
        payg_instalment_schedule(INCOME.iloc[1:], deferred_bas_payer=False, rate=0.05)


def test_a_quarter_after_the_reviewed_horizon_is_refused():
    income = pd.Series(1000.0, index=pd.period_range("2027-04", periods=6, freq="M"))
    with pytest.raises(ValueError, match="verified only to 2027-06-30"):
        payg_instalment_schedule(income, deferred_bas_payer=False, rate=0.05)
