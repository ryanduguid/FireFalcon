"""Structural review controls for a monthly forecast frame.

Each mutation below changes one field that takes part in exactly one control,
so the review must report exactly that control, for exactly that month, and
nothing else. The forecast comes from cashflow_from_config, whose frame the
controls describe; a generated company model that returns the same columns
can be reviewed the same way.
"""

import math

import pandas as pd
import pytest

from pyfpa.analysis.forecast_review import Status, review_forecast
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
    assert abs(finding.observed - finding.expected) == pytest.approx(1.0)
    assert review.failed


def test_a_break_in_the_last_closing_cash_is_a_roll_forward_failure(sample_config, forecast):
    changed = forecast.copy()
    changed.loc[changed.index[-1], "ending_cash"] += 5.0
    review = review_forecast(changed, sample_config)
    assert codes(review) == [("FR-CASH-ROLLFORWARD", Status.FAIL, "2026-12")]
    [finding] = review.findings
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
    assert all(status is not Status.WARN for _, status, _ in codes(review))
