"""Assemble the Harbour Light Pty Ltd synthetic Australian example.

Xero GST-exclusive fixtures (one month, tracking by region) are annualised
into the monthly engine. Statutory payroll and quarterly BAS cash live in
``pyfpa.au``; they are not re-typed from the Xero payroll-tax line.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pyfpa.au.calendar import fy_month_range
from pyfpa.au.gst import BasCycle, GstAssumptions, bas_schedule, gst_weekly_flows, monthly_gst
from pyfpa.au.payroll import PayrollAssumptions, Role, payroll_forecast
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow
from pyfpa.config.schemas import (
    Channel,
    EntityConfig,
    OpeningBalances,
    OpexLine,
    WorkingCapitalConfig,
)
from pyfpa.io.xero_au import read_xero_report
from pyfpa.models.cashflow import cashflow_from_config

DATA = Path(__file__).parent / "data"
CASH13_START = date(2026, 10, 1)
_DAYS_PER_YEAR = 360.0
_NON_PAYROLL_OPEX = (
    "Advertising",
    "Consulting & Accounting",
    "Office Expenses",
    "Rent",
    "Repairs & Maintenance",
)
# Gross wages tie to the Xero "Wages and Salaries" line ($41,600 / month).
ROLES = [
    Role(name="Workshop manager", annual_salary=130_000, jurisdiction="VIC"),
    Role(name="Electrician", annual_salary=95_000, jurisdiction="VIC"),
    Role(name="Sales", annual_salary=90_000, jurisdiction="VIC"),
    Role(name="Warehouse", annual_salary=85_000, jurisdiction="VIC"),
    Role(name="Bookkeeper", annual_salary=99_200, jurisdiction="VIC"),
]


def profit_and_loss():
    return read_xero_report(DATA / "xero_pl_tracking.csv")


def balance_sheet():
    return read_xero_report(DATA / "xero_bs.csv")


def taxable_sales_pct() -> float:
    accounts = profit_and_loss().by_account()
    domestic = accounts["Sales - Domestic"]
    gst_free = accounts["Sales - GST Free"]
    return domestic / (domestic + gst_free)


def channels_from_xero() -> list[Channel]:
    splits = profit_and_loss().by_tracking()
    channels = []
    for name in ("North", "South"):
        row = splits[name]
        sales = row.get("Sales - Domestic", 0.0) + row.get("Sales - GST Free", 0.0)
        cogs = abs(row["Cost of Goods Sold"])
        channels.append(
            Channel(
                name=name,
                annual_revenue=sales * 12.0,
                growth_rate=0.0,
                seasonality=[1.0] * 12,
                cogs_pct=cogs / sales,
            )
        )
    return channels


def payroll_frame() -> pd.DataFrame:
    return payroll_forecast(
        ROLES,
        fy_month_range(2027),
        PayrollAssumptions(workers_comp_rate=0.02),
    )


def _monthly_opex() -> list[OpexLine]:
    accounts = profit_and_loss().by_account()
    lines = [
        OpexLine(
            name=account,
            kind="fixed",
            monthly_amount=abs(accounts[account]),
        )
        for account in _NON_PAYROLL_OPEX
    ]
    lines.append(
        OpexLine(
            name="Payroll (statutory)",
            kind="fixed",
            monthly_amount=float(payroll_frame()["total_cost"].iloc[0]),
        )
    )
    return lines


def _working_capital() -> WorkingCapitalConfig:
    accounts = profit_and_loss().by_account()
    bs = balance_sheet().by_account()
    annual_sales = (accounts["Sales - Domestic"] + accounts["Sales - GST Free"]) * 12.0
    annual_cogs = abs(accounts["Cost of Goods Sold"]) * 12.0
    return WorkingCapitalConfig(
        dso_days=bs["Accounts Receivable"] / annual_sales * _DAYS_PER_YEAR,
        dio_days=bs["Inventory"] / annual_cogs * _DAYS_PER_YEAR,
        dpo_days=abs(bs["Accounts Payable"]) / annual_cogs * _DAYS_PER_YEAR,
    )


def entity_config() -> EntityConfig:
    bs = balance_sheet().by_account()
    return EntityConfig(
        name="Harbour Light Pty Ltd",
        start_month="2026-07",
        horizon_months=12,
        tax_rate=0.30,
        channels=channels_from_xero(),
        opex=_monthly_opex(),
        working_capital=_working_capital(),
        opening_balances=OpeningBalances(
            cash=bs["Business Bank Account"],
            ar=bs["Accounts Receivable"],
            ap=abs(bs["Accounts Payable"]),
            inventory=bs["Inventory"],
        ),
    )


def monthly_forecast() -> pd.DataFrame:
    return cashflow_from_config(entity_config())


def _gst_inputs() -> tuple[pd.Series, pd.Series]:
    months = fy_month_range(2027)
    accounts = profit_and_loss().by_account()
    monthly_sales = accounts["Sales - Domestic"] + accounts["Sales - GST Free"]
    monthly_purchases = abs(accounts["Cost of Goods Sold"]) + sum(
        abs(accounts[name]) for name in _NON_PAYROLL_OPEX
    )
    revenue = pd.Series(monthly_sales, index=months)
    purchases = pd.Series(monthly_purchases, index=months)
    return revenue, purchases


def bas_settlement() -> pd.DataFrame:
    revenue, purchases = _gst_inputs()
    gst = monthly_gst(
        revenue,
        purchases,
        GstAssumptions(
            bas_cycle=BasCycle.QUARTERLY,
            taxable_sales_pct=taxable_sales_pct(),
        ),
    )
    return bas_schedule(gst["net_gst"], GstAssumptions(bas_cycle=BasCycle.QUARTERLY))


def gst_cash13_flows() -> tuple[list[WeeklyFlow], list[WeeklyFlow]]:
    return gst_weekly_flows(bas_settlement(), window_start=CASH13_START)


def cash13_config() -> Cash13Config:
    monthly = monthly_forecast()
    opening = float(monthly.loc[pd.Period("2026-09", freq="M"), "ending_cash"])
    payroll_cash = float(payroll_frame()["total_cash"].sum()) / 26.0
    gst_receipts, gst_disbursements = gst_cash13_flows()
    accounts = profit_and_loss().by_account()
    weekly_collections = (accounts["Sales - Domestic"] + accounts["Sales - GST Free"]) * 12.0 / 52.0
    weekly_opex = sum(abs(accounts[name]) for name in _NON_PAYROLL_OPEX) * 12.0 / 52.0
    weekly_cogs = abs(accounts["Cost of Goods Sold"]) * 12.0 / 52.0
    return Cash13Config(
        opening_cash=opening,
        weeks=13,
        receipts=[
            WeeklyFlow(
                name="Collections",
                amount=weekly_collections,
                start_week=1,
                recurrence="weekly",
            ),
            *gst_receipts,
        ],
        disbursements=[
            WeeklyFlow(
                name="Payroll",
                amount=payroll_cash,
                start_week=1,
                recurrence="biweekly",
            ),
            WeeklyFlow(
                name="Supplier payments",
                amount=weekly_cogs,
                start_week=1,
                recurrence="weekly",
            ),
            WeeklyFlow(
                name="Operating overhead",
                amount=weekly_opex,
                start_week=1,
                recurrence="weekly",
            ),
            *gst_disbursements,
        ],
    )
