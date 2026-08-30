---
schema_version: 1
business_name: ARB Corporation Limited
facts:
- key: business_model
  topic: business
  question: What does the company sell, and who are the primary customers?
  answer: ARB designs, manufactures and distributes 4x4 accessories in Australia
    and to more than 100 countries. Channels are Australian aftermarket, exports,
    and OEM.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
- key: revenue_model
  topic: business
  question: How is revenue earned and billed, including pricing and payment terms?
  answer: Product sales. Trade receivables have 30 day terms. Channel mix is in
    the Appendix 4E operating review.
  status: inferred
  confidence: 0.85
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
- key: customer_channels
  topic: business
  question: Which channels, products, or segments should the model distinguish?
  answer: Australian Aftermarket, Exports, and Original Equipment. Trailhunter
    sales to Toyota North America sit in exports, not OEM.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - data/segments.csv
  - data/SOURCES.md
  alternatives: []
- key: collections
  topic: cash_cycle
  question: When do customers usually pay, and what causes collections to vary?
  answer: FY2025 trade receivables imply about 45 days sales outstanding on a
    360-day year. Dollar AR barely moved while sales grew 5.3 percent.
  status: inferred
  confidence: 0.8
  source_type: local_file
  sources:
  - data/balance_sheet.csv
  alternatives: []
- key: supplier_payments
  topic: cash_cycle
  question: When are suppliers, payroll, inventory, and other major obligations paid?
  answer: Inventory-heavy manufacturer. FY2025 inventories $249.1m after H2 destock
    from $277.8m at 31 December 2024. Payables $65.2m.
  status: inferred
  confidence: 0.85
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
- key: seasonality
  topic: cash_cycle
  question: What is seasonal or lumpy across revenue, costs, inventory, and cash?
  answer: Annual public proof uses flat monthly phasing. Intra-year seasonality
    is not in the 4E extracts.
  status: inferred
  confidence: 0.8
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
- key: entities
  topic: finance_structure
  question: Which legal entities, currencies, and intercompany relationships matter?
  answer: Consolidated AUD group, 30 June year, Victorian parent, fully franked
    dividends at 30 percent. Associates (ORW) are equity accounted and outside
    the engine.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
- key: financing
  topic: finance_structure
  question: What debt, credit lines, covenants, or other financing is in place?
  answer: No borrowings at 30 June 2025. Finance expense is mainly leases. The
    demo does not put a term loan through the engine.
  status: inferred
  confidence: 0.9
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
- key: data_sources
  topic: finance_structure
  question: Which systems and files contain the financial and operating actuals?
  answer: Committed CSV extracts from the ASX Appendix 4E PDF. No live scrape.
  status: inferred
  confidence: 0.95
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
- key: planning_cadence
  topic: planning
  question: How often do you close, reforecast, report, and make planning decisions?
  answer: The public evidence supports half-yearly ASX reporting (Appendix 4D and
    4E) against a 30 June year end; ARB's internal close and reforecast cadence is
    not public.
  status: inferred
  confidence: 0.85
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
- key: cfo_priorities
  topic: planning
  question: Which decisions, risks, or questions matter most to the CFO right now?
  answer: Export-led growth versus Australian aftermarket softness, and cost
    pressure from the Thai Baht and US tariffs.
  status: inferred
  confidence: 0.85
  source_type: local_file
  sources:
  - data/SOURCES.md
  alternatives: []
---
