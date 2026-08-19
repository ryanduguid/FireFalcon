# Recipe: Australian economic drivers

Adapters for official source data feeding revenue, wage, financing and
sensitivity models. Snapshots keep forecasts reproducible after the
publisher revises a series.

## Sources

| Series | Source | Key | Cadence |
|--------|--------|-----|---------|
| Cash rate target | RBA F1 | `cash_rate_target` | daily, stored monthly |
| AUD/USD | RBA F11.1 | `aud_usd` | daily, stored monthly |
| Trade-weighted index | RBA F11.1 | `twi` | daily, stored monthly |
| CPI | ABS Indicator API | `cpi_monthly` / `cpi_quarterly` | M / Q |
| Wage Price Index | ABS Indicator API | `wpi` | Q |
| Retail trade | ABS Indicator API | `retail_trade` | M |
| Labour force | ABS Indicator API | `labour_force` | M |

RBA tables are public CSV downloads, no key. The ABS Indicator API
requires a key: request from api.data@abs.gov.au, then provide via the
`ABS_API_KEY` environment variable. Never commit the key, and never
bake it into a generated connector.

## Fetch and snapshot

```python
from pyfpa.au.drivers import fetch_rba_series, save_snapshot

cash = fetch_rba_series("cash_rate_target")
save_snapshot(cash, "data/drivers")   # rba_cash_rate_target_2026-08-20.json
```

Or the batch script:

```bash
python3 scripts/au_drivers_snapshot.py --out data/drivers
```

Every snapshot carries source_url, series id, units, frequency and the
retrieval date. Re-running never overwrites an existing file; a
revision by the RBA creates a new dated snapshot, and which one a
forecast used stays auditable.

## Use in a model

```python
from pyfpa.au.drivers import load_snapshot

cash = load_snapshot("data/drivers/rba_cash_rate_target_2026-08-20.json").to_series()
latest = cash.iloc[-1]                      # 4.35 (per cent)
# debt pricing: model facility margin over the latest cash rate, or
# stress with +100bp / +200bp scenarios.
```

Wage escalation: use ABS WPI year-ended growth as the base escalation
for `Role.annual_salary` in `pyfpa.au.payroll`, then layer award or
EBA-specific rates per role in the company workspace. CPI is the
default deflator for revenue sensitivity on CPI-linked contracts.

## Register as a source

Snapshots are data like any other:

```bash
python3 -m pyfpa.cli source-register <company-root> \
  --source-id rba-f1 --kind public_filing \
  --location data/drivers/rba_cash_rate_target_2026-08-20.json \
  --entity "Australia" --currency AUD --period 2026-08 \
  --extraction-method "RBA F1 statistical table CSV snapshot"
```

## Pitfalls

- RBA daily series are stored here at month granularity (month of the
  observation date). For exact announcement-date modelling, snapshot
  the raw table in the company workspace instead.
- The J1 table is market economists' FORECASTS, not actuals. Useful for
  consensus scenarios; label it as such and never mix into an actuals
  series.
- ABS dataflows return full history per dataflow; parse dimensions in
  a generated company skill when you need a specific sub-series
  (e.g. retail by industry group).
