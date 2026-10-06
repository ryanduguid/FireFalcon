# Recipe: Australian economic drivers

Adapters for official source data feeding revenue, wage, financing and
sensitivity models. Snapshots keep forecasts reproducible after the
publisher revises a series.

## Sources

| Series | Source | Key | Dataflow | Cadence |
|--------|--------|-----|----------|---------|
| Cash rate target | RBA F1 | `cash_rate_target` | F1 `FIRMMCRTD` | daily, stored monthly |
| AUD/USD | RBA F11.1 | `aud_usd` | F11.1 `FXRUSD` | daily, stored monthly |
| Trade-weighted index | RBA F11.1 | `twi` | F11.1 `FXRTWI` | daily, stored monthly |
| CPI | ABS Indicator API | `cpi_monthly` | `CPI_H` | M |
| CPI | ABS Indicator API | `cpi_quarterly` | `CPI_Q_H` | Q |
| Wage Price Index | ABS Indicator API | `wpi` | `WPI_H` | Q |
| Retail trade (historical) | ABS Indicator API | `retail_trade` | `RT_H` | M, ceased |
| Labour force | ABS Indicator API | `labour_force` | `LF_H` | M |

Each RBA month uses the latest valid dated observation, independent of CSV row
order, and months are returned chronologically. Identical observations for the
same date are accepted; conflicting values for that date raise `ValueError`.

Indicator API dataflow ids carry the `_H` suffix; the unsuffixed `CPI`, `WPI`,
`RT` and `LF` belong to the separate Data API. `CPI_H` became monthly in
November 2025, when `CPI_M` and `CPI_M_H` ceased, and quarterly CPI returned as
`CPI_Q_H` in April 2026.

**Retail trade is history, not a live driver.** Retail Trade, Australia ceased
with the June 2025 period and `RT_H` is no longer updated. The ABS replacement
publication is the Monthly Household Spending Indicator (`HSI_M_H`), which
measures household spending rather than retail turnover, so assess it as a
different concept rather than a drop-in substitute.

`fetch_abs_series` checks that each key returns the frequency in this table and
raises when it does not, so a monthly dataflow cannot arrive under a quarterly
name.

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

ABS observations must represent one series. Select dimensions explicitly
when a dataflow contains multiple series, using the exact column names and
codes from its export:

```python
from pyfpa.au.drivers import fetch_abs_series

# Supply the dimension columns and codes from the selected ABS series.
series = fetch_abs_series("wpi", dimensions=selected_dimensions)
save_snapshot(series, "data/drivers")
```

The snapshot preserves the selection and reported units. Duplicate periods,
mixed units, multiple dimension combinations and selections with no
observations raise an error. Different series are rejected even when their
periods do not overlap. Observation attributes such as `OBS_STATUS` may
change within a series. The batch
script reports ambiguous dataflows as errors; use the Python function with
an explicit selection for those dataflows. It never picks the last row.

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
- ABS dataflows can contain multiple series. Confirm the dimension selection
  before using a snapshot, including region, industry and adjustment basis.
