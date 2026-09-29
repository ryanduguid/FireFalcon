"""PAYG instalments for quarterly payers, under Taxation Administration Act 1953, Schedule 1.

Sources, checked 29 September 2026 on the ATO legal database: section 45-61
(a quarter's instalment is due by the 21st of the month after the quarter; a
deferred BAS payer's by the 28th, or 28 February for the December quarter) and
section 45-110 (on the instalment income basis, the instalment is the
applicable instalment rate times the quarter's instalment income) and section
45-112 (otherwise the Commissioner notifies the amount for each quarter). A
weekend moves the date to the Monday, as the pack's BAS dates do.
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


def test_the_amount_method_pays_each_quarters_own_notified_amount():
    schedule = payg_instalment_schedule(INCOME, deferred_bas_payer=True,
                                        notified_amounts={"2026-09": 400.0, "2026-12": 420.0})
    assert schedule["amount"].tolist() == [400.0, 420.0]


def test_a_quarter_the_series_has_not_finished_is_left_out():
    schedule = payg_instalment_schedule(INCOME.iloc[:5], deferred_bas_payer=False, rate=0.05)
    assert schedule["quarter"].tolist() == ["2027Q1"]


def test_payments_by_month_is_ready_for_the_income_year_tax_schedule():
    schedule = payg_instalment_schedule(INCOME, deferred_bas_payer=True, rate=0.05)
    assert payments_by_month(schedule) == {"2026-10": 150.0, "2027-03": 150.0}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rate": 0.05, "notified_amounts": {"2026-09": 400.0}}, "either rate or notified_amounts"),
        ({}, "either rate or notified_amounts"),
        ({"rate": 1.5}, "rate"),
        ({"notified_amounts": {"2026-09": 400.0}}, "no amount for the quarter ending 2026-12"),
        ({"notified_amounts": {"2026-09": -1.0, "2026-12": 0.0}}, "finite amount of 0 or more"),
        ({"notified_amounts": {"2026-09": float("nan"), "2026-12": 0.0}}, "finite amount of 0 or more"),
        ({"notified_amounts": {"2026-09": 1.0, "2026-12": float("inf")}}, "finite amount of 0 or more"),
        ({"notified_amounts": {"2026-09": 1.0, "2026-12": 1.0, "2027-03": 1.0}}, "does not finish: 2027-03"),
    ],
)
def test_the_method_must_be_stated_once(kwargs, message):
    with pytest.raises(ValueError, match=message):
        payg_instalment_schedule(INCOME, deferred_bas_payer=False, **kwargs)


def test_an_amount_for_a_quarter_the_income_does_not_finish_is_refused():
    # Five months finish only the September quarter, so a December amount has
    # no instalment to attach to and would otherwise vanish.
    with pytest.raises(ValueError, match="does not finish: 2026-12"):
        payg_instalment_schedule(INCOME.iloc[:5], deferred_bas_payer=False,
                                 notified_amounts={"2026-09": 1.0, "2026-12": 1.0})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        # July and September without August must not pass as a finished quarter.
        (lambda s: s.drop(s.index[1]), "missing"),
        (lambda s: s.iloc[[0, 1, 1, 2, 3, 4, 5]], "unique"),
        (lambda s: s.where(s.index != s.index[2], float("nan")), "finite"),
    ],
    ids=["gap", "repeat", "nan"],
)
def test_income_must_run_without_gaps_repeats_or_missing_values(change, message):
    with pytest.raises(ValueError, match=message):
        payg_instalment_schedule(change(INCOME), deferred_bas_payer=False, rate=0.05)


def test_income_must_start_at_a_quarter():
    with pytest.raises(ValueError, match="start at the beginning of a quarter"):
        payg_instalment_schedule(INCOME.iloc[1:], deferred_bas_payer=False, rate=0.05)


def test_a_quarter_after_the_reviewed_horizon_is_refused():
    income = pd.Series(1000.0, index=pd.period_range("2027-04", periods=6, freq="M"))
    with pytest.raises(ValueError, match="verified only to 2027-06-30"):
        payg_instalment_schedule(income, deferred_bas_payer=False, rate=0.05)
