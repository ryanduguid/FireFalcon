"""The close handoff must tie to the forecast's exact source balances."""
import csv
import hashlib
import json
import runpy
import shutil
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "examples/lumbridge-services"
HANDOFF = runpy.run_path(str(ROOT / "models/generated/close_handoff.py"))["handoff"]


def test_balances_and_identity_survive_the_handoff(tmp_path):
    output = tmp_path / "handoff"
    result = HANDOFF(output)
    assert result["opening_receivables"] == str((40000 + 4000) + (20000 + 2000))
    for name in ("prior", "current"):
        with (output / f"{name}.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert sum(Decimal(row["Debit"]) - Decimal(row["Credit"]) for row in rows) == 0
        assert sum(Decimal(row["YTDDebit"]) - Decimal(row["YTDCredit"]) for row in rows) == 0
        assert {row["Tenant"] for row in rows} == {"Lumbridge Services"}
        assert next(row for row in rows if row["AccountID"] == "BS-090")["AccountCode"] == "090"
    assert json.loads((output / "handoff.json").read_text())["source_sha256"] == result["source_sha256"]
    assert result["opening_payables"] == "-13200.00"
    assert [item["unpaid"] for item in result["payable_items"]] == ["5500.00", "7700.00"]
    assert result["source_sha256"]["opening-payable-items.csv"] == hashlib.sha256((ROOT / "data/opening-payable-items.csv").read_bytes()).hexdigest()
    with (output / "subledger.csv").open(newline="") as stream:
        subledger = list(csv.DictReader(stream))
    assert subledger[1]["SubledgerBalance"] == "-13200.00"
    with pytest.raises(FileExistsError):
        HANDOFF(output)


def test_changed_invoice_is_not_silently_used(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    path = data / "invoices.csv"
    path.write_text(path.read_text().replace("40000,4000", "40001,4000", 1))
    output = tmp_path / "handoff"
    with pytest.raises(ValueError, match="does not tie"):
        HANDOFF(output, data)
    assert not output.exists()


def _payable_fixture(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    path = data / "opening-payable-items.csv"
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns, rows = reader.fieldnames, list(reader)
    return data, path, columns, rows


def _write_items(path, columns, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("kind", ["bill", "credit", "settlement"])
def test_one_cent_item_change_breaks_the_independent_tie(tmp_path, kind):
    data, path, columns, rows = _payable_fixture(tmp_path)
    row = next(row for row in rows if row["Kind"] == kind)
    row["Amount"] = str(Decimal(row["Amount"]) + Decimal("0.01"))
    _write_items(path, columns, rows)
    with pytest.raises(ValueError, match="do not tie"):
        HANDOFF(tmp_path / "handoff", data)
    assert not (tmp_path / "handoff").exists()


@pytest.mark.parametrize("change", ["duplicate_id", "duplicate_bill", "orphan", "supplier", "tenant",
                                   "currency", "account", "future", "before_bill", "negative",
                                   "nan", "fraction", "oversize", "blank", "kind", "overpaid_offset"])
def test_invalid_or_offsetting_payable_evidence_is_refused_before_output(tmp_path, change):
    data, path, columns, rows = _payable_fixture(tmp_path)
    target = rows[-1]
    if change == "duplicate_id":
        target["ItemID"] = rows[0]["ItemID"]
    elif change == "duplicate_bill":
        rows[1]["BillID"] = rows[0]["BillID"]
    elif change == "orphan":
        target["BillID"] = "absent"
    elif change in {"supplier", "tenant", "currency", "account"}:
        target[{"supplier": "SupplierID", "tenant": "Tenant", "currency": "Currency", "account": "AccountID"}[change]] = "Other"
    elif change == "future":
        target["Date"] = "2026-10-07"
    elif change == "before_bill":
        target["Date"] = "2026-09-01"
    elif change in {"negative", "nan", "fraction", "oversize"}:
        target["Amount"] = {"negative": "-2200", "nan": "NaN", "fraction": "2200.001", "oversize": "1000000000000000"}[change]
    elif change == "blank":
        target["Reference"] = ""
    elif change == "kind":
        target["Kind"] = "assumed"
    else:
        # The total still nets to 13,200; one overpaid bill must not hide in it.
        rows[1]["Amount"] = "14300"
        target["Amount"] = "8800"
    _write_items(path, columns, rows)
    with pytest.raises(ValueError):
        HANDOFF(tmp_path / "handoff", data)
    assert not (tmp_path / "handoff").exists()


def test_low_ambient_decimal_precision_does_not_change_the_opening(tmp_path):
    with localcontext() as context:
        context.prec = 3
        context.Emax = 3
        result = HANDOFF(tmp_path / "handoff")
    assert result["opening_payables"] == "-13200.00"
    assert result["opening_cash"] == "30000"
    assert result["payable_difference"] == "0.00"


def test_forecast_settlement_is_separate_and_output_cannot_enter_source_data(tmp_path):
    data, _, _, _ = _payable_fixture(tmp_path)
    path = data / "payments.csv"
    path.write_text(path.read_text().replace("2026-10-07,Materials,13200", "2026-10-07,Materials,13200.01"))
    with pytest.raises(ValueError, match="does not tie"):
        HANDOFF(tmp_path / "handoff", data)
    with pytest.raises(ValueError, match="outside"):
        HANDOFF(data / "handoff", data)


def test_balance_sheet_target_does_not_supply_the_payable_subledger(tmp_path):
    data, _, _, _ = _payable_fixture(tmp_path)
    path = data / "xero_bs.csv"
    # Keep the TB balanced while changing its payable assertion.
    path.write_text(path.read_text().replace("-13200", "-13201").replace("-57200", "-57199"))
    with pytest.raises(ValueError, match="do not tie"):
        HANDOFF(tmp_path / "handoff", data)


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_date"])
def test_planned_settlement_needs_one_separate_matching_row(tmp_path, change):
    data, _, _, _ = _payable_fixture(tmp_path)
    path = data / "payments.csv"
    content = path.read_text()
    line = "2026-10-07,Materials,13200\n"
    replacement = "" if change == "missing" else line + line if change == "duplicate" else line.replace("10-07", "10-08")
    path.write_text(content.replace(line, replacement))
    with pytest.raises(ValueError, match="does not tie"):
        HANDOFF(tmp_path / "handoff", data)
    assert not (tmp_path / "handoff").exists()


def test_fully_settled_bill_remains_visible(tmp_path):
    data, path, columns, rows = _payable_fixture(tmp_path)
    rows.extend([dict(rows[0], BillID="settled", ItemID="bill-settled", Amount="1000"),
                 dict(rows[-1], BillID="settled", ItemID="payment-settled", Amount="1000")])
    _write_items(path, columns, rows)
    result = HANDOFF(tmp_path / "handoff", data)
    assert result["payable_items"][-1]["unpaid"] == "0.00"
    assert result["opening_payables"] == "-13200.00"


def test_write_failure_removes_only_this_new_incomplete_handoff(tmp_path, monkeypatch):
    original_open = Path.open

    def fail_mapping(path, *args, **kwargs):
        if path.name == "mapping.csv":
            raise OSError("Synthetic write failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_mapping)
    output = tmp_path / "handoff"
    with pytest.raises(OSError, match="Synthetic write failure"):
        HANDOFF(output)
    assert not output.exists()


@pytest.mark.parametrize("change", ["quote", "duplicate_balance", "duplicate_invoice", "duplicate_payment", "short_invoice"])
def test_ambiguous_or_malformed_source_csv_is_refused(tmp_path, change):
    data, path, _, _ = _payable_fixture(tmp_path)
    if change == "quote":
        path.write_bytes(path.read_bytes().rstrip(b"\n").rsplit(b",", 1)[0] + b',"unfinished reference')
    else:
        filename = "xero_bs.csv" if change == "duplicate_balance" else "payments.csv" if change == "duplicate_payment" else "invoices.csv"
        path = data / filename
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        if change == "short_invoice":
            rows[1] = rows[1][:-1]
        else:
            field = "Amount" if change == "duplicate_balance" else "amount" if change == "duplicate_payment" else "net"
            position = rows[0].index(field)
            rows[0].append(field)
            for row in rows[1:]:
                value = row[position]
                row[position] = "NaN"
                row.append(value)
        with path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)
    with pytest.raises(ValueError):
        HANDOFF(tmp_path / "handoff", data)
    assert not (tmp_path / "handoff").exists()
    assert not list(tmp_path.glob(".handoff-*.partial"))


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_valid_quoted_payable_csv_keeps_exact_values(tmp_path, newline):
    data, path, columns, rows = _payable_fixture(tmp_path)
    rows[0]["Reference"] = "Fabricated, supplier bill"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, columns, lineterminator=newline)
        writer.writeheader()
        writer.writerows(rows)
    assert HANDOFF(tmp_path / "handoff", data)["opening_payables"] == "-13200.00"


def test_close_and_cleanup_failures_preserve_error_and_unrelated_files(tmp_path, monkeypatch):
    original_open, original_unlink = Path.open, Path.unlink
    failure = OSError("Synthetic close failure")
    attempted = []

    class FailingClose:
        def __init__(self, path, stream):
            self.path, self.stream = path, stream

        def __enter__(self):
            return self.stream.__enter__()

        def __exit__(self, *args):
            self.stream.__exit__(*args)
            (self.path.parent / "unrelated.txt").write_bytes(b"preserve")
            raise failure

    def open_with_close_failure(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return FailingClose(path, stream) if path.name == "handoff.json" else stream

    def unlink_with_failure(path, *args, **kwargs):
        attempted.append(path.name)
        if path.name == "handoff.json":
            raise PermissionError("Synthetic cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_with_close_failure)
    monkeypatch.setattr(Path, "unlink", unlink_with_failure)
    output = tmp_path / "handoff"
    with pytest.raises(OSError, match="Synthetic close failure") as raised:
        HANDOFF(output)
    assert raised.value is failure
    assert set(attempted) == {"prior.csv", "current.csv", "mapping.csv", "subledger.csv", "handoff.json"}
    assert not output.exists()
    stages = list(tmp_path.glob(".handoff-*.partial"))
    assert len(stages) == 1
    assert {path.name for path in stages[0].iterdir()} == {"handoff.json", "unrelated.txt"}
    assert (stages[0] / "unrelated.txt").read_bytes() == b"preserve"
    assert str(stages[0]) in " ".join(failure.__notes__)
