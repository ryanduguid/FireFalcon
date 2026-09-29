"""Bad debts and write-offs under a collection profile.

With `bad_debt_share` set, that share of each month's revenue is never
collected: it is recognised as a bad-debt expense in the month of sale (an
allowance) and written off `write_off_after_months` later, when gross
receivables and the allowance fall together with no cash. The collection
profile then adds up to 1 - bad_debt_share, so every recognised dollar is
collected once or written off once. Receipts come straight from the profile;
the balances roll forward from them. Figures are worked out by hand.
"""

import math

import pandas as pd
import pydantic
import pytest

from pyfpa.analysis.divestiture import Carveout, divest
from pyfpa.analysis.forecast_review import review_forecast
from pyfpa.config.schemas import EntityConfig
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.models.cashflow import cashflow_from_config
from pyfpa.models.working_capital import working_capital_from_config

BAD_DEBTS = {"collection_profile": [0.5, 0.45], "bad_debt_share": 0.05, "write_off_after_months": 3}


def _config(working_capital: dict, *, months: int = 12) -> EntityConfig:
    return EntityConfig.model_validate({
        "name": "Debtors", "start_month": "2026-07", "horizon_months": months, "tax_rate": 0.0,
        "channels": [{"name": "C", "annual_revenue": 1200.0, "seasonality": [1.0] * 12, "cogs_pct": 0.0}],
        "working_capital": {"dpo_days": 0, "dio_days": 0, **working_capital},
    })


def _frames(revenue: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.period_range("2026-07", periods=len(revenue), freq="M")
    return pd.DataFrame({"total": revenue}, index=months), pd.DataFrame({"total": [0.0] * len(revenue)}, index=months)


def _rounded(series: pd.Series) -> list[float]:
    return [round(value, 6) for value in series]


def test_one_sale_is_collected_or_written_off_once():
    revenue, cogs = _frames([100, 0, 0, 0, 0])
    df = working_capital_from_config(_config(BAD_DEBTS), revenue, cogs)
    assert _rounded(df["receipts"]) == [50.0, 45.0, 0.0, 0.0, 0.0]
    assert _rounded(df["bad_debts"]) == [5.0, 0.0, 0.0, 0.0, 0.0]
    assert _rounded(df["write_offs"]) == [0.0, 0.0, 0.0, 5.0, 0.0]
    assert _rounded(df["gross_ar"]) == [50.0, 5.0, 5.0, 0.0, 0.0]
    assert _rounded(df["allowance"]) == [5.0, 5.0, 5.0, 0.0, 0.0]
    assert _rounded(df["ar"]) == [45.0, 0.0, 0.0, 0.0, 0.0]
    assert df["receipts"].sum() + df["write_offs"].sum() == pytest.approx(100.0)


def test_the_write_off_moves_neither_net_receivables_nor_cash():
    revenue, cogs = _frames([100, 0, 0, 0, 0])
    df = working_capital_from_config(_config(BAD_DEBTS), revenue, cogs)
    # October: gross receivables and the allowance both fall by 5.
    assert df["d_ar"].iloc[3] == pytest.approx(0.0)
    assert df["wc_cash_impact"].iloc[3] == pytest.approx(0.0)
    # Cash from receivables is receipts less revenue plus the non-cash bad debt,
    # which is also the fall in net receivables.
    direct = df["receipts"] - revenue["total"] + df["bad_debts"]
    assert _rounded(direct) == _rounded(-df["d_ar"])


def test_several_sales_are_each_collected_or_written_off_once():
    revenue, cogs = _frames([100, 200, 300, 0, 0, 0, 0])
    df = working_capital_from_config(_config(BAD_DEBTS), revenue, cogs)
    assert df["receipts"].sum() == pytest.approx(0.95 * 600)
    assert df["write_offs"].sum() == pytest.approx(0.05 * 600)
    assert df["ar"].iloc[-1] == pytest.approx(0.0)
    assert df["gross_ar"].iloc[-1] == pytest.approx(0.0)


def test_amounts_not_yet_collected_or_written_off_stay_in_gross_receivables():
    revenue, cogs = _frames([100, 0])
    df = working_capital_from_config(_config(BAD_DEBTS), revenue, cogs)
    # After two months, the 5 not yet written off stays gross and in the allowance.
    assert _rounded(df["gross_ar"]) == [50.0, 5.0]
    assert _rounded(df["allowance"]) == [5.0, 5.0]
    assert df["write_offs"].sum() == 0.0


def test_without_bad_debts_the_frames_are_unchanged():
    revenue, cogs = _frames([100, 200, 0])
    plain = working_capital_from_config(_config({"collection_profile": [0.5, 0.5]}), revenue, cogs)
    assert "bad_debts" not in plain.columns
    assert "bad_debts" not in cashflow_from_config(_config({"collection_profile": [0.5, 0.5]})).columns


def test_bad_debts_reduce_ebitda_and_profit_but_not_cash():
    config = _config(BAD_DEBTS)
    df = cashflow_from_config(config)
    assert _rounded(df["bad_debts"]) == [5.0] * 12
    assert _rounded(df["ebitda"]) == _rounded(df["gross_profit"] - df["opex"] - df["bad_debts"])
    assert _rounded(df["net_income"]) == [95.0] * 12
    # No tax, costs or depreciation: operating cash is the receipts.
    receipts = working_capital_from_config(config, *_frames([100.0] * 12))["receipts"]
    assert _rounded(df["operating_cash_flow"]) == _rounded(receipts)
    assert review_forecast(df, config).findings == ()


def test_the_review_checks_ebitda_with_the_bad_debts():
    config = _config(BAD_DEBTS)
    df = cashflow_from_config(config)
    tampered = df.copy()
    tampered.loc[tampered.index[2], "bad_debts"] += 1.0
    assert [(f.code, f.status.value, f.period) for f in review_forecast(tampered, config).findings] == [
        ("FR-IDENTITY-EBITDA", "FAIL", "2026-09")
    ]
    broken = df.copy()
    broken.loc[broken.index[2], "bad_debts"] = math.nan
    codes = [(f.code, f.status.value) for f in review_forecast(broken, config).findings]
    assert ("FR-NON-FINITE", "FAIL") in codes and ("FR-IDENTITY-EBITDA", "NOT_RUN") in codes


def test_a_divestiture_keeps_the_bad_debts_in_ebitda():
    config = _config(BAD_DEBTS)
    df = cashflow_from_config(config)
    sold = divest(df, Carveout(revenue=40.0, gross_profit=40.0, opex=0.0),
                  sale_month=3, proceeds=0.0, annual_rate=0.0, tax_rate=0.0)
    # After the sale: 100 of revenue less the unit's 40, less 5 of bad debts
    # held at the source amount, leaves 55 of EBITDA and profit.
    assert _rounded(sold["ebitda"])[3:] == [55.0] * 9
    assert _rounded(sold["net_income"])[3:] == [55.0] * 9
    assert review_forecast(sold, config).findings == ()


@pytest.mark.parametrize(
    ("working_capital", "message"),
    [
        ({"dso_days": 30, "bad_debt_share": 0.05, "write_off_after_months": 3}, "bad_debt_share needs collection_profile"),
        ({"collection_profile": [0.5, 0.45], "bad_debt_share": 0.05}, "needs write_off_after_months"),
        ({"collection_profile": [0.5, 0.5], "write_off_after_months": 3}, "write_off_after_months applies only"),
        ({"collection_profile": [0.5, 0.5], "bad_debt_share": 0.05, "write_off_after_months": 3}, "add up to 0.95"),
        ({"collection_profile": [0.5, 0.45], "bad_debt_share": 0.05, "write_off_after_months": -1}, "greater than or equal"),
        ({"collection_profile": [0.0], "bad_debt_share": 1.0, "write_off_after_months": 0}, "less than 1"),
        # A tiny collectible share must still be collected: an absolute tolerance
        # of 1e-9 would accept nothing, or twice it, and leave receivables behind.
        ({"collection_profile": [0.0], "bad_debt_share": 0.9999999995, "write_off_after_months": 0},
         "collection_profile shares must add up to"),
        ({"collection_profile": [1e-9], "bad_debt_share": 0.9999999995, "write_off_after_months": 0},
         "collection_profile shares must add up to"),
    ],
)
def test_bad_debts_refuse_what_they_cannot_place(working_capital, message):
    with pytest.raises(pydantic.ValidationError, match=message):
        _config(working_capital)


@pytest.mark.parametrize(("share", "collected"), [(0.9999999995, 5e-10), (0.9999999999999999, 1e-16)])
def test_a_tiny_collectible_share_that_completes_the_bad_debt_share_is_accepted(share, collected):
    # 1 - share keeps share's rounding at full size (1 - 0.9999999995 is
    # 5.0000000414e-10 in floating point), so the profile that completes it on
    # paper must still pass.
    config = _config({"collection_profile": [collected], "bad_debt_share": share, "write_off_after_months": 0})
    assert config.working_capital.collection_profile == [collected]


def test_the_excel_export_refuses_bad_debts_before_writing(tmp_path):
    path = tmp_path / "model.xlsx"
    with pytest.raises(ValueError, match="collection_profile"):
        model_to_excel(_config(BAD_DEBTS), path)
    assert not path.exists()
