"""Accounting depreciation for a forecast, from evidence held on disk.

Three things stay apart here, because a model that mixes them produces a
plausible cash forecast that is wrong:

- **Depreciation expense** reduces profit and moves no cash.
- **An asset purchase** moves cash on its own date, which is usually not the
  date the charge begins.
- **Tax** is a separate assumption. An AASB 116 carrying amount is not a
  deduction under ITAA 1997 Division 40, the two use different lives and
  conventions, and nothing in this module produces a tax figure.

`load_evidence` reads a calculation-evidence file something else produced. It
opens no socket and calls no service, which is what makes this usable in a
default model run: the figures were obtained once, deliberately, and committed
or kept beside the workspace.

`asset_movement` closes or refuses. If opening plus additions less depreciation
does not equal closing, it says so and names the gap. It never derives the
addition that would close it, because a number computed to make a
reconciliation pass is not evidence of anything.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

SUPPORTED_EVIDENCE_SCHEMAS = ("lodgeit-calculation-evidence/1",)
TOLERANCE = Decimal("0.01")


class DepreciationEvidenceError(ValueError):
    """An evidence file cannot support a forecast figure."""


@dataclass(frozen=True)
class DepreciationEvidence:
    """One validated accounting-depreciation figure, and where it came from."""

    label: str
    calculator: str
    period: str
    status: str
    opening: Decimal | None
    closing: Decimal | None
    charge: Decimal | None
    additions: Decimal | None
    advisory_notes: tuple[str, ...]
    source_path: Path
    calculation_sha256: str
    synthetic_input: bool
    #: The producer's own verdict on the response it recorded, and what it
    #: found wrong with it. A file can carry a COMPUTED call beside a
    #: validation block that rejected it, and the rejection is the one that
    #: decides whether a figure may be used.
    accepted: bool = False
    findings: tuple[str, ...] = ()

    @property
    def blocking_findings(self) -> tuple[str, ...]:
        """The findings that stop the figure being used.

        The producer prefixes an observation it did not treat as blocking
        with `note:`, and repeating that distinction here is what keeps an
        ordinary remark from rejecting a good file.
        """
        return tuple(item for item in self.findings if not item.startswith("note:"))

    @property
    def usable(self) -> bool:
        return (
            self.status == "COMPUTED"
            and self.charge is not None
            and self.accepted
            and not self.blocking_findings
        )

    @property
    def refusal_reasons(self) -> tuple[str, ...]:
        """Why this evidence cannot support a figure. Empty when it can."""
        if self.usable:
            return ()
        reasons = []
        if self.status != "COMPUTED":
            reasons.append(f"the recorded call status is {self.status}, not COMPUTED")
        if self.charge is None:
            reasons.append("the record carries no range_dep charge")
        if not self.accepted:
            reasons.append("the producer's own validation block did not accept the response")
        reasons.extend(f"producer finding: {item}" for item in self.blocking_findings)
        return tuple(reasons)


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _object(value: object, field: str, source: Path) -> dict[str, object]:
    """One nested object, or an empty one. A wrong type is an error, not a crash.

    An evidence file is untrusted input. `(x or {}).get(...)` reads an absent
    block safely and raises AttributeError on a scalar, which escaped as a
    traceback rather than as this module's own error.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DepreciationEvidenceError(
            f"{source}: {field} is {type(value).__name__}, not an object."
        )
    return value


def _strings(value: object, field: str, source: Path) -> tuple[str, ...]:
    """A list of strings, or an error naming what arrived instead.

    Discarding a non-string entry silently let `{"notes": [123]}` satisfy a
    presence check and then yield no advisory text at all.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        raise DepreciationEvidenceError(
            f"{source}: {field} is {type(value).__name__}, not an array."
        )
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise DepreciationEvidenceError(
                f"{source}: {field}[{index}] is {type(item).__name__}, not a string."
            )
    return tuple(value)


def _disclaimer(value: object, field: str, source: Path) -> tuple[str, ...]:
    """The provider's boundary statement, when the advisory carries it as one string.

    The producer contract records that the live div7a route writes its advisory
    as `disclaimer`, not the `notes` array; reading `notes` alone dropped that
    sentence from advisory_notes while keeping the figure usable.
    """
    if value is None:
        return ()
    if not isinstance(value, str):
        raise DepreciationEvidenceError(
            f"{source}: {field} is {type(value).__name__}, not a string."
        )
    return (value.strip(),) if value.strip() else ()


def _money(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DepreciationEvidenceError(
            f"{field} is {type(value).__name__}, not a decimal string. A JSON number has "
            "already lost whatever the calculator meant by it."
        )
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise DepreciationEvidenceError(f"{field} is not a decimal: {value!r}") from exc
    if not amount.is_finite():
        raise DepreciationEvidenceError(f"{field} is not finite")
    return amount


def load_evidence(path: str | Path) -> DepreciationEvidence:
    """Read one evidence file. Reads a file; contacts nothing.

    The digest is checked against the file's own calculation block, so a file
    edited after it was produced is refused rather than quietly believed.
    """
    source = Path(path)
    try:
        record = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        # A file that is not UTF-8 is a file that cannot be read, and this
        # module's own error is the one a caller catches for that.
        raise DepreciationEvidenceError(f"{source} could not be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DepreciationEvidenceError(f"{source} is not valid JSON: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") not in SUPPORTED_EVIDENCE_SCHEMAS:
        raise DepreciationEvidenceError(
            f"{source}: evidence schema {record.get('schema') if isinstance(record, dict) else None!r} "
            f"is not one this pack reads ({', '.join(SUPPORTED_EVIDENCE_SCHEMAS)})."
        )
    calculation = record.get("calculation")
    if not isinstance(calculation, dict):
        raise DepreciationEvidenceError(f"{source}: no calculation block.")
    recorded = record.get("calculation_sha256")
    try:
        actual = hashlib.sha256(_canonical(calculation)).hexdigest()
    except ValueError as exc:
        # json.loads accepts NaN and Infinity; the canonical form refuses
        # them, and that refusal is this module's to report.
        raise DepreciationEvidenceError(
            f"{source}: the calculation block cannot be canonicalised: {exc}"
        ) from exc
    if recorded != actual:
        raise DepreciationEvidenceError(
            f"{source}: calculation_sha256 {recorded} does not match the calculation block "
            f"({actual}). The file has changed since it was produced."
        )
    if calculation.get("schema") not in SUPPORTED_EVIDENCE_SCHEMAS:
        # The record and its own calculation block each name a schema. A file
        # whose inner block names a different one is a file whose fields are
        # not the fields read below.
        raise DepreciationEvidenceError(
            f"{source}: the calculation block names schema "
            f"{calculation.get('schema')!r}, not one this pack reads."
        )
    call = _object(calculation.get("call"), "calculation.call", source)
    normalised = _object(calculation.get("normalised"), "calculation.normalised", source)
    values = _object(normalised.get("values"), "calculation.normalised.values", source)
    upstream = _object(calculation.get("upstream"), "calculation.upstream", source)
    advisory = _object(upstream.get("advisory"), "calculation.upstream.advisory", source)
    notes = _strings(advisory.get("notes"), "calculation.upstream.advisory.notes", source)
    notes += _disclaimer(
        advisory.get("disclaimer"), "calculation.upstream.advisory.disclaimer", source
    )
    validation = _object(calculation.get("validation"), "calculation.validation", source)
    accepted = validation.get("accepted")
    if not isinstance(accepted, bool):
        raise DepreciationEvidenceError(
            f"{source}: calculation.validation.accepted is "
            f"{type(accepted).__name__}, not a boolean. Nothing in the file says whether "
            "the producer accepted the response."
        )
    findings = _strings(
        validation.get("findings"), "calculation.validation.findings", source,
    )
    synthetic_input = calculation.get("synthetic_input", False)
    if type(synthetic_input) is not bool:
        raise DepreciationEvidenceError(
            f"{source}: calculation.synthetic_input is "
            f"{type(synthetic_input).__name__}, not a boolean."
        )
    return DepreciationEvidence(
        label=str(calculation.get("label") or source.stem),
        calculator=str(call.get("calculator") or ""),
        period=str(call.get("period") or ""),
        status=str(call.get("status") or "UNKNOWN"),
        opening=_money(values.get("opening_wdv"), "opening_wdv"),
        closing=_money(values.get("closing_wdv"), "closing_wdv"),
        charge=_money(values.get("range_dep"), "range_dep"),
        additions=_money(values.get("cost_additions"), "cost_additions"),
        advisory_notes=notes,
        source_path=source,
        calculation_sha256=actual,
        synthetic_input=synthetic_input,
        accepted=accepted,
        findings=findings,
    )


@dataclass(frozen=True)
class MovementCheck:
    """Whether an asset movement closes, and by how much it does not."""

    opening: Decimal
    additions: Decimal
    depreciation: Decimal
    closing: Decimal
    gap: Decimal
    closes: bool
    reasons: tuple[str, ...]


def asset_movement(
    opening: Decimal,
    additions: Decimal,
    depreciation: Decimal,
    closing: Decimal,
    *,
    tolerance: Decimal = TOLERANCE,
) -> MovementCheck:
    """opening + additions - depreciation = closing, or a named gap.

    Nothing is derived to make it close. A gap is returned as a gap.
    """
    expected = opening + additions - depreciation
    gap = closing - expected
    closes = gap.copy_abs() <= tolerance
    reasons: tuple[str, ...] = ()
    if not closes:
        reasons = (
            f"movement does not close: opening {opening} plus additions {additions} less "
            f"depreciation {depreciation} is {expected}, against a closing balance of "
            f"{closing}, a gap of {gap}. No addition has been derived to close it.",
        )
    return MovementCheck(opening, additions, depreciation, closing, gap, closes, reasons)


def straight_line_schedule(
    evidence: DepreciationEvidence,
    months: pd.PeriodIndex,
) -> pd.Series:
    """Spread one evidenced charge evenly across the forecast months.

    A deliberate simplification, and the only kind of spreading this module
    does. The evidence carries a charge for a window; a monthly forecast needs
    it by month, and without a monthly breakdown the honest options are an even
    spread or nothing.

    ponytail: even spreading is wrong for a diminishing-value asset within the
    window. Where that matters, obtain evidence per month and sum it; the
    upgrade is more evidence, not more arithmetic here.
    """
    if not evidence.usable:
        raise DepreciationEvidenceError(
            f"{evidence.label}: this evidence cannot support a figure, so there is nothing "
            "to spread, and a refusal is not a nil amount. "
            + "; ".join(evidence.refusal_reasons)
        )
    if len(months) == 0:
        raise DepreciationEvidenceError("no months to spread the charge across")
    assert evidence.charge is not None
    if not math.isfinite(float(evidence.charge)):
        # A finite Decimal beyond float range became an infinite forecast in
        # every month. Nothing in a workpaper is that large; refuse it.
        raise DepreciationEvidenceError(
            f"{evidence.label}: charge {evidence.charge} is outside the range a forecast "
            "series can carry."
        )
    # Split in whole cents, the extra cents on the earliest months, so the
    # months sum back to the evidenced charge: an even float division of
    # $100.00 over twelve months gave twelve 8.333... figures that summed to
    # 100.00000000000001, and no month was a figure anyone could post.
    try:
        charge = evidence.charge.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise DepreciationEvidenceError(
            f"{evidence.label}: charge {evidence.charge} has too many digits to spread in cents"
        ) from exc
    if charge != evidence.charge:
        raise DepreciationEvidenceError(
            f"{evidence.label}: charge {evidence.charge} is not a whole-cent amount"
        )
    # Split the magnitude, then restore the sign, so a reversal's extra cents
    # also fall on the earliest months rather than the latest.
    sign = -1 if charge < 0 else 1
    cents, extra = divmod(abs(int(charge * 100)), len(months))
    values = [sign * (cents + (1 if index < extra else 0)) / 100 for index in range(len(months))]
    return pd.Series(values, index=months, name="depreciation_expense")


def cash_and_expense(
    schedule: pd.Series,
    purchases: pd.Series | None = None,
) -> pd.DataFrame:
    """Depreciation expense beside asset purchases, kept apart.

    Returns a frame with `depreciation_expense` (profit, no cash) and
    `asset_purchases` (cash, no profit effect on its own). A caller that adds
    the two has undone the point of the split.
    """
    frame = pd.DataFrame({"depreciation_expense": schedule})
    if purchases is not None:
        # Reindexing drops any purchase whose month the schedule does not hold, and
        # a DatetimeIndex against the schedule's PeriodIndex matches nothing at all,
        # so every purchase would read as nil cash. Refuse rather than lose them.
        outside = purchases.index.difference(schedule.index)
        if len(outside):
            raise ValueError(
                f"{len(outside)} asset purchase(s) fall outside the schedule's months, "
                f"first {outside[0]!r}; pass purchases indexed by the schedule's periods"
            )
    frame["asset_purchases"] = 0.0 if purchases is None else purchases.reindex(
        schedule.index, fill_value=0.0,
    )
    frame["cash_effect"] = -frame["asset_purchases"]
    frame["profit_effect"] = -frame["depreciation_expense"]
    return frame
