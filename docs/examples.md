## Runnable examples

### Lumbridge Services

[`examples/lumbridge-services/`](../examples/lumbridge-services/) is a synthetic
Newcastle NSW maintenance business with OSRS references. It reconciles source
accounts, monthly pre-tax profit and 13 weeks of dated bank cash. A
45-day receipt delay changes cash and receivables without changing profit.

```bash
uv run --locked --extra dev python examples/lumbridge-services/models/generated/lumbridge.py
```

The output includes a verified Excel workbook, management briefing and CSVs.
The [trial guide](../examples/lumbridge-services/TRIAL.md) separates technical
verification from an independent accountant trial, which has not been performed.

### Ridgeline Chair Co.

[`examples/ridgeline/`](../examples/ridgeline/) is a synthetic product-company
example with a monthly forecast, a 13-week cash forecast, and reporting output.

```bash
python3 examples/ridgeline/run_demo.py
```

The example shows an inventory build creating a near-term liquidity gap before
seasonal collections arrive.

### Fox Factory

[`examples/foxfactory/`](../examples/foxfactory/) applies the workflow to public,
source-traced SEC data for Fox Factory Holding Corp.

```bash
python3 examples/foxfactory/run_foxf.py
```

The example has 4 distinct phases:

1. **Actual-driver reproduction.** The engine reproduces known accounting
   mechanics using reported drivers. This validates arithmetic, not forecast
   skill.
2. **Historical holdout research.** A FY2025 holdout rejects an aggressive
   recovery challenger and proposes a better revenue-recovery and slow-margin
   challenger.
3. **Forward forecast.** A FY2026-FY2027 segment forecast is anchored to the
   reported Q1 FY2026 result.
4. **Capital allocation sensitivity.** A labelled Marucci divestiture scenario
   shows the tradeoff between free cash flow and leverage.

The full proof runs in CI across Python 3.14. See
[`examples/foxfactory/README.md`](../examples/foxfactory/README.md) for the
methodology and limitations.
