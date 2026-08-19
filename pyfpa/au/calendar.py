"""Australian fiscal calendar helpers.

Australian financial years run 1 July to 30 June and are labelled by the
ending year: FY2027 covers July 2026 to June 2027. Quarters follow the
fiscal year (Q1 FY2027 = Jul-Sep 2026); halves are 1H (Jul-Dec) and
2H (Jan-Jun). Dates render dd/mm/yyyy.

All helpers accept a ``pandas.Period`` (freq M) or a ``YYYY-MM`` string,
matching the kernel's monthly convention in ``pyfpa.models.periods``.
"""

from __future__ import annotations

import pandas as pd


def _as_period(period: str | pd.Period) -> pd.Period:
    if isinstance(period, pd.Period):
        if period.freq != pd.tseries.offsets.MonthEnd():
            return period.asfreq("M")
        return period
    return pd.Period(period, freq="M")


def fy_year(period: str | pd.Period) -> int:
    """Financial year (labelled by ending year) containing `period`.

    July 2026 -> 2027; June 2026 -> 2026.
    """
    p = _as_period(period)
    return p.year + 1 if p.month >= 7 else p.year


def fy_label(period: str | pd.Period) -> str:
    """'FY2027' for any month in July 2026 - June 2027."""
    return f"FY{fy_year(period)}"


def fy_quarter_label(period: str | pd.Period) -> str:
    """'Q1 FY2027' for Jul-Sep 2026, through 'Q4 FY2027' for Apr-Jun 2027."""
    p = _as_period(period)
    quarter = ((p.month - 7) % 12) // 3 + 1
    return f"Q{quarter} {fy_label(p)}"


def fy_half_label(period: str | pd.Period) -> str:
    """'1H FY2027' for Jul-Dec 2026, '2H FY2027' for Jan-Jun 2027."""
    p = _as_period(period)
    half = 1 if p.month >= 7 else 2
    return f"{half}H {fy_label(p)}"


def fy_month_range(fy: int) -> pd.PeriodIndex:
    """Monthly PeriodIndex for the financial year ending 30 June `fy`.

    fy_month_range(2027) -> 2026-07 .. 2027-06.
    """
    return pd.period_range(start=pd.Period(f"{fy - 1}-07", freq="M"), periods=12, freq="M")


def format_au_date(value: pd.Timestamp | str) -> str:
    """Render a date as dd/mm/yyyy."""
    return pd.Timestamp(value).strftime("%d/%m/%Y")


def fy_summary(frame: pd.DataFrame, by: str = "fy") -> pd.DataFrame:
    """Sum a monthly frame (PeriodIndex rows) into FY, FY-quarter or FY-half rows.

    `by` is one of 'fy', 'quarter', 'half'. Row order follows the calendar.
    """
    if by == "fy":
        keys = [fy_label(p) for p in frame.index]
    elif by == "quarter":
        keys = [fy_quarter_label(p) for p in frame.index]
    elif by == "half":
        keys = [fy_half_label(p) for p in frame.index]
    else:
        raise ValueError(f"by must be 'fy', 'quarter' or 'half', got {by!r}")
    grouped = frame.groupby(keys, sort=False).sum()
    grouped.index.name = by
    return grouped
