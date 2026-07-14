"""Redact and restore secrets embedded in manufacturer configuration JSON."""

from __future__ import annotations

from typing import Any

REDACTED_VALUE = "********"
_SECRET_KEY_PARTS = (
    "api_key",
    "credential",
    "password",
    "private_key",
    "secret",
    "shared_key",
    "token",
)


def is_secret_key(key: object) -> bool:
    """Return whether a configuration key conventionally carries a secret."""
    normalized = str(key).strip().lower()
    return any(part in normalized for part in _SECRET_KEY_PARTS)


def redact_secrets(value: Any) -> Any:
    """Return a copy of nested JSON data with secret values replaced."""
    if isinstance(value, dict):
        return {
            key: REDACTED_VALUE if is_secret_key(key) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def restore_redacted_secrets(value: Any, original: Any) -> Any:
    """Restore unchanged placeholders from the original nested JSON data."""
    if isinstance(value, dict):
        original_dict = original if isinstance(original, dict) else {}
        restored: dict[str, Any] = {}
        for key, item in value.items():
            original_item = original_dict.get(key)
            if is_secret_key(key) and item == REDACTED_VALUE:
                restored[key] = original_item
            else:
                restored[key] = restore_redacted_secrets(item, original_item)
        return restored
    if isinstance(value, list):
        original_list = original if isinstance(original, list) else []
        return [
            restore_redacted_secrets(
                item, original_list[index] if index < len(original_list) else None
            )
            for index, item in enumerate(value)
        ]
    return value
