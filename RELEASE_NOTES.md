# v0.1.2

Breaking for scripts written against 0.1.1:

- `reconcile-source` and `reconcile_account_table` agree a target within half a cent
  by default (`--abs-tolerance 0.005`), and the relative `--tolerance` is off unless
  set. The old 1% default passed 3,000 cross-mapped between two revenue targets.
  Whole-dollar controls need `--abs-tolerance 0.5`.
- `EntityConfig.tax_rate` is required; the old 21% default was the US federal rate.
  `start_month` must be `YYYY-MM`, and date text given to payroll, GST, rate lookups and
  `format_au_date` must be ISO: day-first text such as `1/10/2026` is refused instead
  of being read as January.
- Config and 13-week cash files refuse unknown keys (`EntityConfig` and its parts,
  `Cash13Config`, `WeeklyFlow`), and opex amounts cannot be negative.
- `read_xero_report` refuses a report whose amount columns are not periods, such as a
  comparison or tracking export, unless `tracking_comparison=True` is set for a
  standard P&L with one tracking option per column. It also refuses a `Total X` row
  with no `X` heading above it and, in the flat layout, a row with more fields than
  the header, a filled row with no account, and unnamed or repeated columns.
  `pyfpa.io.xero_au.from_xero` is removed.
- Payroll tax and super guarantee lookups after 30 June 2027, the date those tables
  were verified to, raise until the tables are verified again.
- `fetch_abs_series` reads its key only from `ABS_API_KEY` and no longer takes an
  `api_key` argument. Its keys map to the ABS Indicator API's `_H` dataflows, a
  response in the wrong frequency is refused, and retail trade is history only: the
  ABS ceased it with the June 2025 period.
- Cross-client promotion is default-deny (below), `seed_from_library` requires
  `company_root` and `seeded_at`, and `promote_challenger` requires `objective` and
  `approved_at`.
- `verify_workbook` requires every expected column, a matching period header and zero
  `check_*` rows. `recover_actuals` raises for a line it cannot recover instead of
  skipping it, `score_forecast` skips zero-weight lines and refuses all-zero weights,
  and `pyfpa.memory.diagnostics.validate_workspace` is removed in favour of
  `Workspace.validate`.

Figures that change:

- A BAS due date on a weekend moves to the following Monday, and a leading partial
  quarter settles the months the series holds instead of being dropped.
- Workers compensation includes bonuses, as every state's wage definition does.
- `fy_summary` orders periods by date, and a divestiture keeps cogs consistent with
  gross profit.

New:

- 13-week cash scenarios: `Scenario`, `apply_scenario`, `compare_scenarios` and
  `load_cash13_scenarios`.
- `pyfpa.au.depreciation` reads accounting-depreciation evidence files, refuses one
  whose producer rejected it or whose digest no longer matches, and spreads a charge
  in whole cents with expense and asset purchases kept apart.
- `verify_structure` checks a workbook's layout contract, and `model_to_excel` writes
  `check_*` self-check rows.

Cross-client promotion:

- Cross-client promotion in `pyfpa/portfolio` is default-deny. `promote_prior` and
  `promote_skill` refuse unless a practitioner has recorded a `PromotionApproval` for
  that exact candidate's sha256 digest, listing the purpose, the contributing
  workspaces, the authorisation reference and a confidentiality review.
  `record_promotion_approval` is the only writer of an approval and refuses to
  overwrite one. The approval is an acknowledgement, not authentication and not legal
  proof of client consent.
- `validate_prior` accepts the candidate it validates and stamps its digest into
  `ValidationResult`; a result without the candidate's digest cannot support a
  promotion. `screen_candidate` reports ABN and TFN shaped numbers, email addresses,
  Australian phone numbers, BSB and account patterns, narrative dollar amounts and the
  contributing clients' business names, and any finding blocks promotion until the
  recorded review lists it.
- `promote_skill` copies only the files the approval lists in `allowed_files`. The gate
  counts distinct clients by normalised business-profile heading, ignoring case,
  punctuation, bracketed qualifiers and entity suffixes, and treats a workspace with no
  heading as establishing no client. Promoting across two workspaces that normalise to
  one name takes both workspace ids in the approval's `aliases_acknowledged` and review
  notes saying why they are separate.
- Shared library records now carry opaque workspace ids and the approval digest instead
  of client paths, with the path map in `<library>/provenance/workspaces.yaml`.
  `seed_from_library` takes the receiving `company_root` and `seeded_at`, records the
  seed in that workspace's `.fpa/library-seeds.yaml` and in the library's seed index,
  and the new `withdraw_prior` removes a prior and reports the workspaces it seeded
  without touching anything inside them.
- Approval files store contributing workspaces as opaque ids, so nothing in a shared
  library names a client directory. Building one still accepts paths. The library's seed
  index records the receiving workspace by id too, and `withdraw_prior` resolves ids back
  to paths through `provenance/workspaces.yaml` when it reports affected workspaces.
- `record_promotion_approval` writes with an exclusive create through the new
  `pyfpa.io.loaders.create_yaml`, so a second writer racing on the same digest is
  refused instead of replacing a recorded decision.
- `validate_prior` stamps each result it produces, and `promote_prior` refuses a result
  that stamp does not cover, which rejects a `ValidationResult` built by hand, edited on
  disk or carried over from another candidate. The stamp is a per-process structural
  barrier, not a security control, so validate and promote in one session.
- `validate_prior` also refuses a candidate whose business type or value are not the ones
  its folds tested.
- `promote_skill` reads the skill tree once and writes those exact bytes, instead of
  copying the client's directory again after the screen, and refuses a symlink, junction
  or other reparse point inside the tree.
- `seed_from_library` digests each stored prior again from its driver, business type,
  value and contributing workspace ids, and refuses it unless that reproduces the
  recorded digest and its approval is on disk. A legacy entry with no digest, and an
  entry edited after promotion, are both refused.
- Loading an approval checks that the record's own `candidate_digest` is the one it was
  looked up by, so a record copied onto another candidate's filename is refused, and the
  findings stamp writes to the digest the gate verified.
- Documentation states that "nothing leaves your machine" is about network egress and
  does not by itself permit moving one client's information into another client's work.

# v0.1.1

- Publishes the attested wheel and source distribution to PyPI as `au-fpa-pack` through trusted publishing.
- No functional change since v0.1.0.

# v0.1.0

First release of the Australian FP&A pack for openfpa: 30 June financial years,
Xero AU mapping, GST and BAS cash timing, and payroll on-cost assumptions.

- `openfpa`, a JSON-emitting CLI for company workspace intake, source lineage,
  mappings, reconciliation, connector scaffolding, corrections, scorecards,
  context packs and verified Excel export.
- 17 skills under `skills/`, plus the `.claude-plugin/plugin.json` manifest that
  declares the repository as the `openfpa` plugin.
- Five worked examples: Lumbridge Services, Harbour Light and Ridgeline Chair
  Co. from synthetic records, ARB Corporation from its FY2025 Appendix 4E, and
  Fox Factory Holding Corp. from public SEC filings.
- The distribution is `au-fpa-pack` and the import is `pyfpa`. Version 0.1.1
  is available on [PyPI](https://pypi.org/project/au-fpa-pack/0.1.1/).
- Tested on Python 3.11, 3.12 and 3.13.
