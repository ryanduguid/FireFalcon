"""Snapshot Australian economic driver series to disk with provenance.

Usage:

    python3 scripts/au_drivers_snapshot.py --out data/drivers
    python3 scripts/au_drivers_snapshot.py --out data/drivers --rba-only

RBA series (cash rate target, AUD/USD, TWI) need no credentials. ABS
Indicator API series (CPI, WPI, retail trade, labour force) need
ABS_API_KEY in the environment; without one the script snapshots RBA
series and reports ABS as skipped, exit code 0 (absence of a key is a
configuration fact, not a failure). Pass --require-abs to make a
missing key fail the run (exit 1) for CI or scheduled refresh.

Each series lands as <source>_<name>_<YYYY-MM-DD>.json. Existing
snapshots are never overwritten; a same-day re-fetch appends a counter.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from pyfpa.au.drivers import (
    ABS_DATAFLOWS,
    RBA_SERIES,
    fetch_abs_series,
    fetch_rba_series,
    save_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot AU economic driver series.")
    parser.add_argument("--out", default="data/drivers", help="output directory")
    parser.add_argument("--rba-only", action="store_true", help="skip ABS series")
    parser.add_argument(
        "--require-abs",
        action="store_true",
        help="fail (exit 1) when ABS_API_KEY is unset instead of skipping",
    )
    args = parser.parse_args()

    out = Path(args.out)
    report: dict[str, list[str] | dict[str, str]] = {"saved": [], "skipped": {}, "errors": {}}

    for name in RBA_SERIES:
        try:
            path = save_snapshot(fetch_rba_series(name), out)
            report["saved"].append(str(path))
        except Exception as exc:  # noqa: BLE001 - report, do not abort the batch
            report["errors"][f"rba:{name}"] = str(exc)

    if not args.rba_only:
        import os

        if os.environ.get("ABS_API_KEY"):
            for name in ABS_DATAFLOWS:
                try:
                    path = save_snapshot(fetch_abs_series(name), out)
                    report["saved"].append(str(path))
                except Exception as exc:  # noqa: BLE001
                    report["errors"][f"abs:{name}"] = str(exc)
        else:
            for name in ABS_DATAFLOWS:
                report["skipped"][f"abs:{name}"] = "ABS_API_KEY not set"
            if args.require_abs:
                report["errors"]["abs"] = "ABS_API_KEY required (--require-abs)"

    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
