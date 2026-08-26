from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from pyfpa.memory.workspace import WORKSPACE_DIRS, workspace_path


class WorkspaceReport(BaseModel):
    healthy: bool
    checks: list[dict[str, str]]
    error_count: int
    warning_count: int


def _check(
    checks: list[dict[str, str]],
    *,
    name: str,
    result: str,
    details: str,
) -> None:
    checks.append({"name": name, "result": result, "details": details})


def _report(checks: list[dict[str, str]]) -> WorkspaceReport:
    errors = [c for c in checks if c["result"] == "error"]
    warnings = [c for c in checks if c["result"] == "warning"]
    return WorkspaceReport(
        healthy=not errors,
        checks=checks,
        error_count=len(errors),
        warning_count=len(warnings),
    )


def _run_check(
    name: str,
    fn: Callable[[Path, Path, list[dict[str, str]]], None],
    root: Path,
    workspace: Path,
    checks: list[dict[str, str]],
) -> None:
    """Run one checker; any exception becomes an error entry under `name`.

    Imports stay lazy inside each checker so a broken optional dependency
    surfaces as a failed check rather than a failed import of this module.
    """
    try:
        fn(root, workspace, checks)
    except Exception as exc:
        _check(checks, name=name, result="error", details=str(exc))


def _check_directories(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    for directory in WORKSPACE_DIRS:
        path = workspace / directory
        _check(
            checks,
            name=f"directory:{directory}",
            result="pass" if path.is_dir() else "error",
            details=str(path),
        )


def _check_intake(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.memory.intake import intake_ready, load_intake

    intake = load_intake(workspace / "intake.md")
    _check(
        checks,
        name="intake",
        result="pass",
        details=(
            f"{len(intake.facts)} facts; "
            f"ready={str(intake_ready(intake)).lower()}"
        ),
    )


def _check_research_objective(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.research.objective import load_research_objective

    objective = load_research_objective(workspace / "research" / "objective.yaml")
    _check(
        checks,
        name="research_objective",
        result="pass",
        details=f"{len(objective.metrics)} metrics; {len(objective.hard_checks)} hard checks",
    )


def _check_model_registry(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.research.registry import load_model_registry

    registry = load_model_registry(workspace / "models" / "registry.yaml")
    _check(
        checks,
        name="model_registry",
        result="pass",
        details=(
            f"champion={registry.champion.model_id if registry.champion else 'none'}; "
            f"challengers={len(registry.challengers)}"
        ),
    )


def _check_entrypoint_registry(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.memory.entrypoints import load_entrypoint_registry

    entrypoint_path = workspace / "models" / "entrypoints.yaml"
    if not entrypoint_path.exists():
        raise FileNotFoundError(f"entrypoint registry not found: {entrypoint_path}")
    entrypoints = load_entrypoint_registry(entrypoint_path)
    _check(
        checks,
        name="entrypoint_registry",
        result="pass",
        details=f"{len(entrypoints.entrypoints)} registered entrypoints",
    )


def _check_source_registry(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.memory.lineage import load_source_registry

    source_path = workspace / "sources" / "registry.yaml"
    if not source_path.exists():
        raise FileNotFoundError(f"source registry not found: {source_path}")
    sources = load_source_registry(source_path)
    _check(
        checks,
        name="source_registry",
        result="pass",
        details=f"{len(sources.sources)} registered sources",
    )


def _check_mapping_registry(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.memory.lineage import load_mapping_registry

    mapping_path = workspace / "mappings" / "registry.yaml"
    if not mapping_path.exists():
        raise FileNotFoundError(f"mapping registry not found: {mapping_path}")
    mappings = load_mapping_registry(mapping_path)
    _check(
        checks,
        name="mapping_registry",
        result="pass",
        details=f"{len(mappings.mappings)} registered mappings",
    )


def _check_connector_contracts(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.memory.connectors import load_connector_manifests

    connectors = load_connector_manifests(root)
    _check(
        checks,
        name="generated_connector_contracts",
        result="pass",
        details=f"{len(connectors)} generated connector manifests",
    )


def _check_corrections(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.memory.corrections import load_corrections

    corrections = load_corrections(workspace / "corrections")
    _check(
        checks,
        name="corrections",
        result="pass",
        details=f"{len(corrections)} corrections",
    )


def _check_snapshots(
    root: Path, workspace: Path, checks: list[dict[str, str]]
) -> None:
    from pyfpa.backtest.snapshot import load_snapshot

    forecasts_dir = workspace / "forecasts"
    snapshot_count = 0
    parse_errors: list[str] = []
    if forecasts_dir.is_dir():
        for snap_path in sorted(forecasts_dir.glob("*.yaml")):
            try:
                load_snapshot(snap_path)
                snapshot_count += 1
            except Exception as snap_exc:
                parse_errors.append(f"{snap_path.name}: {snap_exc}")
    if parse_errors:
        _check(
            checks,
            name="snapshots",
            result="error",
            details=f"{snapshot_count} ok; errors: {'; '.join(parse_errors)}",
        )
    else:
        _check(
            checks,
            name="snapshots",
            result="pass",
            details=f"{snapshot_count} snapshots",
        )


# Check order is part of the report contract: entries appear in this order.
_CHECKS: tuple[tuple[str, Callable[[Path, Path, list[dict[str, str]]], None]], ...] = (
    ("intake", _check_intake),
    ("research_objective", _check_research_objective),
    ("model_registry", _check_model_registry),
    ("entrypoint_registry", _check_entrypoint_registry),
    ("source_registry", _check_source_registry),
    ("mapping_registry", _check_mapping_registry),
    ("generated_connector_contracts", _check_connector_contracts),
    ("corrections", _check_corrections),
    ("snapshots", _check_snapshots),
)


def validate_workspace(root: Path) -> WorkspaceReport:
    """Run all workspace contract checks and return a typed report.
    Pure: reads files, does not write anything."""
    workspace = workspace_path(root)
    checks: list[dict[str, str]] = []

    if not workspace.is_dir():
        _check(
            checks,
            name="workspace",
            result="error",
            details=f"missing workspace: {workspace}",
        )
        return _report(checks)

    _check(checks, name="workspace", result="pass", details=str(workspace))

    _check_directories(root, workspace, checks)
    for name, fn in _CHECKS:
        _run_check(name, fn, root, workspace, checks)

    return _report(checks)
