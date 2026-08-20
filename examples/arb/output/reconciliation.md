# Phase A - FY2025 actual-driver reproduction

The engine is driven with ARB's reported sales mix, materials/sales COGS,
working-capital days, D&A and PPE capex. EBITDA is EBIT + D&A.
Gross profit is sales minus materials (ARB does not print GP).

| Line | Model | Actual | Variance |
|---|--:|--:|--:|
| net_sales | 729,949,000 | 729,949,000 | +0.00% |
| gross_profit | 414,228,000 | 414,228,000 | +0.00% |
| ebitda | 168,653,000 | 168,653,000 | +0.00% |
| depreciation_amortization | 32,509,000 | 32,509,000 | -0.00% |
| capex | 46,194,000 | 46,194,000 | +0.00% |
| operating_cash_flow_before_tax | 161,098,000 | 161,098,000 | -0.00% |

This validates operating arithmetic, not forecast skill. Target-year
drivers are inputs. Tax, franking, associates, and acquisitions sit
outside the engine.
