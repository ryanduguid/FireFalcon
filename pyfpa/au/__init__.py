"""Australian localisation pack for pyfpa.

Adds Australian fiscal-calendar helpers, effective-dated statutory rate
tables, payroll cost forecasting (super guarantee, state payroll tax,
workers compensation, leave provisions, bonuses) and GST/BAS cash-timing
for the monthly model and the 13-week cash forecast.

Scope: forecast-grade cash and P&L modelling. Not tax-return software.
Payroll tax grouping provisions, per-state threshold apportionment
subtleties and contractor deeming rules are documented simplifications.
"""

from pyfpa.au.calendar import (
    format_au_date,
    fy_half_label,
    fy_label,
    fy_month_range,
    fy_quarter_label,
    fy_summary,
    fy_year,
)
from pyfpa.au.drivers import (
    DriverSeries,
    fetch_abs_series,
    fetch_rba_series,
    load_snapshot,
    save_snapshot,
)
from pyfpa.au.gst import BasCycle, GstAssumptions, bas_schedule, gst_weekly_flows, monthly_gst
from pyfpa.au.payroll import PayrollAssumptions, Role, payroll_forecast
from pyfpa.au.rates import (
    load_gst_bas_data,
    load_payroll_tax_table,
    load_super_guarantee_table,
    rate_at,
)

__all__ = [
    "BasCycle",
    "DriverSeries",
    "GstAssumptions",
    "PayrollAssumptions",
    "Role",
    "bas_schedule",
    "fetch_abs_series",
    "fetch_rba_series",
    "format_au_date",
    "fy_half_label",
    "fy_label",
    "fy_month_range",
    "fy_quarter_label",
    "fy_summary",
    "fy_year",
    "gst_weekly_flows",
    "load_gst_bas_data",
    "load_payroll_tax_table",
    "load_snapshot",
    "load_super_guarantee_table",
    "monthly_gst",
    "payroll_forecast",
    "rate_at",
    "save_snapshot",
]
