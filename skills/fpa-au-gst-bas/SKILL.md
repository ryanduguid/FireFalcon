---
name: fpa-au-gst-bas
description: Use when forecasting cash for a GST-registered Australian entity - net GST positions, BAS settlement timing (monthly or quarterly), GST-free and input-taxed categories, 13-week cash impacts.
---

# Australian GST and BAS Cash Timing

Use when forecasting cash for a GST-registered Australian entity. GST
collections and BAS settlements create material cash swings that a
naive P&L-to-cash bridge misses entirely.

## Workflow

1. Establish facts (intake): BAS cycle (quarterly default; monthly
   mandatory at $20m+ GST turnover), share of GST-free or input-taxed
   revenue, share of purchases without input tax credits, whether a
   tax/BAS agent lodges (extensions).
2. Compute the monthly net GST position from GST-EXCLUSIVE series:

   ```python
   from pyfpa.au import BasCycle, GstAssumptions, bas_schedule, monthly_gst

   gst = monthly_gst(revenue_ex_gst, purchases_ex_gst,
                     GstAssumptions(bas_cycle=BasCycle.QUARTERLY))
   schedule = bas_schedule(gst["net_gst"])
   ```

3. Feed the 13-week model:

   ```python
   from pyfpa.au import gst_weekly_flows

   receipts, disbursements = gst_weekly_flows(schedule, window_start="2026-10-01")
   config.receipts.extend(receipts)
   config.disbursements.extend(disbursements)
   ```

4. Reconcile: management P&L (GST-exclusive) vs bank cash (GST-inclusive).
   Receipts in the cash model should run ~1.1x taxable revenue; the
   difference accumulates as a GST liability until BAS settlement.

## Due dates

Original due dates only (28 Oct / 28 Feb / 28 Apr / 28 Jul quarterly;
21st following month for monthly). Agent lodgment program extensions
are NOT modelled; forecasting on original dates is conservative for
payments. If the company relies on agent extensions for cash, override
due dates in a generated company skill.

## Pitfalls

- Never apply 10% to a GST-inclusive number; divide by 11 to extract
  GST from inclusive amounts.
- Wages and super carry no GST; do not run payroll through
  `monthly_gst` purchases.
- A quarter is only scheduled when all 3 months exist in the series;
  partial trailing quarters are dropped, not prorated.
- Refund positions (heavy capex) return as receipts; check the refund
  is plausible before banking it in week 4.
