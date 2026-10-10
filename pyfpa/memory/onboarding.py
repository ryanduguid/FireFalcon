from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from pyfpa.memory.intake import Intake, intake_ready, is_fact_known
from pyfpa.memory.workspace import Workspace


class ArchitectureProposal(BaseModel):
    summary: str
    connectors: list[str] = Field(default_factory=list)
    model_components: list[str] = Field(default_factory=list)
    generated_skills: list[str] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


PROFILE_HEADINGS: dict[str, str] = {
    "business": "Business Model And Revenue",
    "cash_cycle": "Cash Cycle And Seasonality",
    "finance_structure": "Entity, Financing, And Data Structure",
    "planning": "Planning Cadence And CFO Priorities",
}


def _bullet(items: list[str], *, empty: str = "None proposed.") -> str:
    if not items:
        return f"- {empty}\n"
    return "".join(f"- {item}\n" for item in items)


def render_business_profile(intake: Intake) -> str:
    """Render a cited business profile from the structured intake facts."""
    lines = [
        f"# {intake.business_name} Business Profile",
        "",
        "> Generated from `.fpa/intake.md`. Update the intake when facts change.",
        "",
    ]
    headings = list(PROFILE_HEADINGS.items())
    if any(fact.topic not in PROFILE_HEADINGS for fact in intake.facts):
        headings.append(("__other__", "Other Context"))
    for topic, heading in headings:
        lines.extend([f"## {heading}", ""])
        facts = [fact for fact in intake.facts if (
            fact.topic not in PROFILE_HEADINGS if topic == "__other__" else fact.topic == topic
        )]
        if not facts:
            lines.extend(["- Not yet known.", ""])
            continue
        for fact in facts:
            confidence = f"{fact.confidence:.0%}"
            sources = ", ".join(fact.sources) if fact.sources else fact.source_type
            lines.append(
                f"- **{fact.question}** {fact.answer} "
                f"_(status: {fact.status}; confidence: {confidence}; source: {sources})_"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_architecture_proposal(
    intake: Intake,
    proposal: ArchitectureProposal,
) -> str:
    """Render the human-review gate before model or connector generation."""
    knowns = [
        f"{fact.question}: {fact.answer}"
        for fact in intake.facts
        if is_fact_known(fact)
    ]
    unresolved = [
        f"{fact.question}: {fact.answer}"
        for fact in intake.facts
        if not is_fact_known(fact)
    ]
    return (
        "# Initial Model Architecture Proposal\n\n"
        "**Status:** Proposed. Human approval required before scaffolding.\n\n"
        "## Objective\n\n"
        f"{proposal.summary.strip()}\n\n"
        "## Known Facts\n\n"
        f"{_bullet(knowns, empty='No confirmed facts recorded.')}\n"
        "## Remaining Unknowns\n\n"
        f"{_bullet(unresolved, empty='No architecture-critical unknowns remain.')}\n"
        "## Proposed Connectors\n\n"
        f"{_bullet(proposal.connectors)}\n"
        "## Proposed Model Components\n\n"
        f"{_bullet(proposal.model_components)}\n"
        "## Proposed Generated Skills\n\n"
        f"{_bullet(proposal.generated_skills)}\n"
        "## Risks And Judgment Areas\n\n"
        f"{_bullet(proposal.risks, empty='No additional risks recorded.')}\n"
        "## Validation Checks\n\n"
        f"{_bullet(proposal.validation_checks)}\n"
        "## Decision\n\n"
        "- [ ] Approved to scaffold\n"
        "- [ ] Revise proposal\n"
        "- [ ] Stop after business profile\n"
    )


_PROFILE_TITLE_SUFFIX = " Business Profile"


def is_seeded_business_profile(text: str) -> bool:
    """True when the profile is still the empty one `openfpa init` writes.

    The seed is a fact-free render, so reproducing it exactly from its own title
    establishes that nobody has written anything into it yet.
    """
    first_line = text.partition("\n")[0]
    if not (first_line.startswith("# ") and first_line.endswith(_PROFILE_TITLE_SUFFIX)):
        return False
    name = first_line[2: -len(_PROFILE_TITLE_SUFFIX)]
    if not name:
        return False
    return text == render_business_profile(Intake(business_name=name))


def _replace_onboarding_text(
    path: Path, text: str, check: Callable[[Path], None],
) -> None:
    check(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"onboarding output is not a regular file: {path}")
    descriptor = os.open(path, os.O_WRONLY)
    try:
        previous = os.fstat(descriptor)
        if not stat.S_ISREG(previous.st_mode):
            raise ValueError(f"onboarding output is not a regular file: {path}")
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    else:
        os.close(descriptor)

    check(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".onboarding-", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        output = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with output as writer:
            writer.write(text)
        os.chmod(temporary, previous.st_mode & 0o777)
        check(path)
        os.replace(temporary, path)
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _is_untouched_profile(path: Path, check: Callable[[Path], None]) -> bool:
    check(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"onboarding output is not a regular file: {path}")
    try:
        return is_seeded_business_profile(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return False


def write_onboarding_outputs(
    intake: Intake,
    workspace: str | Path,
    proposal: ArchitectureProposal,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write the business profile and architecture proposal after intake is ready.

    `openfpa init` seeds an empty `business-profile.md`, so the first render
    replaces that untouched seed. A profile carrying any recorded fact, and an
    existing architecture decision, still need an explicit `overwrite`.

    Permitted replacements preserve prior bytes on handled write or rename
    failures and keep ordinary mode bits. File identity and other metadata can
    change. The two outputs are published separately.
    """
    if not intake_ready(intake):
        raise ValueError("intake is not ready for architecture proposal")
    workspace = Path(workspace)
    decisions = workspace / "decisions"
    profile_path = workspace / "business-profile.md"
    proposal_path = decisions / "initial-model-architecture.md"
    checked_workspace = workspace.absolute()
    boundary = Workspace.open(checked_workspace.parent)
    checked_memory = boundary.root / checked_workspace.name

    def check(path: Path) -> None:
        boundary.assert_safe_existing_chain(checked_memory / path.relative_to(workspace))

    check(profile_path)
    check(proposal_path)
    workspace.mkdir(parents=True, exist_ok=True)
    check(proposal_path)
    decisions.mkdir(exist_ok=True)
    check(profile_path)
    replace_seed = not overwrite and profile_path.exists() and _is_untouched_profile(profile_path, check)
    if not overwrite:
        if proposal_path.exists():
            raise FileExistsError(f"onboarding output already exists: {proposal_path}")
        if profile_path.exists() and not replace_seed:
            raise FileExistsError(f"onboarding output already exists: {profile_path}")
    for path, text in (
        (profile_path, render_business_profile(intake)),
        (proposal_path, render_architecture_proposal(intake, proposal)),
    ):
        check(path)
        replace = overwrite or (path is profile_path and replace_seed)
        if replace and path.exists():
            if not overwrite and not _is_untouched_profile(path, check):
                raise FileExistsError(f"onboarding output already exists: {path}")
            _replace_onboarding_text(path, text, check)
            continue
        try:
            output = path.open("x", encoding="utf-8")
        except FileExistsError:
            if not overwrite:
                raise
            _replace_onboarding_text(path, text, check)
        else:
            with output:
                output.write(text)
    return profile_path, proposal_path
