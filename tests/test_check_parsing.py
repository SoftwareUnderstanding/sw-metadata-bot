"""Tests for shared check parsing helpers."""

from sw_metadata_bot.check_parsing import (
    extract_check_ids,
    get_check_catalog_id,
    get_short_check_code,
    is_check_reported,
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
        {
            "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#P001"},
            "output": "true",
        },
        {
            "pitfall": "https://w3id.org/rsmetacheck/catalog/#W004",
            "output": "true",
        },
        {
            "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#W004"},
            "output": "true",
        },
        {
            "pitfall": "https://w3id.org/rsmetacheck/catalog/#P001",
            "output": "true",
        },
        {
            "pitfall": "https://w3id.org/rsmetacheck/catalog/#P002",
            "output": "true",
        },
        {
            "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#W003"},
            "output": "true",
        },
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


def test_is_check_reported_true_string():
    """output true means the check is reported."""
    check = {
        "pitfall": "https://w3id.org/rsmetacheck/catalog/#P001",
        "output": "true",
    }

    assert is_check_reported(check) is True


def test_is_check_reported_false_string():
    """output false means the check is not reported."""
    check = {
        "pitfall": "https://w3id.org/rsmetacheck/catalog/#P001",
        "output": "false",
    }

    assert is_check_reported(check) is False


def test_is_check_reported_missing_output_is_false():
    """Missing output key is not considered reported in strict mode."""
    check = {"pitfall": "https://w3id.org/rsmetacheck/catalog/#P001"}

    assert is_check_reported(check) is False


def test_extract_check_ids_skips_non_true_output_checks():
    """Only checks with output true are extracted."""
    checks = [
        {
            "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#P001"},
            "output": "true",
        },
        {
            "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#P002"},
            "output": "false",
        },
        {
            "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#W001"},
            "output": "false",
        },
        {
            "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#W002"},
            "output": "true",
        },
        {
            "assessesIndicator": {"@id": "https://w3id.org/rsmetacheck/catalog/#P003"},
        },
    ]

    pitfall_ids, warning_ids = extract_check_ids(checks)

    assert pitfall_ids == ["P001"]
    assert warning_ids == ["W002"]
