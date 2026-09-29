from __future__ import annotations

import numpy as np
import pandas as pd

from pyfpa.config.schemas import EntityConfig, WorkingCapitalConfig

_DAYS_PER_MONTH = 30.0
# Dollars. A derived flow this close below zero is floating-point noise from the
# balance arithmetic, not a real negative receipt or payment.
_NEGATIVE_FLOW_TOLERANCE = 1e-6


def _refuse_impossible_flows(
    revenue: pd.Series, cogs: pd.Series, balances: pd.DataFrame
) -> None:
    """Raise if the balances imply a negative receipt, purchase or payment.

    A days-based balance tracks the month's own flow, so above 30 days a sharp
    rise in revenue or cost of sales, or a sharp fall in cost of sales against
    inventory days, moves the balance by more than the month's flow. Revenue and
    cost of sales are never negative in this kernel, so a negative derived flow
    can only mean the days assumption cannot follow that month.
    """
    flows = pd.DataFrame(
        {
            "customer receipts": revenue - balances["d_ar"],
            "purchases": cogs + balances["d_inventory"],
        },
        index=balances.index,
    )
    flows["supplier payments"] = flows["purchases"] - balances["d_ap"]
    for period, row in flows.iterrows():
        for flow, amount in row.items():
            if amount < -_NEGATIVE_FLOW_TOLERANCE:
                raise ValueError(
                    f"working capital implies negative {flow} of {amount:,.2f} in {period}: "
                    "the days-based balance moved by more than the month's flow"
                )


def _receivables(wc: WorkingCapitalConfig, revenue: pd.Series, opening_ar: float) -> pd.Series:
    """Closing receivables by month, from days of revenue or a collection profile.

    With a profile, receipts are the profile's shares of each month's revenue plus
    the opening profile's shares of the opening balance; shares that fall after the
    last forecast month stay in closing receivables.
    """
    if wc.collection_profile is None:
        if wc.dso_days is None:  # a config built without validation, e.g. model_copy
            raise ValueError("working capital needs dso_days or collection_profile")
        return revenue * (wc.dso_days / _DAYS_PER_MONTH)
    values = revenue.to_numpy(dtype=float)
    receipts = np.zeros(len(values))
    for lag, share in enumerate(wc.collection_profile[: len(values)]):
        receipts[lag:] += share * values[: len(values) - lag]
    for month, share in enumerate((wc.opening_ar_collection_profile or [])[: len(values)]):
        receipts[month] += share * opening_ar
    return opening_ar + (revenue - pd.Series(receipts, index=revenue.index)).cumsum()


def working_capital_from_config(
    cfg: EntityConfig, revenue_df: pd.DataFrame, cogs_df: pd.DataFrame
) -> pd.DataFrame:
    """AR/AP/inventory balances and their cash impact (rising AR/inventory uses
    cash; rising AP frees cash). First-period delta is versus opening balances.

    Receivables follow `dso_days` or, when given, `collection_profile`.
    Opening balances are assumed to sit at the modelled steady state of the days
    models. If a supplied opening balance diverges from the day-count-implied
    balance, the full gap flows through month 1 as a one-time working-capital
    cash impact. Under a collection profile, opening receivables are collected by
    `opening_ar_collection_profile` instead.

    Raises ValueError when the balances imply negative customer receipts,
    purchases or supplier payments in any month, naming the first such month
    and flow.
    """
    idx = revenue_df.index
    wc = cfg.working_capital
    opening = cfg.opening_balances

    ar = _receivables(wc, revenue_df["total"], opening.ar)
    ap = cogs_df["total"] * (wc.dpo_days / _DAYS_PER_MONTH)
    inventory = cogs_df["total"] * (wc.dio_days / _DAYS_PER_MONTH)

    df = pd.DataFrame({"ar": ar, "ap": ap, "inventory": inventory}, index=idx)
    df = df.assign(
        d_ar=df["ar"].diff().fillna(df["ar"] - opening.ar),
        d_ap=df["ap"].diff().fillna(df["ap"] - opening.ap),
        d_inventory=df["inventory"].diff().fillna(df["inventory"] - opening.inventory),
    )
    _refuse_impossible_flows(revenue_df["total"], cogs_df["total"], df)
    return df.assign(
        wc_cash_impact=(-df["d_ar"] + df["d_ap"] - df["d_inventory"])
    )
