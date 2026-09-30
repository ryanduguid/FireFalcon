"""The opt-in accounting-depreciation scenario.

Every test runs with sockets blocked. The module reads a file that something
else produced; it makes no call, and the block is what proves it.
"""

from __future__ import annotations

import json
import socket
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from pyfpa.au import depreciation as dep

FIXTURES = Path(dep.__file__).resolve().parent / "fixtures"
GOOD = FIXTURES / "depreciation-evidence-lumbridge.json"
UNRECONCILED = FIXTURES / "depreciation-evidence-unreconciled.json"

# 120,000.00 over five years on a prime-cost basis, 92 days of a 365-day year.
ANNUAL = Decimal("24000.00")
QUARTER = Decimal("6049.32")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the depreciation scenario opened a socket")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def months():
    return pd.period_range("2026-10", periods=3, freq="M")


def test_the_committed_fixtures_are_fabricated():
    for path in (GOOD, UNRECONCILED):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["calculation"]["synthetic_input"] is True, path.name


def test_the_fixture_charge_is_the_arithmetic_it_claims():
    """Derived here, not read back from the file that asserts it."""
    charge = (ANNUAL * Decimal(92) / Decimal(365)).quantize(Decimal("0.01"))
    assert charge == QUARTER
    evidence = dep.load_evidence(GOOD)
    assert evidence.charge == QUARTER
    assert evidence.opening == Decimal("120000.00") - QUARTER
    assert evidence.closing == evidence.opening - QUARTER


def test_evidence_loads_with_its_provenance_and_advisory():
    evidence = dep.load_evidence(GOOD)
    assert evidence.usable is True
    assert evidence.calculator == "urn:sbrm:calculator:depreciation:range"
    assert len(evidence.calculation_sha256) == 64
    assert any("not a deduction under" in note for note in evidence.advisory_notes)


def test_a_tampered_file_is_refused(tmp_path):
    record = json.loads(GOOD.read_text(encoding="utf-8"))
    record["calculation"]["normalised"]["values"]["range_dep"] = "1.00"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(dep.DepreciationEvidenceError, match="does not match"):
        dep.load_evidence(path)


def test_a_json_number_for_money_is_refused(tmp_path):
    import hashlib

    record = json.loads(GOOD.read_text(encoding="utf-8"))
    record["calculation"]["normalised"]["values"]["range_dep"] = 6049.32
    record["calculation_sha256"] = hashlib.sha256(
        json.dumps(record["calculation"], sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    path = tmp_path / "float.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(dep.DepreciationEvidenceError, match="not a decimal string"):
        dep.load_evidence(path)


def test_an_unknown_schema_is_refused(tmp_path):
    record = json.loads(GOOD.read_text(encoding="utf-8"))
    record["schema"] = "something-else/2"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(dep.DepreciationEvidenceError, match="not one this pack reads"):
        dep.load_evidence(path)


def test_the_movement_closes():
    evidence = dep.load_evidence(GOOD)
    assert evidence.opening is not None
    assert evidence.charge is not None
    assert evidence.closing is not None
    check = dep.asset_movement(
        opening=evidence.opening, additions=Decimal("0.00"),
        depreciation=evidence.charge, closing=evidence.closing,
    )
    assert check.closes is True
    assert check.gap == Decimal("0.00")
    assert check.reasons == ()


def test_an_unreconciled_movement_is_refused_and_nothing_is_derived():
    evidence = dep.load_evidence(UNRECONCILED)
    assert evidence.usable is False, "a contract failure carries no figure"
    check = dep.asset_movement(
        opening=Decimal("0.00"), additions=Decimal("0.00"),
        depreciation=QUARTER, closing=Decimal("120000.00") - QUARTER,
    )
    assert check.closes is False
    assert check.gap == Decimal("120000.00")
    assert any("No addition has been derived" in reason for reason in check.reasons)


def test_a_separately_evidenced_addition_closes_it():
    check = dep.asset_movement(
        opening=Decimal("0.00"), additions=Decimal("120000.00"),
        depreciation=QUARTER, closing=Decimal("120000.00") - QUARTER,
    )
    assert check.closes is True


def test_a_refusal_cannot_be_spread_across_months():
    evidence = dep.load_evidence(UNRECONCILED)
    with pytest.raises(dep.DepreciationEvidenceError, match="not a nil amount"):
        dep.straight_line_schedule(evidence, months())


def test_the_charge_spreads_evenly_and_sums_back(tmp_path):
    schedule = dep.straight_line_schedule(dep.load_evidence(GOOD), months())
    assert len(schedule) == 3
    assert round(schedule.sum(), 2) == float(QUARTER)
    assert schedule.index.equals(months())


def test_the_spread_is_whole_cents_that_sum_exactly_to_the_charge():
    # 6049.32 over three months: two cents cannot split three ways evenly.
    schedule = dep.straight_line_schedule(dep.load_evidence(GOOD), months())
    cents = [round(value * 100) for value in schedule]
    assert cents == [201644, 201644, 201644]
    assert sum(cents) == int(QUARTER * 100)
    twelve = pd.period_range("2026-07", periods=12, freq="M")
    evidence = dep.load_evidence(GOOD)
    hundred = dep.DepreciationEvidence(**{**evidence.__dict__, "charge": Decimal("100.00")})
    spread = dep.straight_line_schedule(hundred, twelve)
    assert [round(value * 100) for value in spread] == [834] * 4 + [833] * 8
    assert sum(round(value * 100) for value in spread) == 10000


def test_a_reversal_puts_its_extra_cents_on_the_earliest_months_too():
    twelve = pd.period_range("2026-07", periods=12, freq="M")
    evidence = dep.load_evidence(GOOD)
    reversal = dep.DepreciationEvidence(**{**evidence.__dict__, "charge": Decimal("-100.00")})
    spread = dep.straight_line_schedule(reversal, twelve)
    assert [round(value * 100) for value in spread] == [-834] * 4 + [-833] * 8


def test_a_charge_too_wide_for_cents_is_refused_with_the_reason():
    evidence = dep.load_evidence(GOOD)
    huge = dep.DepreciationEvidence(**{**evidence.__dict__, "charge": Decimal("1e100")})
    with pytest.raises(dep.DepreciationEvidenceError, match="too many digits"):
        dep.straight_line_schedule(huge, months())


def test_expense_and_purchases_stay_apart():
    schedule = dep.straight_line_schedule(dep.load_evidence(GOOD), months())
    purchases = pd.Series([120000.0, 0.0, 0.0], index=months())
    frame = dep.cash_and_expense(schedule, purchases)
    # The charge moves no cash, and the purchase moves no profit.
    assert frame["cash_effect"].tolist() == [-120000.0, 0.0, 0.0]
    assert round(frame["profit_effect"].sum(), 2) == -float(QUARTER)
    assert frame["asset_purchases"].sum() == 120000.0
    assert frame["depreciation_expense"].sum() != frame["asset_purchases"].sum()


def test_a_purchase_outside_the_schedule_is_refused_not_dropped():
    schedule = dep.straight_line_schedule(dep.load_evidence(GOOD), months())
    later = pd.Series([50000.0], index=pd.PeriodIndex(["2027-01"], freq="M"))
    with pytest.raises(ValueError, match="1 asset purchase"):
        dep.cash_and_expense(schedule, later)
    # Timestamps never match the schedule's periods, so every purchase would vanish.
    stamped = pd.Series([120000.0, 0.0, 0.0], index=months().to_timestamp())
    with pytest.raises(ValueError, match="3 asset purchase"):
        dep.cash_and_expense(schedule, stamped)


def test_with_no_purchases_the_cash_effect_is_nil():
    frame = dep.cash_and_expense(dep.straight_line_schedule(dep.load_evidence(GOOD), months()))
    assert frame["cash_effect"].tolist() == [0.0, 0.0, 0.0]
    assert frame["depreciation_expense"].sum() > 0


def test_the_module_produces_no_tax_figure():
    """There is no tax function here, and the advisory says why."""
    assert not [name for name in dir(dep) if "tax" in name.lower() or "division40" in name.lower()]
    evidence = dep.load_evidence(GOOD)
    assert any("Division 40" in note for note in evidence.advisory_notes)


def _resealed(tmp_path, name, mutate):
    """The good fixture with one change, re-digested so the seal still holds.

    Without this the digest check fires first and nothing downstream is
    exercised, which is how a rejected record reached a forecast unnoticed.
    """
    import hashlib

    record = json.loads(GOOD.read_text(encoding="utf-8"))
    mutate(record)
    record["calculation_sha256"] = hashlib.sha256(
        json.dumps(record["calculation"], sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    path = tmp_path / name
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


@pytest.mark.parametrize("value", [None, "false", 0, 1, 0.0, [], [False], {}, {"value": False}])
def test_a_non_boolean_synthetic_flag_is_refused(tmp_path, value):
    path = _resealed(
        tmp_path, "malformed-flag.json",
        lambda record: record["calculation"].__setitem__("synthetic_input", value),
    )
    with pytest.raises(
        dep.DepreciationEvidenceError, match=r"calculation\.synthetic_input.*not a boolean",
    ):
        dep.load_evidence(path)


@pytest.mark.parametrize("value", [True, False])
def test_a_boolean_synthetic_flag_is_preserved(tmp_path, value):
    path = _resealed(
        tmp_path, "boolean-flag.json",
        lambda record: record["calculation"].__setitem__("synthetic_input", value),
    )
    evidence = dep.load_evidence(path)
    assert evidence.synthetic_input is value
    assert evidence.usable is True


def test_an_absent_synthetic_flag_keeps_its_false_default(tmp_path):
    path = _resealed(
        tmp_path, "absent-flag.json",
        lambda record: record["calculation"].pop("synthetic_input"),
    )
    evidence = dep.load_evidence(path)
    assert evidence.synthetic_input is False
    assert evidence.usable is True


def test_a_producer_that_rejected_its_own_response_is_not_usable(tmp_path):
    # A digest-valid file can carry a COMPUTED call beside a validation block
    # that rejected it. The rejection decides, or a figure the producer refused
    # reaches the forecast.
    path = _resealed(
        tmp_path, "rejected.json",
        lambda record: record["calculation"]["validation"].update({"accepted": False}),
    )
    evidence = dep.load_evidence(path)
    assert evidence.usable is False
    assert any("did not accept" in reason for reason in evidence.refusal_reasons)
    with pytest.raises(dep.DepreciationEvidenceError, match="did not accept"):
        dep.straight_line_schedule(evidence, pd.period_range("2024-07", periods=12, freq="M"))


def test_a_blocking_producer_finding_is_not_usable(tmp_path):
    path = _resealed(
        tmp_path, "finding.json",
        lambda record: record["calculation"]["validation"]["findings"].append(
            "required decimal field range_dep is absent"
        ),
    )
    evidence = dep.load_evidence(path)
    assert evidence.usable is False
    assert any("range_dep is absent" in reason for reason in evidence.refusal_reasons)


def test_an_observation_the_producer_did_not_block_on_stays_usable(tmp_path):
    # The producer prefixes a non-blocking remark with `note:`. Treating one as
    # a rejection would refuse every good file that carried a remark.
    path = _resealed(
        tmp_path, "note.json",
        lambda record: record["calculation"]["validation"]["findings"].append(
            "note: response carries unrecorded fields: numeric_mode"
        ),
    )
    assert dep.load_evidence(path).usable is True


def test_a_missing_validation_block_is_refused(tmp_path):
    path = _resealed(
        tmp_path, "novalidation.json",
        lambda record: record["calculation"].pop("validation"),
    )
    with pytest.raises(dep.DepreciationEvidenceError, match="not a boolean"):
        dep.load_evidence(path)


@pytest.mark.parametrize("mutate,expected", [
    (lambda r: r["calculation"].__setitem__("call", "COMPUTED"), "call is str"),
    (lambda r: r["calculation"].__setitem__("normalised", 1), "normalised is int"),
    (lambda r: r["calculation"]["normalised"].__setitem__("values", []),
     "normalised.values is list"),
    (lambda r: r["calculation"]["upstream"].__setitem__("advisory", "none"),
     "advisory is str"),
    (lambda r: r["calculation"]["upstream"]["advisory"].__setitem__("notes", 1),
     "notes is int"),
    (lambda r: r["calculation"]["upstream"]["advisory"].__setitem__("notes", [123]),
     r"notes\[0\] is int"),
    (lambda r: r["calculation"]["validation"].__setitem__("findings", "none"),
     "findings is str"),
])
def test_a_scalar_where_a_block_belongs_is_an_error_not_a_traceback(tmp_path, mutate, expected):
    # These used to escape as AttributeError or TypeError from `(x or {}).get`,
    # which no caller catches. An evidence file is untrusted input.
    path = _resealed(tmp_path, "malformed.json", mutate)
    with pytest.raises(dep.DepreciationEvidenceError, match=expected):
        dep.load_evidence(path)


def test_an_inner_schema_that_disagrees_with_the_record_is_refused(tmp_path):
    path = _resealed(
        tmp_path, "innerschema.json",
        lambda record: record["calculation"].__setitem__("schema", "something-else/9"),
    )
    with pytest.raises(dep.DepreciationEvidenceError, match="calculation block names schema"):
        dep.load_evidence(path)


def test_a_nan_in_the_calculation_block_is_this_modules_error(tmp_path):
    # json.loads accepts NaN; the canonical form refuses it. That refusal
    # used to escape as a bare ValueError a caller catching
    # DepreciationEvidenceError never saw.
    path = tmp_path / "nan.json"
    path.write_text(
        '{"schema": "lodgeit-calculation-evidence/1", "calculation_sha256": "0",'
        ' "calculation": {"schema": "lodgeit-calculation-evidence/1", "x": NaN}}',
        encoding="utf-8",
    )
    with pytest.raises(dep.DepreciationEvidenceError, match="cannot be canonicalised"):
        dep.load_evidence(path)


def test_a_file_that_is_not_utf8_is_this_modules_error(tmp_path):
    path = tmp_path / "latin1.json"
    path.write_bytes(b'{"schema": "lodgeit-calculation-evidence/1", "note": "\xff"}')
    with pytest.raises(dep.DepreciationEvidenceError, match="could not be read"):
        dep.load_evidence(path)


def test_a_disclaimer_only_advisory_keeps_its_boundary_statement(tmp_path):
    # The producer contract records the live div7a route writing `disclaimer`
    # rather than `notes`. Reading notes alone dropped the sentence and kept
    # the figure.
    def mutate(record):
        advisory = record["calculation"]["upstream"]["advisory"]
        del advisory["notes"]
        advisory["disclaimer"] = "  Figures are indicative and not a substitute for advice.  "

    evidence = dep.load_evidence(_resealed(tmp_path, "disclaimer.json", mutate))
    assert evidence.usable is True
    assert evidence.advisory_notes == (
        "Figures are indicative and not a substitute for advice.",
    )


def test_notes_and_a_disclaimer_both_travel(tmp_path):
    def mutate(record):
        record["calculation"]["upstream"]["advisory"]["disclaimer"] = "Provider boundary."

    evidence = dep.load_evidence(_resealed(tmp_path, "both.json", mutate))
    original = dep.load_evidence(GOOD).advisory_notes
    assert evidence.advisory_notes == original + ("Provider boundary.",)


def test_a_blank_disclaimer_adds_nothing(tmp_path):
    def mutate(record):
        record["calculation"]["upstream"]["advisory"]["disclaimer"] = "   "

    assert dep.load_evidence(_resealed(tmp_path, "blank.json", mutate)).advisory_notes == (
        dep.load_evidence(GOOD).advisory_notes
    )


def test_a_disclaimer_that_is_not_a_string_is_this_modules_error(tmp_path):
    def mutate(record):
        record["calculation"]["upstream"]["advisory"]["disclaimer"] = ["not", "a", "string"]

    with pytest.raises(dep.DepreciationEvidenceError, match="disclaimer is list"):
        dep.load_evidence(_resealed(tmp_path, "list.json", mutate))


def test_a_charge_beyond_float_range_is_refused_not_spread_as_infinity():
    evidence = replace(dep.load_evidence(GOOD), charge=Decimal("1e1000"))
    assert evidence.usable is True
    with pytest.raises(dep.DepreciationEvidenceError, match="outside the range"):
        dep.straight_line_schedule(evidence, months())
