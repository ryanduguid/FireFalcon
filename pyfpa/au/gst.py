"""GST and BAS cash timing.

Turns a monthly P&L view (GST-exclusive revenue and purchases) into net
GST positions and BAS settlement cash flows, for both the monthly model
and the 13-week cash forecast. Cash timing only; not tax-return
software. Fuel tax credits, PAYG withholding and instalments on the BAS
are out of scope here (PAYG withholding belongs with payroll cash).

Categories: `taxable_sales_pct` covers GST-free (exports, basic food,
health) and input-taxed (financial supplies, residential rent) revenue
by exclusion; likewise `creditable_purchases_pct` for acquisitions
without input tax credits.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

import pandas as pd
from pydantic import BaseModel, Field

from pyfpa.au.rates import load_gst_bas_data
from pyfpa.cash13.schemas import WeeklyFlow


class BasCycle(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class GstAssumptions(BaseModel):
    """Entity-level GST assumptions for cash forecasting."""

    bas_cycle: BasCycle = BasCycle.QUARTERLY
    taxable_sales_pct: float = Field(default=1.0, ge=0, le=1)
    creditable_purchases_pct: float = Field(default=1.0, ge=0, le=1)
    agent_lodgment: bool = False  # tax/BAS agent program extensions not modelled; flag only
    gst_rate: float | None = None  # None = statutory rate from data file

    def resolved_rate(self) -> float:
        if self.gst_rate is not None:
            return self.gst_rate
        return float(load_gst_bas_data()["gst_rate"])


def monthly_gst(
    revenue: pd.Series,
    purchases: pd.Series,
    assumptions: GstAssumptions | None = None,
) -> pd.DataFrame:
    """Net GST position by month from GST-exclusive revenue and purchases.

    `revenue` and `purchases` share a monthly PeriodIndex. Positive
    net_gst is payable to the ATO; negative is a refund.
    """
    assumptions = assumptions or GstAssumptions()
    rate = assumptions.resolved_rate()
    if not revenue.index.equals(purchases.index):
        raise ValueError("revenue and purchases must share the same monthly index")
    output_gst = revenue * assumptions.taxable_sales_pct * rate
    input_gst = purchases * assumptions.creditable_purchases_pct * rate
    frame = pd.DataFrame(
        {
            "output_gst": output_gst,
            "input_gst": input_gst,
            "net_gst": output_gst - input_gst,
        }
    )
    return frame


def _quarter_due_date(quarter_end: pd.Period) -> date:
    """Original due date for the quarterly BAS ending at `quarter_end`."""
    rules = load_gst_bas_data()["quarterly_due"]
    key = f"{quarter_end.month:02d}"
    rule = rules[key]  # {'month': int, 'day': int} relative to quarter end
    due_year = quarter_end.year + (1 if rule["month"] < quarter_end.month else 0)
    return date(due_year, rule["month"], rule["day"])


def _month_due_date(month: pd.Period) -> date:
    """Original due date for the monthly BAS for `month` (21st following)."""
    day = int(load_gst_bas_data()["monthly_due_day"])
    following = month + 1
    return date(following.year, following.month, day)


def bas_schedule(
    net_gst: pd.Series,
    assumptions: GstAssumptions | None = None,
) -> pd.DataFrame:
    """BAS settlement events from a monthly net_gst series.

    Returns a frame with columns period_label, due_date, amount.
    Quarterly cycles sum months into Sep/Dec/Mar/Jun quarters; partial
    trailing quarters are excluded (their BAS falls beyond the series).
    Positive amount = payment to ATO; negative = refund.
    """
    assumptions = assumptions or GstAssumptions()
    rows: list[dict] = []
    if assumptions.bas_cycle is BasCycle.MONTHLY:
        for period, amount in net_gst.items():
            rows.append(
                {
                    "period_label": str(period),
                    "due_date": _month_due_date(period),
                    "amount": float(amount),
                }
            )
    else:
        quarters = net_gst.groupby(net_gst.index.asfreq("Q-JUN")).sum()
        for quarter, amount in quarters.items():
            months_in_series = sum(
                1 for p in net_gst.index if p.asfreq("Q-JUN") == quarter
            )
            if months_in_series < 3:
                continue  # incomplete quarter; BAS not yet determinable
            quarter_end = quarter.asfreq("M", how="end")
            rows.append(
                {
                    "period_label": str(quarter),
                    "due_date": _quarter_due_date(quarter_end),
                    "amount": float(amount),
                }
            )
    return pd.DataFrame(rows, columns=["period_label", "due_date", "amount"])


def gst_weekly_flows(
    schedule: pd.DataFrame,
    window_start: date | str,
    weeks: int = 13,
) -> tuple[list[WeeklyFlow], list[WeeklyFlow]]:
    """Map BAS settlements into 13-week-forecast flows.

    Returns (receipts, disbursements) of `WeeklyFlow` for settlements
    due inside the window. Payments become disbursements; refunds
    become receipts. Settlements outside the window are dropped.
    """
    start = pd.Timestamp(window_start).date()
    receipts: list[WeeklyFlow] = []
    disbursements: list[WeeklyFlow] = []
    for row in schedule.itertuples(index=False):
        offset_days = (row.due_date - start).days
        if offset_days < 0:
            continue
        week = offset_days // 7 + 1
        if week > weeks:
            continue
        name = f"BAS {row.period_label}"
        if row.amount >= 0:
            disbursements.append(
                WeeklyFlow(name=name, amount=row.amount, start_week=week, recurrence="once")
            )
        else:
            receipts.append(
                WeeklyFlow(name=name, amount=-row.amount, start_week=week, recurrence="once")
            )
    return receipts, disbursements
