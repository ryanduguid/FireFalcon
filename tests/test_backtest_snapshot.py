import pytest
import yaml

from pyfpa.backtest.score import score_forecast
from pyfpa.backtest.snapshot import (
    Snapshot,
    load_snapshot,
    save_snapshot,
    snapshot_forecast,
)
from pyfpa.config.schemas import EntityConfig
from pyfpa.models.cashflow import cashflow_from_config


def _cfg():
    return EntityConfig.model_validate({
        "name": "T", "start_month": "2026-01", "horizon_months": 12, "tax_rate": 0.0,
        "channels": [{"name": "C", "annual_revenue": 1_200_000.0, "growth_rate": 0.0,
                      "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
        "opex": [], "debt": [],
        "working_capital": {"dso_days": 0, "dpo_days": 0, "dio_days": 0},
        "opening_balances": {"cash": 0.0},
    })


def test_snapshot_forecast_captures_assumptions_and_predictions():
    cfg = _cfg()
    snap = snapshot_forecast(cfg, cashflow_from_config(cfg),
                             label="2026", created="2026-02-01")
    assert snap.label == "2026"
    assert snap.assumptions["channels"][0]["annual_revenue"] == 1_200_000.0
    assert snap.predicted["revenue"] == pytest.approx(1_200_000.0)
    assert snap.score is None


def test_snapshot_round_trip(tmp_path):
    cfg = _cfg()
    snap = snapshot_forecast(cfg, cashflow_from_config(cfg),
                             label="2026", created="2026-02-01")
    snap = snap.model_copy(update={"score": score_forecast(snap.predicted, snap.predicted)})
    p = tmp_path / "2026.snapshot.yaml"
    save_snapshot(snap, p)
    back = load_snapshot(p)
    assert back.label == "2026"
    assert back.predicted == snap.predicted
    assert back.score is not None
    assert back.score.fitness == pytest.approx(0.0)
    assert back.assumptions == snap.assumptions


@pytest.mark.parametrize("overwrite,destination_exists", [(False, False), (True, False), (True, True)])
def test_snapshot_serialisation_failure_preserves_destination(tmp_path, overwrite, destination_exists):
    path = tmp_path / "forecast.yaml"
    original = Snapshot(label="Original", created="2026-10-09", assumptions={}, predicted={})
    if destination_exists:
        save_snapshot(original, path)
        original_bytes = path.read_bytes()
    invalid = Snapshot(label="Invalid", created="2026-10-09",
                       assumptions={"unsupported": object()}, predicted={})

    with pytest.raises(yaml.representer.RepresenterError):
        save_snapshot(invalid, path, overwrite=overwrite)

    if destination_exists:
        assert path.read_bytes() == original_bytes
        assert load_snapshot(path) == original
    else:
        assert not path.exists()
