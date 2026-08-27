import os
from pathlib import Path
import subprocess

import pytest

from pyfpa.memory.connectors import (
    ConnectorManifest,
    connector_bundle_path,
    load_connector_manifest,
    load_connector_manifests,
    scaffold_connector_bundle,
    validate_connector_bundle,
)
from pyfpa.memory.lineage import MappingRegistry, MappingRule


def mappings() -> MappingRegistry:
    return MappingRegistry(mappings=[
        MappingRule(
            source_id="gl-actuals",
            source_value="Product Revenue",
            target="revenue.product",
        ),
        MappingRule(
            source_id="gl-actuals",
            source_value="Rent",
            target="opex.rent",
        ),
    ])


def fixture(path: Path) -> Path:
    path.write_text("Account,Amount\nProduct Revenue,100\nRent,(20)\n")
    return path


def manifest_values() -> dict:
    return {
        "name": "quickbooks-pl",
        "source_id": "gl-actuals",
        "description": "Pull the monthly P&L.",
        "auth_method": "host_environment",
        "source_account_column": "Account",
        "source_amount_column": "Amount",
        "fixture_path": "fixtures/source.csv",
        "expected_totals": {"revenue.product": 100.0},
    }


def directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.fail(f"could not create test junction: {completed.stderr}")
        return
    link.symlink_to(target, target_is_directory=True)


def test_connector_manifest_rejects_unsafe_fixture_paths():
    values = manifest_values()
    values["fixture_path"] = "../production.csv"

    with pytest.raises(ValueError, match="relative path"):
        ConnectorManifest(**values)


def test_connector_bundle_path_rejects_unsafe_name(tmp_path):
    with pytest.raises(ValueError, match="connector name"):
        connector_bundle_path(tmp_path, "../../outside")


@pytest.mark.parametrize(
    "field",
    ["fixture_command", "live_command", "live_ready", "unknown_capability"],
)
def test_connector_manifest_rejects_unknown_capability_fields(field):
    values = manifest_values()
    values[field] = ["python3", "run.py"] if field.endswith("command") else True

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ConnectorManifest(**values)


def test_connector_manifest_rejects_unsupported_fixture_adapter():
    with pytest.raises(ValueError, match="account-amount-csv"):
        ConnectorManifest(**manifest_values(), fixture_adapter="python-command")


def test_connector_manifest_requires_schema_version_two():
    assert ConnectorManifest(**manifest_values()).schema_version == 2

    with pytest.raises(ValueError, match="Input should be 2"):
        ConnectorManifest(**manifest_values(), schema_version=1)


def test_connector_listing_rejects_bundle_without_manifest(tmp_path):
    (tmp_path / "connectors" / "generated" / "broken").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="manifest not found"):
        load_connector_manifests(tmp_path)


def test_scaffold_and_validate_connector_bundle(tmp_path):
    source_fixture = fixture(tmp_path / "redacted.csv")

    manifest, reconciliation = scaffold_connector_bundle(
        tmp_path,
        name="quickbooks-pl",
        source_id="gl-actuals",
        description="Pull and normalize the monthly P&L.",
        auth_method="host_environment",
        fixture=source_fixture,
        account_column="Account",
        amount_column="Amount",
        mappings=mappings(),
    )

    bundle = tmp_path / "connectors" / "generated" / "quickbooks-pl"
    assert manifest.expected_totals == {
        "revenue.product": 100.0,
        "opex.rent": -20.0,
    }
    assert reconciliation["passed"] is True
    assert (bundle / "connector.yaml").exists()
    assert (bundle / "connector.py").exists()
    assert (bundle / "run.py").exists()
    assert (bundle / "fixtures" / "source.csv").read_text() == source_fixture.read_text()
    assert load_connector_manifest(bundle) == manifest
    assert load_connector_manifests(tmp_path) == [manifest]

    result = validate_connector_bundle(
        tmp_path,
        name="quickbooks-pl",
        mappings=mappings(),
    )

    assert result["passed"] is True
    assert result["adapter"] == "account-amount-csv"
    assert result["command"] == ["builtin:account-amount-csv"]
    assert result["reconciliation"]["unmapped"] == []
    assert result["reconciliation"]["mapped_totals"] == manifest.expected_totals


def test_validation_does_not_execute_bundle_code(tmp_path, monkeypatch):
    source_fixture = fixture(tmp_path / "redacted.csv")
    scaffold_connector_bundle(
        tmp_path,
        name="quickbooks-pl",
        source_id="gl-actuals",
        description="Pull and normalize the monthly P&L.",
        auth_method="host_environment",
        fixture=source_fixture,
        account_column="Account",
        amount_column="Amount",
        mappings=mappings(),
    )
    marker = tmp_path / "bundle-code-executed"
    run_file = (
        tmp_path / "connectors" / "generated" / "quickbooks-pl" / "run.py"
    )
    run_file.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "raise SystemExit(99)\n"
    )

    def reject_subprocess(*_args, **_kwargs):
        raise AssertionError("fixture validation attempted to start a subprocess")

    monkeypatch.setattr(subprocess, "run", reject_subprocess)

    result = validate_connector_bundle(
        tmp_path,
        name="quickbooks-pl",
        mappings=mappings(),
    )

    assert result["passed"] is True
    assert not marker.exists()


def test_scaffold_requires_explicit_overwrite(tmp_path):
    source_fixture = fixture(tmp_path / "redacted.csv")
    kwargs = {
        "name": "quickbooks-pl",
        "source_id": "gl-actuals",
        "description": "Pull and normalize the monthly P&L.",
        "auth_method": "host_environment",
        "fixture": source_fixture,
        "account_column": "Account",
        "amount_column": "Amount",
        "mappings": mappings(),
    }
    scaffold_connector_bundle(tmp_path, **kwargs)

    with pytest.raises(FileExistsError, match="already exists"):
        scaffold_connector_bundle(tmp_path, **kwargs)

    manifest, _ = scaffold_connector_bundle(tmp_path, overwrite=True, **kwargs)
    assert manifest.name == "quickbooks-pl"
    generated = tmp_path / "connectors" / "generated"
    assert not list(generated.glob(".quickbooks-pl.*"))


def test_scaffold_overwrite_restores_original_bundle_when_swap_fails(
    tmp_path,
    monkeypatch,
):
    source_fixture = fixture(tmp_path / "redacted.csv")
    original_fixture = source_fixture.read_text()
    kwargs = {
        "name": "quickbooks-pl",
        "source_id": "gl-actuals",
        "description": "Pull and normalize the monthly P&L.",
        "auth_method": "host_environment",
        "fixture": source_fixture,
        "account_column": "Account",
        "amount_column": "Amount",
        "mappings": mappings(),
    }
    scaffold_connector_bundle(tmp_path, **kwargs)
    source_fixture.write_text("Account,Amount\nProduct Revenue,200\nRent,(20)\n")

    real_rename = Path.rename

    def fail_staging_swap(path, target):
        if path.name.startswith(".quickbooks-pl.staging-"):
            raise OSError("simulated atomic swap failure")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_staging_swap)

    with pytest.raises(OSError, match="simulated atomic swap failure"):
        scaffold_connector_bundle(tmp_path, overwrite=True, **kwargs)

    generated = tmp_path / "connectors" / "generated"
    bundle = generated / "quickbooks-pl"
    assert (bundle / "fixtures" / "source.csv").read_text() == original_fixture
    assert not list(generated.glob(".quickbooks-pl.*"))


@pytest.mark.parametrize("linked_part", ["connectors", "generated", "bundle"])
def test_scaffold_overwrite_rejects_linked_workspace_ancestors(
    tmp_path,
    linked_part,
):
    company_root = tmp_path / "company"
    company_root.mkdir()
    outside = tmp_path / f"outside-{linked_part}"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep")

    connectors = company_root / "connectors"
    generated = connectors / "generated"
    bundle = generated / "quickbooks-pl"
    if linked_part == "connectors":
        directory_link(connectors, outside)
    elif linked_part == "generated":
        connectors.mkdir()
        directory_link(generated, outside)
    else:
        generated.mkdir(parents=True)
        directory_link(bundle, outside)

    source_fixture = fixture(tmp_path / "redacted.csv")
    with pytest.raises(ValueError, match="symlinks or reparse points"):
        scaffold_connector_bundle(
            company_root,
            name="quickbooks-pl",
            source_id="gl-actuals",
            description="Pull and normalize the monthly P&L.",
            auth_method="host_environment",
            fixture=source_fixture,
            account_column="Account",
            amount_column="Amount",
            mappings=mappings(),
            overwrite=True,
        )

    assert sentinel.read_text() == "keep"
    assert list(outside.iterdir()) == [sentinel]


def test_scaffold_rejects_unmapped_fixture(tmp_path):
    source_fixture = tmp_path / "redacted.csv"
    source_fixture.write_text("Account,Amount\nMystery,10\n")

    with pytest.raises(ValueError, match="duplicate or unmapped"):
        scaffold_connector_bundle(
            tmp_path,
            name="quickbooks-pl",
            source_id="gl-actuals",
            description="Pull and normalize the monthly P&L.",
            auth_method="host_environment",
            fixture=source_fixture,
            account_column="Account",
            amount_column="Amount",
            mappings=mappings(),
        )

    assert not (
        tmp_path / "connectors" / "generated" / "quickbooks-pl"
    ).exists()


def test_validation_detects_golden_total_regression(tmp_path):
    source_fixture = fixture(tmp_path / "redacted.csv")
    scaffold_connector_bundle(
        tmp_path,
        name="quickbooks-pl",
        source_id="gl-actuals",
        description="Pull and normalize the monthly P&L.",
        auth_method="host_environment",
        fixture=source_fixture,
        account_column="Account",
        amount_column="Amount",
        mappings=mappings(),
    )
    connector_file = (
        tmp_path
        / "connectors"
        / "generated"
        / "quickbooks-pl"
        / "fixtures"
        / "source.csv"
    )
    connector_file.write_text("Account,Amount\nProduct Revenue,90\nRent,(20)\n")

    result = validate_connector_bundle(
        tmp_path,
        name="quickbooks-pl",
        mappings=mappings(),
    )

    assert result["passed"] is False
    assert (
        result["reconciliation"]["variances"]["revenue.product"][
            "within_tolerance"
        ]
        is False
    )
