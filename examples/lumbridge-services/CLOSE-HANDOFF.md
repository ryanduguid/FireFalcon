# Use the forecast opening balances in a close review

From this example directory, generate a new input directory outside both
repositories. The destination must not exist and must be outside every Git
checkout and the source data directory:

```powershell
python models/generated/close_handoff.py --output /local/demo/close-inputs
```

From the Monthly Close Controls component in Accounting Review Pipeline:

```powershell
uv run --locked close-control review --current /local/demo/close-inputs/current.csv --prior /local/demo/close-inputs/prior.csv --mapping /local/demo/close-inputs/mapping.csv --subledger /local/demo/close-inputs/subledger.csv --output /local/demo/close-pack
uv run --locked close-control view --pack-dir /local/demo/close-pack
```

The current trial balance uses the forecast's September balance sheet. Cash is
30000.00; the two opening invoices total 66000.00. The payable balance derives
from [separately fabricated gross events](data/opening-payable-items.csv):

| Bill | Gross amount | Credit | Prior settlement | Unpaid at 30 September |
| --- | ---: | ---: | ---: | ---: |
| LB-M01 | 8800.00 | 1100.00 | 2200.00 | 5500.00 |
| LB-M02 | 7700.00 | 0.00 | 0.00 | 7700.00 |
| Total | 16500.00 | 1100.00 | 2200.00 | 13200.00 |

The handoff checks that this derived total agrees with the balance sheet's
credit liability. It separately checks the assumed Materials payment on
7 October. That payment does not determine the opening payable. The handoff
records per-bill amounts and hashes of all 4 source files.
Run [the recurring forecast](RECURRING.md) against those same sources to follow
opening cash through October actuals and the revised receipt schedule.

The August balance sheet is an explicitly constructed prior for this example.
It is not an observed export. The receivable tie uses invoice detail; the payable
tie uses separately specified synthetic bills, credits and prior settlements.
Supplier documents are not authenticated and source completeness is not
established. The October settlement remains a forecast assumption, not an
executed payment. Retain these limits beside the close pack. The engine does not
approve accounting, and a close result does not approve the forecast assumptions.

The event file requires one originating bill per BillID, unique ItemIDs, the
declared entity, BS-800 and AUD. Credits and prior settlements must identify
the same supplier and an earlier or same-day bill. Every event must be dated
on or before 30 September, with a positive gross amount. All four CSV inputs
require strict quoting, unique expected headers and every explicit cell.
Duplicates, orphan events, invalid money and reductions exceeding a bill are
refused. Validation finishes before writing to a new staging directory. The
requested destination appears only after every file closes successfully.
A failed write attempts to remove every owned staging file, preserves the
original error and names retained staging paths if cleanup also fails.

Account IDs use `BS-` plus the source code because code 800 has different
meanings in the supplied balance sheet and profit and loss. The separate source
code remains text. No production component imports another component.

This bounded route reuses Lumbridge Services. It does not replace the pipeline's
Fabricated Firm proposal, migrate its entities or claim full ledger, payroll and
Power BI consistency across that proposed group.
