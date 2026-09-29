from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
import yaml
from pydantic import ValidationError

from pyfpa.memory.experiments import (
    Experiment,
    ExperimentCheck,
    ExperimentDecision,
    load_experiment,
    load_experiments,
    save_experiment,
)


def _accepted_experiment() -> Experiment:
    return Experiment(
        slug="2026-06-09-collections-lag",
        created="2026-06-09",
        status="accepted",
        hypothesis="Wholesale collections arrive one month later than the base model.",
        cfo_question="Why does cash keep landing below forecast?",
        evidence=["AR aging export", ".fpa/corrections/collections.md"],
        training_periods=["2025-01..2025-09"],
        holdout_periods=["2025-10..2025-12"],
        files_changed=["models/generated/collections.py"],
        metrics_before={"ending_cash_wape": 0.18},
        metrics_after={"ending_cash_wape": 0.07},
        checks=[
            ExperimentCheck(name="cash reconciliation", result="pass"),
            ExperimentCheck(name="holdout improvement", result="pass"),
        ],
        decision=ExperimentDecision(
            outcome="accepted",
            decided_by="CFO",
            decided_at="2026-06-09",
            notes="Matches the collections process.",
        ),
    )


def test_experiment_round_trip(tmp_path):
    experiment = _accepted_experiment()
    path = save_experiment(experiment, tmp_path)

    assert load_experiment(path) == experiment
    assert load_experiments(tmp_path) == [experiment]


def test_experiment_history_does_not_overwrite_implicitly(tmp_path):
    experiment = _accepted_experiment()
    path = save_experiment(experiment, tmp_path)
    updated = experiment.model_copy(update={"hypothesis": "A revised hypothesis."})

    with pytest.raises(FileExistsError):
        save_experiment(updated, tmp_path)
    assert load_experiment(path) == experiment

    assert save_experiment(updated, tmp_path, overwrite=True) == path
    assert load_experiment(path) == updated


def test_experiment_preserves_an_intervening_creation(tmp_path, monkeypatch):
    experiment = _accepted_experiment()
    competing = experiment.model_copy(update={"hypothesis": "The competing saved hypothesis."})
    path = tmp_path / f"{experiment.slug}.experiment.yaml"
    original_open = Path.open
    inserted = False

    def open_after_competing_save(destination, *args, **kwargs):
        nonlocal inserted
        if destination == path and not inserted:
            inserted = True
            with original_open(path, "x", encoding="utf-8") as output:
                output.write(yaml.safe_dump(competing.model_dump(), sort_keys=False))
        return original_open(destination, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_after_competing_save)
    with pytest.raises(FileExistsError):
        save_experiment(experiment, tmp_path)
    assert inserted
    assert load_experiment(path) == competing


def test_only_one_concurrent_experiment_creator_succeeds(tmp_path, monkeypatch):
    first = _accepted_experiment()
    second = first.model_copy(update={"hypothesis": "A different concurrent hypothesis."})
    path = tmp_path / f"{first.slug}.experiment.yaml"
    original_open = Path.open
    barrier = Barrier(2)

    def open_together(destination, *args, **kwargs):
        mode = kwargs.get("mode", args[0] if args else "r")
        if destination == path and mode in {"w", "x"}:
            barrier.wait(timeout=10)
        return original_open(destination, *args, **kwargs)

    def save(record):
        try:
            save_experiment(record, tmp_path)
        except FileExistsError:
            return None
        return record

    monkeypatch.setattr(Path, "open", open_together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [first, second]))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    assert load_experiment(path) == winners[0]


def test_experiment_serialisation_failure_preserves_an_existing_record(tmp_path, monkeypatch):
    experiment = _accepted_experiment()
    path = save_experiment(experiment, tmp_path)
    before = path.read_bytes()

    def fail_serialisation(*args, **kwargs):
        raise ValueError("Fabricated serialisation failure")

    monkeypatch.setattr(yaml, "safe_dump", fail_serialisation)
    with pytest.raises(ValueError, match="serialisation"):
        save_experiment(experiment, tmp_path, overwrite=True)
    assert path.read_bytes() == before


def test_accepted_experiment_requires_ratification_and_passing_checks():
    data = _accepted_experiment().model_dump()
    data["decision"] = None
    with pytest.raises(ValidationError, match="require a decision"):
        Experiment.model_validate(data)

    data = _accepted_experiment().model_dump()
    data["checks"][0]["result"] = "fail"
    with pytest.raises(ValidationError, match="all checks to pass"):
        Experiment.model_validate(data)


def test_proposed_experiment_cannot_claim_a_decision():
    data = _accepted_experiment().model_dump()
    data["status"] = "proposed"
    with pytest.raises(ValidationError, match="cannot have a decision"):
        Experiment.model_validate(data)


def test_experiment_snapshot_field_round_trips(tmp_path):
    """snapshot field is preserved on save/load and defaults to None."""
    base = _accepted_experiment()

    # defaults to None when absent
    assert base.snapshot is None

    # explicit snapshot label round-trips
    with_snapshot = base.model_copy(
        update={"snapshot": "forecasts/2025-12.snapshot.yaml"}
    )
    path = save_experiment(with_snapshot, tmp_path)
    loaded = load_experiment(path)
    assert loaded.snapshot == "forecasts/2025-12.snapshot.yaml"


def test_experiment_without_snapshot_round_trips(tmp_path):
    """Experiments without a snapshot still save and load correctly."""
    experiment = _accepted_experiment()
    path = save_experiment(experiment, tmp_path)
    loaded = load_experiment(path)
    assert loaded.snapshot is None
    assert loaded == experiment
