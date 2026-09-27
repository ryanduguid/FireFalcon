"""Australian day-first text used to be read month first by pandas."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pyfpa.au.calendar import format_au_date
from pyfpa.au.gst import gst_weekly_flows
from pyfpa.au.payroll import Role
from pyfpa.au.rates import load_super_guarantee_table, rate_at

DAY_FIRST = ["1/10/2026", "01/07/2026", "1/7/2025", "10/2026"]


@pytest.mark.parametrize("text", DAY_FIRST)
def test_day_first_text_is_refused_everywhere(text: str) -> None:
    with pytest.raises(ValueError, match="ISO date"):
        format_au_date(text)
    with pytest.raises(ValueError, match="ISO date"):
        rate_at(load_super_guarantee_table(), text)
    with pytest.raises(ValueError, match="ISO date"):
        gst_weekly_flows(pd.DataFrame(), text)
    with pytest.raises(ValueError, match="ISO date"):
        Role(name="Analyst", annual_salary=90000.0, start_month=text)


def test_iso_inputs_read_as_before() -> None:
    assert format_au_date("2026-07-01") == "01/07/2026"
    assert format_au_date(pd.Timestamp(2026, 7, 1)) == "01/07/2026"
    table = load_super_guarantee_table()
    assert rate_at(table, "2025-07-01") == rate_at(table, date(2025, 7, 1)) == rate_at(table, "2025-07")
    assert Role(name="Analyst", annual_salary=90000.0, start_month="2026-10").start_month == "2026-10"
