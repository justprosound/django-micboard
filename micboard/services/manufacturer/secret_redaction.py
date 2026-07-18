"""Redact and restore secrets embedded in manufacturer configuration JSON."""

from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ValidationError

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
_LIST_IDENTITY_KEYS = ("id", "key", "code", "name")


def _compact_key(key: object) -> str:
    """Normalize snake, kebab, spaced, and camel case keys for policy matching."""
    return re.sub(r"[^a-z0-9]", "", str(key).casefold())


def is_secret_key(key: object) -> bool:
    """Return whether a configuration key conventionally carries a secret."""
    compact = _compact_key(key)
    return any(_compact_key(part) in compact for part in _SECRET_KEY_PARTS)


def _contains_secret_placeholder(value: Any) -> bool:
    """Return whether nested submitted data asks to retain an existing secret."""
    if isinstance(value, dict):
        return any(
            (is_secret_key(key) and item == REDACTED_VALUE) or _contains_secret_placeholder(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_secret_placeholder(item) for item in value)
    return False


def _contains_secret_key(value: Any) -> bool:
    """Return whether nested original data contains any secret-bearing key."""
    if isinstance(value, dict):
        return any(is_secret_key(key) or _contains_secret_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _list_item_identity(value: Any) -> tuple[str, object] | None:
    """Return the first conventional stable identity for a configuration list item."""
    if not isinstance(value, dict):
        return None
    compact_items = {_compact_key(key): item for key, item in value.items()}
    for identity_key in _LIST_IDENTITY_KEYS:
        identity = compact_items.get(identity_key)
        if isinstance(identity, str | int) and not isinstance(identity, bool):
            return identity_key, identity
    return None


def _original_list_item(
    item: Any,
    original: list[Any],
    *,
    require_identity: bool,
) -> Any:
    """Resolve a masked list item without depending on mutable list position."""
    identity = _list_item_identity(item)
    if identity is not None:
        matches = [
            candidate for candidate in original if _list_item_identity(candidate) == identity
        ]
    elif require_identity:
        matches = []
    else:
        matches = [candidate for candidate in original if _contains_secret_key(candidate)]
    if len(matches) != 1:
        raise ValidationError(
            "Masked secrets in configuration lists require one unique id, key, code, or name."
        )
    return matches[0]


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
                if key not in original_dict:
                    raise ValidationError("A masked configuration secret has no original value.")
                restored[key] = original_item
            else:
                restored[key] = restore_redacted_secrets(item, original_item)
        return restored
    if isinstance(value, list):
        original_list = original if isinstance(original, list) else []
        return [
            restore_redacted_secrets(
                item,
                _original_list_item(
                    item,
                    original_list,
                    require_identity=len(value) > 1,
                )
                if _contains_secret_placeholder(item)
                else original_list[index]
                if index < len(original_list)
                else None,
            )
            for index, item in enumerate(value)
        ]
    return value
