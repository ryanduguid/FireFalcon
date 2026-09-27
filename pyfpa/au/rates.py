"""Effective-dated statutory rate tables for the Australian pack.

Rates and thresholds live in YAML data files under ``pyfpa/au/data/``,
each entry carrying ``from`` (effective date), the value, and a
``source_url``. Nothing statutory is hardcoded in engine modules; a
forecast for FY2027 and a backtest against FY2025 both resolve the rate
that applied at the time. Each table's earliest ``from`` date bounds the
backtest: payroll-tax entries start on 1 July 2024 (1 July 2025 for VIC
and NT), and a lookup before a table's first entry raises ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from importlib import resources
from typing import Any, TypeVar, cast

import pandas as pd
import yaml
from pydantic import BaseModel, Field, field_validator

from pyfpa.au.calendar import require_iso


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
    annual_deduction: float | None = Field(default=None, ge=0)
    annual_rate_ramp_width: float = Field(default=0, ge=0)
    notes: str = ""
    source_url: str = ""

    model_config = {"populate_by_name": True}

    @field_validator("jurisdiction")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


JURISDICTIONS = ("NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT")

_Entry = TypeVar("_Entry", bound=BaseModel)


class Schedule(list[_Entry]):
    """A rate table together with the date its maintainer verified it to.

    The last entry in a table is open-ended, so without a ceiling a lookup
    for 2031 silently returns whatever was current when the table was last
    checked. ``reviewed_until`` is that check's horizon; a lookup past it
    raises until someone re-verifies the sources and moves the date.
    """

    def __init__(self, entries: Iterable[_Entry], reviewed_until: date | None) -> None:
        super().__init__(entries)
        self.reviewed_until = reviewed_until


def _load_yaml(name: str) -> dict[str, Any]:
    ref = resources.files("pyfpa.au.data").joinpath(name)
    loaded: dict[str, Any] = yaml.safe_load(ref.read_text(encoding="utf-8"))
    return loaded


def _reviewed_until(raw: dict[str, Any], name: str) -> date:
    value = raw.get("reviewed_until")
    if not isinstance(value, date):
        raise ValueError(f"{name} must state reviewed_until as an ISO date")
    return value


def load_super_guarantee_table() -> Schedule[RateEntry]:
    """Super guarantee rate schedule, oldest first."""
    raw = _load_yaml("super_guarantee.yaml")
    entries = [RateEntry.model_validate(item) for item in raw["schedule"]]
    return Schedule(
        sorted(entries, key=lambda e: e.effective_from),
        _reviewed_until(raw, "super_guarantee.yaml"),
    )


def load_payroll_tax_table() -> Schedule[PayrollTaxEntry]:
    """Payroll tax rate/threshold entries for all jurisdictions, oldest first."""
    raw = _load_yaml("payroll_tax.yaml")
    entries = [PayrollTaxEntry.model_validate(item) for item in raw["jurisdictions"]]
    return Schedule(
        sorted(entries, key=lambda e: (e.jurisdiction, e.effective_from)),
        _reviewed_until(raw, "payroll_tax.yaml"),
    )


def _within_review(entries: list[Any], when_date: date) -> None:
    reviewed_until = getattr(entries, "reviewed_until", None)
    if reviewed_until is not None and when_date > reviewed_until:
        raise ValueError(
            f"the schedule was verified only to {reviewed_until.isoformat()}; re-verify it "
            f"against its sources and extend reviewed_until before forecasting "
            f"{when_date.isoformat()}"
        )


def load_gst_bas_data() -> dict[str, Any]:
    """GST rate, registration/lodgment thresholds and BAS due-date rules."""
    return _load_yaml("gst_bas.yaml")


def rate_at(entries: list[RateEntry], when: date | str | pd.Period) -> float:
    """Rate applying on `when` from an effective-dated schedule.

    Accepts a date, ISO string, or monthly Period (start of month is used).
    Raises ValueError when `when` predates the whole schedule or falls after
    the date the schedule was verified to.
    """
    when_date = _as_date(when)
    _within_review(entries, when_date)
    applicable = [e for e in entries if e.effective_from <= when_date]
    if not applicable:
        raise ValueError(f"no rate effective on {when_date.isoformat()}")
    return max(applicable, key=lambda e: e.effective_from).rate


def payroll_tax_at(
    entries: list[PayrollTaxEntry], jurisdiction: str, when: date | str | pd.Period
) -> PayrollTaxEntry:
    """Payroll tax entry for `jurisdiction` applying on `when`."""
    when_date = _as_date(when)
    _within_review(entries, when_date)
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
        return cast(date, when.to_timestamp(how="start").date())
    if isinstance(when, str):
        return cast(date, pd.Timestamp(require_iso(when, "rate date")).date())
    return when
