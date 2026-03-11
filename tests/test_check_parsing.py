"""Tests for shared check parsing helpers."""

from sw_metadata_bot.check_parsing import (
    extract_check_ids,
    get_check_catalog_id,
    get_short_check_code,
)


def test_get_check_catalog_id_prefers_new_schema():
    """Use assessesIndicator.@id when it points to RSMetacheck catalog."""
    check = {
        "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#W004"},
        "pitfall": "https://w3id.org/rsmetacheck/catalog/#P001",
    }

    assert get_check_catalog_id(check) == "https://w3id.org/rsmetacheck/catalog/#W004"


def test_get_check_catalog_id_falls_back_to_legacy_key():
    """Use legacy pitfall key when assessesIndicator is not a catalog ID."""
    check = {
        "assessesIndicator": {
            "@id": "https://w3id.org/example/metacheck/i/indicators/codemeta"
        },
        "pitfall": "https://w3id.org/rsmetacheck/catalog/#P001",
    }

    assert get_check_catalog_id(check) == "https://w3id.org/rsmetacheck/catalog/#P001"


def test_get_short_check_code_returns_suffix_after_hash():
    """Extract short check code from resolved full identifier."""
    check = {"assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#P017"}}

    assert get_short_check_code(check) == "P017"


def test_extract_check_ids_handles_new_and_old_schema_with_dedup():
    """Collect unique ordered P/W IDs across mixed schema payloads."""
    checks = [
        {"assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#P001"}},
        {"pitfall": "https://w3id.org/rsmetacheck/catalog/#W004"},
        {"assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#W004"}},
        {"pitfall": "https://w3id.org/rsmetacheck/catalog/#P001"},
        {"pitfall": "https://w3id.org/rsmetacheck/catalog/#P002"},
        {"assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#W003"}},
    ]

    pitfall_ids, warning_ids = extract_check_ids(checks)

    assert pitfall_ids == ["P001", "P002"]
    assert warning_ids == ["W004", "W003"]


def test_extract_check_ids_ignores_invalid_entries():
    """Skip checks that do not resolve to pitfall/warning codes."""
    checks = [
        {
            "assessesIndicator": {
                "@id": "https://w3id.org/example/metacheck/i/indicators/codemeta"
            }
        },
        {"pitfall": ""},
        {},
    ]

    pitfall_ids, warning_ids = extract_check_ids(checks)

    assert pitfall_ids == []
    assert warning_ids == []
