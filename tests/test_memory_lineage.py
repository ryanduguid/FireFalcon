import pytest

from pyfpa.memory.lineage import (
    MappingRegistry,
    MappingRule,
    SourceRecord,
    SourceRegistry,
    load_mapping_registry,
    load_source_registry,
    profile_table,
    reconcile_account_table,
    register_mapping,
    register_source,
    save_mapping_registry,
    save_source_registry,
)


def source() -> SourceRecord:
    return SourceRecord(
        source_id="gl-actuals",
        kind="local_file",
        location="data/gl.csv",
        entity="Acme",
        currency="usd",
        periods=["2026-01"],
        extraction_method="Manual export",
    )


def test_source_and_mapping_registries_round_trip(tmp_path):
    source_path = tmp_path / "sources.yaml"
    mapping_path = tmp_path / "mappings.yaml"
    sources = register_source(SourceRegistry(), source())
    mappings = register_mapping(
        MappingRegistry(),
        MappingRule(
            source_id="gl-actuals",
            source_value="Product Revenue",
            target="revenue",
        ),
    )

    save_source_registry(sources, source_path)
    save_mapping_registry(mappings, mapping_path)

    assert load_source_registry(source_path) == sources
    assert load_mapping_registry(mapping_path) == mappings
    assert sources.sources[0].currency == "USD"


def test_registry_updates_require_explicit_overwrite():
    sources = register_source(SourceRegistry(), source())
    mappings = register_mapping(
        MappingRegistry(),
        MappingRule(source_id="gl-actuals", source_value="Rent", target="opex.rent"),
    )

    with pytest.raises(ValueError, match="already registered"):
        register_source(sources, source())
    with pytest.raises(ValueError, match="already registered"):
        register_mapping(
            mappings,
            MappingRule(source_id="gl-actuals", source_value="Rent", target="opex.rent"),
        )


def test_registries_reject_duplicate_keys():
    with pytest.raises(ValueError, match="duplicate source IDs"):
        SourceRegistry(sources=[source(), source()])
    mapping = MappingRule(
        source_id="gl-actuals",
        source_value="Rent",
        target="opex.rent",
    )
    with pytest.raises(ValueError, match="duplicate mapping keys"):
        MappingRegistry(mappings=[mapping, mapping])


def test_ignored_mapping_requires_rationale():
    with pytest.raises(ValueError, match="ignored rules require a rationale"):
        MappingRule(
            source_id="gl-actuals",
            source_value="Subtotal",
            target="",
            status="ignored",
        )


def test_profile_table_reports_shape_and_duplicates(tmp_path):
    path = tmp_path / "actuals.csv"
    path.write_text("Account,Amount\nRevenue,10\nRevenue,10\nRent,\n")

    profile = profile_table(path)

    assert profile["rows"] == 3
    assert profile["columns"] == ["Account", "Amount"]
    assert profile["empty_by_column"]["Amount"] == 1
    assert profile["duplicate_rows"] == 1


def test_reconcile_account_table_reports_unmapped_duplicates_and_variance(tmp_path):
    path = tmp_path / "actuals.csv"
    path.write_text(
        "Account,Amount\n"
        "Product Revenue,100\n"
        "Product Revenue,50\n"
        "Rent,(20)\n"
        "Mystery,5\n"
    )
    mappings = MappingRegistry(mappings=[
        MappingRule(
            source_id="gl-actuals",
            source_value="Product Revenue",
            target="revenue",
        ),
        MappingRule(
            source_id="gl-actuals",
            source_value="Rent",
            target="opex",
        ),
    ])

    result = reconcile_account_table(
        path,
        source_id="gl-actuals",
        mappings=mappings,
        account_column="Account",
        amount_column="Amount",
        expected={"revenue": 140, "opex": -20},
    )

    assert result["passed"] is False
    assert result["duplicates"] == ["Product Revenue"]
    assert result["unmapped"] == ["Mystery"]
    assert result["mapped_totals"] == {"revenue": 150.0, "opex": -20.0}
    assert result["variances"]["revenue"]["within_tolerance"] is False


def test_ignored_mapping_does_not_count_as_unmapped(tmp_path):
    path = tmp_path / "actuals.csv"
    path.write_text("Account,Amount\nSubtotal,100\n")
    mappings = MappingRegistry(mappings=[
        MappingRule(
            source_id="gl-actuals",
            source_value="Subtotal",
            target="",
            status="ignored",
            rationale="Presentation subtotal",
        )
    ])

    result = reconcile_account_table(
        path,
        source_id="gl-actuals",
        mappings=mappings,
        account_column="Account",
        amount_column="Amount",
    )

    assert result["passed"] is True
    assert result["ignored"] == ["Subtotal"]
    assert result["unmapped"] == []


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_reconciliation_accepts_utf8_with_or_without_bom(tmp_path, encoding):
    path = tmp_path / "actuals.csv"
    path.write_text("Account,Amount\nCafé,100\n", encoding=encoding)
    registry = MappingRegistry(mappings=[
        MappingRule(source_id="gl-actuals", source_value="Café", target="revenue"),
    ])
    result = reconcile_account_table(
        path, source_id="gl-actuals", mappings=registry,
        account_column="Account", amount_column="Amount", expected={"revenue": 100},
    )
    assert result["passed"] is True
    assert result["mapped_totals"] == {"revenue": 100.0}


def test_missing_expected_target_cannot_pass_as_a_real_zero(tmp_path):
    path = tmp_path / "actuals.csv"
    path.write_text("Account,Amount\nRevenue,100\n", encoding="utf-8")
    registry = MappingRegistry(mappings=[MappingRule(source_id="gl", source_value="Revenue", target="revenue")])
    result = reconcile_account_table(path, source_id="gl", mappings=registry,
                                     account_column="Account", amount_column="Amount",
                                     expected={"revenue": 100, "missing": 0})
    assert not result["passed"]
    assert result["variances"]["missing"]["mapped"] is None


def _revenue_rules() -> MappingRegistry:
    return MappingRegistry(mappings=[
        MappingRule(source_id="gl", source_value="Product Revenue", target="revenue.product"),
        MappingRule(source_id="gl", source_value="Service Revenue", target="revenue.service"),
        MappingRule(source_id="gl", source_value="Clearing", target="clearing"),
    ])


def _reconcile(path, expected, **tolerances):
    return reconcile_account_table(
        path, source_id="gl", mappings=_revenue_rules(), account_column="Account",
        amount_column="Amount", expected=expected, **tolerances,
    )


def test_amounts_cross_mapped_between_targets_fail_by_default(tmp_path):
    # 3,000 of service revenue booked to product revenue: each target is within 1%,
    # which the old relative default passed.
    path = tmp_path / "gl.csv"
    path.write_text("Account,Amount\nProduct Revenue,503000\nService Revenue,297000\n")
    expected = {"revenue.product": 500000, "revenue.service": 300000}
    assert _reconcile(path, expected)["passed"] is False
    assert _reconcile(path, expected, tolerance=0.01)["passed"] is True


def test_float_noise_on_a_nil_target_passes(tmp_path):
    # 0.10 + 0.20 - 0.30 is 5.55e-17 in floats, which an exact nil check failed.
    path = tmp_path / "gl.csv"
    path.write_text("Account,Amount\nClearing A,0.10\nClearing B,0.20\nClearing C,-0.30\n")
    mappings = MappingRegistry(mappings=[
        MappingRule(source_id="gl", source_value=name, target="clearing")
        for name in ("Clearing A", "Clearing B", "Clearing C")
    ])
    result = reconcile_account_table(
        path, source_id="gl", mappings=mappings, account_column="Account",
        amount_column="Amount", expected={"clearing": 0},
    )
    assert result["mapped_totals"]["clearing"] != 0
    assert result["passed"] is True


def test_a_whole_dollar_control_needs_the_absolute_allowance(tmp_path):
    path = tmp_path / "gl.csv"
    path.write_text("Account,Amount\nProduct Revenue,1000.20\n")
    expected = {"revenue.product": 1000}
    assert _reconcile(path, expected)["passed"] is False
    assert _reconcile(path, expected, abs_tolerance=0.5)["passed"] is True


def test_an_exact_half_cent_is_within_the_default(tmp_path):
    # 0.1 + 0.005 - 0.1 is 0.0050000000000000044 in floats, just over the limit.
    path = tmp_path / "gl.csv"
    path.write_text("Account,Amount\nA,0.1\nB,0.005\n")
    mappings = MappingRegistry(mappings=[
        MappingRule(source_id="gl", source_value=name, target="t") for name in ("A", "B")
    ])

    def passed(expected: float) -> bool:
        return reconcile_account_table(
            path, source_id="gl", mappings=mappings, account_column="Account",
            amount_column="Amount", expected={"t": expected},
        )["passed"]

    assert passed(0.1) is True
    assert passed(0.09) is False
