# Recipe: Xero Australia data access

Reusable recipe for identifying, requesting, mapping, testing and
reconciling Xero report exports for an Australian entity. Follows the
`pull_edgar.py` pattern: fixture-first, source-registered, mapped
exactly, reconciled before use. No credentials in this repo - the live
connector is generated per company and uses host-managed OAuth.

## What to request from the client

From Xero, Accounting > Reports, one CSV each:

1. **Profit and Loss** - the modelling period, monthly if the forecast
   needs monthly actuals. Include tracking columns when departments or
   business units matter (Tracking Category > include in report).
2. **Balance Sheet** - as at the model's opening date.
3. **Account Transactions** (optional) - for GST verification on
   specific accounts when the P&L/BS don't tie to the BAS.

Ask whether reports were run GST-inclusive or GST-exclusive. Xero
defaults to exclusive; BAS-cash modelling breaks if an inclusive
export is treated as exclusive. If the client doesn't know, get the
period's total revenue independently (BAS 1A, bank deposits) and use
`detect_gst_inclusive` with that control.

## Load and inspect

```python
from pyfpa.io.xero_au import read_xero_report, detect_gst_inclusive

pl = read_xero_report("data/xero_pl_jul2026.csv")
pl.by_account()        # {account: amount} summed across tracking
pl.by_tracking()       # {"North": {...}, "South": {...}, "(untracked)": {...}}
flag = detect_gst_inclusive(pl, control_total=111000.00)
# False -> exclusive (safe); True -> inclusive (STOP, divide by 11 or re-export)
```

The raw export loads as it comes from Reports (observed on the Demo
Company (AU) Excel exports of the Profit and Loss and Balance Sheet,
5 September 2026, saved as CSV): three title rows, a blank row, then a
header whose account column is `Account` (column B on the Balance
Sheet). The reader takes the first period column after `Account` and
ignores comparative columns, so export one period per file rather than
a compare-periods layout. Section rows, `Total <section>` subtotals and
the derived Gross Profit, Net Profit and Net Assets rows are dropped.
Xero writes natural balances (expenses and liabilities positive); the
reader negates rows under expense, cost, liability and equity sections
so income and assets come out positive, matching the flat
`Code,Account,Amount` shape the fixtures use. Account codes appear only
when the report is set to show them, as `Sales (200)`, and are split
off. Export CSV or save the workbook from Excel first: every total in
the `.xlsx` is a formula whose cached value is 0, which any non-Excel
reader of the total rows would take at face value.

Untracked rows land under `(untracked)` - if the entity tracks
departments, any `(untracked)` balance on revenue or direct costs is a
mapping conversation, not a default to sweep under head office.

## Register and map

```bash
python3 -m pyfpa.cli init <company-root> --business-name "<Name>"
python3 -m pyfpa.cli source-register <company-root> \
  --source-id xero-au --kind accounting_system \
  --location "data/xero_pl_jul2026.csv" \
  --entity "<Entity Pty Ltd>" --currency AUD \
  --period 2026-07 \
  --extraction-method "Xero P&L CSV export, GST-exclusive, tracking by Region"

python3 -m pyfpa.cli mapping-register <company-root> --source-id xero-au \
  --source-value "Sales - Domestic" --target revenue.domestic
python3 -m pyfpa.cli mapping-register <company-root> --source-id xero-au \
  --source-value "Sales - GST Free" --target revenue.gst_free \
  --rationale "No output GST; excluded from monthly_gst taxable share"
python3 -m pyfpa.cli mapping-register <company-root> --source-id xero-au \
  --source-value "Wages and Salaries" --target opex.wages
python3 -m pyfpa.cli mapping-register <company-root> --source-id xero-au \
  --source-value "Superannuation" --target opex.super \
  --rationale "Reconcile against pyfpa.au payroll_forecast SG line"
python3 -m pyfpa.cli mapping-register <company-root> --source-id xero-au \
  --source-value "Payroll Tax" --target opex.payroll_tax
python3 -m pyfpa.cli mapping-register <company-root> --source-id xero-au \
  --source-value "Workers Compensation" --target opex.workers_comp
# Balance-sheet clearing accounts feed the GST/PAYG cash bridge:
python3 -m pyfpa.cli mapping-register <company-root> --source-id xero-au \
  --source-value "GST" --target liability.gst_clearing
python3 -m pyfpa.cli mapping-register <company-root> --source-id xero-au \
  --source-value "PAYG Withholdings Payable" --target liability.payg
```

Ignore nothing silently: `Interest Income` either maps
(`revenue.other`) or gets an explicit ignored rule with rationale.

## Reconcile before modelling

```bash
python3 -m pyfpa.cli reconcile-source <company-root> --source-id xero-au \
  --account-column Account --amount-column Amount
```

- Fails on duplicate account names in the export, unmapped accounts, or
  out-of-tolerance totals. That is the point: unmapped is surfaced, not
  defaulted.
- **Tracking-split exports repeat account rows** (one per option), which
  `reconcile-source` reads as duplicates. Aggregate to one row per
  account with `report.by_account()` before reconciling (or export
  per-option columns). Keep the split file for department mapping; keep
  the aggregated file as the registered source.
- Tie P&L revenue to BAS 1A + GST-free sales for the same period.
  Difference should equal output GST within rounding; record a
  correction note if not.
- Payroll actuals vs `pyfpa.au.payroll_forecast`: wages, super and
  payroll tax lines each reconcile to the model's gross_wages,
  super_guarantee and payroll_tax columns for the same month.

## Connector

Only when recurring access is worth it:

```bash
python3 -m pyfpa.cli connector-scaffold <company-root> --name xero-au \
  --source-id xero-au --description "Monthly Xero P&L + BS pull" \
  --auth-method host_environment --fixture data/xero_pl_jul2026.csv
python3 -m pyfpa.cli connector-validate <company-root> --name xero-au
```

The scaffolded connector runs in fixture mode as a contract test. Live
extraction (Xero API, OAuth 2.0 PKCE, token refresh) is implemented
separately per company with host-managed credentials; register the
tested recurring command with `entrypoint-register`.

## Australian specifics to check every time

- **GST-inclusive exports**: the single most common silent error. Run
  the detector or get a control total.
- **Clearing accounts**: `GST`, `GST Clearing`, `PAYG Withholdings
  Payable` balances reconcile to the last lodged BAS and the next
  expected settlement in the 13-week model.
- **Wages timing**: Xero accrues wages on pay date; the cash model
  assumes same-month cash. Material for fortnightly payroll crossing
  month boundaries - note it, rarely model it.
- **Tracking categories**: confirm all revenue and COGS rows carry an
  option before relying on department forecasts.
