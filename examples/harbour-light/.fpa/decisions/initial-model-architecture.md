# Initial Model Architecture

**Status:** Approved for the synthetic Harbour Light example.

## Objective

Prove the Australian pack on one company: Xero mapping, statutory payroll,
quarterly BAS into 13-week cash, and a verified live-formula workbook.

## Data Access

- Committed Xero Australia GST-exclusive fixtures.
- Tracking file is the channel source. Aggregated P&L is the lineage source
  (`reconcile-source` rejects duplicate account rows).

## Model Components

- North / South revenue channels, 30 June year, 30 percent company tax.
- Payroll from `payroll_forecast`, not from copying Xero wage on-cost lines
  except as a reconciling check.
- GST cash on the 13-week model only. The monthly engine has no GST ledger.

## Validation

- Fixture mapping totals.
- BAS due dates for FY2027.
- `verify_workbook` against `cashflow_from_config`.
