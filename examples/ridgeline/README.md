# Review Ridgeline cash decisions

Compare the baseline with delayed wholesale receipts, lower D2C sales and two
additional staff using the existing weekly scenario engine. These are fabricated
sensitivities for review, with no approval of funding or management action.

From the repository root, use its locked environment and a new output directory:

```powershell
uv run --locked --extra dev python -m examples.ridgeline.decisions --output ../ridgeline-decisions
```

`decisions.json` retains the changed assumptions, unrounded metrics and one-off
receipts beyond the horizon. `decisions.md` renders the same result and includes
the metric dictionary. Each weekly frame is calculated once. These outputs use
model currency units and ordinal forecast weeks: `cash13.yaml` supplies neither
a currency nor a calendar start date.

The wholesale scenario delays both flows named `Wholesale AR collection` by
five weeks. One moves from week 9 to week 14, outside the thirteen-week horizon;
it is deferred, not cancelled. The D2C scenario applies its factor to the named
weekly sales flow. The hiring scenario adds payroll from week 5. Inspect their
cash troughs and first negative weeks before accepting the proposed timing.

The monthly model's December ending cash is a separate metric. The weekly
decision pack does not substitute that value for week-13 cash. `run_demo.py`
continues to demonstrate the monthly model and verified workbook.

## Test a weekly cash floor

Run the fixed grid of receipt delays from zero to five weeks, each with and
without the existing hiring package:

```powershell
uv run --locked --extra dev python -m examples.ridgeline.liquidity_grid --floor 0 --output ../ridgeline-liquidity
```

The 12 cells each rerun the weekly model. They report the additional opening
cash needed to meet the chosen floor at every weekly ending balance, then rerun
with that buffer to check the result. The buffer excludes the opening balance
and intraweek cash troughs. It is a counterfactual amount, with no assumption
that funding is available. The delay to week 14 remains outside the forecast
and is reported separately. Negative floors are permitted; non-finite values
are refused. `liquidity.json` retains unrounded values and the metric dictionary;
`liquidity.md` renders the same cells.
