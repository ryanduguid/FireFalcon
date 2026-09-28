import math

import pandas as pd
import pytest
from pydantic import ValidationError

from pyfpa.config.schemas import (
    Channel,
    EntityConfig,
    OpeningBalances,
    OpexLine,
    WorkingCapitalConfig,
)
from pyfpa.models.cashflow import apply_receipt_delay, cashflow_from_config


@pytest.fixture
def finite_config():
    return EntityConfig(
        name="Synthetic forecast",
        start_month="2026-01",
        tax_rate=0,
        channels=[Channel(name="Sales", annual_revenue=1200,
                          seasonality=[1.0] * 12, cogs_pct=0)],
        working_capital=WorkingCapitalConfig(dso_days=0, dpo_days=0, dio_days=0),
    )


@pytest.mark.parametrize("weights", [[1e308] * 12, [1e308, 1e308] + [0.0] * 10])
def test_seasonality_rejects_overflowed_total(weights):
    with pytest.raises(ValidationError, match="seasonality weights must sum to a finite number"):
        Channel(name="Sales", annual_revenue=1200, seasonality=weights, cogs_pct=0)


@pytest.mark.parametrize("in_place", [False, True])
def test_forecast_rejects_mutated_seasonality_total(finite_config, in_place):
    if in_place:
        finite_config.channels[0].seasonality[:] = [1e308] * 12
    else:
        finite_config.channels[0].seasonality = [1e308] * 12

    with pytest.raises(ValueError, match="seasonality weights must sum to a finite number"):
        cashflow_from_config(finite_config)


def test_large_finite_seasonality_preserves_revenue(finite_config):
    weights = [1e307] * 12
    finite_config.channels = [Channel(name="Sales", annual_revenue=1200,
                                     seasonality=weights, cogs_pct=0)]

    forecast = cashflow_from_config(finite_config)

    assert finite_config.channels[0].seasonality == weights
    assert forecast["revenue"].tolist() == pytest.approx([100.0] * 12)
    assert forecast["ending_cash"].iloc[-1] == pytest.approx(1200)


def test_large_finite_forecast_is_allowed(finite_config):
    finite_config.channels[0].annual_revenue = 1e308

    forecast = cashflow_from_config(finite_config)

    assert all(math.isfinite(value) for value in forecast.to_numpy().flat)
    assert forecast["ending_cash"].iloc[-1] == pytest.approx(1e308)


def test_forecast_rejects_growth_overflow(finite_config):
    finite_config.channels[0].annual_revenue = 1e308
    finite_config.channels[0].growth_rate = 1
    finite_config.horizon_months = 120

    with pytest.raises(ValueError, match="^revenue contains non-finite values$"):
        cashflow_from_config(finite_config)


def test_forecast_rejects_intermediate_cost_overflow(finite_config):
    finite_config.opex = [
        OpexLine(name=name, kind="fixed", monthly_amount=1e308)
        for name in ("Synthetic cost A", "Synthetic cost B")
    ]

    with pytest.raises(ValueError, match="^opex contains non-finite values$"):
        cashflow_from_config(finite_config)


@pytest.mark.parametrize(
    "annual_revenue, opening_cash, capex",
    [(1e308, 1e308, 0), (1200, -1e308, 1e307)],
)
def test_forecast_rejects_cash_accumulation_overflow(
    finite_config, annual_revenue, opening_cash, capex
):
    finite_config.channels[0].annual_revenue = annual_revenue
    finite_config.opening_balances = OpeningBalances(cash=opening_cash)
    finite_config.capex_monthly = capex

    with pytest.raises(ValueError, match="^ending_cash contains non-finite values$"):
        cashflow_from_config(finite_config)


@pytest.mark.parametrize("opening_cash, amount", [(1e308, -1e308), (-1e308, 1e308)])
def test_receipt_shift_rejects_cash_overflow_without_mutating_input(
    finite_config, opening_cash, amount
):
    finite_config.opening_balances = OpeningBalances(cash=opening_cash)
    forecast = cashflow_from_config(finite_config)
    original = forecast.copy(deep=True)

    with pytest.raises(ValueError, match="^ending_cash contains non-finite values$"):
        apply_receipt_delay(forecast, "2026-01", "2026-03", amount)

    pd.testing.assert_frame_equal(forecast, original)


@pytest.mark.parametrize("amount", [1e308, -1e308])
def test_large_finite_receipt_shift_is_allowed(finite_config, amount):
    finite_config.channels[0].annual_revenue = 0
    forecast = cashflow_from_config(finite_config)
    original = forecast.copy(deep=True)

    shifted = apply_receipt_delay(forecast, "2026-01", "2026-03", amount)

    assert all(math.isfinite(value) for value in shifted.to_numpy().flat)
    assert shifted["ending_cash"].tolist() == pytest.approx([-amount, -amount] + [0.0] * 10)
    assert shifted["ending_cash"].iloc[-1] == forecast["ending_cash"].iloc[-1]
    pd.testing.assert_frame_equal(forecast, original)


@pytest.mark.parametrize("amount", [1e308, -1e308])
def test_large_same_month_shift_remains_an_independent_copy(finite_config, amount):
    finite_config.opening_balances = OpeningBalances(cash=1e308)
    forecast = cashflow_from_config(finite_config)

    shifted = apply_receipt_delay(forecast, "2026-01", "2026-01", amount)

    pd.testing.assert_frame_equal(shifted, forecast)
    shifted.iloc[0, 0] = -1
    assert forecast.iloc[0, 0] == 100


def test_receipt_shift_preserves_unrelated_columns(finite_config):
    forecast = cashflow_from_config(finite_config)
    forecast["note"] = "Synthetic scenario"
    forecast["external_estimate"] = float("nan")

    shifted = apply_receipt_delay(forecast, "2026-01", "2026-03", 50)

    pd.testing.assert_frame_equal(
        shifted[["note", "external_estimate"]], forecast[["note", "external_estimate"]]
    )
    assert shifted["ending_cash"].tolist() == pytest.approx(
        [50, 150, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200]
    )
