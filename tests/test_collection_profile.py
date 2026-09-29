"""Receivables collected by a stated profile instead of a days-based balance.

A collection profile gives the share of each month's revenue received in that
month and each following month; the shares add up to one, so every dollar
recognised is collected exactly once. Opening receivables follow their own
profile. Shares that fall after the forecast's last month stay in closing
receivables. Expected figures are worked out by hand in each test.
"""

import pandas as pd
import pydantic
import pytest

from pyfpa.config.schemas import EntityConfig
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.models.working_capital import working_capital_from_config


def _config(working_capital: dict, *, ar: float = 0.0) -> EntityConfig:
    return EntityConfig.model_validate({
        "name": "Profile", "start_month": "2026-07", "horizon_months": 12, "tax_rate": 0.25,
        "channels": [{"name": "C", "annual_revenue": 1200.0, "seasonality": [1.0] * 12, "cogs_pct": 0.0}],
        "working_capital": {"dpo_days": 0, "dio_days": 0, **working_capital},
        "opening_balances": {"ar": ar},
    })


def _frames(revenue: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.period_range("2026-07", periods=len(revenue), freq="M")
    return pd.DataFrame({"total": revenue}, index=months), pd.DataFrame({"total": [0.0] * len(revenue)}, index=months)


def test_each_months_revenue_is_collected_by_the_profile():
    # Receipts: Jul 0.5*100 = 50; Aug 0.5*200 + 0.3*100 = 130;
    # Sep 0.5*300 + 0.3*200 + 0.2*100 = 230; Oct 0.3*300 + 0.2*200 = 130.
    revenue, cogs = _frames([100, 200, 300, 0])
    df = working_capital_from_config(_config({"collection_profile": [0.5, 0.3, 0.2]}), revenue, cogs)
    receipts = revenue["total"] - df["d_ar"]
    assert receipts.round(6).tolist() == [50.0, 130.0, 230.0, 130.0]
    # The last 0.2 of September's 300 falls after October and stays owed.
    assert df["ar"].round(6).tolist() == [50.0, 120.0, 190.0, 60.0]
    assert df["wc_cash_impact"].round(6).tolist() == [-50.0, -70.0, -70.0, 130.0]


def test_collections_after_the_last_month_stay_in_closing_receivables():
    revenue, cogs = _frames([100, 100])
    df = working_capital_from_config(_config({"collection_profile": [0.0, 0.0, 1.0]}), revenue, cogs)
    assert df["ar"].round(6).tolist() == [100.0, 200.0]


def test_opening_receivables_follow_their_own_profile():
    revenue, cogs = _frames([0, 0, 0])
    config = _config({"collection_profile": [1.0], "opening_ar_collection_profile": [0.6, 0.4]}, ar=1000.0)
    df = working_capital_from_config(config, revenue, cogs)
    assert (revenue["total"] - df["d_ar"]).round(6).tolist() == [600.0, 400.0, 0.0]
    assert df["ar"].round(6).tolist() == [400.0, 0.0, 0.0]


def test_collecting_everything_the_next_month_matches_thirty_days():
    # A [0, 1] profile with opening receivables collected in the first month is the
    # days model at DSO 30 for any revenue path, including sharp swings.
    revenue, cogs = _frames([100, 400, 50, 900, 0, 300])
    by_profile = working_capital_from_config(
        _config({"collection_profile": [0.0, 1.0], "opening_ar_collection_profile": [1.0]}, ar=80.0), revenue, cogs)
    by_days = working_capital_from_config(_config({"dso_days": 30}, ar=80.0), revenue, cogs)
    pd.testing.assert_series_equal(by_profile["wc_cash_impact"], by_days["wc_cash_impact"])
    pd.testing.assert_series_equal(by_profile["ar"], by_days["ar"])


@pytest.mark.parametrize(
    ("working_capital", "ar", "message"),
    [
        ({"collection_profile": [0.5, 0.3]}, 0.0, "add up to 1"),
        ({"collection_profile": [1.2, -0.2]}, 0.0, "greater than or equal to 0"),
        ({"collection_profile": [float("nan"), 1.0]}, 0.0, "finite"),
        ({"collection_profile": []}, 0.0, "at least 1"),
        ({"dso_days": 30, "collection_profile": [1.0]}, 0.0, "not both"),
        ({}, 0.0, "dso_days or collection_profile"),
        ({"dso_days": 30, "opening_ar_collection_profile": [1.0]}, 50.0, "only with collection_profile"),
        ({"collection_profile": [1.0]}, 50.0, "opening_ar_collection_profile"),
        ({"collection_profile": [1.0], "opening_ar_collection_profile": [0.5]}, 50.0, "add up to 1"),
    ],
)
def test_a_profile_that_would_lose_or_double_count_revenue_is_refused(working_capital, ar, message):
    with pytest.raises(pydantic.ValidationError, match=message):
        _config(working_capital, ar=ar)


def test_the_excel_export_refuses_a_profile_before_writing_anything(tmp_path):
    path = tmp_path / "profile.xlsx"
    with pytest.raises(ValueError, match="collection_profile"):
        model_to_excel(_config({"collection_profile": [0.5, 0.5]}), path)
    assert not path.exists()
