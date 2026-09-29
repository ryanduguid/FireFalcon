from pyfpa.backtest.score import score_forecast
from pyfpa.backtest.snapshot import save_snapshot, snapshot_forecast
from pyfpa.config.schemas import EntityConfig
from pyfpa.models.cashflow import cashflow_from_config
from pyfpa.portfolio.manifest import ClientRef
from pyfpa.portfolio.validate import validate_prior


def _base_cfg(dio, inventory=0.0):
    return EntityConfig.model_validate({
        "name": "c", "start_month": "2026-01", "horizon_months": 12, "tax_rate": 0.0,
        "channels": [{"name": "C", "annual_revenue": 1_200_000.0, "growth_rate": 0.0,
                      "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
        "opex": [], "debt": [],
        "working_capital": {"dso_days": 30.0, "dpo_days": 30.0, "dio_days": dio},
        "opening_balances": {"cash": 0.0, "inventory": inventory},
    })


def _make_client(tmp_path, name, dio, inventory=0.0):
    root = tmp_path / name
    cfg = _base_cfg(dio, inventory)
    snap = snapshot_forecast(cfg, cashflow_from_config(cfg), label="2026", created="2026-01-01")
    snap = snap.model_copy(update={"score": score_forecast(snap.predicted, snap.predicted)})
    (root / ".fpa" / "forecasts").mkdir(parents=True, exist_ok=True)
    save_snapshot(snap, root / ".fpa" / "forecasts" / "2026.snapshot.yaml")
    return ClientRef(path=str(root), type="d2c")


def test_validate_tight_cluster_is_validated(tmp_path):
    clients = [_make_client(tmp_path, n, dio) for n, dio in [("a", 44.0), ("b", 45.0), ("c", 46.0)]]
    res = validate_prior("working_capital.dio_days", clients, tolerance=0.01)
    assert res.n_folds == 3
    assert res.mean_delta <= 0.01
    assert res.validated is True


def test_validate_scattered_not_validated(tmp_path):
    clients = [_make_client(tmp_path, n, dio) for n, dio in [("a", 10.0), ("b", 60.0), ("c", 120.0)]]
    res = validate_prior("working_capital.dio_days", clients, tolerance=0.0)
    assert res.validated is False


def test_a_prior_that_leaves_a_client_no_forecast_fails_validation_without_aborting(tmp_path):
    # Each client opens at its own steady-state stock: cost of sales is 50,000 a
    # month, so 150 days hold 250,000. The peers' median of 20 days sets the first
    # client's January target at 33,333.33, which would need purchases of
    # 50,000 + 33,333.33 - 250,000 < 0, so the engine refuses that fold.
    clients = [
        _make_client(tmp_path, "a", 150.0, inventory=250_000.0),
        _make_client(tmp_path, "b", 20.0, inventory=50_000.0 * 20 / 30),
        _make_client(tmp_path, "c", 20.0, inventory=50_000.0 * 20 / 30),
    ]
    res = validate_prior("working_capital.dio_days", clients, tolerance=1e9)
    assert res.n_folds == 3
    assert res.mean_delta == float("inf")
    assert res.validated is False


def test_validate_too_few_clients(tmp_path):
    clients = [_make_client(tmp_path, "a", 45.0)]
    res = validate_prior("working_capital.dio_days", clients)
    assert res.n_folds == 1
    assert res.validated is False


def test_incomplete_recovered_actuals_do_not_count_as_validation(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("pyfpa.portfolio.validate")
    clients = [_make_client(tmp_path, name, 45) for name in ("a", "b", "c")]
    recover = module.recover_actuals

    def incomplete(snapshot):
        result = recover(snapshot)
        result.pop("ebitda")
        return result

    monkeypatch.setattr(module, "recover_actuals", incomplete)
    result = validate_prior("working_capital.dio_days", clients)
    assert result.n_folds == 0
    assert not result.validated


def test_unrecoverable_actuals_do_not_count_as_validation(tmp_path):
    from pathlib import Path

    from pyfpa.backtest.snapshot import load_snapshot

    clients = [_make_client(tmp_path, name, 45) for name in ("a", "b", "c")]
    for client in clients:
        path = Path(client.path) / ".fpa" / "forecasts" / "2026.snapshot.yaml"
        snapshot = load_snapshot(path)
        snapshot.predicted["ebitda"] = 0.0
        assert snapshot.score is not None
        snapshot.score.per_line["ebitda"] = -1.0
        save_snapshot(snapshot, path, overwrite=True)
    result = validate_prior("working_capital.dio_days", clients)
    assert result.n_folds == 0
    assert not result.validated


def test_repeated_workspaces_cannot_fill_the_folds(tmp_path):
    # F080: one client listed three times used to report 3 folds, zero mean
    # degradation and validated=True, although every peer was a copy of the
    # held-out client.
    import pytest

    client = _make_client(tmp_path, "a", 45.0)
    with pytest.raises(ValueError, match="same workspace twice"):
        validate_prior("working_capital.dio_days", [client, client, client])
