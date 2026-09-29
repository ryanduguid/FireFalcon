"""Structural review controls for a monthly forecast frame.

Each mutation below changes one field that takes part in exactly one control,
so the review must report exactly that control, for exactly that month, and
nothing else. The forecast comes from cashflow_from_config, whose frame the
controls describe; a generated company model that returns the same columns
can be reviewed the same way.
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pyfpa.analysis.forecast_review import Status, review_forecast
from pyfpa.config.loader import load_config
from pyfpa.models.cashflow import cashflow_from_config


@pytest.fixture
def forecast(sample_config):
    return cashflow_from_config(sample_config)


def codes(review):
    return [(f.code, f.status, f.period) for f in review.findings]


def test_a_forecast_from_the_engine_has_no_findings(sample_config, forecast):
    review = review_forecast(forecast, sample_config)
    assert review.findings == ()
    assert not review.failed


def test_the_shipped_ridgeline_forecast_reviews_clean():
    config = load_config(Path(__file__).resolve().parents[1] / "examples" / "ridgeline" / "config.yaml")
    assert review_forecast(cashflow_from_config(config), config).findings == ()


@pytest.mark.parametrize(
    ("column", "code"),
    [
        ("revenue", "FR-IDENTITY-GROSS-PROFIT"),
        ("opex", "FR-IDENTITY-EBITDA"),
        ("interest", "FR-IDENTITY-PRETAX-INCOME"),
        ("tax", "FR-IDENTITY-NET-INCOME"),
        ("wc_cash_impact", "FR-IDENTITY-OPERATING-CASH-FLOW"),
        ("capex", "FR-IDENTITY-FREE-CASH-FLOW"),
        ("principal", "FR-IDENTITY-CHANGE-IN-CASH"),
    ],
)
def test_one_changed_input_breaks_exactly_its_identity(sample_config, forecast, column, code):
    changed = forecast.copy()
    changed.loc[changed.index[2], column] += 1.0
    review = review_forecast(changed, sample_config)
    assert codes(review) == [(code, Status.FAIL, "2026-03")]
    [finding] = review.findings
    assert finding.observed is not None and finding.expected is not None
    assert abs(finding.observed - finding.expected) == pytest.approx(1.0)
    assert review.failed


def test_a_break_in_the_last_closing_cash_is_a_roll_forward_failure(sample_config, forecast):
    changed = forecast.copy()
    changed.loc[changed.index[-1], "ending_cash"] += 5.0
    review = review_forecast(changed, sample_config)
    assert codes(review) == [("FR-CASH-ROLLFORWARD", Status.FAIL, "2026-12")]
    [finding] = review.findings
    assert finding.observed is not None and finding.expected is not None
    assert finding.observed - finding.expected == pytest.approx(5.0)


def test_the_first_month_rolls_forward_from_the_configured_opening_cash(sample_config, forecast):
    config = sample_config.model_copy(update={
        "opening_balances": sample_config.opening_balances.model_copy(update={"cash": 400.0}),
    })
    review = review_forecast(forecast, config)
    assert codes(review) == [("FR-CASH-ROLLFORWARD", Status.FAIL, "2026-01")]


def test_differences_inside_the_tolerance_are_not_findings(sample_config, forecast):
    changed = forecast.copy()
    changed.loc[changed.index[4], "revenue"] += 0.004
    assert review_forecast(changed, sample_config).findings == ()


@pytest.mark.parametrize(
    ("change", "detail"),
    [
        (lambda f: f.iloc[[0, 1, 1, *range(3, 12)]], "duplicate"),
        (lambda f: f.drop(f.index[5]), "missing"),
        (lambda f: f.iloc[1:], "start"),
        (lambda f: f.iloc[:-1], "length"),
        (lambda f: f.set_axis(pd.RangeIndex(len(f))), "monthly"),
        # Right months, right start and length, but April and May swapped.
        (lambda f: f.iloc[[0, 1, 2, 4, 3, *range(5, 12)]], "order"),
    ],
)
def test_a_malformed_month_index_fails_and_the_roll_forward_is_not_run(sample_config, forecast, change, detail):
    review = review_forecast(change(forecast), sample_config)
    index_findings = [f for f in review.findings if f.code == "FR-INDEX"]
    assert [f.status for f in index_findings] == [Status.FAIL]
    assert detail in index_findings[0].message
    assert ("FR-CASH-ROLLFORWARD", Status.NOT_RUN, None) in codes(review)


def test_a_missing_column_fails_and_the_identities_that_need_it_are_not_run(sample_config, forecast):
    review = review_forecast(forecast.drop(columns=["opex"]), sample_config)
    assert ("FR-MISSING-COLUMN", Status.FAIL, None) in codes(review)
    assert ("FR-IDENTITY-EBITDA", Status.NOT_RUN, None) in codes(review)
    assert not any(code == "FR-IDENTITY-GROSS-PROFIT" for code, _, _ in codes(review))


def test_a_non_finite_value_fails_for_its_column_and_month(sample_config, forecast):
    changed = forecast.copy()
    changed.loc[changed.index[7], "tax"] = math.nan
    review = review_forecast(changed, sample_config)
    assert ("FR-NON-FINITE", Status.FAIL, "2026-08") in codes(review)
    assert all(status is Status.FAIL for code, status, _ in codes(review) if code == "FR-NON-FINITE")
    # The identity that needs tax is reported as not run, not silently skipped.
    assert ("FR-IDENTITY-NET-INCOME", Status.NOT_RUN, "2026-08") in codes(review)


def test_a_value_that_is_not_a_number_is_reported_not_raised(sample_config, forecast):
    changed = forecast.astype(object)
    changed.loc[changed.index[7], "tax"] = "bad"
    review = review_forecast(changed, sample_config)
    assert ("FR-NON-FINITE", Status.FAIL, "2026-08") in codes(review)
    assert ("FR-IDENTITY-NET-INCOME", Status.NOT_RUN, "2026-08") in codes(review)


def test_an_integer_too_large_for_a_float_is_reported_not_raised(sample_config, forecast):
    changed = forecast.astype(object)
    changed.loc[changed.index[7], "tax"] = 10**400
    review = review_forecast(changed, sample_config)
    assert ("FR-NON-FINITE", Status.FAIL, "2026-08") in codes(review)
    assert ("FR-IDENTITY-NET-INCOME", Status.NOT_RUN, "2026-08") in codes(review)


def test_arithmetic_that_overflows_is_not_run_rather_than_failed(sample_config, forecast):
    changed = forecast.copy()
    # pretax_income = ebitda - da - interest holds in exact arithmetic, but
    # 1e308 - (-1e308) overflows a float before interest is taken off.
    changed.loc[changed.index[2], ["ebitda", "da", "interest", "pretax_income"]] = [1e308, -1e308, 1e308, 1e308]
    # The cash roll-forward: March opens at 1e308 and its change adds 1e308 more.
    changed.loc[changed.index[1:3], "ending_cash"] = 1e308
    changed.loc[changed.index[2], "change_in_cash"] = 1e308
    review = review_forecast(changed, sample_config)
    assert ("FR-IDENTITY-PRETAX-INCOME", Status.NOT_RUN, "2026-03") in codes(review)
    assert ("FR-IDENTITY-PRETAX-INCOME", Status.FAIL, "2026-03") not in codes(review)
    assert ("FR-CASH-ROLLFORWARD", Status.NOT_RUN, "2026-03") in codes(review)


def test_integer_arithmetic_is_exact_rather_than_wrapping(sample_config, forecast):
    changed = forecast.astype(object)
    big = np.int64(6_000_000_000_000_000_000)
    changed.loc[changed.index[4], ["net_income", "da", "wc_cash_impact"]] = [big, big, np.int64(0)]
    # 12e18 wrapped at 64 bits: 12,000,000,000,000,000,000 - 2**64.
    changed.loc[changed.index[4], "operating_cash_flow"] = np.int64(-6_446_744_073_709_551_616)
    review = review_forecast(changed, sample_config)
    assert ("FR-IDENTITY-OPERATING-CASH-FLOW", Status.FAIL, "2026-05") in codes(review)


@pytest.mark.parametrize("column", ["ending_cash", "revenue"])
def test_a_duplicate_column_fails_and_the_checks_that_read_it_are_not_run(sample_config, forecast, column):
    # Two identical copies: nothing else is wrong, so only the duplicate can fail.
    changed = pd.concat([forecast, forecast[[column]]], axis=1)
    review = review_forecast(changed, sample_config)
    assert review.failed
    assert ("FR-DUPLICATE-COLUMN", Status.FAIL, None) in codes(review)
    blocked = "FR-CASH-ROLLFORWARD" if column == "ending_cash" else "FR-IDENTITY-GROSS-PROFIT"
    assert (blocked, Status.NOT_RUN, None) in codes(review)


def test_a_non_finite_closing_cash_leaves_its_month_and_the_next_not_run(sample_config, forecast):
    changed = forecast.copy()
    changed.loc[changed.index[4], "ending_cash"] = math.nan
    review = review_forecast(changed, sample_config)
    # May cannot be checked, nor June, whose opening cash is May's closing cash;
    # July onwards is checked again.
    assert [(status, period) for code, status, period in codes(review) if code == "FR-CASH-ROLLFORWARD"] == [
        (Status.NOT_RUN, "2026-05"), (Status.NOT_RUN, "2026-06"),
    ]
