import pandas as pd
import pytest

from pyfpa.models.cashflow import apply_receipt_delay, cashflow_from_config


def test_cashflow_full_forecast(sample_config):
    df = cashflow_from_config(sample_config)
    assert len(df) == 12
    for col in ["revenue", "cogs", "gross_profit", "opex", "ebitda", "interest",
                "pretax_income", "tax", "net_income", "wc_cash_impact",
                "principal", "change_in_cash", "ending_cash"]:
        assert col in df.columns
    assert not df.isna().any().any(), "output DataFrame must contain no NaN values"

    assert round(df["gross_profit"].iloc[0], 6) == 50.0
    assert round(df["ebitda"].iloc[0], 6) == -50.0
    assert round(df["pretax_income"].iloc[0], 6) == -62.0
    assert round(df["net_income"].iloc[0], 6) == -62.0
    assert round(df["change_in_cash"].iloc[0], 6) == -212.0
    assert round(df["ending_cash"].iloc[0], 6) == 288.0
    assert round(df["ending_cash"].iloc[1], 6) == 127.0


def test_nol_shelters_tax():
    from pyfpa.config.schemas import (
        Channel,
        EntityConfig,
        OpeningBalances,
        WorkingCapitalConfig,
    )
    cfg = EntityConfig(
        name="P", start_month="2026-01", horizon_months=12, tax_rate=0.25,
        channels=[Channel(name="C", annual_revenue=2400.0,
                          seasonality=[1.0] * 12, cogs_pct=0.0)],
        working_capital=WorkingCapitalConfig(dso_days=0, dpo_days=0, dio_days=0),
        opening_balances=OpeningBalances(nol=100.0),
    )
    df = cashflow_from_config(cfg)
    # Month 1 pretax = 200 (rev 200, no cogs/opex/interest). NOL 100 shelters
    # 100 -> taxable 100 -> tax 25.
    assert round(df["pretax_income"].iloc[0], 6) == 200.0
    assert round(df["tax"].iloc[0], 6) == 25.0
    # Month 2: NOL exhausted -> taxable 200 -> tax 50.
    assert round(df["tax"].iloc[1], 6) == 50.0


def test_ridgeline_config_runs_end_to_end():
    from pathlib import Path

    from pyfpa.config.loader import load_config
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root / "examples/ridgeline/config.yaml")
    df = cashflow_from_config(cfg)
    assert len(df) == 12
    assert df["ending_cash"].notna().all()
    assert df["revenue"].iloc[0] > 0


def test_ridgeline_golden_snapshot():
    """Locks the flagship demo output. If engine maths changes, update intentionally."""
    from pathlib import Path

    from pyfpa.config.loader import load_config
    repo_root = Path(__file__).resolve().parents[1]
    cf = cashflow_from_config(load_config(repo_root / "examples/ridgeline/config.yaml"))
    # Month-1 working capital impact must be ~0 now that opening balances are
    # steady-state-consistent (regression guard for the opening-balance seam).
    assert abs(cf["wc_cash_impact"].iloc[0]) < 2000
    assert round(cf["revenue"].sum()) == 6000000
    assert round(cf["ebitda"].sum()) == 824000
    assert round(cf["net_income"].sum()) == 572651
    assert round(cf["ending_cash"].iloc[-1]) == 720418
    assert round(cf["ending_cash"].min()) == -85585


@pytest.mark.parametrize("amount", [0.0, 1000.0, -1000.0, 1e20, -1e20])
@pytest.mark.parametrize("position", [0, 5, 11])
def test_receipt_shift_within_one_month_is_an_independent_copy(sample_config, amount, position):
    forecast = cashflow_from_config(sample_config)
    original = forecast.copy()
    month = str(forecast.index[position])
    shifted = apply_receipt_delay(forecast, month, month, amount)
    assert shifted is not forecast
    pd.testing.assert_frame_equal(shifted, original, check_exact=True)
    shifted.iloc[0, 0] += 1
    pd.testing.assert_frame_equal(forecast, original, check_exact=True)


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("target", [0, 2])
def test_receipt_shift_rejects_non_finite_amounts(sample_config, amount, target):
    forecast = cashflow_from_config(sample_config)
    original = forecast.copy()
    with pytest.raises(ValueError, match="finite"):
        apply_receipt_delay(forecast, str(forecast.index[0]), str(forecast.index[target]), amount)
    pd.testing.assert_frame_equal(forecast, original, check_exact=True)


@pytest.mark.parametrize("source,target,amount,flow_delta,cash_delta", [
    (0, 2, 50.0, [-50, 0, 50] + [0] * 9, [-50, -50] + [0] * 10),
    (2, 0, 50.0, [50, 0, -50] + [0] * 9, [50, 50] + [0] * 10),
    (0, 2, -50.0, [50, 0, -50] + [0] * 9, [50, 50] + [0] * 10),
    (0, 2, 0.0, [0] * 12, [0] * 12),
    (0, 11, 50.0, [-50] + [0] * 10 + [50], [-50] * 11 + [0]),
    (5, 11, 50.0, [0] * 5 + [-50] + [0] * 5 + [50], [0] * 5 + [-50] * 6 + [0]),
])
def test_receipt_shift_conserves_cash_and_preserves_other_rows(
    sample_config, source, target, amount, flow_delta, cash_delta
):
    forecast = cashflow_from_config(sample_config)
    original = forecast.copy()
    shifted = apply_receipt_delay(
        forecast, str(forecast.index[source]), str(forecast.index[target]), amount
    )
    flow_columns = ["wc_cash_impact", "operating_cash_flow", "free_cash_flow", "change_in_cash"]
    for column in flow_columns:
        assert (shifted[column] - forecast[column]).tolist() == pytest.approx(flow_delta)
    assert (shifted["ending_cash"] - forecast["ending_cash"]).tolist() == pytest.approx(cash_delta)
    assert shifted["ending_cash"].iloc[-1] == pytest.approx(forecast["ending_cash"].iloc[-1])
    cash_columns = [*flow_columns, "ending_cash"]
    pd.testing.assert_frame_equal(
        shifted.drop(columns=cash_columns), original.drop(columns=cash_columns), check_exact=True
    )
    pd.testing.assert_frame_equal(forecast, original, check_exact=True)


@pytest.mark.parametrize("amount", [50.0, float("nan")])
@pytest.mark.parametrize("month,to_month,field", [
    ("2025-12", "2026-01", "month"),
    ("2026-01", "2027-01", "to_month"),
    ("2027-01", "2027-01", "month"),
])
def test_receipt_shift_keeps_missing_period_errors(sample_config, amount, month, to_month, field):
    forecast = cashflow_from_config(sample_config)
    with pytest.raises(ValueError, match=f"^{field} .* is not a forecast period$"):
        apply_receipt_delay(forecast, month, to_month, amount)
