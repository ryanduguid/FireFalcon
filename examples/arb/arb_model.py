"""Assemble ARB Corporation models from the committed Appendix 4E extracts.

Importable by both ``run_arb.py`` and the reconciliation tests so the pipeline
and the regression guards share one code path. Every Phase A driver comes from
``data/*.csv``. Channel EBITDA is allocated from consolidated EBIT + D&A
because ARB does not disclose it.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from pyfpa.analysis.reconcile import reconcile
from pyfpa.analysis.segments import Segment, roll_up_segments, segments_to_channels
from pyfpa.config.schemas import EntityConfig, OpeningBalances, OpexLine, WorkingCapitalConfig
from pyfpa.memory.experiments import ExperimentCheck
from pyfpa.models.cashflow import cashflow_from_config
from pyfpa.models.cogs import cogs_from_config
from pyfpa.models.revenue import revenue_from_config
from pyfpa.models.working_capital import working_capital_from_config
from pyfpa.research.epochs import ResearchEpoch, evaluate_challenger
from pyfpa.research.objective import MetricObjective, ResearchObjective

DATA = Path(__file__).parent / "data"
SEGMENT_NAMES = ("Australian Aftermarket", "Exports", "Original Equipment")
_DAYS_PER_YEAR = 360.0
FY25_COGS_PCT = 315_721_000.0 / 729_949_000.0

HOLDOUT_OBJECTIVE = ResearchObjective(
    metrics=[
        MetricObjective(name="revenue_error", weight=0.40),
        MetricObjective(name="gross_profit_error", weight=0.30),
        MetricObjective(name="ebitda_error", weight=0.30),
    ],
    hard_checks=["holdout separation", "channel rollup"],
    min_improvement=0.02,
    complexity_penalty=0.01,
    max_metric_regression=0.50,
)

# August 2025 view from the FY2025 4E. Not a 2026 refresh.
FORECAST = {
    "FY2026": {
        "start_month": "2025-07",
        "growth": {
            "Australian Aftermarket": 0.02,
            "Exports": 0.10,
            "Original Equipment": 0.02,
        },
        "margin": 0.225,
        "cogs_pct": FY25_COGS_PCT,
        "da": 34_000_000.0,
        "capex": 25_000_000.0,
        "tax_rate": 0.30,
    },
    "FY2027": {
        "start_month": "2026-07",
        "growth": {
            "Australian Aftermarket": 0.03,
            "Exports": 0.08,
            "Original Equipment": 0.04,
        },
        "margin": 0.228,
        "cogs_pct": 0.430,
        "da": 33_000_000.0,
        "capex": 28_000_000.0,
        "tax_rate": 0.30,
    },
}


def income_statement() -> pd.DataFrame:
    return pd.read_csv(DATA / "income_statement.csv").set_index("line")


def balance_sheet() -> pd.DataFrame:
    return pd.read_csv(DATA / "balance_sheet.csv").set_index("line")


def cash_flow() -> pd.DataFrame:
    return pd.read_csv(DATA / "cash_flow.csv").set_index("line")


def segment_table() -> pd.DataFrame:
    return pd.read_csv(DATA / "segments.csv")


def ebitda_actual(fy: str) -> float:
    inc, cf = income_statement(), cash_flow()
    return float(inc.loc["ebit", fy]) + float(cf.loc["depreciation_amortization", fy])


def segments_for_year(fy: str) -> list[Segment]:
    df = segment_table()
    sales = {
        name: float(df[(df.segment == name) & (df.metric == "net_sales")][fy].iloc[0])
        for name in SEGMENT_NAMES
    }
    margin = ebitda_actual(fy) / sum(sales.values())
    return [
        Segment(name=name, net_sales=sales[name], ebitda_margin=margin)
        for name in SEGMENT_NAMES
    ]


def wc_days(fy: str) -> WorkingCapitalConfig:
    inc, bs = income_statement(), balance_sheet()
    revenue = float(inc.loc["net_sales", fy])
    cogs = float(inc.loc["cost_of_sales", fy])
    return WorkingCapitalConfig(
        dso_days=float(bs.loc["accounts_receivable", fy]) / revenue * _DAYS_PER_YEAR,
        dio_days=float(bs.loc["inventory", fy]) / cogs * _DAYS_PER_YEAR,
        dpo_days=float(bs.loc["accounts_payable", fy]) / cogs * _DAYS_PER_YEAR,
    )


def opening_balances(prior_fy: str) -> OpeningBalances:
    bs = balance_sheet()
    return OpeningBalances(
        cash=float(bs.loc["cash", prior_fy]),
        ar=float(bs.loc["accounts_receivable", prior_fy]),
        ap=float(bs.loc["accounts_payable", prior_fy]),
        inventory=float(bs.loc["inventory", prior_fy]),
    )


def _start_month(fy: str) -> str:
    year = int(fy[-4:])
    return f"{year - 1}-07"


def reconciliation_config(fy: str, prior_fy: str) -> EntityConfig:
    inc, cf = income_statement(), cash_flow()
    revenue = float(inc.loc["net_sales", fy])
    cogs = float(inc.loc["cost_of_sales", fy])
    gross_profit = float(inc.loc["gross_profit", fy])
    ebitda = ebitda_actual(fy)
    segments = segments_for_year(fy)
    return EntityConfig(
        name=f"ARB Corporation {fy} (operating)",
        start_month=_start_month(fy),
        horizon_months=12,
        tax_rate=0.0,
        channels=segments_to_channels(segments, cogs_pct=cogs / revenue),
        opex=[
            OpexLine(
                name="operating_opex",
                kind="fixed",
                monthly_amount=(gross_profit - ebitda) / 12,
            )
        ],
        working_capital=wc_days(fy),
        opening_balances=opening_balances(prior_fy),
        da_monthly=float(cf.loc["depreciation_amortization", fy]) / 12,
        capex_monthly=float(cf.loc["capex", fy]) / 12,
    )


def phase_a_model(fy: str, prior_fy: str) -> dict[str, float]:
    cfg = reconciliation_config(fy, prior_fy)
    annual = cashflow_from_config(cfg).sum()
    segments = segments_for_year(fy)
    return {
        "net_sales": float(annual["revenue"]),
        "gross_profit": float(annual["gross_profit"]),
        "ebitda": float(roll_up_segments(segments)["adjusted_ebitda"]),
        "depreciation_amortization": float(annual["da"]),
        "capex": float(annual["capex"]),
        "operating_cash_flow_before_tax": float(annual["ebitda"] + annual["wc_cash_impact"]),
    }


def phase_a_actual(fy: str, prior_fy: str) -> dict[str, float]:
    inc, cf, bs = income_statement(), cash_flow(), balance_sheet()
    d_ar = float(bs.loc["accounts_receivable", fy]) - float(bs.loc["accounts_receivable", prior_fy])
    d_inv = float(bs.loc["inventory", fy]) - float(bs.loc["inventory", prior_fy])
    d_ap = float(bs.loc["accounts_payable", fy]) - float(bs.loc["accounts_payable", prior_fy])
    ebitda = ebitda_actual(fy)
    return {
        "net_sales": float(inc.loc["net_sales", fy]),
        "gross_profit": float(inc.loc["gross_profit", fy]),
        "ebitda": ebitda,
        "depreciation_amortization": float(cf.loc["depreciation_amortization", fy]),
        "capex": float(cf.loc["capex", fy]),
        "operating_cash_flow_before_tax": ebitda + (-d_ar - d_inv + d_ap),
    }


def historical_candidate(
    *,
    export_growth: float,
    other_growth: float,
    margin_delta: float,
) -> tuple[EntityConfig, list[Segment]]:
    """Predict FY2025 using only FY2024 information plus an explicit hypothesis."""
    base = {segment.name: segment for segment in segments_for_year("FY2024")}
    margin = base["Exports"].ebitda_margin + margin_delta
    segments = [
        Segment(
            name=name,
            net_sales=base[name].net_sales
            * (1 + (export_growth if name == "Exports" else other_growth)),
            ebitda_margin=margin,
        )
        for name in SEGMENT_NAMES
    ]
    inc, cf = income_statement(), cash_flow()
    revenue = sum(segment.net_sales for segment in segments)
    cogs_pct = float(inc.loc["cost_of_sales", "FY2024"]) / float(inc.loc["net_sales", "FY2024"])
    gross_profit = revenue * (1 - cogs_pct)
    ebitda = float(roll_up_segments(segments)["adjusted_ebitda"])
    cfg = EntityConfig(
        name=(
            "ARB FY2025 holdout "
            f"(export {export_growth:.1%} / other {other_growth:.1%} / "
            f"margin {margin_delta:+.1%})"
        ),
        start_month="2024-07",
        horizon_months=12,
        tax_rate=0.0,
        channels=segments_to_channels(segments, cogs_pct=cogs_pct),
        opex=[
            OpexLine(
                name="operating_opex",
                kind="fixed",
                monthly_amount=(gross_profit - ebitda) / 12,
            )
        ],
        working_capital=wc_days("FY2024"),
        opening_balances=opening_balances("FY2024"),
        da_monthly=float(cf.loc["depreciation_amortization", "FY2024"]) / 12,
        capex_monthly=float(cf.loc["capex", "FY2024"]) / 12,
    )
    return cfg, segments


def _abs_variance_pct(predicted: float, actual: float) -> float:
    if actual == 0:
        raise ValueError("holdout metric actual must be non-zero")
    row = reconcile({"v": predicted}, {"v": actual}).iloc[0]
    return abs(float(row["variance_pct"]))


def holdout_metrics(
    *,
    export_growth: float,
    other_growth: float,
    margin_delta: float,
) -> dict[str, float]:
    cfg, segments = historical_candidate(
        export_growth=export_growth,
        other_growth=other_growth,
        margin_delta=margin_delta,
    )
    annual = cashflow_from_config(cfg).sum()
    inc = income_statement()
    return {
        "revenue_error": _abs_variance_pct(
            float(annual["revenue"]), float(inc.loc["net_sales", "FY2025"])
        ),
        "gross_profit_error": _abs_variance_pct(
            float(annual["gross_profit"]), float(inc.loc["gross_profit", "FY2025"])
        ),
        "ebitda_error": _abs_variance_pct(
            float(roll_up_segments(segments)["adjusted_ebitda"]),
            ebitda_actual("FY2025"),
        ),
    }


def _historical_epoch(
    *,
    epoch_id: str,
    challenger_id: str,
    hypothesis: str,
    export_growth: float,
    other_growth: float,
    margin_delta: float,
) -> ResearchEpoch:
    champion = holdout_metrics(export_growth=0.0, other_growth=0.0, margin_delta=0.0)
    challenger = holdout_metrics(
        export_growth=export_growth,
        other_growth=other_growth,
        margin_delta=margin_delta,
    )
    checks = [
        ExperimentCheck(
            name="holdout separation",
            result="pass",
            details="Candidate uses FY2024 only; FY2025 is held out.",
        ),
        ExperimentCheck(
            name="channel rollup",
            result="pass",
            details="Australian Aftermarket, Exports, and OEM sales roll to consolidated.",
        ),
    ]
    evaluation = evaluate_challenger(
        HOLDOUT_OBJECTIVE,
        champion,
        challenger,
        checks,
        champion_complexity=1.0,
        challenger_complexity=1.1,
    )
    status = "proposed" if evaluation.promotion_eligible else "discarded"
    return ResearchEpoch(
        epoch_id=epoch_id,
        created="2026-08-20",
        status=status,
        hypothesis=hypothesis,
        champion_id="arb-flat-fy2024-run-rate",
        challenger_id=challenger_id,
        memory_sources=[
            ".fpa/business-profile.md",
            "data/segments.csv",
            "data/income_statement.csv",
            "data/balance_sheet.csv",
            "data/cash_flow.csv",
        ],
        files_changed=["arb_model.py"],
        training_periods=["FY2024"],
        holdout_periods=["FY2025"],
        checks=checks,
        evaluation=evaluation,
        notes=(
            "Working-capital days are reproduced in Phase A but not used as a "
            "holdout metric: FY2025 AR barely moved while sales grew, and H2 "
            "destocking is a management action, not a stable sales function."
        ),
    )


def historical_research_epochs() -> list[ResearchEpoch]:
    uniform = _historical_epoch(
        epoch_id="arb-fy2025-001-uniform-export-rate",
        challenger_id="arb-uniform-16pct",
        hypothesis=(
            "Apply the 16.4 percent export growth rate to every sales channel "
            "and hold FY2024 EBITDA margin."
        ),
        export_growth=0.164,
        other_growth=0.164,
        margin_delta=0.0,
    )
    export_led = _historical_epoch(
        epoch_id="arb-fy2025-002-export-led-margin-pressure",
        challenger_id="arb-export-led-150bps",
        hypothesis=(
            "Exports grow 16.4 percent, Australian aftermarket and OEM stay "
            "flat, and EBITDA margin compresses 150bps on THB and tariff cost "
            "pressure known as a 2025 risk."
        ),
        export_growth=0.164,
        other_growth=0.0,
        margin_delta=-0.015,
    )
    return [uniform, export_led]


def _grow(segments: list[Segment], growth: dict, margin: float) -> list[Segment]:
    return [
        Segment(
            name=segment.name,
            net_sales=segment.net_sales * (1 + growth[segment.name]),
            ebitda_margin=margin,
        )
        for segment in segments
    ]


def forecast_year(
    base: list[Segment],
    fy: str,
    opening: OpeningBalances,
    *,
    cogs_pct: float | None = None,
    opex_annual: float | None = None,
) -> tuple[pd.DataFrame, list[Segment], OpeningBalances]:
    assumptions = FORECAST[fy]
    segs = _grow(base, assumptions["growth"], assumptions["margin"])
    revenue = sum(segment.net_sales for segment in segs)
    pct = assumptions["cogs_pct"] if cogs_pct is None else cogs_pct
    gross_profit = revenue * (1 - pct)
    ebitda = float(roll_up_segments(segs)["adjusted_ebitda"])
    opex_amount = (gross_profit - ebitda) if opex_annual is None else opex_annual
    cfg = EntityConfig(
        name=f"ARB Corporation {fy} (forecast)",
        start_month=assumptions["start_month"],
        horizon_months=12,
        tax_rate=assumptions["tax_rate"],
        channels=segments_to_channels(segs, cogs_pct=pct),
        opex=[
            OpexLine(
                name="operating_opex",
                kind="fixed",
                monthly_amount=opex_amount / 12,
            )
        ],
        working_capital=wc_days("FY2025"),
        opening_balances=opening,
        da_monthly=assumptions["da"] / 12,
        capex_monthly=assumptions["capex"] / 12,
    )
    frame = cashflow_from_config(cfg)
    revenue_frame = revenue_from_config(cfg)
    cogs_frame = cogs_from_config(cfg, revenue_frame)
    wc_frame = working_capital_from_config(cfg, revenue_frame, cogs_frame)
    closing = OpeningBalances(
        cash=float(frame["ending_cash"].iloc[-1]),
        ar=float(wc_frame["ar"].iloc[-1]),
        ap=float(wc_frame["ap"].iloc[-1]),
        inventory=float(wc_frame["inventory"].iloc[-1]),
    )
    return frame, segs, closing


def build_forecast() -> tuple[pd.DataFrame, dict[str, list[Segment]]]:
    base = segments_for_year("FY2025")
    f26, segs26, open27 = forecast_year(base, "FY2026", opening_balances("FY2025"))
    f27, segs27, _ = forecast_year(segs26, "FY2027", open27)
    return pd.concat([f26, f27]), {"FY2026": segs26, "FY2027": segs27}


def cost_pressure_sensitivity() -> pd.DataFrame:
    """Labeled THB / US-tariff sensitivity. Not a kernel FX engine.

    Holds FY2026 operating opex in dollars so extra materials cost hits EBITDA
    instead of being absorbed by the GP-minus-EBITDA opex identity.
    """
    opening = opening_balances("FY2025")
    base_frame, _, _ = forecast_year(
        segments_for_year("FY2025"), "FY2026", opening
    )
    opex_annual = float(base_frame["opex"].sum())
    stressed_frame, _, _ = forecast_year(
        segments_for_year("FY2025"),
        "FY2026",
        opening,
        cogs_pct=FY25_COGS_PCT + 0.015,
        opex_annual=opex_annual,
    )
    return pd.DataFrame(
        [
            {
                "scenario": "Base",
                "fy2026_ebitda": float(base_frame["ebitda"].sum()),
                "fy2026_fcf": float(base_frame["free_cash_flow"].sum()),
            },
            {
                "scenario": "THB/tariff +150bps COGS",
                "fy2026_ebitda": float(stressed_frame["ebitda"].sum()),
                "fy2026_fcf": float(stressed_frame["free_cash_flow"].sum()),
            },
        ]
    ).set_index("scenario")
