---
name: fpa-scaffold-model
description: Use when building a new openfpa forecast model from a company's financials - a trial balance, a P&L export, or a pasted income statement - and you need a runnable config to exist before any forecasting or analysis.
---

# Scaffold a model (Phase 1)

## Overview

Turn a company's financials into a runnable `pyfpa` config. Read the business profile first (see **fpa-learn-business**), infer the chart-of-accounts → model-line mapping, and write a validated `EntityConfig` YAML following openfpa conventions. Output a runnable skeleton plus an explicit list of assumptions to confirm.

Map the real numbers onto the existing engine structure.

## When to use

- A trial balance / P&L (CSV, XLSX, or pasted) needs to become a forecast model
- Onboarding follow-on after `.fpa/business-profile.md` exists

## Workflow

1. **Normalise and ingest** the financials. For XLSX or pasted statements, first save a reviewed UTF-8 CSV with `Account,Amount` columns, one row per account and numeric signed amounts. Reconcile the conversion to the supplied statement and preserve its source reference. Then call `pyfpa.read_pl_csv(path)` → `{account: amount}`. The reader accepts CSV, not workbooks or pasted text.
2. **Map accounts to model lines** of the `EntityConfig` schema:
   - revenue accounts → `channels[]` (one `Channel` per channel/segment, with `annual_revenue`, a 12-month `seasonality` weight list, `growth_rate`, `cogs_pct`)
   - cost accounts → `opex[]` as `OpexLine(kind="fixed", monthly_amount=…)` or `kind="variable", pct_of_revenue=…`
   - debt → `debt[]` (`term_loan` with `monthly_principal`, or interest-only `loc`)
   - balance-sheet rhythm → `working_capital(dso_days, dpo_days, dio_days)` and `opening_balances`
   - income tax → `tax_rate`, which is required: 25% for a base rate entity, otherwise 30%. Ask; do not assume either.
3. **Write** the company model and config under `models/generated/`. Validate
   config with `pyfpa.load_config(path)`, which raises on a missing required
   field, an out-of-range value, and any key the schema does not define, so a
   misspelt field cannot fall back to its default unreported.
4. **Create a runnable command** such as
   `python3 models/generated/run_forecast.py`. Keep the runner thin and make its
   output locations explicit.
5. **Run and validate it.** Confirm the model executes, reconciles its inputs,
   and writes the expected outputs.
6. **Register the tested command** with `openfpa entrypoint-register`, including
   its inputs and outputs. Registration publishes the command for agent
   discovery; it does not run it.
7. **Surface assumptions**: list the 6 to 10 inferences a human must confirm
   (seasonality shape, fixed versus variable splits, cogs_pct per channel, opening
   balances, the company tax rate). Do not bury them.

## Conventions (match the engine)

- For a config-backed generated model, keep assumptions in validated YAML rather
  than scattering company numbers through code.
- Set `opening_balances` AR/AP/inventory to the **first forecast month's** DSO/DPO/DIO-implied balances - the engine diffs each month against the prior, seeding month 1 against opening, so use month-1 projected revenue/COGS, NOT the annual average. Get this wrong and month-1 cash swings on a one-time artefact (see **fpa-cfo-judgment** working-capital seam).
- `"total"` is a reserved channel/opex name (the engine adds a `total` column).

A live-formula Excel edition of the model is available via **fpa-excel-model**.

## Next

Runnable config confirmed → **fpa-configure-actuals** to wire live/real numbers, then the operate skills.
