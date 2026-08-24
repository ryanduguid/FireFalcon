from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pyfpa.memory.intake import Intake, save_intake

WORKSPACE_DIRS = (
    "sources",
    "mappings",
    "corrections",
    "forecasts",
    "experiments",
    "decisions",
    "models",
    "research",
)

_GENERATED_DIRS = (
    "connectors/generated",
    "models/generated",
    "skills/generated",
    "agents/generated",
)


def workspace_path(company_root: str | Path) -> Path:
    """Return the `.fpa` memory path for a company workspace."""
    return Path(company_root) / ".fpa"


def _seed_source_registry(target: Path, business_name: str) -> None:
    from pyfpa.memory.lineage import SourceRegistry, save_source_registry

    save_source_registry(SourceRegistry(), target)


def _seed_mapping_registry(target: Path, business_name: str) -> None:
    from pyfpa.memory.lineage import MappingRegistry, save_mapping_registry

    save_mapping_registry(MappingRegistry(), target)


def _seed_research_objective(target: Path, business_name: str) -> None:
    from pyfpa.research.objective import (
        MetricObjective,
        ResearchObjective,
        save_research_objective,
    )

    save_research_objective(
        ResearchObjective(
            metrics=[
                MetricObjective(name="ending_cash_error", weight=0.4),
                MetricObjective(name="ebitda_error", weight=0.3),
                MetricObjective(name="revenue_error", weight=0.2),
                MetricObjective(name="gross_margin_error", weight=0.1),
            ],
            hard_checks=[
                "source reconciliation",
                "accounting invariants",
                "holdout separation",
            ],
            min_improvement=0.02,
            complexity_penalty=0.01,
        ),
        target,
    )


def _seed_model_registry(target: Path, business_name: str) -> None:
    from pyfpa.research.registry import ModelRegistry, save_model_registry

    save_model_registry(ModelRegistry(), target)


def _seed_entrypoints(target: Path, business_name: str) -> None:
    from pyfpa.memory.entrypoints import (
        EntrypointRegistry,
        save_entrypoint_registry,
    )

    save_entrypoint_registry(EntrypointRegistry(), target)


def _seed_intake(target: Path, business_name: str) -> None:
    save_intake(Intake(business_name=business_name), target)


def _seed_profile(target: Path, business_name: str) -> None:
    from pyfpa.memory.onboarding import render_business_profile

    target.write_text(render_business_profile(Intake(business_name=business_name)))


def _seed_scorecard(target: Path, business_name: str) -> None:
    target.write_text("# Forecast Scorecard\n")


def _seed_learnings(target: Path, business_name: str) -> None:
    target.write_text("# Learnings\n")


def _seed_memory_index(target: Path, business_name: str) -> None:
    target.write_text(
        f"# {business_name} FP&A Memory\n\n"
        "- `intake.md`: onboarding facts, evidence, confidence, and open questions\n"
        "- `business-profile.md`: durable business context derived from intake\n"
        "- `sources/`: source inventory and data provenance\n"
        "- `mappings/`: account and operational-data mappings\n"
        "- `corrections/`: typed human corrections recorded by fpa-capture-correction, applied via pyfpa.apply_corrections\n"
        "- `forecasts/`: immutable forecast snapshots and their scores, written by pyfpa.backtest\n"
        "- `scorecard.md`: rendered forecast track record across all scored periods\n"
        "- `learnings.md`: accepted model changes with evidence and backtest delta\n"
        "- `experiments/`: model hypotheses, evidence, checks, and ratification decisions\n"
        "- `decisions/`: material CFO decisions and approvals\n"
        "- `models/`: champion/challenger history and generated entrypoints\n"
        "- `research/`: immutable autonomous research epochs\n"
        "- `../connectors/generated/`: fixture-tested company data access\n"
    )


# Files seeded on first run, in creation order. Each writer receives the target
# path and the business name; registry writers ignore the name.
_SEED_FILES: tuple[tuple[str, Callable[[Path, str], None]], ...] = (
    ("sources/registry.yaml", _seed_source_registry),
    ("mappings/registry.yaml", _seed_mapping_registry),
    ("research/objective.yaml", _seed_research_objective),
    ("models/registry.yaml", _seed_model_registry),
    ("models/entrypoints.yaml", _seed_entrypoints),
    ("intake.md", _seed_intake),
    ("business-profile.md", _seed_profile),
    ("scorecard.md", _seed_scorecard),
    ("learnings.md", _seed_learnings),
    ("MEMORY.md", _seed_memory_index),
)


def initialize_workspace(
    company_root: str | Path,
    *,
    business_name: str = "Company",
) -> Path:
    """Create a company `.fpa` workspace without overwriting existing memory."""
    workspace = workspace_path(company_root)
    workspace.mkdir(parents=True, exist_ok=True)
    for directory in WORKSPACE_DIRS:
        (workspace / directory).mkdir(exist_ok=True)
    for directory in _GENERATED_DIRS:
        (Path(company_root) / directory).mkdir(parents=True, exist_ok=True)

    for relative, seed in _SEED_FILES:
        target = workspace / relative
        if not target.exists():
            seed(target, business_name)
    return workspace
