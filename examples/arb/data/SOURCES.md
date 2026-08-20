# Sources

All figures transcribed from ARB Corporation Limited's Appendix 4E and annual
report for the year ended 30 June 2025, released to ASX on 19 August 2025.

PDF: https://announcements.asx.com.au/asxpdf/20250819/pdf/06n0z50mr65hhq.pdf

CSV amounts are in AUD, not $'000. Multiply the report's thousands by 1,000.

## Income statement

Consolidated income statement (report $'000):

| Line | FY2025 | FY2024 | Notes |
|---|--:|--:|---|
| Sales revenue | 729,949 | 693,154 | `net_sales` |
| Materials and consumables used | 315,721 | 296,468 | `cost_of_sales` |
| Gross profit | 414,228 | 396,686 | **Constructed** as sales minus materials. ARB does not print a gross-profit line. |
| EBIT | 136,144 | 141,813 | KPI table "Earnings before interest and tax" |
| Finance expense | 2,357 | 1,693 | `interest_expense`. Includes lease interest; ARB reports no borrowings. |
| Profit before income tax | 134,938 | 141,419 | |
| Income tax expense | 37,411 | 38,736 | |
| NPAT | 97,527 | 102,683 | |

## Balance sheet

| Line | FY2025 | FY2024 | Notes |
|---|--:|--:|---|
| Cash | 69,198 | 56,502 | |
| Trade receivables | 90,481 | 89,950 | Note 7. Used as AR, not the broader receivables line 93,342. |
| Inventories | 249,061 | 239,755 | |
| Payables | 65,163 | 62,881 | Note 12 total current payables (trade + other). |

## Cash flow

| Line | FY2025 | FY2024 | Notes |
|---|--:|--:|---|
| Operating cash flow | 127,953 | 125,285 | |
| Payments for PPE | 46,194 | 48,050 | `capex`. Excludes associates, intangibles, and acquisitions. |
| Depreciation and amortisation | 32,509 | 28,434 | P&L figure. Cash-flow note 20 shows 32,510 for FY2025 ($1k rounding). |

## Sales channels

Operating and financial review, sales channel table ($'000):

| Channel | FY2025 | FY2024 | Change |
|---|--:|--:|---|
| Australian Aftermarket | 403,281 | 404,135 | (0.2%) |
| Exports | 266,993 | 229,424 | 16.4% |
| Original Equipment | 59,675 | 59,595 | 0.1% |
| Total | 729,949 | 693,154 | 5.3% |

ARB does not disclose channel EBITDA. The model allocates consolidated EBITDA
(EBIT + D&A) by sales mix so the engine has a Segment object. That allocation
is a modelling choice, not a filing line.

## Honest strain

- PDF transcription, not an XBRL pull. Re-check the PDF before treating a
  figure as authoritative.
- Thai Baht and US auto/steel/aluminium tariffs are a **labeled sensitivity**
  (+150bps COGS), not a kernel FX/tariff engine.
- Franking credits ($112,022k) and special/final dividends are documented in
  the filing and not modelled.
- No FY2023 balance sheet in this 4E, so Phase A reproduces FY2025 only.
- GST/BAS is the Harbour Light example. ARB is an annual public proof.
