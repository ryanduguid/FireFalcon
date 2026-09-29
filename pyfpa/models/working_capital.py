from __future__ import annotations

import pandas as pd

from pyfpa.config.schemas import EntityConfig

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


def working_capital_from_config(
    cfg: EntityConfig, revenue_df: pd.DataFrame, cogs_df: pd.DataFrame
) -> pd.DataFrame:
    """AR/AP/inventory balances and their cash impact (rising AR/inventory uses
    cash; rising AP frees cash). First-period delta is versus opening balances.

    Opening balances are assumed to sit at the modelled steady state. If a
    supplied opening balance diverges from the day-count-implied balance, the
    full gap flows through month 1 as a one-time working-capital cash impact.

    Raises ValueError when the balances imply negative customer receipts,
    purchases or supplier payments in any month, naming the first such month
    and flow.
    """
    idx = revenue_df.index
    wc = cfg.working_capital
    opening = cfg.opening_balances

    ar = revenue_df["total"] * (wc.dso_days / _DAYS_PER_MONTH)
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
