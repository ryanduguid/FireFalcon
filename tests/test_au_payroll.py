import pandas as pd
import pytest

from pyfpa.au.calendar import fy_month_range
from pyfpa.au.payroll import PayrollAssumptions, Role, payroll_forecast


@pytest.fixture
def months():
    return fy_month_range(2027)  # 2026-07 .. 2027-06


def test_single_role_gross_and_super(months):
    roles = [Role(name="Engineer", annual_salary=120000, jurisdiction="NSW")]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame.loc[months[0], "gross_wages"] == pytest.approx(10000.0)
    # SG 12% from 1 July 2025
    assert frame.loc[months[0], "super_guarantee"] == pytest.approx(1200.0)


def test_contractor_gets_no_super_or_leave(months):
    roles = [Role(name="Contractor", annual_salary=120000, contractor=True)]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame["super_guarantee"].sum() == 0.0
    assert frame["leave_provisions"].sum() == 0.0
    assert frame.loc[months[0], "gross_wages"] == pytest.approx(10000.0)


def test_start_month_vacancy(months):
    roles = [
        Role(name="Hire", annual_salary=120000, start_month="2027-01"),
    ]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame.loc[pd.Period("2026-12", freq="M"), "gross_wages"] == 0.0
    assert frame.loc[pd.Period("2027-01", freq="M"), "gross_wages"] == pytest.approx(10000.0)


def test_end_month_departure(months):
    roles = [Role(name="Leaver", annual_salary=120000, end_month="2026-09")]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame.loc[pd.Period("2026-09", freq="M"), "gross_wages"] == pytest.approx(10000.0)
    assert frame.loc[pd.Period("2026-10", freq="M"), "gross_wages"] == 0.0


def test_below_threshold_pays_no_payroll_tax(months):
    # One modest salary sits under every jurisdiction's monthly threshold slice.
    roles = [Role(name="Solo", annual_salary=60000, jurisdiction="QLD")]
    frame = payroll_forecast(roles, months)
    assert frame["payroll_tax"].sum() == 0.0


def test_above_threshold_pays_payroll_tax(months):
    # 40 x 150k in NSW: ~6.17m taxable wages incl super, well above threshold.
    roles = [
        Role(name=f"Role {i}", annual_salary=150000, jurisdiction="NSW") for i in range(40)
    ]
    frame = payroll_forecast(roles, months)
    assert frame["payroll_tax"].sum() > 0.0


def test_unregistered_entity_pays_no_payroll_tax(months):
    roles = [
        Role(name=f"Role {i}", annual_salary=150000, jurisdiction="NSW") for i in range(40)
    ]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    assert frame["payroll_tax"].sum() == 0.0


def test_total_cash_excludes_leave_provisions(months):
    roles = [Role(name="Engineer", annual_salary=120000)]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    first = months[0]
    assert frame.loc[first, "total_cost"] - frame.loc[first, "total_cash"] == pytest.approx(
        frame.loc[first, "leave_provisions"]
    )
    assert frame.loc[first, "leave_provisions"] > 0


def test_bonus_attracts_super(months):
    base = [Role(name="NoBonus", annual_salary=120000)]
    bonused = [Role(name="Bonus", annual_salary=120000, bonus_pct=0.10)]
    plain = payroll_forecast(base, months, PayrollAssumptions(payroll_tax_registered=False))
    with_bonus = payroll_forecast(
        bonused, months, PayrollAssumptions(payroll_tax_registered=False)
    )
    assert with_bonus.loc[months[0], "bonuses"] == pytest.approx(1000.0)
    assert (
        with_bonus.loc[months[0], "super_guarantee"]
        > plain.loc[months[0], "super_guarantee"]
    )


def test_sg_rate_change_at_fy_boundary():
    # FY2025 spans the 11.5% -> 12% step on 1 July 2025.
    months = pd.period_range("2025-06", periods=2, freq="M")
    roles = [Role(name="Engineer", annual_salary=120000)]
    frame = payroll_forecast(roles, months, PayrollAssumptions(payroll_tax_registered=False))
    june = frame.loc[pd.Period("2025-06", freq="M"), "super_guarantee"]
    july = frame.loc[pd.Period("2025-07", freq="M"), "super_guarantee"]
    assert june == pytest.approx(10000 * 0.115)
    assert july == pytest.approx(10000 * 0.12)
