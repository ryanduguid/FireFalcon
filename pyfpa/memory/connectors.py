from __future__ import annotations

from math import isfinite
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Callable, Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pyfpa.memory.lineage import MappingRegistry, reconcile_account_table
from pyfpa.memory.workspace import Workspace


ConnectorAuth = Literal["none", "host_environment", "mcp"]
_CONNECTOR_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _relative_path(value: str) -> str:
    value = value.strip()
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError("path must be a non-empty relative path without '..'")
    return path.as_posix()


def _connector_name(value: str) -> str:
    if not _CONNECTOR_NAME.fullmatch(value):
        raise ValueError("connector name must use lowercase letters, numbers, and hyphens")
    return value


def _lstat(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _is_link_or_reparse(path_stat) -> bool:
    return stat.S_ISLNK(path_stat.st_mode) or bool(
        getattr(path_stat, "st_file_attributes", 0)
        & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _ensure_plain_directory(root: Path, directory: Path) -> None:
    relative = directory.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        current_stat = _lstat(current)
        if current_stat is None:
            try:
                current.mkdir()
            except FileExistsError:
                pass
            current_stat = current.lstat()
        if _is_link_or_reparse(current_stat):
            raise ValueError(
                "connector workspace paths must not contain symlinks or "
                f"reparse points: {current}"
            )
        if not stat.S_ISDIR(current_stat.st_mode):
            raise NotADirectoryError(
                f"connector workspace path is not a directory: {current}"
            )


def _assert_plain_tree(workspace: Workspace, tree: Path) -> None:
    workspace.assert_safe_existing_chain(tree)
    pending = [tree]
    while pending:
        current = pending.pop()
        current_stat = current.lstat()
        if _is_link_or_reparse(current_stat):
            raise ValueError(
                "connector bundle trees must not contain symlinks or "
                f"reparse points: {current}"
            )
        if stat.S_ISDIR(current_stat.st_mode):
            pending.extend(current.iterdir())


def _remove_verified_tree(workspace: Workspace, tree: Path) -> None:
    _assert_plain_tree(workspace, tree)
    shutil.rmtree(tree)


def _replace_generated_tree(
    workspace: Workspace,
    bundle: Path,
    *,
    overwrite: bool,
    build_fn: Callable[[Path], None],
) -> None:
    root = workspace.root
    workspace.assert_safe_existing_chain(bundle)
    existing_bundle = _lstat(bundle)
    if existing_bundle is not None:
        if not stat.S_ISDIR(existing_bundle.st_mode):
            raise NotADirectoryError(f"connector bundle is not a directory: {bundle}")
        if not overwrite:
            raise FileExistsError(f"connector bundle already exists: {bundle}")
        _assert_plain_tree(workspace, bundle)

    generated = bundle.parent
    _ensure_plain_directory(root, generated)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{bundle.name}.staging-", dir=generated)
    )
    installed = False
    try:
        build_fn(staging)
        _assert_plain_tree(workspace, staging)

        workspace.assert_safe_existing_chain(bundle)
        existing_bundle = _lstat(bundle)
        backup = None
        if existing_bundle is not None:
            if not overwrite:
                raise FileExistsError(f"connector bundle already exists: {bundle}")
            if not stat.S_ISDIR(existing_bundle.st_mode):
                raise NotADirectoryError(
                    f"connector bundle is not a directory: {bundle}"
                )
            _assert_plain_tree(workspace, bundle)
            backup = generated / f".{bundle.name}.backup-{uuid4().hex}"
            bundle.rename(backup)

        try:
            staging.rename(bundle)
        except OSError:
            if backup is not None and _lstat(bundle) is None:
                backup.rename(bundle)
            raise
        installed = True

        if backup is not None:
            _remove_verified_tree(workspace, backup)
    finally:
        if not installed and _lstat(staging) is not None:
            _remove_verified_tree(workspace, staging)


class ConnectorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    source_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    description: str
    auth_method: ConnectorAuth
    source_account_column: str
    source_amount_column: str
    fixture_path: str
    fixture_adapter: Literal["account-amount-csv"] = "account-amount-csv"
    expected_totals: dict[str, float] = Field(min_length=1)

    @field_validator(
        "description",
        "source_account_column",
        "source_amount_column",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("fixture_path")
    @classmethod
    def validate_fixture_path(cls, value: str) -> str:
        return _relative_path(value)

    @field_validator("expected_totals")
    @classmethod
    def validate_expected_totals(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not key.strip() for key in value):
            raise ValueError("expected total names must not be empty")
        if any(not isfinite(amount) for amount in value.values()):
            raise ValueError("expected totals must be finite")
        return value

    @model_validator(mode="after")
    def validate_manifest_contract(self):
        if self.source_account_column == self.source_amount_column:
            raise ValueError("source account and amount columns must differ")
        return self


def connector_generated_root(company_root: str | Path) -> Path:
    return Workspace.open(company_root).generated_path("connectors")


def connector_bundle_path(company_root: str | Path, name: str) -> Path:
    return connector_generated_root(company_root) / _connector_name(name)


def load_connector_manifest(path: str | Path) -> ConnectorManifest:
    path = Path(path)
    if path.is_dir():
        path = path / "connector.yaml"
    if not path.exists():
        raise FileNotFoundError(f"connector manifest not found: {path}")
    return ConnectorManifest.model_validate(yaml.safe_load(path.read_text()) or {})


def save_connector_manifest(
    manifest: ConnectorManifest,
    path: str | Path,
) -> None:
    path = Path(path)
    if path.suffix != ".yaml":
        path = path / "connector.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(manifest.model_dump(), sort_keys=False))


def load_connector_manifests(company_root: str | Path) -> list[ConnectorManifest]:
    root = connector_generated_root(company_root)
    if not root.exists():
        return []
    manifests = []
    for bundle in sorted(
        path for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ):
        manifest = load_connector_manifest(bundle)
        if manifest.name != bundle.name:
            raise ValueError(
                f"connector directory {bundle.name!r} contains manifest for "
                f"{manifest.name!r}"
            )
        manifests.append(manifest)
    return manifests


def _connector_module(
    *,
    account_column: str,
    amount_column: str,
) -> str:
    return f'''from __future__ import annotations

import csv
from pathlib import Path


SOURCE_ACCOUNT_COLUMN = {account_column!r}
SOURCE_AMOUNT_COLUMN = {amount_column!r}


def _parse_amount(raw: str | None) -> float:
    value = (raw or "").strip().replace("$", "").replace(",", "")
    if value in ("", "-"):
        return 0.0
    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = value[1:-1]
    amount = float(value)
    return -amount if negative else amount


def normalize_fixture(path: str | Path) -> dict[str, float]:
    path = Path(path)
    result: dict[str, float] = {{}}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        required = {{SOURCE_ACCOUNT_COLUMN, SOURCE_AMOUNT_COLUMN}}
        if not required.issubset(fields):
            raise ValueError(
                f"expected columns {{sorted(required)}}, got {{fields}}"
            )
        for row in reader:
            account = (row.get(SOURCE_ACCOUNT_COLUMN) or "").strip()
            if not account:
                continue
            if account in result:
                raise ValueError(f"duplicate account: {{account}}")
            result[account] = _parse_amount(row.get(SOURCE_AMOUNT_COLUMN))
    return result


def extract_live() -> dict[str, float]:
    raise NotImplementedError(
        "Implement host-authenticated live extraction before invoking live mode"
    )


def write_normalized(values: dict[str, float], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Account", "Amount"])
        writer.writerows(sorted(values.items()))
'''


def _runner_module() -> str:
    return '''from __future__ import annotations

import argparse

from connector import extract_live, normalize_fixture, write_normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    values = extract_live() if args.live else normalize_fixture(args.fixture)
    write_normalized(values, args.output)


if __name__ == "__main__":
    main()
'''


def _readme(manifest: ConnectorManifest) -> str:
    return f"""# {manifest.name}

{manifest.description}

## Contract

- Source ID: `{manifest.source_id}`
- Authentication: `{manifest.auth_method}`
- Fixture: `{manifest.fixture_path}`
- Fixture adapter: built-in `{manifest.fixture_adapter}` parser
- Duplicate accounts: fail
- Unmapped accounts: fail
- Golden mapped totals: stored in `connector.yaml`

## Validate

```bash
openfpa connector-validate . --name {manifest.name}
```

Fixture validation never accesses a live system. Implement `extract_live()` in
`connector.py` and add a fixture-backed test for the source response shape.
Keep live extraction outside `connector.yaml` and invoke it only through an
explicit, host-controlled workflow.

Never commit credentials or an unredacted production export.
"""


def scaffold_connector_bundle(
    company_root: str | Path,
    *,
    name: str,
    source_id: str,
    description: str,
    auth_method: ConnectorAuth,
    fixture: str | Path,
    account_column: str,
    amount_column: str,
    mappings: MappingRegistry,
    overwrite: bool = False,
) -> tuple[ConnectorManifest, dict]:
    workspace = Workspace.open(company_root).require_root()
    bundle = connector_bundle_path(workspace.root, name)
    fixture = Path(fixture)
    if not fixture.exists():
        raise FileNotFoundError(f"connector fixture not found: {fixture}")
    if fixture.suffix.casefold() != ".csv":
        raise ValueError("connector scaffold currently requires a CSV fixture")

    reconciliation = reconcile_account_table(
        fixture,
        source_id=source_id,
        mappings=mappings,
        account_column=account_column,
        amount_column=amount_column,
    )
    if not reconciliation["passed"]:
        raise ValueError(
            "fixture must have no duplicate or unmapped accounts before scaffolding"
        )
    if not reconciliation["mapped_totals"]:
        raise ValueError("fixture must produce at least one mapped total")

    manifest = ConnectorManifest(
        name=name,
        source_id=source_id,
        description=description,
        auth_method=auth_method,
        source_account_column=account_column,
        source_amount_column=amount_column,
        fixture_path="fixtures/source.csv",
        expected_totals=reconciliation["mapped_totals"],
    )

    def build_bundle(staging: Path) -> None:
        (staging / "fixtures").mkdir()
        shutil.copyfile(fixture, staging / manifest.fixture_path)
        save_connector_manifest(manifest, staging)
        (staging / "connector.py").write_text(
            _connector_module(
                account_column=account_column,
                amount_column=amount_column,
            )
        )
        (staging / "run.py").write_text(_runner_module())
        (staging / "README.md").write_text(_readme(manifest))

    _replace_generated_tree(
        workspace,
        bundle,
        overwrite=overwrite,
        build_fn=build_bundle,
    )
    return manifest, reconciliation


def validate_connector_bundle(
    company_root: str | Path,
    *,
    name: str,
    mappings: MappingRegistry,
    timeout: float = 30.0,
) -> dict:
    # Retained for callers of the schema-v1 API. The closed in-process adapter
    # does not start a process whose runtime can be bounded by this value.
    del timeout
    workspace = Workspace.open(company_root).require_root()
    bundle = connector_bundle_path(workspace.root, name)
    workspace.assert_safe_existing_chain(bundle)
    bundle_stat = _lstat(bundle)
    if bundle_stat is None:
        raise FileNotFoundError(f"connector bundle not found: {bundle}")
    if not stat.S_ISDIR(bundle_stat.st_mode):
        raise NotADirectoryError(f"connector bundle is not a directory: {bundle}")
    workspace.assert_safe_existing_chain(bundle / "connector.yaml")
    manifest = load_connector_manifest(bundle)
    if manifest.name != name:
        raise ValueError(
            f"connector directory {name!r} contains manifest for {manifest.name!r}"
        )
    fixture_path = bundle / manifest.fixture_path
    workspace.assert_safe_existing_chain(fixture_path)
    if _lstat(fixture_path) is None:
        raise FileNotFoundError(f"connector fixture not found: {fixture_path}")
    fixture = fixture_path.resolve(strict=True)
    if not fixture.is_relative_to(bundle.resolve(strict=True)):
        raise ValueError("fixture path escapes connector bundle")
    reconciliation = reconcile_account_table(
        fixture,
        source_id=manifest.source_id,
        mappings=mappings,
        account_column=manifest.source_account_column,
        amount_column=manifest.source_amount_column,
        expected=manifest.expected_totals,
        tolerance=0.0,
    )
    return {
        "manifest": manifest.model_dump(),
        "adapter": manifest.fixture_adapter,
        "command": [f"builtin:{manifest.fixture_adapter}"],
        "returncode": 0,
        "reconciliation": reconciliation,
        "passed": reconciliation["passed"],
    }
