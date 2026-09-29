# Contributing to openfpa

openfpa is an open-source experiment from [Guiderail](https://www.guiderail.io). It's
early, and help is genuinely welcome, whether that's a bug report, a sharper piece of
CFO judgement, or a whole new industry pack. No promises on response time, and please be
kind; this is a side-of-the-desk project.

## Getting set up

```bash
git clone https://github.com/ryanduguid/au-fpa-pack
cd au-fpa-pack
pip install -e ".[dev]"
ruff check .       # lint and import order, part of the merge gate
mypy               # strict type check of pyfpa, part of the merge gate
pytest -q          # the merge gate, and it should be green
pytest -m network  # the live checks, which fetch RBA CSVs over the internet
```

CI runs `ruff check .` and `mypy` before the test matrix, so a lint or typing
failure stops the run early. `ruff check . --fix` applies the safe fixes.

`mypy` checks against Python 3.11, the floor in `requires-python`, and CI runs it
on a 3.11 environment. Run it on 3.11 too: on 3.12 or newer, pip resolves numpy
2.5, whose stubs use syntax mypy will not parse while targeting 3.11, and you get
an error inside `numpy/__init__.pyi` rather than anything about your change.

`pytest.ini` deselects the `network` marker by default, so a Reserve Bank outage or a
published layout change cannot fail a branch that did not cause it. Run `pytest -m
network` when you touch `pyfpa/au/drivers.py` or refresh the RBA fixtures under
`tests/fixtures/`.

The distribution is `au-fpa-pack`; the importable package is `pyfpa` (`import pyfpa`).

The openpyxl minimum is 3.1.3. Earlier versions can retain workbook file handles
on Windows with Python 3.11.8 or newer, preventing verified exports from replacing
their destination. See [openpyxl issue 2149 in its release notes](https://openpyxl.readthedocs.io/en/stable/changes.html).
CI runs the minimum-dependency suite on both Linux and Windows.

## The workflow

`joined-fixtures.yml` runs the fabricated close-to-forecast, quarter and
job-to-cash examples on this repository's pull requests, pushes to `main` and manual
runs. Linux and Windows jobs use the proposed FPA checkout with full commit pins for
Accounting Review Pipeline and Australian Accounting. Update those pins deliberately
when adopting compatible changes. Each owner runs in a separate process and fresh
environment, using its workspace lock where applicable.

The existing [joined example driver](https://github.com/ryanduguid/accounting-review-pipeline/blob/3dcb5304f4c67c01de98b34638999b5f274d1810/packages/monthly-close-control-plane/docs/utility-workflows.md)
checks cash values and retained REVIEW findings. Separate operating-system artefacts
retain fabricated results, failure diagnostics, the escaped summary, success manifest
and replay record for seven days. These public routes require no
private grant checkout or cross-repository secret. Linux keeps the `public-fixtures`
check name and Windows adds `public-fixtures (Windows)`; branch protection requires
`public-fixtures-gates`, which needs both.

1. Fork, branch, and make your change.
2. **Add tests for new behaviour.** The project is test-first, and CI runs the suite on
   Python 3.11, 3.12, 3.13, and 3.14. A green suite is required to merge, as are clean
   `ruff check .` and `mypy` runs.
3. Open a PR describing what you changed and why. For anything non-trivial, describe the
   approach in a draft PR before you build: Issues are switched off in this repository, and
   changes to the shared openfpa core belong in [openfpa's issues](https://github.com/JeffBrines/openfpa/issues).

## What's most useful to contribute

The engine is deliberately lean; the value is in the skillset and how widely it covers
real businesses. The contributions that help most:

- **Industry packs:** a polished generated skill for a vertical the toolkit doesn't cover
  well yet (SaaS, restaurant, logistics, agency, and so on). The `fpa-learn-business` skill
  spins these up per business; a generalised, well-documented one helps everyone. See the
  `segment-rollup` skill in the Fox Factory example for the shape.
- **Data-access recipes:** teach the agent how to identify, request, map, test,
  and reconcile a source such as QuickBooks, Xero, NetSuite, Stripe, a bank
  export, or a local reporting folder. Reusable primitives are welcome, but live
  company connectors should remain generated for that company. See
  `examples/foxfactory/pull_edgar.py` for the pattern.
- **CFO judgement rules:** a real-world gotcha worth encoding into `fpa-cfo-judgment`.
- **Public-company proofs:** apply the workflow to another source-traced public
  company with honest accounting reproduction, a historical holdout, and clear
  forecast limitations.

## House rules

- **No real client data, ever, and no secrets.** Use synthetic data or public filings
  only (the Fox example uses nothing but public SEC data). Credentials come from the host
  environment or an MCP server, never committed.
- Keep modules small, pure, and immutable; config is pydantic-validated; disk I/O stays in
  the `io/` layer. Match the surrounding style.
- Open-sourced under MIT. By contributing, you agree your work is offered under the same.

Questions or ideas about the shared core go to [openfpa's issues](https://github.com/JeffBrines/openfpa/issues);
for the Australian layer, use the [contact page](https://duguid.com.au/contact/).

## Release checks

The release caller names the component checks that must have succeeded for the
exact release commit on `main`. It advances the policy SHA, `required-checks`
and `actions: read` together. Skipped, missing, cancelled or failed checks block
publication, including component tests skipped by a path filter. An aggregate
gates job cannot replace those checks. Before tagging, choose a main-branch
commit with successful component CI; a successful run for an older commit is
not evidence for the release. Tags and publication still require explicit approval.
