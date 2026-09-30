from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import yaml

from pyfpa.analysis.sku import Sku
from pyfpa.cash13.scenarios import Scenario
from pyfpa.cash13.schemas import Cash13Config


def read_yaml(path: str | Path) -> Any:
    """Parse a YAML file as UTF-8, whatever the platform's preferred encoding is.

    `pyfpa.memory` already reads and writes its YAML as UTF-8 explicitly. This
    pair is the same contract for the research and portfolio stores, so a
    workspace written on one machine reads back on another.
    """
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def read_optional_yaml(path: str | Path) -> Any:
    """Return an empty mapping for absence, but propagate broken paths and reads."""
    path = Path(path)
    try:
        path.lstat()
    except FileNotFoundError:
        for parent in path.parents:
            try:
                parent.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(parent.stat().st_mode):
                raise
            return {}
        raise
    return read_yaml(path)


def write_yaml(path: str | Path, data: Any) -> None:
    """Write `data` as UTF-8 YAML, preserving key order."""
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def create_yaml(path: str | Path, data: Any) -> None:
    """Write `data` as UTF-8 YAML only if `path` does not exist yet.

    The exclusive create is the existence check: an `exists()` test followed by a
    write lets a second writer slip between the two and replace a record the
    first one just made. Raises `FileExistsError` instead.
    """
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(yaml.safe_dump(data, sort_keys=False))


def load_cash13_config(path: str | Path) -> Cash13Config:
    """Load and validate a Cash13Config from a YAML file."""
    return Cash13Config.model_validate(read_yaml(path))


def load_cash13_scenarios(path: str | Path) -> list[Scenario]:
    """Load and validate a list of Scenario from a YAML file with a top-level `scenarios:` list."""
    return [Scenario.model_validate(item) for item in read_yaml(path)["scenarios"]]


def load_skus(path: str | Path) -> list[Sku]:
    """Load a list of Sku from a YAML file with a top-level `skus:` list."""
    return [Sku.model_validate(item) for item in read_yaml(path)["skus"]]
