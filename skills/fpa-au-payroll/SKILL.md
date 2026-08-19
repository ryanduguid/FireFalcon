---
name: fpa-au-payroll
description: Use when forecasting payroll costs for an Australian employer - superannuation guarantee, state payroll tax, workers compensation, leave provisions, headcount plans with start dates and vacancies.
---

# Australian Payroll Cost Forecasting

Use when a company's payroll runs under Australian law: superannuation
guarantee, state/territory payroll tax, workers compensation, leave
provisions.

## Workflow

1. Confirm jurisdictions. Ask which state(s)/territory(ies) employees
   work in; payroll tax is per-jurisdiction. Record in intake.
2. Build roles from the staffing plan, effective-dated:

   ```python
   from pyfpa.au import PayrollAssumptions, Role, payroll_forecast
   from pyfpa.au.calendar import fy_month_range

   roles = [
       Role(name="MD", annual_salary=220000, jurisdiction="VIC"),
       Role(name="Senior 2", annual_salary=140000, jurisdiction="VIC",
            start_month="2026-10", bonus_pct=0.10),
       Role(name="Offshore dev", annual_salary=90000, contractor=True),
   ]
   frame = payroll_forecast(roles, fy_month_range(2027), PayrollAssumptions())
   ```

3. Wire `total_cash` into the cash model and `total_cost` into the P&L.
   The difference is leave provisioning (non-cash accrual).
4. Present assumptions to the user for ratification: workers comp rate
   (industry-specific, default 2%), payroll tax registration, LSL rate
   (jurisdiction-specific, default ~1.7%).

## Statutory rates

Effective-dated tables live in `pyfpa/au/data/`. `rate_at` resolves the
rate applying in any month, so backtests against FY2024 automatically
use 11%, not today's 12%. Never hardcode a super or payroll tax rate in
a generated model; load the table.

## Known simplifications (state these to the user)

- Payroll tax: marginal rate above annual threshold / 12 per month.
  Grouping provisions, interstate apportionment, QLD deduction taper,
  WA diminishing threshold, VIC surcharge tiers are NOT modelled. For
  a grouped or multi-state employer, generate a company-specific
  calculator and register it as an entrypoint.
- SG quarterly maximum contribution base not modelled (only matters
  for salaries above ~$260k).
- PAYG withholding timing is not split out; `total_cash` assumes wages
  and withholding leave in the wage month. Add a lag in a generated
  skill if the company remits monthly/quarterly with material timing.

## Verification

- `pytest tests/test_au_payroll.py tests/test_au_rates.py`
- Reconcile one historical month of actual payroll against the model
  before trusting the forward view; record differences as corrections.
