from dataclasses import asdict

import pytest

from pyfpa.io.xero_au import AccountIdentity, XeroReport, XeroRow
from pyfpa.memory.lineage import MappingRegistry, MappingRule, SourceRecord
from pyfpa.memory.reimport import compare_reimport


def source(**changes):
    return SourceRecord(**({"source_id": "xero", "kind": "local_file", "entity": "Demo",
                           "location": "before.csv", "currency": "AUD",
                           "extraction_method": "report export"} | changes))


def test_identity_preserves_codes_tracking_and_leading_zeros():
    report = XeroReport(rows=[XeroRow(code="090", account="Bank", amount=0),
                             XeroRow(code="091", account="Bank", amount=7),
                             XeroRow(code="090", account="Bank", amount=3, tracking_option="North")])
    assert report.account_identities() == (
        AccountIdentity("090", "Bank", ("", "North")), AccountIdentity("091", "Bank", ("",)),
    )
    assert report.by_account() == {"Bank": 10}


@pytest.mark.parametrize("rows", [
    [XeroRow(account="Sales", amount=1)],
    [XeroRow(code="200", account="", amount=1)],
    [XeroRow(code=" ", account="Sales", amount=1)],
    [XeroRow(code="200", account=" ", amount=1)],
    [XeroRow(code=" 200 ", account="Sales", amount=1)],
    [XeroRow(code="200", account="Sales", amount=1),
     XeroRow(code="200", account="Other", amount=2)],
])
def test_identity_refuses_missing_or_ambiguous_codes(rows):
    with pytest.raises(ValueError):
        XeroReport(rows=rows).account_identities()


def test_reimport_separates_identity_mapping_and_source_changes():
    old = (AccountIdentity("090", "Bank", ("",)), AccountIdentity("200", "Sales", ("North",)))
    new = (AccountIdentity("200", "Revenue", ("South",)), AccountIdentity("201", "Sales", ("",)))
    previous_rules = MappingRegistry(mappings=[
        MappingRule(source_id="xero", source_value="200", target="sales"),
    ])
    current_rules = MappingRegistry(mappings=[
        MappingRule(source_id="xero", source_value="200", target="", status="ignored",
                    rationale="reviewed exclusion"),
        MappingRule(source_id="other", source_value="201", target="sales"),
    ])
    original = current_rules.model_dump()
    result = compare_reimport(old, new, previous_source=source(),
                              current_source=source(location="after.csv", periods=["2026-09"]),
                              mappings=current_rules, previous_mappings=previous_rules)
    assert result.added == (new[1],)
    assert result.removed == (old[0],)
    assert result.renamed == (("200", "Sales", "Revenue"),)
    assert result.tracking_changed == (("200", ("North",), ("South",)),)
    assert result.mapping_changed == (("200", ("mapped", "sales", ""),
                                       ("ignored", "", "reviewed exclusion")),)
    assert result.unmapped == ("201",)
    assert result.ignored == ("200",)
    assert result.source_changed == (("location", "before.csv", "after.csv"),
                                     ("periods", (), ("2026-09",)))
    assert current_rules.model_dump() == original
    assert asdict(result)["source_id"] == "xero"


@pytest.mark.parametrize("field,value", [("source_id", "other"), ("entity", "Other"),
                                         ("currency", "USD")])
def test_comparison_refuses_cross_source_or_entity(field, value):
    with pytest.raises(ValueError, match=field):
        compare_reimport((), (), previous_source=source(), current_source=source(**{field: value}),
                         mappings=MappingRegistry())


def test_duplicate_identity_is_refused_and_default_mapping_snapshot_is_unchanged():
    account = AccountIdentity("090", "Bank", ("",))
    with pytest.raises(ValueError, match="unique"):
        compare_reimport((account, account), (), previous_source=source(), current_source=source(),
                         mappings=MappingRegistry())
    result = compare_reimport((account,), (account,), previous_source=source(),
                              current_source=source(), mappings=MappingRegistry())
    assert not result.mapping_changed
    assert not result.added
    assert not result.removed
    assert not result.renamed
    assert result.unmapped == ("090",)


@pytest.mark.parametrize("code,name", [(" ", "Bank"), ("090", " "), (" 090 ", "Bank")])
def test_direct_identity_refuses_blank_or_untrimmed_keys(code, name):
    with pytest.raises(ValueError):
        compare_reimport((AccountIdentity(code, name, ()),), (), previous_source=source(),
                         current_source=source(), mappings=MappingRegistry())


def test_direct_tracking_options_compare_as_sets():
    before = AccountIdentity("200", "Sales", ("North", "South", "North"))
    after = AccountIdentity("200", "Sales", ("South", "North"))
    result = compare_reimport((before,), (after,), previous_source=source(),
                              current_source=source(), mappings=MappingRegistry())
    assert not result.tracking_changed
