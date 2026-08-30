---
schema_version: 1
business_name: Harbour Light Pty Ltd
facts:
- key: business_model
  topic: business
  question: What does the company sell, and who are the primary customers?
  answer: Harbour Light is a synthetic Victorian lighting wholesaler selling
    domestic fittings (GST-taxable) and export/GST-free fittings, tracked North
    and South.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - data/xero_pl_tracking.csv
  - .fpa/business-profile.md
  alternatives: []
- key: revenue_model
  topic: business
  question: How is revenue earned and billed, including pricing and payment terms?
  answer: One month of Xero GST-exclusive sales is annualised at a flat run rate.
    Interest income is ignored. GST-free sales are North-only.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - data/xero_pl_tracking.csv
  alternatives: []
- key: customer_channels
  topic: business
  question: Which channels, products, or segments should the model distinguish?
  answer: Model North and South tracking options as revenue channels. GST-free
    sales stay inside North and reduce the entity taxable_sales_pct.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - data/xero_pl_tracking.csv
  alternatives: []
- key: collections
  topic: cash_cycle
  question: When do customers usually pay, and what causes collections to vary?
  answer: Opening AR implies a short DSO on the 360-day convention used by the
    monthly engine.
  status: inferred
  confidence: 0.8
  source_type: local_file
  sources:
  - data/xero_bs.csv
  alternatives: []
- key: supplier_payments
  topic: cash_cycle
  question: When are suppliers, payroll, inventory, and other major obligations paid?
  answer: Payroll is modelled from statutory VIC on-costs, paid fortnightly in
    the 13-week cash view. Quarterly BAS is a scheduled disbursement.
  status: inferred
  confidence: 0.85
  source_type: local_file
  sources:
  - harbour_model.py
  alternatives: []
- key: seasonality
  topic: cash_cycle
  question: What is seasonal or lumpy across revenue, costs, inventory, and cash?
  answer: The synthetic month is repeated with flat seasonality. Cash is lumpy
    because of quarterly BAS.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - harbour_model.py
  alternatives: []
- key: entities
  topic: finance_structure
  question: Which legal entities, currencies, and intercompany relationships matter?
  answer: Single AUD company, 30 June year, Victorian payroll tax jurisdiction,
    30 percent company tax.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - harbour_model.py
  alternatives: []
- key: financing
  topic: finance_structure
  question: What debt, credit lines, covenants, or other financing is in place?
  answer: The Xero balance sheet has a $60,000 business loan with no interest
    expense in the P&L. The demo leaves it off the engine rather than invent a
    rate.
  status: inferred
  confidence: 0.85
  source_type: local_file
  sources:
  - data/xero_bs.csv
  alternatives: []
- key: data_sources
  topic: finance_structure
  question: Which systems and files contain the financial and operating actuals?
  answer: Fixture-backed Xero Australia P&L and balance sheet CSVs. No live OAuth.
  status: inferred
  confidence: 0.95
  source_type: local_file
  sources:
  - data/xero_pl.csv
  - data/xero_bs.csv
  alternatives: []
- key: planning_cadence
  topic: planning
  question: How often do you close, reforecast, report, and make planning decisions?
  answer: Monthly close off the Xero export, quarterly BAS lodgement, and a 13-week
    cash review rebuilt whenever a BAS quarter rolls into the window.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - harbour_model.py
  - .fpa/decisions/initial-model-architecture.md
  alternatives: []
- key: cfo_priorities
  topic: planning
  question: Which decisions, risks, or questions matter most to the CFO right now?
  answer: Show that Xero mapping, AU payroll, and BAS cash timing compose on one
    synthetic company without inventing client data.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - .fpa/decisions/initial-model-architecture.md
  alternatives: []
---
Synthetic example. Not a real entity.

