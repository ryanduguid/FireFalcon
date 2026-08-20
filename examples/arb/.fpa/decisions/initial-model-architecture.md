# Initial Model Architecture

**Status:** Approved for the ARB Corporation public example.

## Objective

Demonstrate a source-traced ASX workflow with separate accounting
reproduction, historical holdout, forward forecast, and a labeled cost-pressure
sensitivity.

## Data Access

- Committed CSV extracts from the FY2025 Appendix 4E PDF.
- `data/SOURCES.md` preserves the filing trail. No live scrape.

## Model Components

- Consolidated kernel for revenue, materials-as-COGS, working capital, cash.
- Three sales channels. Channel EBITDA allocated from consolidated EBIT + D&A.
- FY2025 champion/challenger holdout (no WC-days metric).
- FY2026-FY2027 forecast from the August 2025 view.
- THB/tariff +150bps COGS sensitivity.

## Validation

- Source totals versus SOURCES.md.
- FY2025 actual-driver reproduction at 1 percent tolerance.
- Holdout rejects uniform export-rate growth.
