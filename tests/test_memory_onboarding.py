import os
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

from pyfpa.memory.intake import (
    Intake,
    intake_ready,
    load_intake,
    next_intake_questions,
    record_intake_fact,
)
from pyfpa.memory.onboarding import (
    PROFILE_HEADINGS,
    ArchitectureProposal,
    render_architecture_proposal,
    render_business_profile,
    write_onboarding_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_INTAKES = sorted((ROOT / "examples").glob("*/.fpa/intake.md"))


def _ready_intake() -> Intake:
    intake = Intake(business_name="Acme")
    while questions := next_intake_questions(intake):
        for question in questions:
            intake = record_intake_fact(
                intake,
                key=question.key,
                answer=f"Known {question.key}",
                source_type="user",
                sources=["CFO interview"],
            )
    return intake


def _proposal() -> ArchitectureProposal:
    return ArchitectureProposal(
        summary="Build a driver-based monthly forecast and direct cash model.",
        connectors=["QuickBooks P&L and balance sheet export"],
        model_components=["Channel revenue model", "13-week cash model"],
        generated_skills=["wholesale-collections"],
        risks=["Collections timing is operationally managed outside the GL."],
        validation_checks=["Reconcile imported totals", "Backtest ending cash"],
    )


def test_render_business_profile_includes_sources_and_confidence():
    profile = render_business_profile(_ready_intake())

    assert "# Acme Business Profile" in profile
    assert "confidence: 100%" in profile
    assert "source: CFO interview" in profile


def test_other_topics_and_conflicts_are_preserved_without_duplicate_classification():
    intake = record_intake_fact(_ready_intake(), key="extra", answer="Additional fact", source_type="user", topic="custom")
    assert "Additional fact" in render_business_profile(intake)
    intake.facts[-1] = intake.facts[-1].model_copy(update={"status": "conflict"})
    rendered = render_architecture_proposal(intake, _proposal())
    known, unresolved = rendered.split("## Remaining Unknowns")
    assert "Additional fact" not in known
    assert "Additional fact" in unresolved


def test_onboarding_refuses_to_replace_either_existing_output(tmp_path):
    paths = write_onboarding_outputs(_ready_intake(), tmp_path, _proposal())
    previous = [path.read_bytes() for path in paths]
    with pytest.raises(FileExistsError):
        write_onboarding_outputs(_ready_intake(), tmp_path, _proposal())
    assert [path.read_bytes() for path in paths] == previous


def test_architecture_proposal_is_an_explicit_human_gate():
    proposal = render_architecture_proposal(_ready_intake(), _proposal())

    assert "Human approval required before scaffolding" in proposal
    assert "## Proposed Connectors" in proposal
    assert "QuickBooks P&L and balance sheet export" in proposal
    assert "- [ ] Approved to scaffold" in proposal


def test_write_onboarding_outputs_requires_ready_intake(tmp_path):
    with pytest.raises(ValueError, match="not ready"):
        write_onboarding_outputs(Intake(), tmp_path, _proposal())


def test_write_onboarding_outputs_creates_profile_and_decision(tmp_path):
    profile, proposal = write_onboarding_outputs(
        _ready_intake(),
        tmp_path,
        _proposal(),
    )

    assert profile == tmp_path / "business-profile.md"
    assert proposal == tmp_path / "decisions" / "initial-model-architecture.md"
    assert profile.exists()
    assert proposal.exists()


@pytest.mark.parametrize("path", EXAMPLE_INTAKES, ids=lambda p: p.parents[1].name)
def test_shipped_example_intake_supports_its_approved_architecture(path):
    """Each example ships an approved architecture decision, which is a state
    `write_onboarding_outputs` refuses to produce from a not-ready intake. Facts
    filed under an unknown key or topic leave the intake short of the contract
    and drop out of the rendered profile without a word."""
    intake = load_intake(path)
    decision = path.parent / "decisions" / "initial-model-architecture.md"
    assert "**Status:** Approved" in decision.read_text()
    assert intake_ready(intake), path
    profile = " ".join(render_business_profile(intake).split())
    for fact in intake.facts:
        assert fact.topic in PROFILE_HEADINGS, (path, fact.key)
        assert " ".join(fact.answer.split()) in profile, (path, fact.key)


def test_first_render_replaces_the_untouched_seeded_profile(tmp_path):
    # F072: `openfpa init` seeds business-profile.md, so the documented first
    # `write_onboarding_outputs(...)` call used to fail with FileExistsError and
    # create no architecture proposal.
    from pyfpa.memory.workspace import initialize_workspace

    workspace = initialize_workspace(tmp_path, business_name="Acme")
    profile, proposal = write_onboarding_outputs(_ready_intake(), workspace, _proposal())
    assert "Known business_model" in profile.read_text(encoding="utf-8")
    assert proposal.exists()


def test_a_profile_with_recorded_facts_is_still_protected(tmp_path):
    # Control: only the fact-free seed is replaceable.
    from pyfpa.memory.workspace import initialize_workspace

    workspace = initialize_workspace(tmp_path, business_name="Acme")
    profile_path = workspace / "business-profile.md"
    profile_path.write_text(
        render_business_profile(
            record_intake_fact(
                Intake(business_name="Acme"),
                key="business_model",
                answer="Wholesale to independents",
                source_type="user",
            )
        ),
        encoding="utf-8",
    )
    previous = profile_path.read_bytes()
    with pytest.raises(FileExistsError):
        write_onboarding_outputs(_ready_intake(), workspace, _proposal())
    assert profile_path.read_bytes() == previous
    assert not (workspace / "decisions" / "initial-model-architecture.md").exists()


@pytest.mark.parametrize("directory_name", [".fpa", "memory"])
@pytest.mark.parametrize("linked", ["memory", "decisions", "profile", "proposal"])
def test_onboarding_rejects_links_before_changing_outputs(tmp_path, directory_name, linked):
    memory = tmp_path / directory_name
    outside = tmp_path / "outside"
    outside.mkdir()
    if linked == "memory":
        memory.symlink_to(outside, target_is_directory=True)
    else:
        memory.mkdir()
    profile = memory / "business-profile.md"
    decisions = memory / "decisions"
    proposal = decisions / "initial-model-architecture.md"
    if linked == "decisions":
        decisions.symlink_to(outside, target_is_directory=True)
    else:
        decisions.mkdir()
    if linked in {"profile", "proposal"}:
        target = outside / "sentinel.md"
        target.write_bytes(b"outside sentinel")
        (profile if linked == "profile" else proposal).symlink_to(target)
    profile.write_bytes(b"profile sentinel" if linked != "profile" else b"outside sentinel")
    proposal.write_bytes(b"proposal sentinel" if linked != "proposal" else b"outside sentinel")
    before = (profile.read_bytes(), proposal.read_bytes())
    outside_before = {path.name: path.read_bytes() for path in outside.iterdir() if path.is_file()}

    with pytest.raises(ValueError, match="symlinks or reparse points"):
        write_onboarding_outputs(_ready_intake(), memory, _proposal(), overwrite=True)

    assert (profile.read_bytes(), proposal.read_bytes()) == before
    assert {path.name: path.read_bytes() for path in outside.iterdir() if path.is_file()} == outside_before
    assert not list(memory.glob(".onboarding-*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junction")
def test_onboarding_rejects_windows_junction_before_replacing_profile(tmp_path):
    memory = tmp_path / ".fpa"
    memory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    profile = memory / "business-profile.md"
    profile.write_bytes(b"profile sentinel")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(memory / "decisions"), str(outside)],
        capture_output=True, text=True, check=False, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    with pytest.raises(ValueError, match="symlinks or reparse points"):
        write_onboarding_outputs(_ready_intake(), memory, _proposal(), overwrite=True)

    assert profile.read_bytes() == b"profile sentinel"
    assert not list(outside.iterdir())


def _fail_after_partial_write(monkeypatch, destination):
    original_open = Path.open
    original_fdopen = os.fdopen

    class PartialWriter:
        def __init__(self, output):
            self.output = output

        def write(self, text):
            self.output.write(text[:20])
            raise OSError("injected partial write")

    @contextmanager
    def broken_open(path, mode="r", *args, **kwargs):
        with original_open(path, mode, *args, **kwargs) as output:
            yield PartialWriter(output) if path == destination and mode in {"w", "x"} else output

    @contextmanager
    def broken_fdopen(*args, **kwargs):
        with original_fdopen(*args, **kwargs) as output:
            yield PartialWriter(output)

    monkeypatch.setattr(Path, "open", broken_open)
    monkeypatch.setattr(os, "fdopen", broken_fdopen)


@pytest.mark.parametrize("seed", [False, True])
def test_failed_replacement_keeps_existing_profile_and_removes_temporary(tmp_path, monkeypatch, seed):
    profile = tmp_path / "business-profile.md"
    before = render_business_profile(Intake(business_name="Acme")).encode() if seed else b"previous profile"
    profile.write_bytes(before)
    _fail_after_partial_write(monkeypatch, profile)

    with pytest.raises(OSError, match="injected partial write"):
        write_onboarding_outputs(_ready_intake(), tmp_path, _proposal(), overwrite=not seed)

    assert profile.read_bytes() == before
    assert not (tmp_path / "decisions" / "initial-model-architecture.md").exists()
    assert not list(tmp_path.glob(".onboarding-*.tmp"))


@pytest.mark.parametrize("failed_name", ["business-profile.md", "initial-model-architecture.md"])
def test_failed_publication_keeps_previous_destination(tmp_path, monkeypatch, failed_name):
    profile, proposal = write_onboarding_outputs(_ready_intake(), tmp_path, _proposal())
    profile.write_bytes(b"old profile")
    proposal.write_bytes(b"old proposal")
    failed = profile if failed_name == profile.name else proposal
    before = failed.read_bytes()
    replace = os.replace

    def fail_publication(source, destination):
        if destination == failed:
            raise OSError("injected replacement failure")
        return replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_publication)
    with pytest.raises(OSError, match="injected replacement failure"):
        write_onboarding_outputs(_ready_intake(), tmp_path, _proposal(), overwrite=True)

    assert failed.read_bytes() == before
    assert not list(tmp_path.rglob(".onboarding-*.tmp"))


def test_no_overwrite_preserves_a_destination_created_after_preflight(tmp_path, monkeypatch):
    proposal = tmp_path / "decisions" / "initial-model-architecture.md"
    original_open = Path.open

    def race_open(path, mode="r", *args, **kwargs):
        if path == proposal and mode == "x":
            with original_open(path, "x", encoding="utf-8") as competing:
                competing.write("raced proposal")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", race_open)
    with pytest.raises(FileExistsError):
        write_onboarding_outputs(_ready_intake(), tmp_path, _proposal())
    assert proposal.read_text() == "raced proposal"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_replacement_preserves_ordinary_permission_bits(tmp_path):
    profile, _ = write_onboarding_outputs(_ready_intake(), tmp_path, _proposal())
    profile.chmod(0o640)
    write_onboarding_outputs(_ready_intake(), tmp_path, _proposal(), overwrite=True)
    assert stat.S_IMODE(profile.stat().st_mode) == 0o640
