# Grant workpapers to restricted cash

Build the fabricated workpaper with the grant workpapers CLI, `apps/grant-acquittal-workpapers/grant_workpaper.py` in Accounting Review Pipeline, then run this consumer from the au-fpa-pack checkout:

```powershell
uv run --locked python examples/restricted-cash/grant_cash.py --workpaper path/to/workpaper.json --workpaper-sha256 EXPECTED_SHA256 --plan examples/restricted-cash/grant-plan.json
```

The digest binds the exact producer output. Supply it from the trusted build or review record, rather than accepting a digest offered beside an untrusted replacement. Entity, currency and period must match. The forecast begins the day after the workpaper's ledger end. The portable utility-workflows recipe performs both steps and passes the digest of its own generated workpaper.

The source example contains $6,300 allocated expenditure and $3,200 unpaid allocations. Only $200 has the required source approval, evidence and in-period classification for this cash plan. The unresolved $3,000 remains visible, with the original findings. A cash plan never changes an acquittal decision.

Opening bank cash is an independent supplied $30,000 assumption. Reviewed restrictions allocate $14,220 to grant A and $7,680 to grant B, using source cash allocations rather than unspent funding. An explicitly conditional $5,000 future receipt and $200 of planned payments produce $34,800 closing cash, $26,700 restricted and $8,100 available under these assumptions. Expected funding is not observed funding or a promise of renewal. No further programme spending is assumed.

Plans must cover each supported unpaid allocation exactly. Restriction decisions cover every source grant and cannot exceed its source cash allocation. Invalid hashes, changed entity/period, duplicate payments, excessive allocations or missing restriction decisions stop the handoff. Source review findings and excluded commitments accompany the existing restricted-cash engine's output.

The additional `liquidity` result reports dated bank cash, available cash, each grant's remaining allocation, minimum balances and the first shortfall date. A positive closing balance does not clear an earlier shortfall. For example, an $80 opening bank balance followed by $200 of payments and a later $5,000 receipt ends at $4,880 but first falls to negative $120. The period-end forecast retains its own reconciliation status; `liquidity.status` separately reports that temporary shortfall. A grant allocation can also run short while total bank cash stays positive.

Balances use the opening position and each event day's closing position. Same-day receipts and payments are netted; intraday funding order is not assessed. Negative grant allocations never increase available unrestricted cash. Unresolved commitments remain excluded and visible. If general receipts or spending are non-zero, supply `general_cash_plan` rows with unique `id`, canonical `date`, `kind` (`receipt` or `payment`), positive decimal-string `amount` and `evidence`. Those rows must sum exactly to the general receipt and spending inputs; the model does not invent payment dates.

The copied `tests/fixtures/grant-workpaper.json` is the fabricated producer's deterministic output for its two-grant example, used to test the file contract without importing the producer. The joined fixtures and the portable integration run also check the current producer directly.
