"""Discovery trigger transaction and shared-cache contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from micboard.services.sync.discovery_trigger_service import (
    DISCOVERY_DISPATCH_COALESCE_SECONDS,
    claim_discovery_dispatch,
    trigger_discovery,
)


def test_dispatch_claim_uses_bounded_ttl_and_request_shape() -> None:
    """Queue claims distinguish scan shapes and always expire quickly."""
    with patch(
        "micboard.services.sync.discovery_trigger_service.cache.add",
        return_value=True,
    ) as cache_add:
        claimed = claim_discovery_dispatch(
            91,
            scan_cidrs=False,
            scan_fqdns=True,
        )

    assert claimed is True
    cache_add.assert_called_once_with(
        "micboard:discovery-dispatch:91:0:1",
        True,
        timeout=DISCOVERY_DISPATCH_COALESCE_SECONDS,
    )
    assert 0 < DISCOVERY_DISPATCH_COALESCE_SECONDS <= 30


@pytest.mark.parametrize(
    ("cached_value", "expected"),
    [(True, False), (None, True)],
)
def test_dispatch_claim_distinguishes_duplicates_from_disabled_cache(
    cached_value: object,
    expected: bool,
) -> None:
    """Existing claims coalesce; cache backends that discard writes fail open."""
    with (
        patch(
            "micboard.services.sync.discovery_trigger_service.cache.add",
            return_value=False,
        ),
        patch(
            "micboard.services.sync.discovery_trigger_service.cache.get",
            return_value=cached_value,
        ),
    ):
        claimed = claim_discovery_dispatch(
            92,
            scan_cidrs=True,
            scan_fqdns=False,
        )

    assert claimed is expected


def test_trigger_contains_missing_task_receiver(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A misconfigured worker registration is observable without raising."""
    with (
        patch(
            "micboard.services.sync.discovery_trigger_service.huey_is_configured",
            return_value=True,
        ),
        patch(
            "micboard.services.sync.discovery_trigger_service.discovery_requested.send_robust",
            return_value=[],
        ),
        caplog.at_level("WARNING"),
    ):
        trigger_discovery(91)

    assert "No task-layer discovery dispatcher is registered" in caplog.text
