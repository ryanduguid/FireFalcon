"""Compare supplied account identities and mappings without changing company memory."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from pyfpa.io.xero_au import AccountIdentity
from pyfpa.memory.lineage import MappingRegistry, SourceRecord

MappingValue = tuple[str, str, str]
MetadataValue = str | tuple[str, ...]


@dataclass(frozen=True)
class ReimportComparison:
    source_id: str
    added: tuple[AccountIdentity, ...]
    removed: tuple[AccountIdentity, ...]
    renamed: tuple[tuple[str, str, str], ...]
    tracking_changed: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]
    mapping_changed: tuple[tuple[str, MappingValue | None, MappingValue | None], ...]
    unmapped: tuple[str, ...]
    ignored: tuple[str, ...]
    source_changed: tuple[tuple[str, MetadataValue, MetadataValue], ...]


def _index(accounts: Iterable[AccountIdentity]) -> dict[str, AccountIdentity]:
    result: dict[str, AccountIdentity] = {}
    for account in accounts:
        if (not account.code.strip() or account.code != account.code.strip()
                or not account.name.strip() or account.code in result):
            raise ValueError("account identities require unique non-empty codes and names")
        result[account.code] = replace(
            account, tracking_options=tuple(sorted(set(account.tracking_options)))
        )
    return result


def compare_reimport(
    previous: Iterable[AccountIdentity],
    current: Iterable[AccountIdentity],
    *,
    previous_source: SourceRecord,
    current_source: SourceRecord,
    mappings: MappingRegistry,
    previous_mappings: MappingRegistry | None = None,
) -> ReimportComparison:
    """Compare one source using exact account-code mapping keys, never display names.

    Missing accounts describe the supplied exports only. A zero balance omitted
    by an upstream export is not proof that the account was deleted. This report
    performs no reconciliation, remapping, registry write or financial approval.
    Mapping changes cover only codes present in either supplied export.
    """
    for field in ("source_id", "entity", "currency"):
        if getattr(previous_source, field) != getattr(current_source, field):
            raise ValueError(f"re-import {field} differs")
    before, after = _index(previous), _index(current)
    source_id = current_source.source_id

    def rules(registry: MappingRegistry) -> dict[str, MappingValue]:
        return {
            rule.source_value: (rule.status, rule.target, rule.rationale)
            for rule in registry.mappings if rule.source_id == source_id
        }

    old_rules = rules(mappings if previous_mappings is None else previous_mappings)
    new_rules = rules(mappings)
    common = sorted(before.keys() & after.keys())
    fields = ("kind", "location", "periods", "extraction_method", "refreshed_at", "notes")

    def metadata(source: SourceRecord, field: str) -> MetadataValue:
        return tuple(source.periods) if field == "periods" else str(getattr(source, field))

    return ReimportComparison(
        source_id=source_id,
        added=tuple(after[key] for key in sorted(after.keys() - before.keys())),
        removed=tuple(before[key] for key in sorted(before.keys() - after.keys())),
        renamed=tuple((key, before[key].name, after[key].name) for key in common
                      if before[key].name != after[key].name),
        tracking_changed=tuple(
            (key, before[key].tracking_options, after[key].tracking_options)
            for key in common if before[key].tracking_options != after[key].tracking_options
        ),
        mapping_changed=tuple(
            (key, old_rules.get(key), new_rules.get(key))
            for key in sorted(before.keys() | after.keys())
            if old_rules.get(key) != new_rules.get(key)
        ),
        unmapped=tuple(key for key in sorted(after) if key not in new_rules),
        ignored=tuple(key for key in sorted(after)
                      if key in new_rules and new_rules[key][0] == "ignored"),
        source_changed=tuple(
            (field, metadata(previous_source, field), metadata(current_source, field))
            for field in fields if metadata(previous_source, field) != metadata(current_source, field)
        ),
    )
