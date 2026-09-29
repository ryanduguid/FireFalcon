import pandas as pd
import pytest

from pyfpa.config.schemas import EntityConfig, OpeningBalances, WorkingCapitalConfig
from pyfpa.models.cogs import cogs_from_config
from pyfpa.models.revenue import revenue_from_config
from pyfpa.models.working_capital import working_capital_from_config


def test_working_capital_balances_and_cash_impact(sample_config):
    rev = revenue_from_config(sample_config)
    cogs = cogs_from_config(sample_config, rev)
    df = working_capital_from_config(sample_config, rev, cogs)

    # dso=30 -> AR = revenue(100) * 30/30 = 100 every month
    assert df["ar"].round(6).tolist() == [100.0] * 12
    # dpo=30 -> AP = cogs(50) * 30/30 = 50 every month
    assert df["ap"].round(6).tolist() == [50.0] * 12
    # dio=0 -> inventory 0
    assert df["inventory"].round(6).tolist() == [0.0] * 12

    # Month 1 deltas versus opening (all opening = 0): d_ar=100, d_ap=50, d_inv=0
    assert round(df["d_ar"].iloc[0], 6) == 100.0
    assert round(df["d_ap"].iloc[0], 6) == 50.0
    # cash impact month 1 = -100 + 50 - 0 = -50
    assert round(df["wc_cash_impact"].iloc[0], 6) == -50.0
    # month 2 balances flat -> deltas 0 -> cash impact 0
    assert round(df["wc_cash_impact"].iloc[1], 6) == 0.0


# A days-based balance is a month's flow times days/30, so with k = days/30 the
# implied receipts are k*R[t-1] - (k-1)*R[t]. Above 30 days they turn negative
# once revenue grows by more than k/(k-1) in a month; purchases and supplier
# payments fail the same way. The cases below use July to October 2026.


def _frames(revenue: list[float], cogs: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.period_range("2026-07", periods=len(revenue), freq="M")
    return pd.DataFrame({"total": revenue}, index=months), pd.DataFrame({"total": cogs}, index=months)


def _config(base: EntityConfig, *, dso: float = 0, dpo: float = 0, dio: float = 0,
            ar: float = 0, ap: float = 0, inventory: float = 0) -> EntityConfig:
    return base.model_copy(update={
        "working_capital": WorkingCapitalConfig(dso_days=dso, dpo_days=dpo, dio_days=dio),
        "opening_balances": OpeningBalances(ar=ar, ap=ap, inventory=inventory),
    })


def test_a_revenue_jump_that_implies_negative_customer_receipts_is_refused(sample_config):
    # DSO 60 (k=2): AR goes 200 -> 600, so August receipts are 300 - 400 = -100.
    revenue, cogs = _frames([100, 300], [0, 0])
    with pytest.raises(ValueError, match=r"negative customer receipts of -100\.00 in 2026-08"):
        working_capital_from_config(_config(sample_config, dso=60, ar=200), revenue, cogs)


def test_a_cost_fall_that_implies_negative_purchases_is_refused(sample_config):
    # DIO 60: inventory goes 600 -> 200, so August purchases are 100 - 400 = -300.
    revenue, cogs = _frames([0, 0], [300, 100])
    with pytest.raises(ValueError, match=r"negative purchases of -300\.00 in 2026-08"):
        working_capital_from_config(_config(sample_config, dio=60, inventory=600), revenue, cogs)


def test_a_cost_jump_that_implies_negative_supplier_payments_is_refused(sample_config):
    # DPO 60, no inventory: purchases 300 but AP rises 200 -> 600, so payments are -100.
    revenue, cogs = _frames([0, 0], [100, 300])
    with pytest.raises(ValueError, match=r"negative supplier payments of -100\.00 in 2026-08"):
        working_capital_from_config(_config(sample_config, dpo=60, ap=200), revenue, cogs)


def test_the_first_month_is_checked_against_the_opening_balances(sample_config):
    # DSO 60 from a nil opening balance: July AR of 600 needs receipts of 300 - 600 = -300.
    revenue, cogs = _frames([300], [0])
    with pytest.raises(ValueError, match=r"negative customer receipts of -300\.00 in 2026-07"):
        working_capital_from_config(_config(sample_config, dso=60), revenue, cogs)


def test_the_earliest_month_then_the_first_flow_is_reported(sample_config):
    # August has negative receipts and negative purchases, and September would fail
    # too; the error names August's customer receipts.
    revenue, cogs = _frames([100, 300, 900], [300, 100, 100])
    config = _config(sample_config, dso=60, dio=60, ar=200, inventory=600)
    with pytest.raises(ValueError, match=r"customer receipts of -100\.00 in 2026-08"):
        working_capital_from_config(config, revenue, cogs)


def test_flows_of_exactly_zero_are_accepted(sample_config):
    # DSO 45 (k=1.5): revenue tripling gives receipts of 1.5*100 - 0.5*300 = 0.
    revenue, cogs = _frames([100, 300], [0, 0])
    df = working_capital_from_config(_config(sample_config, dso=45, ar=150), revenue, cogs)
    assert df["ar"].tolist() == [150.0, 450.0]
    assert df["wc_cash_impact"].tolist() == [0.0, -300.0]


def test_growth_the_days_model_can_follow_is_unchanged(sample_config):
    # DSO 45 with revenue 100, 200, 150, 250: receipts 100, 50, 225, 100, all positive.
    revenue, cogs = _frames([100, 200, 150, 250], [0, 0, 0, 0])
    df = working_capital_from_config(_config(sample_config, dso=45, ar=150), revenue, cogs)
    assert df["ar"].tolist() == [150.0, 300.0, 225.0, 375.0]
    assert df["wc_cash_impact"].tolist() == [0.0, -150.0, 75.0, -150.0]
