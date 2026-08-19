import pandas as pd
import pytest

from pyfpa.au.calendar import (
    format_au_date,
    fy_half_label,
    fy_label,
    fy_month_range,
    fy_quarter_label,
    fy_summary,
    fy_year,
)


def test_fy_year_boundary():
    assert fy_year("2026-06") == 2026
    assert fy_year("2026-07") == 2027
    assert fy_year(pd.Period("2025-12", freq="M")) == 2026


def test_fy_label():
    assert fy_label("2026-07") == "FY2027"
    assert fy_label("2027-06") == "FY2027"


def test_fy_quarter_labels_track_july_start():
    assert fy_quarter_label("2026-07") == "Q1 FY2027"
    assert fy_quarter_label("2026-09") == "Q1 FY2027"
    assert fy_quarter_label("2026-10") == "Q2 FY2027"
    assert fy_quarter_label("2027-01") == "Q3 FY2027"
    assert fy_quarter_label("2027-04") == "Q4 FY2027"
    assert fy_quarter_label("2027-06") == "Q4 FY2027"


def test_fy_half_labels():
    assert fy_half_label("2026-07") == "1H FY2027"
    assert fy_half_label("2026-12") == "1H FY2027"
    assert fy_half_label("2027-01") == "2H FY2027"
    assert fy_half_label("2027-06") == "2H FY2027"


def test_fy_month_range_covers_july_to_june():
    months = fy_month_range(2027)
    assert len(months) == 12
    assert str(months[0]) == "2026-07"
    assert str(months[-1]) == "2027-06"


def test_format_au_date_dd_mm_yyyy():
    assert format_au_date("2026-07-01") == "01/07/2026"


def test_fy_summary_groups_quarters_in_calendar_order():
    months = fy_month_range(2027)
    frame = pd.DataFrame({"revenue": [100.0] * 12}, index=months)
    quarters = fy_summary(frame, by="quarter")
    assert list(quarters.index) == [
        "Q1 FY2027",
        "Q2 FY2027",
        "Q3 FY2027",
        "Q4 FY2027",
    ]
    assert quarters["revenue"].tolist() == [300.0, 300.0, 300.0, 300.0]


def test_fy_summary_rejects_unknown_grouping():
    months = fy_month_range(2027)
    frame = pd.DataFrame({"x": [1.0] * 12}, index=months)
    with pytest.raises(ValueError, match="by must be"):
        fy_summary(frame, by="week")
