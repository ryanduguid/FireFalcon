"""Australian payroll cost forecasting.

Produces a monthly payroll cost and cash frame from effective-dated
roles: gross wages, superannuation guarantee, state payroll tax,
workers compensation, and leave provisions.

Forecast-grade simplifications, stated openly:

- SG is applied to gross wages + bonuses as a proxy for the SG earnings
  base (ordinary time earnings before 1 July 2026, qualifying earnings from
  that date); the maximum contribution base (quarterly before 1 July 2026,
  annual from that date) is not modelled.
- Contractor status determines leave provisions, not SG eligibility.
  Establish SG eligibility separately, including the labour-contract rules.
- Outside SA, payroll tax applies the jurisdiction's marginal rate to taxable wages
  (gross + super, which is how the Acts define taxable wages) above the
  annual threshold, apportioned monthly. Grouping provisions, interstate
  apportionment, QLD's deduction taper and WA's diminishing threshold
  are not modelled beyond the threshold itself; encode entity-specific
  treatment in a generated skill when it matters.
- SA separates the registration threshold from the deduction and ramps
  the rate using each month's wages multiplied by 12. This assumes an
  ungrouped, SA-only employer with a steady full-year wage run rate; it
  does not calculate an annual reconciliation or a statutory monthly return.
  Mixed SA/interstate taxable wages anywhere in the forecast are refused because deduction
  apportionment is not modelled.
- Leave provisions are accrual percentages of gross wages, not cash.
  The cash view excludes them; the P&L view includes them.
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

from pyfpa.au.calendar import require_iso
from pyfpa.au.rates import (
    PayrollTaxEntry,
    RateEntry,
    load_payroll_tax_table,
    load_super_guarantee_table,
    payroll_tax_at,
    rate_at,
)

_MONTHS_PER_YEAR = 12


class Role(BaseModel):
    """One role (or vacancy) with an effective employment window."""

    name: str
    annual_salary: float = Field(ge=0)
    fte: float = Field(default=1.0, ge=0, le=1)
    jurisdiction: str = "NSW"
    start_month: str | None = None  # YYYY-MM; None = employed from horizon start
    end_month: str | None = None    # YYYY-MM inclusive; None = employed to horizon end
    bonus_pct: float = Field(default=0.0, ge=0)   # annual bonus as pct of salary
    contractor: bool = False  # True: no leave provisions; payroll tax still applies
    sg_eligible: bool | None = None  # Established eligibility; required for contractors

    @model_validator(mode="after")
    def _require_contractor_sg_status(self) -> Role:
        if self.start_month and self.end_month and pd.Period(self.start_month, freq="M") > pd.Period(self.end_month, freq="M"):
            raise ValueError("start_month must not follow end_month")
        if self.contractor and self.sg_eligible is None:
            raise ValueError("Set sg_eligible after assessing the contractor's SG eligibility")
        return self

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("start_month", "end_month")
    @classmethod
    def _valid_month(cls, v: str | None) -> str | None:
        if v is None:
            return v
        require_iso(v, "month")
        try:
            pd.Period(v, freq="M")
        except Exception as e:
            raise ValueError(f"month must be YYYY-MM, got {v!r}") from e
        return v


class PayrollAssumptions(BaseModel):
    """Entity-level payroll assumptions."""

    workers_comp_rate: float = Field(default=0.02, ge=0, le=1)
    annual_leave_weeks: float = Field(default=4.0, ge=0)
    lsl_accrual_pct: float = Field(default=0.017, ge=0, le=1)  # ~8.67 wks over 10 yrs
    payroll_tax_registered: bool = True

    @property
    def annual_leave_pct(self) -> float:
        return self.annual_leave_weeks / 52.0


def _employed(role: Role, period: pd.Period) -> bool:
    before_start = role.start_month is not None and period < pd.Period(
        role.start_month, freq="M"
    )
    after_end = role.end_month is not None and period > pd.Period(
        role.end_month, freq="M"
    )
    return not (before_start or after_end)


def payroll_forecast(
    roles: list[Role],
    months: pd.PeriodIndex,
    assumptions: PayrollAssumptions | None = None,
    sg_table: list[RateEntry] | None = None,
    payroll_tax_table: list[PayrollTaxEntry] | None = None,
) -> pd.DataFrame:
    """Monthly payroll cost frame over `months`.

    Columns: gross_wages, bonuses, super_guarantee, payroll_tax,
    workers_comp, leave_provisions, total_cost (P&L view),
    total_cash (excludes leave provisions).
    """
    if not isinstance(months, pd.PeriodIndex) or months.freqstr != "M" or not months.is_unique:
        raise ValueError("payroll requires a unique monthly PeriodIndex")
    assumptions = assumptions or PayrollAssumptions()
    sg_table = sg_table or load_super_guarantee_table()
    payroll_tax_table = payroll_tax_table or load_payroll_tax_table()

    columns = [
        "gross_wages",
        "bonuses",
        "super_guarantee",
        "payroll_tax",
        "workers_comp",
        "leave_provisions",
        "total_cost",
        "total_cash",
    ]
    frame = pd.DataFrame(0.0, index=months, columns=columns)
    taxable_jurisdictions: set[str] = set()

    for period in months:
        sg_rate = rate_at(sg_table, period)
        gross = 0.0
        bonuses = 0.0
        sg = 0.0
        leave = 0.0
        taxable_by_jurisdiction: dict[str, float] = {}
        for role in roles:
            if not _employed(role, period):
                continue
            monthly_salary = role.annual_salary * role.fte / _MONTHS_PER_YEAR
            monthly_bonus = monthly_salary * role.bonus_pct
            gross += monthly_salary
            bonuses += monthly_bonus
            role_sg = 0.0 if role.sg_eligible is False else (monthly_salary + monthly_bonus) * sg_rate
            sg += role_sg
            if not role.contractor:
                leave += monthly_salary * (
                    assumptions.annual_leave_pct + assumptions.lsl_accrual_pct
                )
            key = role.jurisdiction.strip().upper()
            taxable_by_jurisdiction[key] = (
                taxable_by_jurisdiction.get(key, 0.0)
                + monthly_salary
                + monthly_bonus
                + role_sg
            )

        payroll_tax = 0.0
        if assumptions.payroll_tax_registered:
            taxable_jurisdictions.update(
                key for key, amount in taxable_by_jurisdiction.items() if amount > 0
            )
            if "SA" in taxable_jurisdictions and len(taxable_jurisdictions) > 1:
                raise ValueError(
                    "SA interstate payroll tax requires deduction apportionment; "
                    "use an entity-specific calculator"
                )
            for jurisdiction, taxable in taxable_by_jurisdiction.items():
                entry = payroll_tax_at(payroll_tax_table, jurisdiction, period)
                annualised_wages = taxable * _MONTHS_PER_YEAR
                if annualised_wages <= entry.annual_threshold:
                    continue
                deduction = (
                    entry.annual_threshold
                    if entry.annual_deduction is None else entry.annual_deduction
                )
                rate = entry.rate
                if entry.annual_rate_ramp_width:
                    rate *= min(
                        1.0,
                        (annualised_wages - entry.annual_threshold) / entry.annual_rate_ramp_width,
                    )
                payroll_tax += max(0.0, taxable - deduction / _MONTHS_PER_YEAR) * rate

        # Every state's workers compensation wage definition includes bonuses, and
        # the payroll tax base above already does. Excluding them here understated
        # the premium for any role with a non-zero bonus_pct.
        workers_comp = (gross + bonuses) * assumptions.workers_comp_rate
        frame.loc[period, "gross_wages"] = gross
        frame.loc[period, "bonuses"] = bonuses
        frame.loc[period, "super_guarantee"] = sg
        frame.loc[period, "payroll_tax"] = payroll_tax
        frame.loc[period, "workers_comp"] = workers_comp
        frame.loc[period, "leave_provisions"] = leave
        cash = gross + bonuses + sg + payroll_tax + workers_comp
        frame.loc[period, "total_cost"] = cash + leave
        frame.loc[period, "total_cash"] = cash

    return frame
