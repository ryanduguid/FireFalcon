from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pydantic import BaseModel

from pyfpa.backtest.score import DEFAULT_SCORE_LINES, ScoreResult, extract_lines
from pyfpa.config.schemas import EntityConfig


class Snapshot(BaseModel):
    """The full record of one forecast: the assumptions it used, the lines it
    predicted, and (once the period closes) the realised score."""

    label: str
    created: str                  # caller-supplied date string; never generated here
    assumptions: dict[str, Any]   # serialised EntityConfig
    predicted: dict[str, float]
    score: ScoreResult | None = None


def snapshot_forecast(
    cfg: EntityConfig,
    forecast_df: pd.DataFrame,
    *,
    label: str,
    created: str,
    score_lines: Sequence[str] = DEFAULT_SCORE_LINES,
) -> Snapshot:
    """Capture a forecast snapshot from an EntityConfig and its computed DataFrame."""
    return Snapshot(
        label=label,
        created=created,
        assumptions=cfg.model_dump(),
        predicted=extract_lines(forecast_df, score_lines),
    )


def save_snapshot(snapshot: Snapshot, path: str | Path, *, overwrite: bool = False) -> None:
    """Serialise a Snapshot to YAML at the given path."""
    with Path(path).open("w" if overwrite else "x", encoding="utf-8") as output:
        output.write(yaml.safe_dump(snapshot.model_dump(), sort_keys=False))


def load_forecast_snapshots(workspace: Path) -> tuple[list[Snapshot], list[str]]:
    """Every snapshot under ``workspace/forecasts``, plus the files that failed to parse."""
    snapshots: list[Snapshot] = []
    errors: list[str] = []
    forecasts_dir = workspace / "forecasts"
    if forecasts_dir.is_dir():
        for path in sorted(forecasts_dir.glob("*.yaml")):
            try:
                snapshots.append(load_snapshot(path))
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
    return snapshots, errors


def load_snapshot(path: str | Path) -> Snapshot:
    """Deserialise a Snapshot from a YAML file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"snapshot not found: {p}")
    return Snapshot.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
