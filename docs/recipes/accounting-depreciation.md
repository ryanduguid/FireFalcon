# Accounting depreciation from evidence, opt in

A forecast often needs a depreciation charge that something else worked out.
`pyfpa.au.depreciation` takes that figure from a file on disk. It opens no
socket and calls no service, which is what lets it sit inside a default model
run: the figure was obtained once, deliberately, and the evidence of it was
kept.

The `pyfpa.au` package imports this module, so `import pyfpa.au` loads it. It
opens no socket and reads no file until you call it. The baseline examples do
not use it and are unchanged.

## Three things that stay apart

A model that folds these together produces a plausible cash forecast that is
wrong.

| | Profit | Cash |
|---|---|---|
| Depreciation expense | reduces it | moves none |
| Asset purchase | none on its own | moves it, on its own date |
| Tax | a separate assumption | a separate assumption |

The third is the one that catches people. An AASB 116 carrying amount is not a
deduction under ITAA 1997 Division 40. The two use different lives, methods and
conventions, and this module produces no tax figure at all. The evidence file's
own advisory says the same thing, and it travels with the figure.

## Reading the evidence

```python
from decimal import Decimal
import pandas as pd
from pyfpa.au import depreciation as dep

evidence = dep.load_evidence("pyfpa/au/fixtures/depreciation-evidence-lumbridge.json")
evidence.charge     # Decimal("6049.32")
evidence.usable     # True
evidence.advisory_notes
```

The file's digest is checked against its own calculation block, so a file
edited after it was produced is refused rather than quietly believed. Money is
read from decimal strings; a JSON number is refused, because a float has
already lost whatever the calculator meant by it.

A file recording a refusal, an outage or a contract failure, with its
producer's validation block present, loads fine and reports `usable` as
false. Asking to spread it raises rather than returning
nil, because a refusal is not a nil amount, and `refusal_reasons` says why.

`usable` reads four things, not one. The call has to be COMPUTED, the charge
has to be there, the producer's own `validation.accepted` has to be true, and
no finding it recorded may be a blocking one. A file can carry a COMPUTED call
beside a validation block that rejected the response, and the rejection is the
one that decides. A finding the producer prefixed with `note:` is an
observation it did not block on, and it does not block here either.

When present, `calculation.synthetic_input` must be a JSON boolean.
`load_evidence` rejects other values, including `null`. If the field is absent,
the reader retains `False` for compatibility. A returned `False` therefore does
not prove that the source data was non-synthetic.

## Checking the movement

```python
check = dep.asset_movement(
    opening=Decimal("113950.68"),
    additions=Decimal("0.00"),
    depreciation=Decimal("6049.32"),
    closing=Decimal("107901.36"),
)
check.closes    # True
```

If it does not close, `check.gap` is the gap and `check.reasons` says so.
Nothing is derived to close it. Where an addition landed inside the window,
supply it as `additions` from your own records: a number computed from the gap
is not evidence of anything, and the second fabricated fixture
(`depreciation-evidence-unreconciled.json`) is an example of the case.

## Into the forecast

```python
months = pd.period_range("2026-10", periods=3, freq="M")
schedule = dep.straight_line_schedule(evidence, months)
frame = dep.cash_and_expense(schedule, purchases=pd.Series([120000.0, 0.0, 0.0], index=months))

frame["cash_effect"]     # -120000, 0, 0: the purchase, not the charge
frame["profit_effect"]   # the charge, spread
```

`straight_line_schedule` spreads one evidenced charge evenly across the months
given. That is a deliberate simplification and the only spreading this module
does: it is wrong for a diminishing-value asset inside the window, and where
that matters the fix is evidence per month, not more arithmetic here.

## The fabricated example

`120,000.00` of plant, five-year life, prime cost, acquired 1 July 2026.
Twenty-four thousand a year. The window 1 October to 31 December 2026 is 92
days of a 365-day year, so the charge is `24,000.00 x 92 / 365 = 6,049.32`, the
opening balance is cost less the same charge for July to September, and the
closing balance is `107,901.36`. `tests/test_au_depreciation.py` derives that
figure itself and compares it with the fixture, rather than reading the
fixture's own claim back.

No client asset. No real figures. The fixtures record `synthetic_input` and the
tests check it.
