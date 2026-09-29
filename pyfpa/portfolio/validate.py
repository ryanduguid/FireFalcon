from __future__ import annotations

import copy
import math
import statistics

from pydantic import BaseModel

from pyfpa.backtest.score import (
    DEFAULT_SCORE_LINES,
    ScoreResult,
    extract_lines,
    score_forecast,
)
from pyfpa.backtest.snapshot import Snapshot
from pyfpa.config.schemas import EntityConfig
from pyfpa.memory.paths import apply_override
from pyfpa.models.cashflow import cashflow_from_config
from pyfpa.portfolio.approval import (
    attest_validation,
    candidate_digest,
    resolved_support,
)
from pyfpa.portfolio.manifest import (
    ClientRef,
    canonical_client_path,
    require_distinct_clients,
)
from pyfpa.portfolio.mine import PriorCandidate, client_driver_value
from pyfpa.portfolio.recover import best_snapshot, recover_actuals


class ValidationResult(BaseModel):
    mean_delta: float
    n_folds: int
    validated: bool
    # The candidate this result validates. promote_prior refuses a result whose
    # digest is not the candidate's, so a result cannot be carried across to a
    # different or later candidate.
    candidate_digest: str = ""
    # validate_prior's per-process stamp over the three fields above. A result
    # built by hand, or carried in from another process, carries none and cannot
    # support a promotion. See pyfpa.portfolio.approval.attest_validation for
    # what it does and does not establish.
    attestation: str = ""


def validate_prior(
    driver: str,
    type_clients: list[ClientRef],
    *,
    tolerance: float = 0.0,
    candidate: PriorCandidate | None = None,
) -> ValidationResult:
    """Leave-one-out cross-client check. For each usable client, derive `driver`'s
    value as the median across the OTHER clients, apply it to the held-out client's
    best-snapshot config, re-forecast, and score against that client's recovered
    actuals. A prior is `validated` if the mean fitness delta (new - original) is
    <= tolerance with >= 2 folds - a peer-derived value does not degrade held-out fit.
    Repeated workspaces are rejected: a fold whose peers include copies of the
    held-out client is not held out. A fold whose peer-derived value leaves the
    held-out client with no forecast, because the engine refuses the result (for
    example impossible working-capital flows), counts as an infinitely worse fit,
    so the prior cannot validate and the other folds still run.

    Pass `candidate` to stamp its digest and an attestation into the result.
    Without it both stay empty and `promote_prior` refuses the result: a fitness
    check on a driver is not evidence about a particular candidate. A candidate
    is refused unless its driver, business type, support and value are the ones
    these folds tested."""
    require_distinct_clients(type_clients)
    digest = _candidate_digest_for(driver, type_clients, candidate)
    usable: list[tuple[float, Snapshot, ScoreResult]] = []
    for c in type_clients:
        snap = best_snapshot(c.path)
        value = client_driver_value(c, driver)
        if snap is not None and snap.score is not None and value is not None:
            recorded_lines = set(snap.score.per_line)
            try:
                recovered = recover_actuals(snap)
            except ValueError:
                continue
            if recorded_lines and recorded_lines == set(snap.score.weights) and all(
                line in recovered and recovered[line] != 0 for line in recorded_lines
            ):
                usable.append((value, snap, snap.score))
    n = len(usable)
    if n < 2:
        return _result(0.0, n, False, digest)
    if candidate is not None:
        _require_validated_value(candidate, [value for value, _, _ in usable])

    deltas = []
    for i, (_, snap, score) in enumerate(usable):
        peer_values = [usable[j][0] for j in range(n) if j != i]
        prior_value = statistics.median(peer_values)
        data = copy.deepcopy(snap.assumptions)
        apply_override(data, driver, prior_value)
        try:
            forecast = cashflow_from_config(EntityConfig.model_validate(data))
        except ValueError:
            deltas.append(math.inf)
            continue
        # Score over the SAME lines/weights Loop A used for this snapshot, so the new
        # fitness and the stored fitness are apples-to-apples (not assumed defaults).
        scored_lines = list(score.per_line) or DEFAULT_SCORE_LINES
        predicted = extract_lines(forecast, scored_lines)
        new_fitness = score_forecast(
            predicted, recover_actuals(snap), weights=score.weights or None
        ).fitness
        deltas.append(new_fitness - score.fitness)

    mean_delta = statistics.fmean(deltas)
    return _result(mean_delta, n, mean_delta <= tolerance, digest)


def _result(mean_delta: float, n_folds: int, validated: bool, digest: str) -> ValidationResult:
    """One validation result, attested when it is about a named candidate."""
    return ValidationResult(
        mean_delta=mean_delta,
        n_folds=n_folds,
        validated=validated,
        candidate_digest=digest,
        attestation=(
            attest_validation(digest, n_folds, mean_delta) if digest else ""
        ),
    )


def _require_validated_value(candidate: PriorCandidate, validated_values: list[float]) -> None:
    """Refuse a candidate whose value is not the one these folds tested.

    Each fold applies the median of its peers, so the value the folds support is
    the median across the clients that were usable. A candidate carrying any
    other value was not validated by this run, whatever its dispersion said.
    """
    tested = statistics.median(validated_values)
    if candidate.value != tested:
        raise ValueError(
            f"candidate value {candidate.value!r} is not the validated median "
            f"{tested!r} across the {len(validated_values)} usable clients"
        )


def _candidate_digest_for(
    driver: str, type_clients: list[ClientRef], candidate: PriorCandidate | None
) -> str:
    """The digest to stamp, refusing a candidate this run does not validate."""
    if candidate is None:
        return ""
    if candidate.driver != driver:
        raise ValueError(
            f"candidate drives {candidate.driver!r}, validation is for {driver!r}"
        )
    types = {client.type for client in type_clients}
    if types != {candidate.business_type}:
        raise ValueError(
            f"candidate is for business type {candidate.business_type!r}, the "
            f"validated clients are {sorted(types)}"
        )
    known = {canonical_client_path(client.path) for client in type_clients}
    missing = [path for path in resolved_support(candidate.support) if path not in known]
    if missing:
        raise ValueError(
            f"candidate support includes {len(missing)} workspace(s) outside the "
            "validated client list, so the folds do not hold them out"
        )
    return candidate_digest(candidate)
