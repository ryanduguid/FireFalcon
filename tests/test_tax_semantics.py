"""Income tax in the monthly forecast: the default approximation and the income-year provision.

By default `_tax_series` taxes every profitable month and lets only the opening
tax loss shelter income, so a loss month never shelters a later profit. The first
tests pin that. `income_tax` opts into an income-year provision: each month's tax
is the movement in tax_rate times year-to-date pre-tax income, reset each 1 July,
so a year's tax depends on the year's result, not the order of its months. Cash
then follows the stated tax payments, never the provision.
"""

import pandas as pd
import pytest

from pyfpa.analysis.forecast_review import review_forecast
from pyfpa.config.schemas import (
    Channel,
    EntityConfig,
    IncomeTaxConfig,
    OpexLine,
    WorkingCapitalConfig,
)
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.models.cashflow import (
    _income_year_tax,
    apply_receipt_delay,
    cashflow_from_config,
)

RATE = 0.25


def _config(seasonality: list[float], *, start: str = "2026-07", months: int = 12,
            income_tax: IncomeTaxConfig | None = None) -> EntityConfig:
    return EntityConfig(
        name="Seasonal", start_month=start, horizon_months=months, tax_rate=RATE,
        channels=[Channel(name="C", annual_revenue=3600.0, seasonality=seasonality, cogs_pct=0.0)],
        opex=[OpexLine(name="Fixed", kind="fixed", monthly_amount=300.0)],
        working_capital=WorkingCapitalConfig(dso_days=0, dpo_days=0, dio_days=0),
        income_tax=income_tax,
    )


# Months of 100 and 500 revenue against 300 of fixed cost: pre-tax income
# alternates -200 and +200, and the income year nets to nil.
LOSS_FIRST = [1.0, 5.0] * 6
PROFIT_FIRST = [5.0, 1.0] * 6


def _provision(values: list[float], *, opening_loss: float = 0.0, deductible: bool | None = None) -> list[float]:
    pretax = pd.Series(values, index=pd.period_range("2025-07", periods=len(values), freq="M"))
    return [round(value, 6) for value in _income_year_tax(pretax, opening_loss, RATE, deductible)]


def test_by_default_each_profitable_month_of_a_nil_year_is_taxed():
    df = cashflow_from_config(_config(LOSS_FIRST))
    assert df["pretax_income"].round(6).tolist() == [-200.0, 200.0] * 6
    # Six profitable months at 200, taxed at 25% with no shelter from the six
    # loss months: 300 of tax on a year that earned nothing.
    assert round(df["tax"].sum(), 6) == 300.0
    assert "tax_paid" not in df.columns


def test_by_default_a_july_loss_never_reverses_the_june_provision():
    weights = [1.0] * 12
    weights[5] = 5.0
    config = _config(weights, start="2026-06", months=2)
    config = config.model_copy(update={"channels": [config.channels[0].model_copy(update={"annual_revenue": 1600.0})]})
    df = cashflow_from_config(config)
    assert df["pretax_income"].round(6).tolist() == [200.0, -200.0]
    assert df["tax"].round(6).tolist() == [50.0, 0.0]


@pytest.mark.parametrize("values", [[-200.0, 200.0] * 6, [200.0, -200.0] * 6])
def test_a_nil_income_year_carries_no_tax_whatever_the_order_of_its_months(values):
    assert sum(_provision(values)) == 0.0


def test_a_loss_after_a_profit_reverses_the_provision():
    assert _provision([200.0, -200.0, 200.0])[:2] == [50.0, -50.0]


def test_a_loss_in_a_new_income_year_never_reverses_the_last_one():
    # Twelve profitable months to June 2026, then a July loss in the next year.
    taxes = _provision([200.0] * 12 + [-200.0])
    assert sum(taxes[:12]) == 600.0
    assert taxes[12] == 0.0


def test_the_opening_tax_loss_shelters_income_first_and_its_unused_part_carries_on():
    # 300 of opening loss: FY2026 earns 200, so 100 carries into FY2027.
    taxes = _provision([200.0] + [0.0] * 11 + [200.0], opening_loss=300.0)
    assert taxes[0] == 0.0
    assert taxes[12] == 25.0


@pytest.mark.parametrize(("deductible", "july_tax"), [(True, 0.0), (False, 50.0)])
def test_a_forecast_loss_shelters_the_next_year_only_when_stated_deductible(deductible, july_tax):
    # FY2026 loses 2,400; July 2026 earns 200.
    assert _provision([-200.0] * 12 + [200.0], deductible=deductible)[12] == july_tax


def test_an_unknown_forecast_loss_is_refused_once_it_would_reduce_tax():
    assert _provision([-200.0] * 12 + [-50.0], deductible=None)[12] == 0.0
    with pytest.raises(ValueError, match=r"forecast tax loss of 2,400\.00 would reduce tax .* 2026-07"):
        _provision([-200.0] * 12 + [200.0], deductible=None)


def test_the_provision_is_not_cash_and_the_payments_are():
    config = _config(PROFIT_FIRST, income_tax=IncomeTaxConfig(payments={"2026-10": 30.0}))
    df = cashflow_from_config(config)
    assert round(df["tax"].sum(), 6) == 0.0
    assert df["tax"].round(6).tolist()[:2] == [50.0, -50.0]
    assert df["tax_paid"].tolist() == [0.0, 0.0, 0.0, 30.0] + [0.0] * 8
    # No depreciation and no working capital: operating cash is pre-tax income
    # less the tax paid, whatever the provision does.
    assert (df["operating_cash_flow"] - (df["pretax_income"] - df["tax_paid"])).abs().max() < 1e-9
    assert review_forecast(df, config).findings == ()
    delayed = apply_receipt_delay(df, "2026-08", "2026-09", 10.0)
    assert review_forecast(delayed, config).findings == ()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"start": "2026-06"}, "needs a forecast starting in July"),
        ({"income_tax": IncomeTaxConfig(payments={"2027-07": 10.0})}, "outside the forecast: 2027-07"),
    ],
)
def test_the_income_year_provision_refuses_what_it_cannot_place(kwargs, message):
    arguments = {"income_tax": IncomeTaxConfig(), **kwargs}
    with pytest.raises(ValueError, match=message):
        _config(PROFIT_FIRST, **arguments)


def test_the_excel_export_refuses_the_income_year_provision(tmp_path):
    path = tmp_path / "model.xlsx"
    with pytest.raises(ValueError, match="does not support income_tax"):
        model_to_excel(_config(PROFIT_FIRST, income_tax=IncomeTaxConfig()), path)
    assert not path.exists()
