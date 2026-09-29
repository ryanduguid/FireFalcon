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

A due date on a weekend moves to the following Monday. Taxation Administration
Act 1953 s 8AAZMB also moves a date that falls on a public holiday for the
whole of any State, the Australian Capital Territory or the Northern Territory,
but this module carries no holiday calendar, so such a date is left as is. For example, 28 February 2027 is a Sunday; the
Monday it moves to, 1 March, is Labour Day throughout Western Australia, so the
statutory date is Tuesday 2 March 2027, one day later than this module gives.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from enum import Enum
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from pyfpa.au.calendar import require_iso
from pyfpa.au.rates import load_gst_bas_data, require_bas_dates_reviewed
from pyfpa.cash13.schemas import WeeklyFlow


class BasCycle(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class GstAssumptions(BaseModel):
    """Entity-level GST assumptions for cash forecasting."""

    bas_cycle: BasCycle = BasCycle.QUARTERLY
    taxable_sales_pct: float = Field(default=1.0, ge=0, le=1)
    creditable_purchases_pct: float = Field(default=1.0, ge=0, le=1)
    # None uses the bundled rate; explicit rates are forecast scenarios.
    gst_rate: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    def resolved_rate(self) -> float:
        if self.gst_rate is not None:
            return self.gst_rate
        return float(load_gst_bas_data()["gst_rate"])


def _validate_monthly_series(series: pd.Series) -> None:
    index = series.index
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != "M":
        raise ValueError("expected a monthly PeriodIndex")
    if index.hasnans or not index.is_unique:
        raise ValueError("monthly periods must be unique and contain no missing dates")
    if len(index) and len(index) != index.max().ordinal - index.min().ordinal + 1:
        raise ValueError("monthly index has missing periods")
    try:
        finite = all(math.isfinite(value) for value in series)
    except TypeError:
        finite = False
    if not finite:
        raise ValueError("monthly amounts must be finite numbers, with no missing values")


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
    _validate_monthly_series(revenue)
    _validate_monthly_series(purchases)
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


def _next_business_day(due: date) -> date:
    """Move a weekend due date to the following Monday.

    Taxation Administration Act 1953 s 8AAZMB makes a tax debt due on the next
    business day when its day is a weekend or a public holiday for the whole of
    any State, the Australian Capital Territory or the Northern Territory, and
    these dates drive cash timing. Public holidays are not modelled: this
    module carries no holiday calendar, so a due date on one is left as is.
    """
    shift = {5: 2, 6: 1}.get(due.weekday(), 0)
    return due + timedelta(days=shift)


def quarterly_bas_due_date(quarter_end: pd.Period) -> date:
    """Due date for the quarterly BAS whose quarter ends with month `quarter_end`."""
    require_bas_dates_reviewed(quarter_end.end_time.date())
    rules = load_gst_bas_data()["quarterly_due"]
    key = f"{quarter_end.month:02d}"
    rule = rules[key]  # {'month': int, 'day': int} relative to quarter end
    due_year = quarter_end.year + (1 if rule["month"] < quarter_end.month else 0)
    return _next_business_day(date(due_year, rule["month"], rule["day"]))


def monthly_activity_statement_due_date(month: pd.Period) -> date:
    """Standard due date for the monthly activity statement for `month`: the 21st following.

    The ATO's 21 February date for an eligible business's December statement
    (monthly GST, turnover up to $10 million, lodged electronically) is not
    modelled, so December gives 21 January.
    """
    require_bas_dates_reviewed(month.end_time.date())
    day = int(load_gst_bas_data()["monthly_due_day"])
    following = month + 1
    return _next_business_day(date(following.year, following.month, day))


def bas_schedule(
    net_gst: pd.Series,
    assumptions: GstAssumptions | None = None,
) -> pd.DataFrame:
    """BAS settlement events from a monthly net_gst series.

    Returns a frame with columns period_label, due_date, amount.
    Quarterly cycles sum months into Sep/Dec/Mar/Jun quarters; a trailing
    quarter that ends after the series is excluded, because its BAS falls
    beyond the series. A leading partial quarter settles the months the
    series actually holds, so its GST cash is not lost.
    Positive amount = payment to ATO; negative = refund.
    Missing values, duplicate months and non-monthly indexes are rejected.
    """
    assumptions = assumptions or GstAssumptions()
    _validate_monthly_series(net_gst)
    rows: list[dict[str, Any]] = []
    if assumptions.bas_cycle is BasCycle.MONTHLY:
        for period, amount in net_gst.items():
            rows.append(
                {
                    "period_label": str(period),
                    "due_date": monthly_activity_statement_due_date(period),
                    "amount": float(amount),
                }
            )
    else:
        last_month = net_gst.index.max()
        for quarter, amounts in net_gst.groupby(net_gst.index.asfreq("Q-JUN")):
            quarter_end = quarter.asfreq("M", how="end")
            if quarter_end > last_month:
                continue  # quarter still open; BAS not yet determinable

            rows.append(
                {
                    "period_label": str(quarter),
                    "due_date": quarterly_bas_due_date(quarter_end),
                    "amount": float(amounts.sum()),
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
    if isinstance(window_start, str):
        window_start = require_iso(window_start, "window_start")
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
