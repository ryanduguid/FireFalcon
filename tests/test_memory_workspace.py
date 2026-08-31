from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pyfpa.memory.workspace import Workspace, initialize_workspace, workspace_path
from pyfpa.memory.entrypoints import load_entrypoint_registry
from pyfpa.memory.lineage import load_mapping_registry, load_source_registry
from pyfpa.memory.onboarding import PROFILE_HEADINGS, render_business_profile
from pyfpa.memory.intake import (
    Intake,
    load_intake,
    next_intake_questions,
    record_intake_fact,
    save_intake,
)
from pyfpa.research.objective import load_research_objective
from pyfpa.research.registry import load_model_registry


def test_workspace_open_returns_a_canonical_immutable_value(tmp_path):
    company = tmp_path / "company"
    company.mkdir()

    workspace = Workspace.open(company / ".." / "company")

    assert workspace.root == company.resolve()
    assert workspace.memory == company.resolve() / ".fpa"
    legacy_root = Path("relative") / ".." / "company"
    assert workspace_path(legacy_root) == legacy_root / ".fpa"
    with pytest.raises(FrozenInstanceError):
        workspace.root = tmp_path


def test_workspace_owns_initialisation_and_intake_readiness(tmp_path):
    workspace = Workspace.open(tmp_path)

    assert workspace.intake_path == workspace.memory / "intake.md"
    assert (
        workspace.source_registry_path
        == workspace.memory / "sources" / "registry.yaml"
    )
    assert (
        workspace.mapping_registry_path
        == workspace.memory / "mappings" / "registry.yaml"
    )
    assert (
        workspace.entrypoint_registry_path
        == workspace.memory / "models" / "entrypoints.yaml"
    )
    assert workspace.initialized is False
    assert workspace.is_ready() is False

    initialize_workspace(tmp_path, business_name="Acme")
    assert workspace.initialized is True
    assert workspace.is_ready() is False

    intake = load_intake(workspace.memory / "intake.md")
    while questions := next_intake_questions(intake):
        for question in questions:
            intake = record_intake_fact(
                intake,
                key=question.key,
                answer=f"Known {question.key}",
                source_type="user",
            )
    save_intake(intake, workspace.memory / "intake.md")

    assert workspace.is_ready() is True


@pytest.mark.parametrize("namespace", ["connectors", "models", "skills", "agents"])
def test_workspace_owns_generated_locations(tmp_path, namespace):
    workspace = Workspace.open(tmp_path)

    assert (
        workspace.generated_path(namespace)
        == tmp_path.resolve() / namespace / "generated"
    )


def test_workspace_rejects_unknown_or_escaping_generated_paths(tmp_path):
    workspace = Workspace.open(tmp_path)

    with pytest.raises(ValueError, match="generated namespace"):
        workspace.generated_path("unknown")
    with pytest.raises(ValueError, match="escapes company root"):
        workspace.assert_safe_existing_chain(tmp_path.parent / "outside")


def test_workspace_require_root_rejects_a_root_that_is_not_a_directory(tmp_path):
    present = tmp_path / "company"
    present.mkdir()
    assert Workspace.open(present).require_root().root == present.resolve()

    missing = tmp_path / "absent"
    with pytest.raises(NotADirectoryError, match="company root is not a directory"):
        Workspace.open(missing).require_root()

    file_root = tmp_path / "company.txt"
    file_root.write_text("a file where a company root must be", encoding="utf-8")
    with pytest.raises(NotADirectoryError, match="company root is not a directory"):
        Workspace.open(file_root).require_root()


def test_workspace_rejects_a_chain_whose_ancestor_is_not_a_directory(tmp_path):
    workspace = Workspace.open(tmp_path)
    blocker = tmp_path / "connectors"
    blocker.write_text("a file where a directory must be", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="ancestor is not a directory"):
        workspace.assert_safe_existing_chain(blocker / "generated" / "thing.json")


def test_workspace_is_the_only_internal_location_seam():
    root = Path(__file__).resolve().parents[1]
    compatibility_surfaces = {
        root / "pyfpa" / "__init__.py",
        root / "pyfpa" / "memory" / "__init__.py",
        root / "pyfpa" / "memory" / "workspace.py",
    }
    lifecycle_sources = [
        path
        for path in (root / "pyfpa").rglob("*.py")
        if path not in compatibility_surfaces
    ]

    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in lifecycle_sources
    )
    assert "workspace_path" not in combined
    assert '/ ".fpa"' not in combined
    assert "/ '.fpa'" not in combined
    assert "_canonical_company_root" not in combined
    assert "def _assert_safe_existing_chain" not in combined


def test_initialize_workspace_creates_memory_contract(tmp_path):
    workspace = initialize_workspace(tmp_path, business_name="Acme")

    assert workspace == workspace_path(tmp_path)
    assert (workspace / "MEMORY.md").exists()
    assert (workspace / "intake.md").exists()
    assert (workspace / "business-profile.md").exists()
    assert (workspace / "scorecard.md").exists()
    assert (workspace / "learnings.md").exists()
    assert load_research_objective(workspace / "research" / "objective.yaml").min_improvement == 0.02
    assert load_model_registry(workspace / "models" / "registry.yaml").champion is None
    assert load_entrypoint_registry(
        workspace / "models" / "entrypoints.yaml"
    ).entrypoints == []
    assert load_source_registry(workspace / "sources" / "registry.yaml").sources == []
    assert load_mapping_registry(workspace / "mappings" / "registry.yaml").mappings == []
    for directory in (
        "sources", "mappings", "corrections", "forecasts", "experiments", "decisions",
        "models", "research",
    ):
        assert (workspace / directory).is_dir()
    for directory in (
        "connectors/generated",
        "models/generated",
        "skills/generated",
        "agents/generated",
    ):
        assert (tmp_path / directory).is_dir()


def test_initialize_workspace_does_not_overwrite_memory(tmp_path):
    workspace = initialize_workspace(tmp_path, business_name="Acme")
    memory = workspace / "MEMORY.md"
    intake = workspace / "intake.md"
    memory.write_text("# Custom Memory\n")
    intake.write_text("---\nbusiness_name: Custom\nfacts: []\n---\n")

    initialize_workspace(tmp_path, business_name="Other")

    assert memory.read_text() == "# Custom Memory\n"
    assert intake.read_text() == "---\nbusiness_name: Custom\nfacts: []\n---\n"


def _extract_h2_headings(text: str) -> list[str]:
    """Return all ## headings from a markdown document."""
    return [
        line[3:].strip()
        for line in text.splitlines()
        if line.startswith("## ")
    ]


def test_business_profile_headings_are_unified_across_init_and_onboarding(tmp_path):
    """initialize_workspace and render_business_profile must share a single
    source of truth for section headings so init-then-onboard produces no
    schema flip."""
    workspace = initialize_workspace(tmp_path, business_name="Acme")
    stub_headings = _extract_h2_headings(
        (workspace / "business-profile.md").read_text()
    )

    rendered = render_business_profile(Intake(business_name="Acme"))
    rendered_headings = _extract_h2_headings(rendered)

    assert stub_headings == rendered_headings, (
        "initialize_workspace stub headings differ from render_business_profile headings; "
        "both must come from PROFILE_HEADINGS"
    )
    assert len(stub_headings) == len(PROFILE_HEADINGS)


def test_memory_index_describes_complete_vault(tmp_path):
    """MEMORY.md must reference every documented vault artifact."""
    workspace = initialize_workspace(tmp_path, business_name="Acme")
    content = (workspace / "MEMORY.md").read_text()

    required_artifacts = [
        "intake.md",
        "business-profile.md",
        "sources/",
        "mappings/",
        "corrections/",
        "forecasts/",
        "scorecard.md",
        "learnings.md",
        "experiments/",
        "decisions/",
        "models/",
        "research/",
    ]
    for artifact in required_artifacts:
        assert artifact in content, f"MEMORY.md missing entry for: {artifact}"
