from __future__ import annotations

import math
from collections.abc import Iterable

import pandas as pd

from pyfpa.config.schemas import EntityConfig
from pyfpa.models.cogs import cogs_from_config
from pyfpa.models.debt import debt_from_config
from pyfpa.models.opex import opex_from_config
from pyfpa.models.revenue import revenue_from_config
from pyfpa.models.working_capital import working_capital_from_config


def _tax_series(pretax: pd.Series, opening_nol: float, tax_rate: float) -> pd.Series:
    """Apply tax_rate to positive pre-tax income after consuming NOL carryforward.

    In-period losses do not generate new NOL for future months; only the
    opening_nol passed in is consumed.
    """
    nol = opening_nol
    out = []
    for value in pretax:
        positive = max(0.0, value)
        used = min(nol, positive)
        nol -= used
        taxable = positive - used
        out.append(taxable * tax_rate)
    return pd.Series(out, index=pretax.index)


def _require_finite_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if frame[column].isna().any() or not all(math.isfinite(value) for value in frame[column]):
            raise ValueError(f"{column} contains non-finite values")


def cashflow_from_config(cfg: EntityConfig) -> pd.DataFrame:
    """Compose the monthly forecast, raising ValueError for non-finite results."""
    # Configs and their weight lists can change after schema validation.
    for channel in cfg.channels:
        if not math.isfinite(sum(channel.seasonality)):
            raise ValueError("seasonality weights must sum to a finite number")
    try:
        revenue = revenue_from_config(cfg)
    except OverflowError as exc:
        raise ValueError("revenue exceeds the supported numeric range") from exc
    cogs = cogs_from_config(cfg, revenue)
    opex = opex_from_config(cfg, revenue)
    wc = working_capital_from_config(cfg, revenue, cogs)
    debt = debt_from_config(cfg)

    n = len(revenue.index)
    da = pd.Series([cfg.da_monthly] * n, index=revenue.index)
    capex = pd.Series([cfg.capex_monthly] * n, index=revenue.index)

    gross_profit = revenue["total"] - cogs["total"]
    ebitda = gross_profit - opex["total"]
    ebit = ebitda - da                 # D&A is a real (non-cash) expense in the P&L...
    interest = debt["interest"]
    pretax = ebit - interest
    tax = _tax_series(pretax, cfg.opening_balances.nol, cfg.tax_rate)
    net_income = pretax - tax

    operating_cash_flow = net_income + da + wc["wc_cash_impact"]  # ...and added back here
    free_cash_flow = operating_cash_flow - capex
    change_in_cash = free_cash_flow - debt["principal"]
    ending_cash = change_in_cash.cumsum() + cfg.opening_balances.cash

    forecast = pd.DataFrame(
        {
            "revenue": revenue["total"],
            "cogs": cogs["total"],
            "gross_profit": gross_profit,
            "opex": opex["total"],
            "ebitda": ebitda,
            "da": da,
            "interest": interest,
            "pretax_income": pretax,
            "tax": tax,
            "net_income": net_income,
            "wc_cash_impact": wc["wc_cash_impact"],
            "operating_cash_flow": operating_cash_flow,
            "capex": capex,
            "principal": debt["principal"],
            "free_cash_flow": free_cash_flow,
            "change_in_cash": change_in_cash,
            "ending_cash": ending_cash,
        },
        index=revenue.index,
    )
    _require_finite_columns(forecast, forecast.columns)
    return forecast


def apply_receipt_delay(
    forecast: pd.DataFrame, month: str, to_month: str, amount: float
) -> pd.DataFrame:
    """Move one named receipt between two months and rebuild the cash rows.

    A receipt that slips is a working-capital timing event: ``wc_cash_impact``
    falls by ``amount`` in ``month`` and rises by ``amount`` in ``to_month``.
    The cash rows derived from it are rebuilt with the definitions above, and
    every P&L line is unchanged. The amount must be finite. A shift within one
    month returns an unchanged, independent copy of the forecast.
    Raise ValueError if a rebuilt cash column contains a non-finite result.
    """
    labels = [str(period) for period in forecast.index]
    if month not in labels:
        raise ValueError(f"month {month} is not a forecast period")
    if to_month not in labels:
        raise ValueError(f"to_month {to_month} is not a forecast period")
    if not math.isfinite(amount):
        raise ValueError("amount must be finite")
    if month == to_month:
        return forecast.copy()

    out = forecast.copy()
    opening_cash = float(out["ending_cash"].iloc[0] - out["change_in_cash"].iloc[0])
    wc = [float(value) for value in out["wc_cash_impact"]]
    for position, label in enumerate(labels):
        if label == month:
            wc[position] -= amount
        elif label == to_month:
            wc[position] += amount
    out["wc_cash_impact"] = pd.Series(wc, index=out.index)
    out["operating_cash_flow"] = out["net_income"] + out["da"] + out["wc_cash_impact"]
    out["free_cash_flow"] = out["operating_cash_flow"] - out["capex"]
    out["change_in_cash"] = out["free_cash_flow"] - out["principal"]
    out["ending_cash"] = out["change_in_cash"].cumsum() + opening_cash
    _require_finite_columns(out, (
        "wc_cash_impact", "operating_cash_flow", "free_cash_flow",
        "change_in_cash", "ending_cash",
    ))
    return out
