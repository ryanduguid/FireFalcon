from datetime import date

import pandas as pd
import pytest

from pyfpa.au.rates import (
    JURISDICTIONS,
    load_gst_bas_data,
    load_payroll_tax_table,
    load_super_guarantee_table,
    payroll_tax_at,
    rate_at,
)


def test_sg_schedule_monotonic_and_current():
    table = load_super_guarantee_table()
    dates = [e.effective_from for e in table]
    assert dates == sorted(dates)
    rates = [e.rate for e in table]
    assert rates == sorted(rates), "SG rates have only ever risen"
    assert rate_at(table, date(2026, 8, 20)) == 0.12


def test_sg_rate_at_boundaries():
    table = load_super_guarantee_table()
    assert rate_at(table, date(2025, 6, 30)) == 0.115
    assert rate_at(table, date(2025, 7, 1)) == 0.12
    assert rate_at(table, "2024-07-01") == 0.115
    assert rate_at(table, pd.Period("2023-07", freq="M")) == 0.11


def test_sg_rate_before_schedule_raises():
    table = load_super_guarantee_table()
    with pytest.raises(ValueError, match="no rate effective"):
        rate_at(table, date(2010, 1, 1))


def test_every_entry_carries_source():
    for entry in load_super_guarantee_table():
        assert entry.source_url.startswith("https://www.ato.gov.au")


def test_payroll_tax_covers_all_jurisdictions():
    table = load_payroll_tax_table()
    covered = {e.jurisdiction for e in table}
    assert covered == set(JURISDICTIONS)
    for entry in table:
        assert 0 < entry.rate < 0.10, f"{entry.jurisdiction} rate implausible"
        assert entry.annual_threshold >= 0
        assert entry.source_url, f"{entry.jurisdiction} missing source"


def test_payroll_tax_lookup_selects_latest_effective():
    table = load_payroll_tax_table()
    entry = payroll_tax_at(table, "nsw", date(2026, 8, 20))
    assert entry.jurisdiction == "NSW"
    assert entry.effective_from <= date(2026, 8, 20)


def test_act_fy2027_change_is_effective_dated():
    # ACT lowered its threshold to $1.75m and moved to tiered rates
    # from 1 July 2026; the FY2026 entry must still resolve for FY2026.
    table = load_payroll_tax_table()
    before = payroll_tax_at(table, "ACT", date(2026, 6, 30))
    after = payroll_tax_at(table, "ACT", date(2026, 7, 1))
    assert before.rate == 0.0685
    assert before.annual_threshold == 2000000
    assert after.rate == 0.0675
    assert after.annual_threshold == 1750000


def test_payroll_tax_unknown_jurisdiction_raises():
    table = load_payroll_tax_table()
    with pytest.raises(ValueError, match="unknown jurisdiction"):
        payroll_tax_at(table, "NZ", date(2026, 1, 1))


def test_gst_bas_data_shape():
    data = load_gst_bas_data()
    assert data["gst_rate"] == 0.10
    assert data["registration_threshold"] == 75000
    assert data["monthly_lodgment_threshold"] == 20000000
    assert set(data["quarterly_due"]) == {"09", "12", "03", "06"}
    assert data["monthly_due_day"] == 21
