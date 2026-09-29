from __future__ import annotations

import math
import re
from typing import Annotated, Literal

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


_SHARE_TOLERANCE = 1e-9
_Share = Annotated[float, Field(ge=0)]


def _require_shares_add_to_one(shares: list[float] | None, name: str) -> None:
    if shares is not None and abs(sum(shares) - 1.0) > _SHARE_TOLERANCE:
        raise ValueError(f"{name} shares must add up to 1, not {sum(shares):g}")


class WorkingCapitalConfig(_ConfigModel):
    # Receivables follow either days of revenue (dso_days) or a collection profile:
    # the share of each month's revenue received that month and in each month after.
    dso_days: float | None = Field(default=None, ge=0)
    dpo_days: float = Field(ge=0)
    dio_days: float = Field(ge=0)
    collection_profile: list[_Share] | None = Field(default=None, min_length=1)
    # Shares of the opening receivables received in the first forecast month and after.
    opening_ar_collection_profile: list[_Share] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _one_receivables_basis(self) -> WorkingCapitalConfig:
        if self.dso_days is not None and self.collection_profile is not None:
            raise ValueError("give dso_days or collection_profile, not both")
        if self.dso_days is None and self.collection_profile is None:
            raise ValueError("give dso_days or collection_profile")
        if self.opening_ar_collection_profile is not None and self.collection_profile is None:
            raise ValueError("opening_ar_collection_profile applies only with collection_profile")
        # Shares adding up to 1 collect every dollar once; write-offs would need
        # a bad-debt expense line, which this model does not have.
        _require_shares_add_to_one(self.collection_profile, "collection_profile")
        _require_shares_add_to_one(self.opening_ar_collection_profile, "opening_ar_collection_profile")
        return self


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

    @model_validator(mode="after")
    def _opening_receivables_have_a_profile(self) -> EntityConfig:
        wc = self.working_capital
        if (wc.collection_profile is not None and self.opening_balances.ar != 0
                and wc.opening_ar_collection_profile is None):
            raise ValueError(
                "opening receivables need opening_ar_collection_profile when collection_profile sets receipts"
            )
        return self
