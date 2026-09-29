"""Structural review controls for a monthly forecast frame.

The frame is the shape cashflow_from_config returns. Each control either passes
silently, fails with a stable code, or reports NOT_RUN when the frame lacks what
it needs, so an absent check is never mistaken for a passed one.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from pyfpa.config.schemas import EntityConfig

# Dollars. A difference up to half a cent is rounding in the frame, not a break.
_TOLERANCE = 0.005

_IDENTITIES: tuple[tuple[str, tuple[str, ...], Callable[[pd.Series], float]], ...] = (
    ("gross_profit", ("revenue", "cogs"), lambda r: r["revenue"] - r["cogs"]),
    ("ebitda", ("gross_profit", "opex"), lambda r: r["gross_profit"] - r["opex"]),
    ("pretax_income", ("ebitda", "da", "interest"), lambda r: r["ebitda"] - r["da"] - r["interest"]),
    ("net_income", ("pretax_income", "tax"), lambda r: r["pretax_income"] - r["tax"]),
    ("operating_cash_flow", ("net_income", "da", "wc_cash_impact"),
     lambda r: r["net_income"] + r["da"] + r["wc_cash_impact"]),
    ("free_cash_flow", ("operating_cash_flow", "capex"), lambda r: r["operating_cash_flow"] - r["capex"]),
    ("change_in_cash", ("free_cash_flow", "principal"), lambda r: r["free_cash_flow"] - r["principal"]),
)
_ROLL_FORWARD = ("ending_cash", "change_in_cash")


class Status(str, Enum):
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class Finding:
    code: str
    status: Status
    period: str | None
    observed: float | None
    expected: float | None
    message: str


@dataclass(frozen=True)
class ForecastReview:
    findings: tuple[Finding, ...]

    @property
    def failed(self) -> bool:
        return any(finding.status is Status.FAIL for finding in self.findings)


def _code(column: str) -> str:
    return "FR-IDENTITY-" + column.upper().replace("_", "-")


def _index_problems(index: pd.Index, cfg: EntityConfig) -> list[str]:
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != "M":
        return ["the index is not a monthly PeriodIndex"]
    problems = [f"duplicate month {period}" for period in index[index.duplicated()].unique()]
    expected = pd.period_range(cfg.start_month, periods=cfg.horizon_months, freq="M")
    problems += [f"missing month {period}" for period in expected.difference(index)]
    if len(index) and index[0] != expected[0]:
        problems.append(f"the forecast starts at {index[0]}, not the configured start {expected[0]}")
    if len(index) != cfg.horizon_months:
        problems.append(f"the forecast has {len(index)} months, not the configured length {cfg.horizon_months}")
    if not problems and not index.equals(expected):
        problems.append("the months are not in calendar order")
    return problems


def _finite(value: object) -> bool:
    if not isinstance(value, numbers.Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too large for a float
        return False


def _finite_float(value: float) -> float | None:
    """The result of a check's arithmetic as a float, or None when it overflows."""
    try:
        result = float(value)
    except OverflowError:  # integer arithmetic beyond the float range
        return None
    return result if math.isfinite(result) else None


def review_forecast(forecast: pd.DataFrame, cfg: EntityConfig) -> ForecastReview:
    """Check a forecast frame's month index, values, identities and cash roll-forward."""
    findings: list[Finding] = []
    index_problems = _index_problems(forecast.index, cfg)
    if index_problems:
        findings.append(Finding("FR-INDEX", Status.FAIL, None, None, None, "; ".join(index_problems)))

    needed = sorted({c for column, inputs, _ in _IDENTITIES for c in (column, *inputs)} | set(_ROLL_FORWARD))
    missing = [column for column in needed if column not in forecast.columns]
    if missing:
        findings.append(Finding("FR-MISSING-COLUMN", Status.FAIL, None, None, None,
                                "missing columns: " + ", ".join(missing)))

    # A repeated label makes row[column] a Series, so no check could read it.
    duplicated = sorted(set(forecast.columns[forecast.columns.duplicated()]) & set(needed))
    if duplicated:
        findings.append(Finding("FR-DUPLICATE-COLUMN", Status.FAIL, None, None, None,
                                "duplicate columns: " + ", ".join(duplicated)))
    unusable_columns = set(missing) | set(duplicated)

    present = [column for column in needed if column not in unusable_columns]
    for period, row in forecast[present].iterrows():
        for column, value in row.items():
            if not _finite(value):
                findings.append(Finding("FR-NON-FINITE", Status.FAIL, str(period), None, None,
                                        f"{column} is not a finite number in {period}"))

    for column, inputs, expected_of in _IDENTITIES:
        if unusable_columns & {column, *inputs}:
            findings.append(Finding(_code(column), Status.NOT_RUN, None, None, None,
                                    f"{column} cannot be checked without one column each for "
                                    + ", ".join((column, *inputs))))
            continue
        for period, row in forecast.iterrows():
            unusable = [name for name in (column, *inputs) if not _finite(row[name])]
            if unusable:
                # Never do the identity's arithmetic on a value that failed the check above.
                findings.append(Finding(_code(column), Status.NOT_RUN, str(period), None, None,
                                        f"{column} cannot be checked in {period}; not a finite number: "
                                        + ", ".join(unusable)))
                continue
            with np.errstate(over="ignore", invalid="ignore"):  # an overflow is reported below
                raw = expected_of(row)
            observed, expected = float(row[column]), _finite_float(raw)
            if expected is None:
                findings.append(Finding(_code(column), Status.NOT_RUN, str(period), None, None,
                                        f"{column} cannot be checked in {period}; its inputs' arithmetic overflows"))
                continue
            if abs(observed - expected) > _TOLERANCE:
                findings.append(Finding(_code(column), Status.FAIL, str(period), observed, expected,
                                        f"{column} is {observed:,.2f} in {period}; its inputs give {expected:,.2f}"))

    if index_problems or unusable_columns & set(_ROLL_FORWARD):
        findings.append(Finding("FR-CASH-ROLLFORWARD", Status.NOT_RUN, None, None, None,
                                "the cash roll-forward needs an ordered monthly index and one column each for "
                                "ending_cash and change_in_cash"))
    else:
        previous: float | None = cfg.opening_balances.cash
        for period, row in forecast.iterrows():
            closing, change = row["ending_cash"], row["change_in_cash"]
            if previous is None or not _finite(closing) or not _finite(change):
                findings.append(Finding("FR-CASH-ROLLFORWARD", Status.NOT_RUN, str(period), None, None,
                                        f"the cash roll-forward cannot be checked in {period}: opening cash, "
                                        "closing cash or the month's change is not a finite number"))
            elif (expected := _finite_float(previous + float(change))) is None:
                findings.append(Finding("FR-CASH-ROLLFORWARD", Status.NOT_RUN, str(period), None, None,
                                        f"the cash roll-forward cannot be checked in {period}: opening cash "
                                        "plus the month's change overflows"))
            else:
                observed = float(closing)
                if abs(observed - expected) > _TOLERANCE:
                    findings.append(Finding("FR-CASH-ROLLFORWARD", Status.FAIL, str(period), observed, expected,
                                            f"closing cash is {observed:,.2f} in {period}; opening cash plus the "
                                            f"month's change gives {expected:,.2f}"))
            previous = float(closing) if _finite(closing) else None

    return ForecastReview(tuple(findings))
