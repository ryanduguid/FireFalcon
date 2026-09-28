from __future__ import annotations

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
        if sum(v) <= 0:
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
