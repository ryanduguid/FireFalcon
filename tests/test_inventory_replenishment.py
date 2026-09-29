"""Inventory by replenishment: purchases top stock up to the days target, never below nil.

The default days basis sets closing inventory to cost of sales times
dio_days / 30 and refuses a month whose implied purchases would be negative.
`inventory_basis: replenishment` instead buys what the target needs, but never
a negative amount: when stock already exceeds the target, purchases are nil and
the excess carries forward, so closing inventory is opening plus purchases less
cost of sales in every month. Figures are worked out by hand.
"""

import pandas as pd
import pytest

from pyfpa.config.schemas import EntityConfig
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.models.working_capital import working_capital_from_config


def _config(working_capital: dict, *, inventory: float = 0.0, ap: float = 0.0) -> EntityConfig:
    return EntityConfig.model_validate({
        "name": "Stock", "start_month": "2026-07", "horizon_months": 12, "tax_rate": 0.0,
        "channels": [{"name": "C", "annual_revenue": 2400.0, "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
        "working_capital": {"dso_days": 0, "dpo_days": 0, "dio_days": 30, **working_capital},
        "opening_balances": {"inventory": inventory, "ap": ap},
    })


def _frames(cogs: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.period_range("2026-07", periods=len(cogs), freq="M")
    return pd.DataFrame({"total": [0.0] * len(cogs)}, index=months), pd.DataFrame({"total": cogs}, index=months)


REPLENISH = {"inventory_basis": "replenishment"}


def test_excess_stock_is_run_down_and_purchases_restart_when_the_target_needs_them():
    # 30 inventory days make the target one month of cost of sales.
    # Jul: 500 on hand against a 100 target buys nothing; 400 left.
    # Aug: 400 against 100 buys nothing; 300 left.
    # Sep: target 300; 300 on hand less 300 used needs 300 bought; 300 left.
    # Oct: 300 against 100 buys nothing; 200 left.
    df = working_capital_from_config(_config(REPLENISH, inventory=500.0), *_frames([100, 100, 300, 100]))
    assert df["purchases"].tolist() == [0.0, 0.0, 300.0, 0.0]
    assert df["inventory"].tolist() == [400.0, 300.0, 300.0, 200.0]


def test_closing_stock_is_opening_plus_purchases_less_cost_of_sales_every_month():
    cogs = [100.0, 250.0, 50.0, 400.0, 0.0, 120.0]
    df = working_capital_from_config(_config(REPLENISH, inventory=80.0), *_frames(cogs))
    opening = [80.0, *df["inventory"].iloc[:-1]]
    for month, (start, bought, used, closing) in enumerate(zip(opening, df["purchases"], cogs, df["inventory"], strict=True)):
        assert closing == pytest.approx(start + bought - used), month
        assert bought >= 0.0, month


def test_stock_reaches_the_target_whenever_a_purchase_is_needed():
    df = working_capital_from_config(_config(REPLENISH, inventory=100.0), *_frames([100, 200, 300]))
    assert df["purchases"].tolist() == [100.0, 300.0, 400.0]
    assert df["inventory"].tolist() == [100.0, 200.0, 300.0]


def test_the_days_basis_is_unchanged_and_still_refuses_negative_purchases():
    with pytest.raises(ValueError, match="negative purchases"):
        working_capital_from_config(_config({}, inventory=500.0), *_frames([100, 100, 300, 100]))
    df = working_capital_from_config(_config({}, inventory=100.0), *_frames([100, 200, 300]))
    assert "purchases" not in df.columns
    assert df["inventory"].tolist() == [100.0, 200.0, 300.0]


def test_negative_supplier_payments_are_still_refused():
    # 90 payable days: payables go 300 to 900 while August buys 500, so August
    # would pay suppliers 500 - 600 = -100.
    config = _config({**REPLENISH, "dpo_days": 90}, inventory=100.0, ap=300.0)
    with pytest.raises(ValueError, match="negative supplier payments"):
        working_capital_from_config(config, *_frames([100, 300]))


def test_the_excel_export_refuses_replenishment_before_writing(tmp_path):
    path = tmp_path / "model.xlsx"
    with pytest.raises(ValueError, match="does not support inventory_basis"):
        model_to_excel(_config(REPLENISH), path)
    assert not path.exists()
