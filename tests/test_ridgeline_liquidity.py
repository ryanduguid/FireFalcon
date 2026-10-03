"""B101 dispositions apply only to pytest outcome assertions."""

import importlib.util
from pathlib import Path

import pytest

import pyfpa
from pyfpa import Cash13Config, WeeklyFlow

spec = importlib.util.spec_from_file_location("ridgeline_liquidity", Path(__file__).resolve().parents[1] / "examples/ridgeline/liquidity_grid.py")
if spec is None or spec.loader is None:
    raise ImportError("Could not load the Ridgeline liquidity example.")
liquidity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(liquidity)


def test_grid_has_independent_cells_and_preserves_horizon_receipts():
    pack = liquidity.liquidity_grid()
    assert len(pack["cells"]) == 12  # nosec B101
    assert [cell["additional_opening_buffer"] for cell in pack["cells"]] == [  # nosec B101
        146000, 164000, 146000, 164000, 146000, 164000, 208000, 217000, 266000, 284000, 266000, 284000]
    assert all(cell["buffered"]["min_cash"] == 0 and cell["buffered"]["first_negative_week"] is None for cell in pack["cells"])  # nosec B101
    base = pack["cells"][0]
    assert base["unbuffered"] == {"min_cash": -146000.0, "min_week": 7,  # nosec B101
                                 "first_negative_week": 3, "ending_cash": 16000.0}
    assert base["buffered_opening_cash"] == 296000  # nosec B101
    assert base["buffered"]["ending_cash"] == 162000  # nosec B101
    assert pack["cells"][-1]["one_off_receipts_beyond_horizon"] == [  # nosec B101
        {"name": "Wholesale AR collection", "amount": 120000.0, "week": 14}]
    reordered = liquidity.liquidity_grid(delays=reversed(range(6)))
    def key(cell):
        return cell["delay_weeks"], cell["hiring_package"]
    assert {key(cell): cell for cell in pack["cells"]} == {key(cell): cell for cell in reordered["cells"]}  # nosec B101


def test_floor_buffer_is_a_rerun_and_does_not_change_flows():
    cfg = Cash13Config(opening_cash=10, weeks=3,
                       disbursements=[WeeklyFlow(name="payment", amount=5, start_week=2)])
    before = cfg.model_dump()
    for floor, expected in [(0, 0), (5, 0), (9, 4), (-5, 0)]:
        result = liquidity.opening_buffer(cfg, floor)
        assert result["additional_opening_buffer"] == expected  # nosec B101
        initial = pyfpa.cash13_forecast(cfg)
        rerun = pyfpa.cash13_forecast(cfg.model_copy(update={"opening_cash": 10 + expected}))
        assert (rerun["ending_cash"] - initial["ending_cash"]).tolist() == [expected] * 3  # nosec B101
        for column in ("receipts", "disbursements", "net_cash"):
            assert rerun[column].equals(initial[column])  # nosec B101
    assert cfg.model_dump() == before  # nosec B101


@pytest.mark.parametrize("floor", [float("nan"), float("inf"), -float("inf"), True, "0"])
def test_invalid_floor_is_rejected(floor):
    with pytest.raises(ValueError):
        liquidity.liquidity_grid(floor)


class DelayInt(int):
    pass


@pytest.mark.parametrize("delays", [[0], list(range(7)), [0, 0, 1, 2, 3, 4], [False, 1, 2, 3, 4, 5],
                                   [DelayInt(0), 1, 2, 3, 4, 5]])
def test_grid_bounds_are_explicit(delays):
    with pytest.raises(ValueError):
        liquidity.liquidity_grid(delays=delays)
