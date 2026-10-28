"""Test double plumbing for code that reads and writes the shared cache."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


@contextmanager
def patched_cache_backend(backend: MagicMock) -> Iterator[None]:
    """Serve ``backend`` to the charger polling adapter and the fair-page cursor module."""
    handler = MagicMock()
    handler.__getitem__.return_value = backend
    with (
        patch("micboard.services.chargers.polling_cache.cache", backend),
        patch("micboard.services.shared.fair_page_cursor.caches", handler),
    ):
        yield
