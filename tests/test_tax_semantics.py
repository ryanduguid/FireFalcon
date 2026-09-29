"""Income tax in the monthly forecast: current behaviour and a proposed treatment.

The fixture alternates months of 100 and 500 revenue against 300 of fixed cost,
so pretax income alternates -200 and +200 and the income year nets to nil.

`_tax_series` taxes every profitable month and lets only the opening tax loss
shelter income; a loss month never shelters a later profit. The first test pins
that behaviour. The tests marked xfail describe a year-to-date provision: each
month's tax is the change in tax on year-to-date taxable income within the
Australian income year (1 July to 30 June), so the year's tax depends on the
year's result, not on the order of its months. They stay xfail until a treatment
is chosen; strict=True makes an accidental pass fail the suite.
"""

import pytest

from pyfpa.config.schemas import Channel, EntityConfig, OpexLine, WorkingCapitalConfig
from pyfpa.models.cashflow import cashflow_from_config

RATE = 0.25
PENDING = pytest.mark.xfail(strict=True, reason="income-tax treatment not yet chosen; see the pull request")


def _config(seasonality: list[float], *, start: str = "2026-07", months: int = 12) -> EntityConfig:
    return EntityConfig(
        name="Seasonal", start_month=start, horizon_months=months, tax_rate=RATE,
        channels=[Channel(name="C", annual_revenue=3600.0, seasonality=seasonality, cogs_pct=0.0)],
        opex=[OpexLine(name="Fixed", kind="fixed", monthly_amount=300.0)],
        working_capital=WorkingCapitalConfig(dso_days=0, dpo_days=0, dio_days=0),
    )


LOSS_FIRST = [1.0, 5.0] * 6
PROFIT_FIRST = [5.0, 1.0] * 6


def test_current_behaviour_taxes_each_profitable_month_of_a_nil_year():
    df = cashflow_from_config(_config(LOSS_FIRST))
    assert df["pretax_income"].round(6).tolist() == [-200.0, 200.0] * 6
    assert round(df["pretax_income"].sum(), 6) == 0.0
    # Six profitable months at 200 each, taxed at 25% with no shelter from the
    # six loss months: 300 of tax on a year that earned nothing.
    assert round(df["tax"].sum(), 6) == 300.0


@PENDING
@pytest.mark.parametrize("seasonality", [LOSS_FIRST, PROFIT_FIRST])
def test_a_nil_year_carries_no_tax_whatever_the_order_of_its_months(seasonality):
    df = cashflow_from_config(_config(seasonality))
    assert round(df["tax"].sum(), 6) == 0.0


@PENDING
def test_a_loss_after_a_profit_reverses_the_provision():
    df = cashflow_from_config(_config(PROFIT_FIRST))
    # Year to date: +200 then nil, so the provision goes 50 then 0.
    assert round(df["tax"].iloc[0], 6) == 50.0
    assert round(df["tax"].iloc[1], 6) == -50.0


def _june_july(june_weight: float, july_weight: float) -> EntityConfig:
    # Seasonality is keyed by calendar month. With 1,600 of annual revenue and every
    # other weight 1, a weight-5 month earns 500 and a weight-1 month 100, so
    # against 300 of fixed cost the two months are +200 and -200 of pretax income.
    weights = [1.0] * 12
    weights[5], weights[6] = june_weight, july_weight
    config = _config(weights, start="2026-06", months=2)
    channel = config.channels[0].model_copy(update={"annual_revenue": 1600.0})
    return config.model_copy(update={"channels": [channel]})


def test_a_july_loss_never_reverses_the_june_provision():
    # June closes its income year; July's loss belongs to the next one. This holds
    # today and must keep holding under a year-to-date provision.
    df = cashflow_from_config(_june_july(5.0, 1.0))
    assert df["pretax_income"].round(6).tolist() == [200.0, -200.0]
    assert df["tax"].round(6).tolist() == [50.0, 0.0]


@PENDING
def test_a_loss_for_one_income_year_shelters_profit_in_the_next():
    # June's -200 is a loss for the year ending 30 June; carried forward, and assumed
    # available for deduction, it shelters July's +200.
    df = cashflow_from_config(_june_july(1.0, 5.0))
    assert df["pretax_income"].round(6).tolist() == [-200.0, 200.0]
    assert df["tax"].round(6).tolist() == [0.0, 0.0]
