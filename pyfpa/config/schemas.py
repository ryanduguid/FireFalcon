from __future__ import annotations

import math
import re
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _ConfigModel(BaseModel):
    """Configuration numbers must be finite and keys must be recognised.

    Accepting extras let a misspelt optional field fall back to its default
    without a word, so a config that looked applied was quietly ignored.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def _reject_reserved_name(v: str) -> str:
    name = v.strip()
    if not name:
        raise ValueError("name must not be empty")
    if name.lower() == "total":
        raise ValueError("'total' is a reserved column name")
    return name


class Channel(_ConfigModel):
    name: str
    annual_revenue: float = Field(ge=0)
    growth_rate: float = Field(default=0.0, gt=-1)  # annual YoY
    seasonality: list[float] = Field(min_length=12, max_length=12)
    cogs_pct: float = Field(ge=0, le=1)

    @field_validator("name")
    @classmethod
    def _name_not_reserved(cls, v: str) -> str:
        return _reject_reserved_name(v)

    @field_validator("seasonality")
    @classmethod
    def _weights_positive(cls, v: list[float]) -> list[float]:
        if any(weight < 0 for weight in v):
            raise ValueError("seasonality weights must be non-negative")
        total = sum(v)
        if not math.isfinite(total):
            raise ValueError("seasonality weights must sum to a finite number")
        if total <= 0:
            raise ValueError("seasonality weights must sum to a positive number")
        return v


class OpexLine(_ConfigModel):
    name: str
    kind: Literal["fixed", "variable"]
    # Bounded like every other amount in this schema. A negative opex line would
    # read as income in the cash model rather than a cost.
    monthly_amount: float = Field(default=0.0, ge=0)   # used when kind == "fixed"
    pct_of_revenue: float = Field(default=0.0, ge=0)   # used when kind == "variable"

    @field_validator("name")
    @classmethod
    def _name_not_reserved(cls, v: str) -> str:
        return _reject_reserved_name(v)


class DebtInstrument(_ConfigModel):
    name: str
    kind: Literal["term_loan", "loc"]
    opening_balance: float = Field(ge=0)
    annual_rate: float = Field(ge=0)
    monthly_principal: float = Field(default=0.0, ge=0)  # term_loan only

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("name must not be empty")
        return name


class WorkingCapitalConfig(_ConfigModel):
    dso_days: float = Field(ge=0)
    dpo_days: float = Field(ge=0)
    dio_days: float = Field(ge=0)


class OpeningBalances(_ConfigModel):
    cash: float = 0.0
    ar: float = 0.0
    ap: float = 0.0
    inventory: float = 0.0
    nol: float = Field(default=0.0, ge=0)  # net operating loss carryforward


class IncomeTaxConfig(_ConfigModel):
    """An income-year tax provision in place of the default monthly approximation.

    For each Australian income year from 1 July, the provision is tax_rate times
    year-to-date pre-tax income (a proxy for taxable income) less the tax loss
    available; each month's tax is the movement in the provision, so a later
    loss can reverse an earlier month's tax. Cash follows `payments`, never the
    provision. `opening_balances.nol` is the tax loss available for deduction at
    the start: the library does not apply the continuity tests in Division 165
    of the Income Tax Assessment Act 1997. Available loss is used in full against
    positive income; a company's choice to deduct less, or nil (s 36-17), is not
    modelled.
    """

    # Whether a loss for a forecast income year may be deducted in a later one.
    # None means unknown, which is refused once such a loss would reduce tax.
    forecast_losses_deductible: bool | None = None
    # Tax paid or refunded (negative) by month, keyed "YYYY-MM": instalments and
    # final payments. A month not listed pays nothing.
    payments: dict[str, float] = Field(default_factory=dict)


class EntityConfig(_ConfigModel):
    name: str
    start_month: str
    horizon_months: int = Field(default=12, ge=1, le=120)
    # Required: the old 0.21 default was the US federal rate, and no single
    # default fits Australia, where a company pays 25% (base rate entity) or 30%.
    tax_rate: float = Field(ge=0, le=1)
    da_monthly: float = Field(default=0.0, ge=0)      # depreciation and amortisation
    capex_monthly: float = Field(default=0.0, ge=0)   # capital expenditure
    channels: list[Channel] = Field(min_length=1)
    opex: list[OpexLine] = Field(default_factory=list)
    debt: list[DebtInstrument] = Field(default_factory=list)
    working_capital: WorkingCapitalConfig
    opening_balances: OpeningBalances = Field(default_factory=OpeningBalances)
    income_tax: IncomeTaxConfig | None = None

    @field_validator("start_month")
    @classmethod
    def _valid_month(cls, v: str) -> str:
        # The exact format, not whatever pandas will parse. "2026" is a valid Period
        # and month_index reads it as January 2026, so a malformed value chose a
        # different start period rather than failing.
        if not re.fullmatch(r"\d{4}-\d{2}", v):
            raise ValueError(f"start_month must be YYYY-MM, got {v!r}")
        try:
            pd.Period(v, freq="M")
        except Exception as e:
            raise ValueError(f"start_month must be YYYY-MM, got {v!r}") from e
        return v

    @model_validator(mode="after")
    def _unique_line_names(self) -> EntityConfig:
        for field in ("channels", "opex", "debt"):
            names = [item.name.casefold() for item in getattr(self, field)]
            if len(names) != len(set(names)):
                raise ValueError(f"{field} names must be unique")
        return self

    @model_validator(mode="after")
    def _income_year_tax_starts_in_july(self) -> EntityConfig:
        if self.income_tax is None:
            return self
        start = pd.Period(self.start_month, freq="M")
        if start.month != 7:
            raise ValueError("income_tax needs a forecast starting in July: a year-to-date "
                             "provision cannot begin part-way through an income year")
        months = {str(period) for period in pd.period_range(start, periods=self.horizon_months, freq="M")}
        outside = sorted(set(self.income_tax.payments) - months)
        if outside:
            raise ValueError("income_tax.payments names months outside the forecast: " + ", ".join(outside))
        return self
