from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from pyfpa.io.loaders import read_optional_yaml, write_yaml
from pyfpa.research.epochs import ResearchEpoch, evaluate_challenger

if TYPE_CHECKING:
    from pyfpa.research.objective import ResearchObjective


class ModelVersion(BaseModel):
    model_id: str
    created: str
    artifact: str
    source_epoch: str | None = None
    description: str = ""


class PromotionRecord(BaseModel):
    from_model: str
    to_model: str
    epoch_id: str
    approved_by: str
    approved_at: str
    notes: str = ""


class ModelRegistry(BaseModel):
    schema_version: int = 1
    champion: ModelVersion | None = None
    challengers: list[ModelVersion] = Field(default_factory=list)
    retired: list[ModelVersion] = Field(default_factory=list)
    promotions: list[PromotionRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _model_ids_are_unique(self) -> ModelRegistry:
        """Reject a registry that names one model id twice.

        register_challenger enforces this on the write path, but a hand-edited
        or externally produced registry.yaml loads straight through. With a
        duplicate id, promote_challenger promotes the first match and drops
        every match, so it can promote one artifact and discard another.
        """
        versions = [
            *self.challengers,
            *self.retired,
            *([self.champion] if self.champion else []),
        ]
        ids = [version.model_id for version in versions]
        duplicates = sorted({model_id for model_id in ids if ids.count(model_id) > 1})
        if duplicates:
            raise ValueError(f"model ids must be unique, repeated: {duplicates}")
        return self


def save_model_registry(registry: ModelRegistry, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(path, registry.model_dump())


def load_model_registry(path: str | Path) -> ModelRegistry:
    return ModelRegistry.model_validate(read_optional_yaml(path))


def register_challenger(
    registry: ModelRegistry,
    challenger: ModelVersion,
) -> ModelRegistry:
    """Return a new registry with a uniquely named challenger."""
    ids = {
        version.model_id
        for version in [
            *registry.challengers,
            *registry.retired,
            *([registry.champion] if registry.champion else []),
        ]
    }
    if challenger.model_id in ids:
        raise ValueError(f"model id already registered: {challenger.model_id}")
    return registry.model_copy(
        update={"challengers": [*registry.challengers, challenger]}
    )


def promote_challenger(
    registry: ModelRegistry,
    *,
    challenger_id: str,
    epoch: ResearchEpoch,
    approved_by: str,
    approved_at: str,
    notes: str = "",
    objective: ResearchObjective | None = None,
) -> ModelRegistry:
    """Promote a challenger only with an explicit human approval record.

    An objective is required to recompute eligibility from the epoch's metrics
    and checks. A stored eligibility flag cannot replace that evidence.
    """
    if not approved_by.strip():
        raise ValueError("promotion requires approved_by")
    if not approved_at.strip():
        # The promotion record is the approval evidence. A blank timestamp leaves
        # no date to audit the decision against.
        raise ValueError("promotion requires approved_at")
    if objective is None:
        raise ValueError("objective is required for promotion validation")
    evaluation = epoch.evaluation
    if (
        epoch.status != "proposed"
        or evaluation is None
        or not evaluation.promotion_eligible
    ):
        raise ValueError("promotion requires a proposed, promotion-eligible epoch")
    if objective.complexity_penalty and (
        evaluation.champion_complexity is None or evaluation.challenger_complexity is None
    ):
        raise ValueError("stored evaluation lacks complexity inputs; evaluate it again")
    recomputed = evaluate_challenger(
        objective,
        evaluation.champion_metrics,
        evaluation.challenger_metrics,
        epoch.checks,
        champion_complexity=evaluation.champion_complexity or 0.0,
        challenger_complexity=evaluation.challenger_complexity or 0.0,
    )
    reproduces = (
        recomputed.promotion_eligible
        and recomputed.complexity_cost == evaluation.complexity_cost
    )
    if not reproduces:
        raise ValueError(
            "stored evaluation does not reproduce: recomputed evaluation is not "
            "promotion_eligible -- the stored YAML may have been hand-edited"
        )
    if registry.champion is not None and registry.champion.model_id != epoch.champion_id:
        raise ValueError("epoch champion does not match current registry champion")
    challenger = next(
        (item for item in registry.challengers if item.model_id == challenger_id),
        None,
    )
    if challenger is None:
        raise ValueError(f"challenger not found: {challenger_id}")
    if epoch.challenger_id != challenger_id:
        raise ValueError("epoch challenger does not match registry challenger")
    if challenger.source_epoch != epoch.epoch_id:
        raise ValueError("challenger source epoch does not match promotion epoch")
    retired = list(registry.retired)
    if registry.champion is not None:
        retired.append(registry.champion)
    promotion = PromotionRecord(
        from_model=registry.champion.model_id if registry.champion else "",
        to_model=challenger.model_id,
        epoch_id=epoch.epoch_id,
        approved_by=approved_by,
        approved_at=approved_at,
        notes=notes,
    )
    return registry.model_copy(update={
        "champion": challenger,
        "challengers": [
            item for item in registry.challengers if item.model_id != challenger_id
        ],
        "retired": retired,
        "promotions": [*registry.promotions, promotion],
    })
