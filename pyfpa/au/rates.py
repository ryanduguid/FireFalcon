"""Effective-dated statutory rate tables for the Australian pack.

Rates and thresholds live in YAML data files under ``pyfpa/au/data/``,
each entry carrying ``from`` (effective date), the value, and a
``source_url``. Nothing statutory is hardcoded in engine modules; a
forecast for FY2027 and a backtest against FY2024 both resolve the rate
that applied at the time.
"""

from __future__ import annotations

from datetime import date
from importlib import resources
from typing import Any

import pandas as pd
import yaml
from pydantic import BaseModel, Field, field_validator


class RateEntry(BaseModel):
    """One effective-dated value in a rate schedule."""

    effective_from: date = Field(alias="from")
    rate: float = Field(ge=0)
    source_url: str = ""

    model_config = {"populate_by_name": True}


class PayrollTaxEntry(BaseModel):
    """One jurisdiction's payroll tax settings from an effective date."""

    jurisdiction: str
    effective_from: date = Field(alias="from")
    rate: float = Field(ge=0, le=1)
    annual_threshold: float = Field(ge=0)
    notes: str = ""
    source_url: str = ""

    model_config = {"populate_by_name": True}

    @field_validator("jurisdiction")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


JURISDICTIONS = ("NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT")


def _load_yaml(name: str) -> Any:
    ref = resources.files("pyfpa.au.data").joinpath(name)
    return yaml.safe_load(ref.read_text(encoding="utf-8"))


def load_super_guarantee_table() -> list[RateEntry]:
    """Super guarantee rate schedule, oldest first."""
    raw = _load_yaml("super_guarantee.yaml")
    entries = [RateEntry.model_validate(item) for item in raw["schedule"]]
    return sorted(entries, key=lambda e: e.effective_from)


def load_payroll_tax_table() -> list[PayrollTaxEntry]:
    """Payroll tax rate/threshold entries for all jurisdictions, oldest first."""
    raw = _load_yaml("payroll_tax.yaml")
    entries = [PayrollTaxEntry.model_validate(item) for item in raw["jurisdictions"]]
    return sorted(entries, key=lambda e: (e.jurisdiction, e.effective_from))


def load_gst_bas_data() -> dict[str, Any]:
    """GST rate, registration/lodgment thresholds and BAS due-date rules."""
    return _load_yaml("gst_bas.yaml")


def rate_at(entries: list[RateEntry], when: date | str | pd.Period) -> float:
    """Rate applying on `when` from an effective-dated schedule.

    Accepts a date, ISO string, or monthly Period (start of month is used).
    Raises ValueError when `when` predates the whole schedule.
    """
    when_date = _as_date(when)
    applicable = [e for e in entries if e.effective_from <= when_date]
    if not applicable:
        raise ValueError(f"no rate effective on {when_date.isoformat()}")
    return max(applicable, key=lambda e: e.effective_from).rate


def payroll_tax_at(
    entries: list[PayrollTaxEntry], jurisdiction: str, when: date | str | pd.Period
) -> PayrollTaxEntry:
    """Payroll tax entry for `jurisdiction` applying on `when`."""
    when_date = _as_date(when)
    key = jurisdiction.strip().upper()
    if key not in JURISDICTIONS:
        raise ValueError(f"unknown jurisdiction {jurisdiction!r}; expected one of {JURISDICTIONS}")
    applicable = [
        e for e in entries if e.jurisdiction == key and e.effective_from <= when_date
    ]
    if not applicable:
        raise ValueError(f"no {key} payroll tax entry effective on {when_date.isoformat()}")
    return max(applicable, key=lambda e: e.effective_from)


def _as_date(when: date | str | pd.Period) -> date:
    if isinstance(when, pd.Period):
        return when.to_timestamp(how="start").date()
    if isinstance(when, str):
        return pd.Timestamp(when).date()
    return when
