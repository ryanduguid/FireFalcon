---
name: fpa-au-drivers
description: Use when an Australian forecast needs official economic drivers - RBA cash rate and exchange rates, ABS CPI/WPI/retail/labour series - snapshotted with provenance for reproducible scenarios.
---

# Australian Economic Drivers

Use when a model's assumptions should tie to official data: debt pricing
off the cash rate, wage escalation off WPI, CPI-linked revenue, FX
sensitivity. Recipe at `docs/recipes/au-drivers.md`; this skill is the
operating loop.

## Workflow

1. **Pick the driver** matching the assumption: cash rate target for
   debt pricing, AUD/USD or TWI for FX exposure, WPI for wage
   escalation, CPI for indexation, retail trade for consumer-demand
   revenue proxies.
2. **Snapshot before modelling**: `fetch_rba_series` (no key) or
   `fetch_abs_series` (ABS_API_KEY env var), then `save_snapshot`. The
   forecast cites the snapshot file, so an upstream revision does not
   silently shift a published forecast.
3. **Register** the snapshot via `source-register` (kind
   `public_filing`) and record the driver-to-assumption link in
   `.fpa/decisions/` or a research epoch.
4. **Scenario**: drivers enter as base-case parameters; stress as
   deltas (+100bp cash rate, -10% AUD, WPI +1pp), never as edited
   source data.
5. **Refresh cadence**: monthly for RBA (tables update daily), on
   release days for ABS. Re-snapshot creates a new dated file; promote
   only after the new values reconcile against the old snapshot's
   overlapping history.

## Pitfalls

- No key handling in code: ABS_API_KEY comes from the host environment,
  full stop. A missing key skips ABS series; it never prompts, never
  fails a cash-rate-only run.
- RBA J1 = economists' forecasts. Consensus scenarios only, labelled.
- Month-granularity storage: daily announcement precision needs the raw
  table snapshotted in the company workspace.
- Driver values are point-in-time facts. Forecast-forward projections
  (e.g. cash rate futures) are assumptions the user supplies, recorded
  as intake facts with confidence, not adapter output.

## Verification

- `pytest tests/test_au_drivers.py`
- Spot-check one snapshot against the publisher's web table before
  first use in a client model; record the check in the research epoch.
