## Current quick start

Clone the repository and install the locked development environment with
[uv](https://docs.astral.sh/uv/), on Python 3.12 or newer:

```bash
git clone https://github.com/ryanduguid/au-fpa-pack
cd au-fpa-pack
uv sync --locked --extra dev
```

`uv sync --locked --extra dev` is the install path. It is what CI runs and what
`uv.lock` pins, so the committed example figures reproduce. Run anything in the
repository through the same environment, for example
`uv run --locked --extra dev pytest -q`.

Secondary, without uv: `python -m pip install -e ".[dev]"` inside a virtual
environment installs the same package, but it resolves dependencies fresh
rather than from `uv.lock`, so versions can differ from CI and from the
recorded outputs.

Then open the repository in Codex or Claude Code and ask:

```text
Help me onboard this company into openfpa.
The financial files are in ./company-data.
Inspect them first, then ask me only what you cannot determine.
```

The repository instructions tell the agent to initialise `.fpa/`, inspect local
evidence, conduct the intake, and stop for architecture approval.
