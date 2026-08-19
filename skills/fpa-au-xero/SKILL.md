---
name: fpa-au-xero
description: Use when onboarding an Australian company whose books are in Xero - request reports, detect GST-inclusive exports, map chart of accounts and tracking categories, reconcile to BAS and payroll before modelling.
---

# Xero Australia Onboarding

Use when a company's accounting system is Xero (AU). The recipe at
`docs/recipes/xero-au.md` is the canonical walkthrough; this skill is
the operating loop.

## Workflow

1. **Request exports** per the recipe: P&L for the period (monthly
   preferred), balance sheet at opening date, both GST-EXCLUSIVE.
   Confirm the basis explicitly; ask for BAS 1A/1B totals for the same
   period as an independent control.
2. **Load and inspect** with `pyfpa.io.xero_au.read_xero_report`.
   Check `by_tracking()` for `(untracked)` revenue/COGS - surface to
   the user before mapping.
3. **GST basis check**: `detect_gst_inclusive(report, control_total=...)`
   when a control exists. Inclusive result = stop; re-export or divide
   by 11, never proceed silently.
4. **Register + map** via `source-register` / `mapping-register`.
   Standard AU accounts get standard targets: Wages -> opex.wages,
   Superannuation -> opex.super, Payroll Tax -> opex.payroll_tax,
   GST/PAYG clearing -> liability.*. GST-free sales map separately
   (revenue.gst_free) so `pyfpa.au.monthly_gst` gets the right
   taxable share.
5. **Reconcile**: `reconcile-source` must pass. Then two AU ties:
   (a) P&L revenue vs BAS 1A + GST-free sales; (b) wages/super/payroll
   tax vs `pyfpa.au.payroll_forecast` for a matching month. Record
   differences as corrections, not adjustments in the fixture.
6. **Connector** only for recurring pulls: `connector-scaffold` from
   the redacted fixture, `connector-validate` as the fixture-mode
   contract test, live OAuth 2.0 PKCE implemented per company with
   host-managed credentials.

## Pitfalls

- Never commit a real client export; fixtures must be synthetic or
  confirmed-safe redactions. House rule, no exceptions.
- Xero report layouts vary: some omit the Code column, some add
  comparative-period columns. Parse by header name, not position.
- Duplicate account names across tracking splits are normal; the
  parser sums them by account. `reconcile-source` still flags
  duplicates in single-account-column exports.
- Balance-sheet clearing accounts drive the GST/PAYG cash bridge in
  the 13-week model; an unreconciled clearing balance means the BAS
  forecast week is a guess.

## Verification

- `pytest tests/test_io_xero_au.py`
- One historical month end-to-end: fixture -> mapping -> reconcile ->
  payroll/GST tie-out -> record evidence in `.fpa/research/`.
