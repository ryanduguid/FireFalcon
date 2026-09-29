"""PAYG instalments for quarterly payers, under Taxation Administration Act 1953, Schedule 1.

Sources, checked 29 September 2026 on the ATO legal database: section 45-61
(a quarter's instalment is due by the 21st of the month after the quarter; a
deferred BAS payer's by the 28th, or 28 February for the December quarter) and
section 45-110 (on the instalment income basis, the instalment is the
applicable instalment rate times the quarter's instalment income) and section
45-112 (otherwise the Commissioner notifies the amount for each quarter, and a
notice given after the quarter ends makes it due by the 21st day after the
notice, s 45-112(3)). A weekend moves the date to the Monday, as the pack's BAS
dates do; public holidays are not modelled.
"""

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.payg_instalments import (
    NotifiedAmount,
    payg_instalment_schedule,
    payments_by_month,
)

INCOME = pd.Series(1000.0, index=pd.period_range("2026-07", periods=6, freq="M"))


def _notice(amount: float, on: date = date(2026, 9, 1)) -> NotifiedAmount:
    """A notice given before either quarter in INCOME ends."""
    return NotifiedAmount(amount, on)


@pytest.mark.parametrize(
    ("deferred", "dates"),
    [
        (False, [date(2026, 10, 21), date(2027, 1, 21)]),
        # 28 February 2027 is a Sunday. Monday 1 March is Labour Day throughout
        # Western Australia, so s 8AAZMB gives 2 March; public holidays are not
        # modelled, which the guide states.
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
                                        notified_amounts={"2026-09": _notice(400.0), "2026-12": _notice(420.0)})
    assert schedule["amount"].tolist() == [400.0, 420.0]
    assert schedule["due_date"].tolist() == [date(2026, 10, 28), date(2027, 3, 1)]


def test_a_notice_given_after_the_quarter_is_due_21_days_after_it():
    # s 45-112(3): the September quarter notified on 2 November 2026 is due by
    # 23 November, not 21 October; the December notice, given on 31 December,
    # is not after its quarter, so the usual 21 January date stands.
    notices = {"2026-09": _notice(400.0, date(2026, 11, 2)), "2026-12": _notice(420.0, date(2026, 12, 31))}
    schedule = payg_instalment_schedule(INCOME, deferred_bas_payer=False, notified_amounts=notices)
    assert schedule["due_date"].tolist() == [date(2026, 11, 23), date(2027, 1, 21)]


def test_a_notified_amount_needs_its_notice_date():
    with pytest.raises(TypeError, match="NotifiedAmount"):
        payg_instalment_schedule(INCOME, deferred_bas_payer=False,
                                 notified_amounts={"2026-09": 400.0, "2026-12": 420.0})  # type: ignore[dict-item]


def test_a_quarter_the_series_has_not_finished_is_left_out():
    schedule = payg_instalment_schedule(INCOME.iloc[:5], deferred_bas_payer=False, rate=0.05)
    assert schedule["quarter"].tolist() == ["2027Q1"]


def test_payments_by_month_is_ready_for_the_income_year_tax_schedule():
    schedule = payg_instalment_schedule(INCOME, deferred_bas_payer=True, rate=0.05)
    assert payments_by_month(schedule) == {"2026-10": 150.0, "2027-03": 150.0}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rate": 0.05, "notified_amounts": {"2026-09": _notice(400.0)}}, "either rate or notified_amounts"),
        ({}, "either rate or notified_amounts"),
        ({"rate": 1.5}, "rate"),
        ({"notified_amounts": {"2026-09": _notice(400.0)}}, "no amount for the quarter ending 2026-12"),
        ({"notified_amounts": {"2026-09": _notice(-1.0), "2026-12": _notice(0.0)}}, "finite amount of 0 or more"),
        ({"notified_amounts": {"2026-09": _notice(float("nan")), "2026-12": _notice(0.0)}}, "finite amount of 0 or more"),
        ({"notified_amounts": {"2026-09": _notice(1.0), "2026-12": _notice(float("inf"))}}, "finite amount of 0 or more"),
        ({"notified_amounts": {"2026-09": _notice(1.0), "2026-12": _notice(1.0), "2027-03": _notice(1.0)}}, "does not finish: 2027-03"),
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
                                 notified_amounts={"2026-09": _notice(1.0), "2026-12": _notice(1.0)})


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


def test_a_shuffled_index_cannot_pass_a_quarter_that_starts_mid_way():
    # May to August stored July first: every month is there once, but the
    # June quarter holds only May and June and must not become an instalment.
    months = pd.PeriodIndex([pd.Period(m, freq="M") for m in ("2026-07", "2026-05", "2026-06", "2026-08")])
    with pytest.raises(ValueError, match="start at the beginning of a quarter"):
        payg_instalment_schedule(pd.Series(1000.0, index=months), deferred_bas_payer=False, rate=0.05)


def test_a_negative_month_is_refused_even_when_its_quarter_is_positive():
    # Instalment income is gross, so August's -200 cannot net against July and September.
    income = INCOME.where(INCOME.index != INCOME.index[1], -200.0)
    with pytest.raises(ValueError, match="gross income"):
        payg_instalment_schedule(income, deferred_bas_payer=False, rate=0.05)


def test_a_quarter_after_the_reviewed_horizon_is_refused():
    income = pd.Series(1000.0, index=pd.period_range("2027-04", periods=6, freq="M"))
    with pytest.raises(ValueError, match="verified only to 2027-06-30"):
        payg_instalment_schedule(income, deferred_bas_payer=False, rate=0.05)
