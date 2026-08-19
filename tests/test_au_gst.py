from datetime import date

import pandas as pd
import pytest

from pyfpa.au.calendar import fy_month_range
from pyfpa.au.gst import BasCycle, GstAssumptions, bas_schedule, gst_weekly_flows, monthly_gst


@pytest.fixture
def months():
    return fy_month_range(2027)  # 2026-07 .. 2027-06


@pytest.fixture
def net_gst(months):
    revenue = pd.Series(100000.0, index=months)
    purchases = pd.Series(40000.0, index=months)
    return monthly_gst(revenue, purchases)


def test_monthly_gst_computes_net(months):
    revenue = pd.Series(100000.0, index=months)
    purchases = pd.Series(40000.0, index=months)
    frame = monthly_gst(revenue, purchases)
    assert frame.loc[months[0], "output_gst"] == pytest.approx(10000.0)
    assert frame.loc[months[0], "input_gst"] == pytest.approx(4000.0)
    assert frame.loc[months[0], "net_gst"] == pytest.approx(6000.0)


def test_gst_free_revenue_share_reduces_output_gst(months):
    revenue = pd.Series(100000.0, index=months)
    purchases = pd.Series(0.0, index=months)
    frame = monthly_gst(revenue, purchases, GstAssumptions(taxable_sales_pct=0.6))
    assert frame.loc[months[0], "output_gst"] == pytest.approx(6000.0)


def test_mismatched_indexes_rejected(months):
    revenue = pd.Series(100000.0, index=months)
    purchases = pd.Series(40000.0, index=months[:6])
    with pytest.raises(ValueError, match="same monthly index"):
        monthly_gst(revenue, purchases)


def test_quarterly_bas_schedule_dates(net_gst):
    schedule = bas_schedule(net_gst["net_gst"], GstAssumptions(bas_cycle=BasCycle.QUARTERLY))
    assert len(schedule) == 4
    assert schedule["due_date"].tolist() == [
        date(2026, 10, 28),  # Sep quarter
        date(2027, 2, 28),   # Dec quarter
        date(2027, 4, 28),   # Mar quarter
        date(2027, 7, 28),   # Jun quarter
    ]
    assert schedule["amount"].tolist() == pytest.approx([18000.0] * 4)


def test_partial_quarter_excluded(months):
    # 8 months: Jul-Feb = Sep + Dec quarters complete, Mar quarter partial.
    partial = pd.Series(6000.0, index=months[:8])
    schedule = bas_schedule(partial, GstAssumptions(bas_cycle=BasCycle.QUARTERLY))
    assert len(schedule) == 2


def test_monthly_bas_schedule_dates(net_gst):
    schedule = bas_schedule(net_gst["net_gst"], GstAssumptions(bas_cycle=BasCycle.MONTHLY))
    assert len(schedule) == 12
    assert schedule["due_date"].iloc[0] == date(2026, 8, 21)
    assert schedule["due_date"].iloc[-1] == date(2027, 7, 21)


def test_refund_position_flows_back(months):
    revenue = pd.Series(10000.0, index=months)
    purchases = pd.Series(90000.0, index=months)  # heavy capex period
    frame = monthly_gst(revenue, purchases)
    schedule = bas_schedule(frame["net_gst"], GstAssumptions(bas_cycle=BasCycle.QUARTERLY))
    assert (schedule["amount"] < 0).all()
    receipts, disbursements = gst_weekly_flows(schedule, window_start=date(2026, 10, 1))
    assert disbursements == []
    assert len(receipts) == 1  # only the Sep-quarter refund lands in 13 weeks
    assert receipts[0].amount > 0


def test_gst_weekly_flows_maps_due_dates_to_weeks(net_gst):
    schedule = bas_schedule(net_gst["net_gst"], GstAssumptions(bas_cycle=BasCycle.QUARTERLY))
    receipts, disbursements = gst_weekly_flows(schedule, window_start=date(2026, 10, 1))
    assert receipts == []
    assert len(disbursements) == 1
    flow = disbursements[0]
    # 28 Oct is 27 days after 1 Oct -> week 4.
    assert flow.start_week == 4
    assert flow.amount == pytest.approx(18000.0)
    assert flow.recurrence == "once"


def test_gst_weekly_flows_drops_out_of_window(net_gst):
    schedule = bas_schedule(net_gst["net_gst"], GstAssumptions(bas_cycle=BasCycle.QUARTERLY))
    receipts, disbursements = gst_weekly_flows(
        schedule, window_start=date(2026, 8, 1), weeks=4
    )
    assert receipts == [] and disbursements == []
