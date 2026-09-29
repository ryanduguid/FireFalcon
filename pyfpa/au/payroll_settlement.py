"""Payroll liabilities and their settlement: when each payroll cost is owed and paid.

`payroll_forecast` gives monthly costs, and its cash view treats them as paid in
the month incurred. This module turns those costs into dated settlement events
and keeps three dates apart: the obligation date (when the liability arises),
the due date (from a rule the caller supplies for each component) and the cash
date (when the forecast pays). Monthly cash, month-end liabilities and 13-week
flows are all derived from the same events, so they cannot disagree.

This is a forecast allocation, not a payroll calculation. Each month's gross pay
is split equally across that month's paydays, and PAYG withholding is a declared
average rate, not a withholding-schedule calculation. Leave provisions are
accruals and have no settlement here. No statutory calendar lives in this
module: due-date rules are passed in.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from pyfpa.cash13.schemas import WeeklyFlow

DueRule = Callable[[date], date]

# Components whose liability arises on each payday, and those that accrue monthly.
PAYDAY_COMPONENTS = ("net_wages", "payg_withholding", "super_guarantee")
MONTHLY_COMPONENTS = ("payroll_tax", "workers_comp")
COMPONENTS = PAYDAY_COMPONENTS + MONTHLY_COMPONENTS


@dataclass(frozen=True)
class SettlementEvent:
    component: str
    source_period: pd.Period
    obligation_date: date
    due_date: date
    cash_date: date
    amount: float


def _event(component: str, period: pd.Period, obligation: date, amount: float,
           due_rules: Mapping[str, DueRule], early: Mapping[str, int]) -> SettlementEvent:
    due = obligation if component == "net_wages" else due_rules[component](obligation)
    if due < obligation:
        raise ValueError(f"the {component} rule makes {period}'s amount due before it arises")
    cash = due - timedelta(days=early.get(component, 0))
    if cash < obligation:
        raise ValueError(f"{component} for {period} would be paid before it arises")
    return SettlementEvent(component, period, obligation, due, cash, amount)


def settlement_events(
    payroll: pd.DataFrame,
    paydays: Sequence[date],
    *,
    payg_withholding_rate_assumption: float,
    due_rules: Mapping[str, DueRule],
    pay_days_before_due: Mapping[str, int] | None = None,
) -> list[SettlementEvent]:
    """Dated settlement events for a `payroll_forecast` frame.

    `due_rules` maps each component other than net wages to a function from its
    obligation date to its due date. `pay_days_before_due` moves a component's
    cash date that many days before its due date (default 0: paid when due).
    """
    rate = payg_withholding_rate_assumption
    if not 0 <= rate < 1:
        raise ValueError("payg_withholding_rate_assumption must be at least 0 and below 1")
    unknown = sorted(set(due_rules) - set(COMPONENTS))
    if unknown:
        raise ValueError("due_rules names an unknown component: " + ", ".join(unknown))
    if len(set(paydays)) != len(paydays):
        raise ValueError("paydays are repeated")
    months = payroll.index
    by_month: dict[pd.Period, list[date]] = {period: [] for period in months}
    for day in sorted(paydays):
        period = pd.Period(day, freq="M")
        if period not in by_month:
            raise ValueError(f"payday {day.isoformat()} falls outside the payroll months")
        by_month[period].append(day)

    early = pay_days_before_due or {}
    events: list[SettlementEvent] = []
    for period, row in payroll.iterrows():
        gross = float(row["gross_wages"] + row["bonuses"])
        amounts = {
            "net_wages": gross * (1 - rate),
            "payg_withholding": gross * rate,
            "super_guarantee": float(row["super_guarantee"]),
            "payroll_tax": float(row["payroll_tax"]),
            "workers_comp": float(row["workers_comp"]),
        }
        for component, amount in amounts.items():
            if amount and component != "net_wages" and component not in due_rules:
                raise ValueError(f"{component} has costs but no due rule")
        days = by_month[period]
        if not days and any(amounts[c] for c in PAYDAY_COMPONENTS):
            raise ValueError(f"{period} has payroll costs but no payday")
        for day in days:
            for component in PAYDAY_COMPONENTS:
                if amounts[component]:
                    events.append(_event(component, period, day, amounts[component] / len(days),
                                         due_rules, early))
        month_end = period.end_time.date()
        for component in MONTHLY_COMPONENTS:
            if amounts[component]:
                events.append(_event(component, period, month_end, amounts[component], due_rules, early))
    return events


def monthly_settlement(events: Sequence[SettlementEvent], months: pd.PeriodIndex) -> pd.DataFrame:
    """Obligations, cash and closing liability by component and month.

    An obligation before the first month opens the liability; cash dated after
    the last month leaves the amount in closing liability.
    """
    columns = [f"{c}_{kind}" for c in COMPONENTS for kind in ("obligations", "cash", "closing")]
    table = pd.DataFrame(0.0, index=months, columns=[*columns, "total_cash"])
    first = months[0]
    for component in COMPONENTS:
        own = [e for e in events if e.component == component]
        opening = sum(e.amount for e in own if pd.Period(e.obligation_date, freq="M") < first) - sum(
            e.amount for e in own if pd.Period(e.cash_date, freq="M") < first)
        closing = opening
        for month in months:
            obligations = sum(e.amount for e in own if pd.Period(e.obligation_date, freq="M") == month)
            cash = sum(e.amount for e in own if pd.Period(e.cash_date, freq="M") == month)
            closing += obligations - cash
            table.loc[month, [f"{component}_obligations", f"{component}_cash", f"{component}_closing"]] = [
                obligations, cash, closing]
    table["total_cash"] = table[[f"{c}_cash" for c in COMPONENTS]].sum(axis=1)
    return table


def settlement_weekly_flows(events: Sequence[SettlementEvent], window_start: date,
                            weeks: int = 13) -> list[WeeklyFlow]:
    """Disbursements for the 13-week forecast; payments outside the window are left out."""
    flows = []
    for event in events:
        offset = (event.cash_date - window_start).days
        if 0 <= offset < weeks * 7:
            flows.append(WeeklyFlow(name=f"{event.component} {event.source_period}",
                                    amount=event.amount, start_week=offset // 7 + 1))
    return flows
