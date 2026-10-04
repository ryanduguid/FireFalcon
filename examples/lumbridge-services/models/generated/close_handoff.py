"""Create close-control inputs from the same fabricated forecast opening balances."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import tempfile
from datetime import date
from decimal import Context, Decimal, localcontext
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
HEADER = ["ReportDate", "Tenant", "Section", "AccountID", "AccountName", "AccountCode",
          "Debit", "Credit", "YTDDebit", "YTDCredit"]
# An explicit fabricated prior snapshot, constructed for this worked route.
# It is not an observed August export or an estimate of historical performance.
PRIOR = {"090": "62414.15", "620": "0", "710": "12200", "800": "0",
         "820": "-8400", "826": "-1000", "860": "-20000", "900": "-45214.15"}
PAYABLE_COLUMNS = ("Tenant", "AccountID", "Currency", "SupplierID", "BillID", "ItemID",
                   "Kind", "Date", "Amount", "Reference")


def _amount(value: str) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"-?\d{1,15}(?:\.\d{1,2})?", value):
        raise ValueError("Amounts need finite decimal text below 10^15 with at most two places")
    return Decimal(value)


def _opening_payables(content: bytes) -> tuple[Decimal, list[dict]]:
    rows = _records(content, PAYABLE_COLUMNS, "opening payable")
    # The fixed fixture's money and row bounds keep every total exact at precision 40.
    if not rows or len(rows) > 10000:
        raise ValueError("Supply between one and 10000 opening payable items")
    seen, bills = set(), {}
    for row in rows:
        if set(row) != set(PAYABLE_COLUMNS) or any(not isinstance(v, str) or not v.strip() or any(ord(c) < 32 for c in v) for v in row.values()):
            raise ValueError("Opening payable fields must be non-blank text without controls")
        if (row["Tenant"], row["AccountID"], row["Currency"]) != ("Lumbridge Services", "BS-800", "AUD"):
            raise ValueError("Opening payable identity must match Lumbridge Services, BS-800 and AUD")
        if row["ItemID"] in seen:
            raise ValueError("Duplicate opening payable ItemID")
        seen.add(row["ItemID"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["Date"]) or date.fromisoformat(row["Date"]) > date(2026, 9, 30):
            raise ValueError("Opening payable events must be dated on or before 30 September 2026")
        amount = _amount(row["Amount"])
        if amount <= 0 or row["Kind"] not in {"bill", "credit", "settlement"}:
            raise ValueError("Opening payable events require a supported kind and positive gross amount")
        if row["Kind"] == "bill":
            if row["BillID"] in bills:
                raise ValueError("Each BillID needs exactly one originating bill")
            bills[row["BillID"]] = {"bill_id": row["BillID"], "supplier_id": row["SupplierID"],
                                    "date": row["Date"], "gross": amount, "credited": Decimal(0),
                                    "paid": Decimal(0), "evidence_reference": row["Reference"]}
    if not bills:
        raise ValueError("Supply the originating opening bills")
    for row in rows:
        if row["Kind"] == "bill":
            continue
        bill = bills.get(row["BillID"])
        if bill is None or row["SupplierID"] != bill["supplier_id"] or row["Date"] < bill["date"]:
            raise ValueError("Every credit or settlement must link to its supplier's earlier bill")
        bill["credited" if row["Kind"] == "credit" else "paid"] += _amount(row["Amount"])
    result = []
    total = Decimal(0)
    for bill in bills.values():
        unpaid = bill["gross"] - bill["credited"] - bill["paid"]
        if unpaid < 0:
            raise ValueError("Credits and settlements exceed a bill's gross amount")
        total += unpaid
        result.append({**bill, "unpaid": unpaid})
    return total, [{key: f"{value:.2f}" if isinstance(value, Decimal) else value
                    for key, value in bill.items()} for bill in result]


def handoff(output: Path, data: Path = DATA) -> dict:
    destination, source_root = output.resolve(), data.resolve()
    if source_root == destination or source_root in destination.parents or any((parent / ".git").exists() for parent in (destination, *destination.parents)):
        raise ValueError("Handoff output must be outside source data and version-control checkouts")
    with localcontext(Context(prec=40)):
        return _handoff(destination, data)


def _handoff(output: Path, data: Path) -> dict:
    sources = {name: (data / name).read_bytes() for name in ("xero_bs.csv", "invoices.csv", "payments.csv", "opening-payable-items.csv")}
    balances = _records(sources["xero_bs.csv"], ("Code", "Account", "Amount"), "balance sheet")
    if {row["Code"] for row in balances} != set(PRIOR) or len(balances) != len(PRIOR):
        raise ValueError("The handoff requires the exact reviewed Lumbridge balance-sheet mapping")
    current = {row["Code"]: _amount(row["Amount"]) for row in balances}
    prior = {key: Decimal(value) for key, value in PRIOR.items()}
    if any(not value.is_finite() for value in current.values()) or sum(current.values()) != 0 or sum(prior.values()) != 0:
        raise ValueError("Both balance sheets must contain finite, balanced amounts")
    invoices = _records(sources["invoices.csv"], ("id", "service_month", "service_line", "net", "gst", "receipt_date"), "invoices")
    opening = [row for row in invoices if row["id"].startswith("OPEN-")]
    if {row["id"] for row in opening} != {"OPEN-V", "OPEN-F"} or len(opening) != 2:
        raise ValueError("Expected the two reviewed opening invoices")
    receivable = sum(_amount(row["net"]) + _amount(row["gst"]) for row in opening)
    payable, payable_items = _opening_payables(sources["opening-payable-items.csv"])
    if -payable != current["800"]:
        raise ValueError("Independently supplied opening payable items do not tie to the balance sheet")
    payments = _records(sources["payments.csv"], ("date", "category", "amount"), "payments")
    settlement = [row for row in payments if row["date"] == "2026-10-07" and row["category"] == "Materials"]
    if receivable != current["620"] or len(settlement) != 1 or _amount(settlement[0]["amount"]) != payable:
        raise ValueError("Opening receivables or the assumed payable settlement does not tie")
    record = {"entity": "Lumbridge Services", "currency": "AUD", "as_at": "2026-09-30",
              "opening_cash": str(current["090"]), "opening_receivables": str(receivable),
              "opening_payables": f"{-payable:.2f}", "payable_items": payable_items,
              "payable_balance_sheet": str(current["800"]), "payable_difference": str(current["800"] + payable),
              "planned_settlement": {"date": "2026-10-07", "amount": settlement[0]["amount"], "status": "forecast assumption"},
              "source_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in sources.items()},
              "scope": "Fabricated closed balance-sheet handoff. Prior values are constructed assumptions. "
                       "Payables derive from separately fabricated gross bills, credits and prior settlements. "
                       "No supplier documents are authenticated and completeness is not established. The October "
                       "settlement is a forecast assumption, not an executed payment. Account IDs use BS- to avoid the P&L code collision."}
    encoded = {}
    for label, when, values in (("prior", "2026-08-31", prior), ("current", "2026-09-30", current)):
        rows = []
        for row in balances:
            code, value = row["Code"], values[row["Code"]]
            movement = value - prior[code] if label == "current" else Decimal(0)
            section = "Assets" if code in {"090", "620", "710"} else "Equity" if code == "900" else "Liabilities"
            rows.append([when, "Lumbridge Services", section, "BS-" + code, row["Account"], code,
                         max(movement, 0), max(-movement, 0), max(value, 0), max(-value, 0)])
        encoded[f"{label}.csv"] = _csv(HEADER, rows)
    encoded["mapping.csv"] = _csv(["AccountID", "ReviewGroup"], [["BS-" + row["Code"], row["Account"]] for row in balances])
    encoded["subledger.csv"] = _csv(["Tenant", "AccountID", "SubledgerBalance"], [
        ["Lumbridge Services", "BS-620", receivable], ["Lumbridge Services", "BS-800", -payable]])
    encoded["handoff.json"] = (json.dumps(record, indent=2) + "\n").encode("utf-8")
    if output.exists():
        raise FileExistsError(f"Handoff destination already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", suffix=".partial", dir=output.parent))
    created = []
    try:
        for name, content in encoded.items():
            target = staging / name
            with target.open("xb") as stream:
                created.append(target)
                stream.write(content)
        if output.exists():
            raise FileExistsError(f"Handoff destination appeared during writing: {output}")
        staging.rename(output)
    except BaseException as original:
        retained = []
        for target in reversed(created):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                retained.append(str(target))
        try:
            staging.rmdir()
        except OSError:
            retained.append(str(staging))
        if retained:
            original.add_note("Handoff staging cleanup incomplete; retained paths: " + ", ".join(retained))
        raise
    return record


def _records(content: bytes, columns: tuple[str, ...], label: str) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        if not reader.fieldnames or len(reader.fieldnames) != len(columns) or set(reader.fieldnames) != set(columns):
            raise ValueError(f"Unexpected {label} columns")
        rows = list(reader)
        if any(set(row) != set(columns) or any(value is None for value in row.values()) for row in rows):
            raise ValueError(f"Every {label} row needs every explicit cell")
        return rows
    except csv.Error as error:
        raise ValueError(f"Malformed {label} CSV: {error}") from error


def _csv(columns: list[str], rows: list[list]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(handoff(args.output), indent=2))
