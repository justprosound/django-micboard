"""Manufacturer configuration secret-redaction contracts."""

from django.core.exceptions import ValidationError

import pytest

from micboard.services.manufacturer.secret_redaction import (
    REDACTED_VALUE,
    is_secret_key,
    redact_secrets,
    restore_redacted_secrets,
)


def test_redaction_recurses_without_mutating_visible_values() -> None:
    """Nested dictionaries and lists mask only conventionally secret keys."""
    source = {
        " API_TOKEN ": "token-value",
        "nested": {
            "password_hint": "secret-value",
            "label": "visible-value",
        },
        "items": [{"private_key": "key-value"}, 42],
        "camelCase": {"apiKey": "camel-token", "privateKey": "camel-key"},
    }

    assert is_secret_key(" Shared_Key ") is True
    assert is_secret_key("display_name") is False
    assert redact_secrets(source) == {
        " API_TOKEN ": REDACTED_VALUE,
        "nested": {
            "password_hint": REDACTED_VALUE,
            "label": "visible-value",
        },
        "items": [{"private_key": REDACTED_VALUE}, 42],
        "camelCase": {"apiKey": REDACTED_VALUE, "privateKey": REDACTED_VALUE},
    }


def test_restore_preserves_placeholders_and_accepts_changed_values() -> None:
    """Unchanged masks recover originals while submitted replacements win."""
    original = {
        "api_key": "original-key",
        "nested": {"password": "original-password", "name": "before"},
        "items": [
            {"name": "primary", "token": "primary-token"},
            {"name": "secondary", "token": "secondary-token"},
        ],
    }
    submitted = {
        "api_key": REDACTED_VALUE,
        "nested": {"password": "replacement-password", "name": "after"},
        "items": [
            {"name": "secondary", "token": REDACTED_VALUE},
            {"name": "primary", "token": REDACTED_VALUE},
        ],
    }

    assert restore_redacted_secrets(submitted, original) == {
        "api_key": "original-key",
        "nested": {"password": "replacement-password", "name": "after"},
        "items": [
            {"name": "secondary", "token": "secondary-token"},
            {"name": "primary", "token": "primary-token"},
        ],
    }


def test_restore_tolerates_mismatched_original_shapes() -> None:
    """Malformed historic shapes fail closed instead of overwriting credentials."""
    with pytest.raises(ValidationError, match="no original"):
        restore_redacted_secrets({"api_key": REDACTED_VALUE}, [])
    with pytest.raises(ValidationError, match="unique"):
        restore_redacted_secrets([{"token": REDACTED_VALUE}], {})
    assert restore_redacted_secrets("visible", {"nested": "ignored"}) == "visible"


def test_restore_rejects_ambiguous_masked_list_entries() -> None:
    """Multiple credential rows need stable identities before masks can be restored."""
    original = [{"token": "first"}, {"token": "second"}]
    submitted = [{"token": REDACTED_VALUE}, {"token": REDACTED_VALUE}]

    with pytest.raises(ValidationError, match="id, key, code, or name"):
        restore_redacted_secrets(submitted, original)


def test_restore_handles_one_nested_unidentified_secret_row() -> None:
    """A sole credential row can be restored safely without an explicit identity."""
    original = [
        {
            "label": "only row",
            "nested": [{"label": "credential", "token": "original-token"}],
        }
    ]
    submitted = [
        {
            "label": "only row updated",
            "nested": [{"label": "credential", "token": REDACTED_VALUE}],
        }
    ]

    assert restore_redacted_secrets(submitted, original) == [
        {
            "label": "only row updated",
            "nested": [{"label": "credential", "token": "original-token"}],
        }
    ]


def test_identity_matching_ignores_non_mapping_original_items() -> None:
    """Mixed configuration lists still resolve a uniquely named credential row."""
    original = [42, {"name": "credential", "token": "original-token"}]
    submitted = [{"name": "credential", "token": REDACTED_VALUE}]

    assert restore_redacted_secrets(submitted, original) == [
        {"name": "credential", "token": "original-token"}
    ]
