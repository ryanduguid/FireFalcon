# Recipe: Xero Australia data access

Reusable recipe for identifying, requesting, mapping, testing and
reconciling Xero report exports for an Australian entity. Follows the
`pull_edgar.py` pattern: fixture-first, source-registered, mapped
exactly, reconciled before use. No credentials in this repo - the live
connector is generated per company and uses host-managed OAuth.

## What to request from the client

From Xero, Reporting > All reports, obtain these reports:

1. **Profit and Loss** - the modelling period, monthly if the forecast
   needs monthly actuals. Keep a separate tracking comparison when departments
   or business units matter; select tracking mode as described below.
2. **Balance Sheet** - as at the model's opening date.
3. **Account Transactions** (optional) - for GST verification on
   specific accounts when the P&L/BS don't tie to the BAS.

The P&L and Balance Sheet export menus observed in Demo Company (AU) on
13 September 2026 offered Excel, PDF and Google Sheets, with no CSV option.
Choose Excel, let Excel recalculate, then save the required worksheet as
CSV UTF-8. Keep the original workbook and record the conversion in the source
manifest. The reader accepts CSV, not an `.xlsx` renamed to `.csv`.

Ask whether reports were run GST-inclusive or GST-exclusive. Xero
defaults to exclusive; BAS-cash modelling breaks if an inclusive
export is treated as exclusive. If the client doesn't know, get the
report settings or an independently reconciled GST-exclusive revenue total
for the same accounts, period and accounting basis. Use that total with
`detect_gst_inclusive`. Without a usable control, it returns `None`.
BAS 1A is GST on sales, not total revenue. Bank deposits also need reconciliation
for timing and non-revenue receipts before they can support a revenue control.

## Load and inspect

```python
from pyfpa.io.xero_au import read_xero_report, detect_gst_inclusive

pl = read_xero_report("data/xero_pl_jul2026.csv")
pl.by_account()        # {account: amount} summed across tracking
pl.by_tracking()       # {"North": {...}, "South": {...}, "(untracked)": {...}}
flag = detect_gst_inclusive(pl, control_total=111000.00)
# False -> consistent with exclusive; True -> consistent with inclusive.
# None -> undetermined. Confirm the report basis before modelling.
```

An inclusive result calls for a GST-exclusive re-export. For a wholly taxable
amount at 10%, divide by 1.1 to obtain the exclusive amount; dividing by 11
extracts only the GST component. For example, $1,100 comprises $1,000 exclusive
and $100 GST. Mixed GST treatments need account-level reconciliation, so the
detector's 1.1 comparison cannot establish their basis.
See the [Moneysmart GST calculator](https://moneysmart.gov.au/work-and-tax/gst-calculator).

The raw export loads as it comes from Reports (observed on the Demo
Company (AU) Excel exports of the Profit and Loss and Balance Sheet,
5 September 2026, saved as CSV): 3 title rows, a blank row, then a
header whose account column is `Account` (column B on the Balance
Sheet). In its default period mode, the reader requires English year,
month/year or day/month/year headings, takes the first period column after
`Account` and ignores subsequent period columns. Export one period per file
when loading monthly actuals. Other headings are refused unless tracking
mode is explicitly selected below. Section rows, `Total <section>` subtotals
and the derived Gross Profit, Net Profit and Net Assets rows are dropped. A
`Total X` row is dropped only after an `X` heading (or `Less X`); any other row
starting `Total ` is refused, because it may be a posting account. A flat file
is refused when a row has more filled fields than the header (quote amounts
that contain commas), a filled row has no account, or a column is unnamed or
repeated.
Xero writes natural balances (expenses and liabilities positive); the
reader negates rows under expense, cost, liability and equity sections
so income and assets come out positive, matching the flat
`Code,Account,Amount` shape the fixtures use. Account codes appear only
when the report is set to show them, as `Sales (200)`, and are split
off. Save the workbook as CSV from Excel first: totals in
the `.xlsx` are formulas whose cached values are 0, which a reader relying
on those cached values would take at face value.

Xero's **Compare Region** export puts tracking options across columns, for
example `Account,Eastside,North,South,West Coast,Unassigned` (observed
13 September 2026). Confirm the source is a single-period P&L with one option
per amount column, then load it directly:

```python
report = read_xero_report("data/xero_pl_regions.csv", tracking_comparison=True)
regional_accounts = report.by_tracking()
combined_accounts = report.by_account()
```

This mode normalises every option's posting accounts and maps `Unassigned`
to `(untracked)`. Reconcile every option and the combined total before use.
The default period mode remains separate: names such as `2026` could be a
year or a tracking option, so the CSV header cannot establish the mode.
Tracking mode refuses duplicate or blank option names, a `Total` column,
the reserved `(untracked)` label, malformed amounts and incomplete posting
rows. Custom totals, renamed derived rows and multi-category layouts are
outside this observed contract.

Existing flat `Code,Account,Amount,Tracking Option` files still load without
the flag. Their amounts must already be signed, with one row per posting
account and option and an empty option for unassigned amounts.

An empty report containing only derived totals is refused with `no rows parsed`.
Confirm the selected period and source completeness before treating it as a
zero-activity period; the reader does not create zero actuals from that error.

Untracked rows land under `(untracked)` - if the entity tracks
departments, any `(untracked)` balance on revenue or direct costs is a
mapping conversation, not a default to sweep under head office.

## Register and map

From the company root, persist the account totals before registration. Keep the original tracking export for department mapping:

```python
import csv
from pathlib import Path
from pyfpa.io.xero_au import read_xero_report

report = read_xero_report("data/xero_pl_jul2026.csv")
with Path("data/xero_pl_jul2026_accounts.csv").open("x", encoding="utf-8", newline="") as output:
    writer = csv.writer(output)
    writer.writerow(["Account", "Amount"])
    writer.writerows(sorted(report.by_account().items()))
```

```bash
python3 -m pyfpa.cli init <company-root> --business-name "<Name>"
python3 -m pyfpa.cli source-register <company-root> \
  --source-id xero-au --kind accounting_system \
  --location "data/xero_pl_jul2026_accounts.csv" \
  --entity "<Entity Pty Ltd>" --currency AUD \
  --period 2026-07 \
  --extraction-method "Account totals from data/xero_pl_jul2026.csv, GST-exclusive, tracking by Region"

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
  --account-column Account --amount-column Amount \
  --expected-json '<reviewed target-to-total JSON object>'
```

- Expected totals must come from an independently reviewed control, not a copy of the mapped totals. A target agrees when its variance is within `--abs-tolerance` (default `0.005`, so only sub-cent differences pass). Whole-dollar controls, such as BAS labels, rounded statements or Xero reports with decimals cleared, need `--abs-tolerance 0.5`. `--tolerance` adds a relative allowance as a fraction (`0.01` means 1%) and is off by default, because a relative allowance hides amounts cross-mapped between targets.
- Fails on missing expected totals, duplicate account names in the export, unmapped accounts, or
  out-of-tolerance totals. That is the point: unmapped is surfaced, not
  defaulted.
- **Tracking-split exports repeat account rows** (one per option), which
  `reconcile-source` reads as duplicates. Aggregate to one row per
  account with `report.by_account()` before reconciling (or export
  per-option columns). Keep the split file for department mapping; keep
  the aggregated file as the registered source.
- Reconcile P&L revenue with BAS G1 total sales for the same period, accounting
  for the declared GST basis, cash/accrual timing and classification differences.
  Reconcile GST on sales separately to 1A. G1 already includes GST-free sales;
  do not add them again. Record the reconciliation and explain differences.
  The [ATO BAS labels](https://softwaredevelopers.ato.gov.au/SimplerBAS) distinguish
  G1 total sales, 1A GST on sales and 1B GST on purchases.
- Payroll actuals versus `pyfpa.au.payroll_forecast`: wages, super and
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

Register the connector's pulls with `--kind api` and keep reports exported
by hand as `accounting_system`, so every source records whether it came
through the Xero API. Xero's
[Developer Platform terms](https://developer.xero.com/xero-developer-platform-terms-conditions)
(last updated 4 December 2025, applying from 2 March 2026 to developers
registered earlier) treat data obtained through the API, raw or processed, as
API data. They limit it to the app's approved use case and bar using it to
train, fine-tune, adapt or enhance AI models, which they define to include
predictive analytics tools. `fpa-backtest-learn`, `fpa-research-loop` and
`fpa-portfolio-learn` change models, priors or skills from actuals, so before
they use an `api` Xero source the company owner confirms that the terms permit
it, and the decision is recorded under `.fpa/decisions/`. Portfolio learning
across clients also needs a check against the terms' restrictions on
aggregating user data or API data. This recipe does not decide whether a
particular workflow falls within the terms.

## Australian specifics to check every time

- **GST-inclusive exports**: confirm the report basis and use a reconciled
  control total. Treat `None` from the detector as unresolved.
- **Clearing accounts**: `GST`, `GST Clearing`, `PAYG Withholdings
  Payable` balances reconcile to the last lodged BAS and the next
  expected settlement in the 13-week model.
- **Wages timing**: Xero accrues wages on pay date; the cash model
  assumes same-month cash. Material for fortnightly payroll crossing
  month boundaries - note it, rarely model it.
- **Tracking categories**: confirm all revenue and COGS rows carry an
  option before relying on department forecasts.
