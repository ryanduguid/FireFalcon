import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyfpa.cli import main
from pyfpa.memory.entrypoints import EntrypointRegistry, load_entrypoint_registry
from pyfpa.memory.lineage import (
    MappingRegistry,
    SourceRegistry,
    load_mapping_registry,
    load_source_registry,
)
from pyfpa.research.registry import ModelRegistry, load_model_registry


@pytest.fixture(params=[
    (load_source_registry, SourceRegistry),
    (load_mapping_registry, MappingRegistry),
    (load_entrypoint_registry, EntrypointRegistry),
    (load_model_registry, ModelRegistry),
], ids=["sources", "mappings", "entrypoints", "models"])
def registry_loader(request):
    return request.param


def link_to(path, target, *, directory=False):
    try:
        path.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlinks unavailable: {error}")


def test_missing_registry_remains_optional(tmp_path, registry_loader):
    load, model = registry_loader
    assert load(tmp_path / "missing.yaml") == model()
    assert load(tmp_path / "missing" / "nested" / "registry.yaml") == model()


@pytest.mark.parametrize("suffix", ["registry.yaml", "nested/registry.yaml"])
def test_dangling_registry_parent_is_not_empty(tmp_path, registry_loader, suffix):
    load, _ = registry_loader
    parent = tmp_path / "linked"
    link_to(parent, tmp_path / "absent", directory=True)
    with pytest.raises(FileNotFoundError):
        load(parent / suffix)


def test_readable_registry_parent_allows_missing_leaf(tmp_path, registry_loader):
    load, model = registry_loader
    target = tmp_path / "target"
    target.mkdir()
    parent = tmp_path / "linked"
    link_to(parent, target, directory=True)
    assert load(parent / "missing.yaml") == model()


@pytest.mark.parametrize("linked", [False, True])
def test_non_directory_registry_parent_is_not_empty(tmp_path, registry_loader, linked):
    load, _ = registry_loader
    parent = tmp_path / "file"
    parent.write_text("sentinel", encoding="utf-8")
    if linked:
        link = tmp_path / "linked"
        link_to(link, parent)
        parent = link
    with pytest.raises(OSError):
        load(parent / "nested" / "registry.yaml")
    assert parent.read_text(encoding="utf-8") == "sentinel"


def test_unavailable_registry_root_is_not_empty(tmp_path, registry_loader, monkeypatch):
    load, _ = registry_loader
    path = tmp_path / "registry.yaml"
    original_error = FileNotFoundError("registry path unavailable")

    def unavailable(item):
        if item == path:
            raise original_error
        raise FileNotFoundError("parent unavailable")

    monkeypatch.setattr(Path, "lstat", unavailable)
    with pytest.raises(FileNotFoundError) as caught:
        load(path)
    assert caught.value is original_error


@pytest.mark.parametrize("operation", ["lstat", "stat"])
def test_registry_parent_inspection_errors_propagate(
    tmp_path, registry_loader, monkeypatch, operation,
):
    load, _ = registry_loader
    error = PermissionError("parent inspection denied")
    original = getattr(Path, operation)

    def denied_parent(path, *args, **kwargs):
        if path == tmp_path:
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, denied_parent)
    with pytest.raises(PermissionError) as caught:
        load(tmp_path / "missing.yaml")
    assert caught.value is error


def test_readable_registry_link_is_loaded(tmp_path, registry_loader):
    load, model = registry_loader
    target = tmp_path / "target.yaml"
    target.write_text("schema_version: 7\n", encoding="utf-8")
    assert load(target) == model(schema_version=7)
    link = tmp_path / "registry.yaml"
    link_to(link, target)
    assert load(link) == model(schema_version=7)


def test_invalid_registry_is_not_empty(tmp_path, registry_loader):
    load, _ = registry_loader
    path = tmp_path / "registry.yaml"
    path.write_text("schema_version: []\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load(path)


def test_empty_registry_mapping_remains_valid(tmp_path, registry_loader):
    load, model = registry_loader
    path = tmp_path / "registry.yaml"
    path.write_text("{}", encoding="utf-8")
    assert load(path) == model()


@pytest.mark.parametrize("document", ["[]", "false", "0", '""'])
def test_non_mapping_registry_is_not_empty(tmp_path, registry_loader, document):
    load, _ = registry_loader
    path = tmp_path / "registry.yaml"
    path.write_text(document, encoding="utf-8")
    with pytest.raises(ValidationError):
        load(path)


def test_dangling_registry_link_is_not_empty(tmp_path, registry_loader):
    load, _ = registry_loader
    link = tmp_path / "registry.yaml"
    link_to(link, tmp_path / "absent.yaml")
    with pytest.raises(FileNotFoundError):
        load(link)


def test_registry_inspection_error_is_not_empty(tmp_path, registry_loader, monkeypatch):
    load, _ = registry_loader
    error = PermissionError("registry inspection denied")

    def denied(path):
        raise error

    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(PermissionError) as caught:
        load(tmp_path / "registry.yaml")
    assert caught.value is error


@pytest.mark.parametrize("error_type", [PermissionError, FileNotFoundError])
def test_present_registry_read_error_is_not_empty(
    tmp_path, registry_loader, monkeypatch, error_type,
):
    load, _ = registry_loader
    path = tmp_path / "registry.yaml"
    path.write_text("{}\n", encoding="utf-8")
    error = error_type("registry read failed")

    def failed_read(path, *args, **kwargs):
        raise error

    monkeypatch.setattr(Path, "read_text", failed_read)
    with pytest.raises(error_type) as caught:
        load(path)
    assert caught.value is error


@pytest.mark.parametrize("document", ["", "null"])
def test_empty_registry_yaml_keeps_existing_validation(tmp_path, registry_loader, document):
    load, model = registry_loader
    path = tmp_path / "registry.yaml"
    path.write_text(document, encoding="utf-8")
    if model is ModelRegistry:
        with pytest.raises(ValidationError):
            load(path)
    else:
        assert load(path) == model()


@pytest.mark.parametrize("command", ["source-list", "source-register"])
@pytest.mark.parametrize("broken_parent", [False, True])
def test_source_commands_refuse_dangling_registry(tmp_path, capsys, command, broken_parent):
    registry = tmp_path / ".fpa" / "sources" / "registry.yaml"
    if broken_parent:
        registry.parent.parent.mkdir()
        target = tmp_path / "absent"
        link_to(registry.parent, target, directory=True)
        link = registry.parent
    else:
        registry.parent.mkdir(parents=True)
        target = tmp_path / "absent.yaml"
        link_to(registry, target)
        link = registry
    args = [command, str(tmp_path)]
    if command == "source-register":
        args += [
            "--source-id", "fixture", "--kind", "local_file",
            "--location", "fixture.csv", "--entity", "Fixture",
            "--currency", "AUD", "--period", "2026-01",
            "--extraction-method", "Fabricated",
        ]
    assert main(args) != 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    expected_error = "invalid_source_registry" if command == "source-list" else "invalid_source"
    assert result["error"]["type"] == expected_error
    assert result["error"]["message"]
    assert link.is_symlink()
    assert not target.exists()
