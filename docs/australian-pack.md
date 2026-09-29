## Australian pack (fork extension)

This fork adds an Australian localisation in `pyfpa/au/`, built on the
data-access-recipe and industry-pack paths in CONTRIBUTING:

- **Calendar** - 30 June financial years, `FY2027` / `Q1 FY2027` /
  `1H FY2027` labels, dd/mm/yyyy (`pyfpa.au.calendar`)
- **Payroll** - super guarantee, state payroll tax (all 8
  jurisdictions, effective-dated), workers comp, leave provisions,
  contractors (`pyfpa.au.payroll`)
- **Payroll settlement** - dated obligation, due and cash events for each
  payroll cost except leave provisions, which stay accruals, with month-end
  liabilities and 13-week flows derived from them; net wages fall due on each
  payday and the caller passes the due-date rule for every other cost
  (`pyfpa.au.payroll_settlement`)
  - PAYG withholding due dates under Taxation Administration Act 1953,
    Schedule 1, section 16-75 (`pyfpa.au.paygw`)
- **GST/BAS** - net GST from GST-exclusive series, monthly and
  quarterly settlement schedules, straight into the 13-week model
  (`pyfpa.au.gst`)
- **Xero** - report parser with tracking-category and GST-basis
  detection plus the full register/map/reconcile recipe
  (`pyfpa.io.xero_au`, [`docs/recipes/xero-au.md`](../docs/recipes/xero-au.md))
- **Accounting depreciation** - an opt-in charge read from a calculation-evidence
  file on disk, with the asset movement reconciled or refused and expense,
  purchases and tax kept apart (`pyfpa.au.depreciation`,
  [`docs/recipes/accounting-depreciation.md`](recipes/accounting-depreciation.md))
- **Economic drivers** - RBA cash rate and exchange rates, ABS CPI/WPI/
  retail/labour series, snapshotted with provenance
  (`pyfpa.au.drivers`, [`docs/recipes/au-drivers.md`](../docs/recipes/au-drivers.md))

Statutory rates are effective-dated YAML data files with official
source URLs, verified at revenue offices (2026-08-20). Simplifications
(grouping, QLD taper, WA diminishing threshold, surcharge tiers) are
documented in the module docstrings. Not tax software: forecast-grade
cash and P&L modelling only.

SA uses a separate $1.5 million liability threshold and $600,000 deduction.
The rate rises linearly from 0% to 4.95% across $1.5 million to $1.7 million
of annualised wages, then stays at 4.95%. The forecast multiplies each
month's wages by 12 to choose the rate. This assumes an ungrouped SA-only
employer with a steady full-year wage run rate. Mixed SA/interstate wages
are refused; use an entity-specific calculator for apportionment, grouping
or part-year adjustments. This is not an annual reconciliation or a
statutory monthly return. See [RevenueSA](https://www.revenuesa.sa.gov.au/payrolltax/rates-and-thresholds)
and [*Payroll Tax Act 2009*, Schedule 1 clauses 2 and 5](https://www.legislation.sa.gov.au/_legislation-documents/lz/c/a/payroll-tax-act-2009/current/2009.22.auth.pdf).

```python
from pyfpa.au import PayrollAssumptions, Role, payroll_forecast
from pyfpa.au.calendar import fy_month_range

frame = payroll_forecast(
    [Role(name="Engineer", annual_salary=150000, jurisdiction="VIC")],
    fy_month_range(2027),
)
```

Skills: `fpa-au-payroll`, `fpa-au-gst-bas`, `fpa-au-xero`, `fpa-au-drivers`.

### Worked GST assumptions

GST-free sales and input-taxed sales both exclude output GST, but their
purchase-credit treatment can differ. Set `taxable_sales_pct` and
`creditable_purchases_pct` independently from reviewed transaction evidence.
A sales percentage does not establish a purchase-credit percentage.

These fabricated scenarios use monthly revenue of $12,000 and purchases of
$4,000, excluding GST, with the bundled 10% rate. The creditable share is an
explicit scenario assumption, with all other credit conditions assumed met.

| Scenario | Taxable sales share | Creditable purchases share | Output GST | Input GST | Net GST |
|---|---:|---:|---:|---:|---:|
| Taxable sales, fully creditable purchases | 100% | 100% | $1,200 | $400 | $800 |
| GST-free sales, fully creditable purchases | 0% | 100% | $0 | $400 | -$400 |
| Input-taxed sales, no credit entitlement | 0% | 0% | $0 | $0 | $0 |
| Mixed sales and independently reviewed purchases | 50% | 75% | $600 | $300 | $300 |

```python
import pandas as pd
from pyfpa.au.gst import GstAssumptions, bas_schedule, monthly_gst

months = pd.period_range("2026-07", periods=3, freq="M")
gst = monthly_gst(
    pd.Series(12000.0, index=months),
    pd.Series(4000.0, index=months),
    GstAssumptions(taxable_sales_pct=0.5, creditable_purchases_pct=0.75),
)
assert gst["net_gst"].tolist() == [300.0, 300.0, 300.0]
assert bas_schedule(gst["net_gst"])["amount"].tolist() == [900.0]
```

The Library's *GST / Claiming Input Tax Credits · Tax Invoices*, creditable-purpose
discussion, and *Accounting Basis · Tax Periods*, paragraph 7-000, prompted
these examples. Authority checked on 10 September 2026: [GST Act, compilation
dated 1 January 2026](https://www.legislation.gov.au/C2004A00446/2026-01-01/2026-01-01/text/original/epub/OEBPS/document_1/document_1.html),
ss 9-70, 11-5, 11-15, 11-25 and 11-30. Financial-supply exceptions and reduced
credits require separate assessment; the zero-credit example does not decide them.

`monthly_gst` applies supplied proportions; it does not classify transactions or
attribute invoices and payments to tax periods. Reconcile cash-basis inputs before
using them. The schedule uses original BAS due dates, moved from a weekend to the
Monday but not past a public holiday or for agent extensions. Under Taxation
Administration Act 1953 s 8AAZMB a public holiday for the whole of any State or
Territory is not a business day either: 28 February 2027 falls on a Sunday and
Monday 1 March is Labour Day throughout Western Australia, so that payment is
due on Tuesday 2 March, a day after the date the schedule gives. A refund on the
due date is a forecast assumption, not a receipt promise. A period ending after
`reviewed_until` in `gst_bas.yaml` (30 June 2027) raises until the dates are
re-checked. Explicit rate overrides must be finite and non-negative. Zero remains
available for scenario modelling; it does not establish a GST exemption.

Worked examples on this fork:

- [`examples/lumbridge-services/`](../examples/lumbridge-services/) - synthetic
  NSW maintenance business: dated receipts, PAYG, super and GST cash, monthly
  commentary and a verified Excel receipt-delay scenario with OSRS references.

- [`examples/harbour-light/`](../examples/harbour-light/) - synthetic VIC
  wholesaler: Xero mapping, statutory payroll, quarterly BAS into 13-week cash,
  verified Excel.
- [`examples/arb/`](../examples/arb/) - ARB Corporation (ASX: ARB) from the FY2025
  Appendix 4E. Annual public proof, not a GST model.

### Cross-client reuse in an Australian practice

The portfolio loop can carry a prior or a generated skill from one client's
workspace into another's. That is a confidentiality decision before it is a
modelling one, so `pyfpa/portfolio` refuses to make it: a promotion needs a
`PromotionApproval` recorded against the exact candidate, with the purpose, the
contributing workspaces, the authorisation it rests on and a confidentiality
review. See [SECURITY.md](../SECURITY.md) for the mechanics and
[`skills/fpa-portfolio-learn`](../skills/fpa-portfolio-learn/SKILL.md) for the
workflow.

Two points worth stating plainly for practice use:

- "Nothing leaves your machine" describes network egress. It does not permit
  moving one client's information into another client's engagement file. Weigh
  the engagement terms, the confidentiality requirements in the APES 110 Code of
  Ethics and, for personal information, the Australian Privacy Principles.
- The recorded approval is an acknowledgement by the practitioner. It is not
  authentication, it is not legal proof of client consent, and it is not a
  substitute for advice on your obligations. The automated screen for ABNs,
  TFNs, contact details, bank details and client names assists that review and
  proves nothing.

Proposed upstream in
[JeffBrines/openfpa#14](https://github.com/JeffBrines/openfpa/issues/14).
This fork is not a claim to be upstream.
