from pathlib import Path

import pytest
from pydantic import ValidationError

from pyfpa.config.loader import load_config
from pyfpa.config.schemas import (
    Channel,
    EntityConfig,
    WorkingCapitalConfig,
)


def _minimal_kwargs():
    return {
        "name": "X",
        "start_month": "2026-01",
        "tax_rate": 0.30,
        "channels": [Channel(name="D2C", annual_revenue=1200.0,
                             seasonality=[1.0] * 12, cogs_pct=0.5)],
        "working_capital": WorkingCapitalConfig(dso_days=30, dpo_days=30, dio_days=0),
    }


def test_entity_config_defaults():
    cfg = EntityConfig(**_minimal_kwargs())
    assert cfg.horizon_months == 12
    assert cfg.opening_balances.cash == 0.0


def test_a_config_without_a_tax_rate_is_refused():
    """No default fits: 0.21 was the US federal rate, and an Australian company
    pays 25% or 30% depending on base rate entity status."""
    kwargs = _minimal_kwargs()
    del kwargs["tax_rate"]
    with pytest.raises(ValidationError, match="tax_rate"):
        EntityConfig(**kwargs)


def test_seasonality_must_be_twelve():
    with pytest.raises(ValidationError):
        Channel(name="D2C", annual_revenue=1.0, seasonality=[1.0] * 11, cogs_pct=0.5)


def test_cogs_pct_bounded():
    with pytest.raises(ValidationError):
        Channel(name="D2C", annual_revenue=1.0, seasonality=[1.0] * 12, cogs_pct=1.5)


def test_bad_start_month_rejected():
    kwargs = _minimal_kwargs() | {"start_month": "not-a-month"}
    with pytest.raises(ValidationError):
        EntityConfig(**kwargs)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_ridgeline_config():
    cfg = load_config(REPO_ROOT / "examples/ridgeline/config.yaml")
    assert cfg.name == "Ridgeline Chair Co."
    assert len(cfg.channels) == 3
    assert cfg.horizon_months == 12


def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config(REPO_ROOT / "examples/does_not_exist.yaml")


def test_channel_name_total_rejected():
    with pytest.raises(ValidationError):
        Channel(name="total", annual_revenue=1.0, seasonality=[1.0] * 12, cogs_pct=0.5)


def test_opex_name_total_rejected():
    from pyfpa.config.schemas import OpexLine
    with pytest.raises(ValidationError):
        OpexLine(name="Total", kind="fixed", monthly_amount=1.0)


def test_duplicate_channel_names_rejected():
    kwargs = _minimal_kwargs()
    kwargs["channels"] = [
        Channel(name="D2C", annual_revenue=1.0, seasonality=[1.0] * 12, cogs_pct=0.5),
        Channel(name="d2c", annual_revenue=2.0, seasonality=[1.0] * 12, cogs_pct=0.5),
    ]
    with pytest.raises(ValidationError, match="channels names must be unique"):
        EntityConfig(**kwargs)


def test_growth_cannot_reduce_revenue_below_zero():
    with pytest.raises(ValidationError):
        Channel(
            name="D2C",
            annual_revenue=1.0,
            growth_rate=-1.0,
            seasonality=[1.0] * 12,
            cogs_pct=0.5,
        )


_MISSPELLABLE_YAML = """
name: Two Year Co.
start_month: 2026-01
horizon_months: 24
tax_rate: 0.0
channels:
  - name: Wholesale
    annual_revenue: 1200.0
    {growth_key}: 0.10
    seasonality: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
    cogs_pct: 0.5
opex: []
debt: []
working_capital:
  dso_days: 0
  dpo_days: 0
  dio_days: 0
opening_balances:
  cash: 0
"""


def test_misspelt_optional_field_is_rejected(tmp_path):
    # F077: growth_rtae used to load silently, leaving the channel at zero
    # growth while the config looked applied.
    path = tmp_path / "misspelt.yaml"
    path.write_text(_MISSPELLABLE_YAML.format(growth_key="growth_rtae"), encoding="utf-8")
    with pytest.raises(ValidationError, match="growth_rtae"):
        load_config(path)


def test_correctly_named_optional_field_still_applies(tmp_path):
    # Control: the same config under the real field name grows year 2 by 10%.
    from pyfpa.models.revenue import revenue_from_config

    path = tmp_path / "correct.yaml"
    path.write_text(_MISSPELLABLE_YAML.format(growth_key="growth_rate"), encoding="utf-8")
    cfg = load_config(path)
    revenue = revenue_from_config(cfg)["total"]
    assert round(float(revenue.iloc[:12].sum())) == 1200
    assert round(float(revenue.iloc[12:].sum())) == 1320


def test_unknown_top_level_key_is_rejected(tmp_path):
    path = tmp_path / "extra.yaml"
    path.write_text(
        _MISSPELLABLE_YAML.format(growth_key="growth_rate") + "tax_ratee: 0.3\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="tax_ratee"):
        load_config(path)


@pytest.mark.parametrize("value", ["2026", "2026-1", "2026-13", "January 2026", "2026-01-15"])
def test_start_month_requires_the_exact_format(value: str) -> None:
    # pd.Period parses far more than YYYY-MM, and month_index read "2026" as January
    # 2026, so a malformed value selected a different start period instead of failing.
    with pytest.raises(ValidationError):
        EntityConfig(**{**_minimal_kwargs(), "start_month": value})


def test_start_month_still_accepts_the_documented_format() -> None:
    assert EntityConfig(**{**_minimal_kwargs(), "start_month": "2026-07"}).start_month == "2026-07"
