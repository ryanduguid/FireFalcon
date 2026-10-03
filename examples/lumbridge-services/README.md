# Lumbridge Services: profit does not pay the next bill

Lumbridge Services is a fictional maintenance business in Newcastle, NSW.
Its Varrock maintenance and Falador repairs service lines are OSRS references.
All amounts are AUD. The business, customers, invoices and accounts are fabricated.

The [recurring cash example](RECURRING.md) retains the original forecast, reconciles
October actuals and carries a partly paid invoice into November exactly once.

The owner expects $35,957.55 profit before income tax for October to December
2026. Delaying one $44,000 receipt by 45 days leaves a $25,160 cash shortfall on
6 November. Both cases end December with $67,320 because the delayed receipt
eventually arrives. That recovery cannot fund payments due earlier.

## Run the example

From the repository root, use Python 3.12 and the locked development environment:

```bash
uv sync --locked --extra dev
uv run --locked --extra dev python examples/lumbridge-services/models/generated/lumbridge.py
```

Open `examples/lumbridge-services/output/briefing.md` and `lumbridge.xlsx`.
The same folder holds monthly, weekly and daily CSVs and a JSON summary.
The runner verifies all 21 monthly workbook lines against the Python model
before replacing the workbook. The briefing, CSVs and JSON summary are committed so the result can be read without running anything; the workbook is rebuilt locally and ignored by Git.

In Excel, change `Assumptions!B2` from 0 to 45. This moves invoice OPEN-V's
receipt from 14 October to 28 November. Restore 0 after the trial.
The workbook supports whole calendar-day delays from 0 to 120. Use desktop
Excel with calculation enabled. Workbook edits do not rewrite CSVs or the
briefing; rerun with the matching delay when you need a consistent export:

```bash
uv run --locked --extra dev python examples/lumbridge-services/models/generated/lumbridge.py --delay-days 45
```

The 13 weeks run from 2 October to 31 December 2026. The monthly view starts
1 October; the fixture has no bank transactions on that day. Week-end and
daily closing balances agree with the same dated cash records. Daily balances
net transactions on the same day and do not establish intraday liquidity.

## Read the source records

| File | What it represents | Use |
| --- | --- | --- |
| [xero_pl.csv](data/xero_pl.csv) | September 2026 fabricated GST-exclusive P&L | Revenue, materials, overhead and prior payroll costs |
| [xero_bs.csv](data/xero_bs.csv) | Fabricated balances at 30 September 2026 | Opening cash, gross receivables, payables, tax and loan balances |
| [payroll.csv](data/payroll.csv) | Three NSW employee roles | Reconcile gross wages, super and leave expense through the existing payroll kernel |
| [invoices.csv](data/invoices.csv) | September opening debtors and forecast October to December invoices | Revenue by service month and dated GST-inclusive receipts |
| [payments.csv](data/payments.csv) | Explicit future bank payments | Supplier, payroll, super, tax and loan cash dates |
| [assumptions.json](data/assumptions.json) | Declared synthetic assumptions | Period, jurisdiction, rates and cash buffer |

The 2 Xero files use the parser's normalised `Code,Account,Amount` layout,
with tracking on revenue. They are fabricated fixtures in a supported format,
not unedited exports captured from a live Xero account. Income and assets
are positive; expenses, liabilities and equity are negative.

The source registry records every input and both bundled payroll rate tables.
Every P&L and balance-sheet account has an exact mapping. Unknown or missing
accounts, unmatched payroll, incorrect invoice totals, duplicate invoice IDs,
non-finite amounts and inconsistent payment totals stop the run. Source cash
dates remain explicit assumptions. For a different business or payment cycle,
extend the example and its liability reconciliation before trusting the results.

## Accounting assumptions

- September revenue repeats at $60,000 a month, split $40,000 Varrock and
  $20,000 Falador. Monthly materials are $12,000 and operating overhead
  $6,000. There is no seasonality, price increase or actual forecast holdout.
- All modelled sales are taxable and the materials and overhead purchases
  are assumed fully creditable, with supporting tax invoices. The business
  uses invoice-basis GST. Net GST accrues at $4,200 a month. The $12,600
  opening GST balance is paid on 28 October. December's $12,600 GST liability
  remains unpaid at the horizon; it is not spendable surplus.
- Gross wages are $24,000 monthly. The 3 salaries total $288,000 a year,
  all assumed qualifying earnings for 12% SG. Super is $2,880 per month and
  cash is scheduled with net wages on 28 October, 27 November and 24 December.
  The example does not prove when a super fund receives a contribution.
- PAYG withheld is an explicit $5,000 monthly payroll assumption, not a
  withholding-table calculation. Employees receive $19,000 net. The prior
  month's $5,000 liability is paid in each forecast month and a new $5,000
  liability remains outstanding. Payment dates are in the CSV.
- This is a single, ungrouped, NSW-only employer for the full year. Annualised
  gross wages plus SG are $322,560, below the bundled $1.2 million NSW payroll
  tax threshold. The existing payroll kernel returns nil payroll tax; the
  case refuses a payroll-tax liability without a corresponding cash schedule.
- Workers compensation is a scenario estimate of 2% of gross wages,
  $480 monthly, paid monthly. It is not an insurer quote or statutory rate.
- Leave provisions add $2,254.15 monthly, using 4 weeks annual leave and
  a 1.7% long-service leave accrual assumption. No leave is taken this quarter.
  These are incremental unused-leave provisions, not another cash wage payment.
- Opening and monthly supplier payables remain $13,200 including GST.
  Each month's materials are purchased on credit and paid the following
  month. Overhead is paid in its expense month. No inventory is held.
- Opening loan principal is $20,000. The schedule pays $1,000 principal and
  a separately supplied $200 interest each month. Fixed interest is a
  synthetic contract assumption, not an amortising-loan calculation.
- A supplied $3,000 income tax instalment is paid on 28 October and treated
  as a tax prepayment. The report presents profit before income tax.
  It does not calculate company income tax expense or final tax liability.
- There is no planned capital expenditure, new borrowing, dividend or other
  owner withdrawal. Depreciation is $200 monthly. The $15,000 cash buffer
  is an owner-policy assumption for the demonstration.

The profit-to-cash bridge adds back depreciation and non-cash leave, adjusts
gross receivables and GST liabilities, then deducts loan principal and the tax
instalment. Supplier and PAYG liabilities are constant in this fixture, so
their changes are zero. The direct cash schedule independently ties to this
bridge to the cent. Equity and equipment support the opening balance-sheet
check; the output is not a complete forecast statutory balance sheet.

## Official reference checks

Checked on 10 September 2026. The source records above remain fictional.

- [Revenue NSW payroll tax thresholds and rates](https://www.revenue.nsw.gov.au/taxes-duties-levies-royalties/payroll-tax/lodge-and-pay-returns/thresholds-and-rates):
  $1.2 million annual threshold and 5.45% rate for 2026-27. Grouping and
  interstate treatment require separate assessment.
- [ATO Payday Super](https://softwaredevelopers.ato.gov.au/PaydaySuper) and
  [ATO's 12% SG explanation](https://community.ato.gov.au/s/article/a07Mo00001qD2iH/payday-super-has-started-heres-what-employers-need-to-know-and-do):
  super is scheduled with each salary payment. The workbook is a bank cash
  forecast, not a super payment-compliance test.
- [ATO BAS due dates](https://www.ato.gov.au/businesses-and-organisations/preparing-lodging-and-paying/business-activity-statements-bas/due-dates-for-lodging-and-paying-your-bas):
  28 October is the standard September-quarter date. The example uses
  explicit payment dates and does not infer agent concessions or holiday extensions.

## Independent trial

Give the reviewer [TRIAL.md](TRIAL.md), the generated workbook and the source
files. Keep [REVIEWER-KEY.md](REVIEWER-KEY.md) aside until they have recorded
their findings. No independent accountant has performed the trial.
Technical verification does not establish client suitability, forecast
accuracy or time saved.

OSRS references are naming and narrative only. No game assets or game prices
are used, and no affiliation with Jagex is claimed.
