"""Regression tests for Huey's native Django integration."""

from __future__ import annotations

from django.db import transaction

import pytest
from huey import MemoryHuey
from huey.contrib.djhuey import HUEY

from micboard.utils.dependencies import (
    enqueue_huey_task,
    huey_is_configured,
    register_huey_task,
)


def _increment(value: int) -> int:
    return value + 1


_COMMITTED_VALUES: list[int] = []


def _record_committed_value(value: int) -> int:
    _COMMITTED_VALUES.append(value)
    return value


def test_native_huey_uses_test_memory_backend() -> None:
    assert isinstance(HUEY, MemoryHuey)
    assert HUEY.immediate is True
    assert huey_is_configured() is True


@pytest.mark.django_db(transaction=True)
def test_enqueue_huey_task_executes_through_native_backend() -> None:
    result = enqueue_huey_task(_increment, 2)

    assert result.get() == 3


def test_register_huey_task_is_idempotent() -> None:
    assert register_huey_task(_increment) is register_huey_task(_increment)


@pytest.mark.django_db(transaction=True)
def test_enqueue_huey_task_waits_for_transaction_commit() -> None:
    _COMMITTED_VALUES.clear()

    with transaction.atomic():
        result = enqueue_huey_task(_record_committed_value, 7)
        assert _COMMITTED_VALUES == []

    assert _COMMITTED_VALUES == [7]
    assert result.get() == 7
