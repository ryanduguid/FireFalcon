# Harbour Light Pty Ltd

Synthetic Victorian lighting wholesaler for FY2027 (July 2026 – June 2027).
This is the Australian pack's Xero / payroll / GST worked example. It is not a
client. Numbers come from the committed Xero fixtures.

```bash
python3 examples/harbour-light/run_harbour.py
```

## What it proves

- Xero GST-exclusive P&L with North/South tracking annualises into `EntityConfig`
  channels.
- `payroll_forecast` for VIC roles ties gross wages and super to the Xero wage
  and super lines. Payroll tax in the fixture ($1,300) is **not** used: wages sit
  under Victoria's $1m threshold, so the kernel pays nil. That gap is the point
  of using statutory tables instead of copying the export.
- Quarterly BAS from GST-exclusive sales and creditable purchases lands in the
  13-week cash model (September quarter due 28 October 2026).
- `model_to_excel` is verified against `cashflow_from_config` in CI.

## What it does not do

- Monthly GST settlement (this entity is quarterly).
- Live Xero OAuth. Fixtures only.
- Franking, PAYG instalments, or grouping.

See `.fpa/` for lineage, intake, and the registered `harbour-light-pipeline`
entrypoint.
