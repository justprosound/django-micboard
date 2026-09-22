"""Behavioral coverage for the thin realtime subscription command.

The command resolves an operator's manufacturer and optional device selection into
persisted identifiers and hands them to the runner. The transport is not an operator
choice, so there is one command for every integration.
"""

from __future__ import annotations

from argparse import ArgumentParser
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.management.commands import realtime_subscribe as command_module


def test_subscription_command_argument_contract() -> None:
    parser = ArgumentParser(add_help=False)
    command_module.Command().add_arguments(parser)

    assert parser.format_help()


def test_subscription_command_rejects_missing_manufacturer(monkeypatch) -> None:
    monkeypatch.setattr(
        command_module.Manufacturer.objects,
        "get",
        Mock(side_effect=command_module.Manufacturer.DoesNotExist),
    )
    errors = StringIO()

    command_module.Command(stderr=errors).handle(manufacturer="missing", device=None)

    assert "Manufacturer 'missing' not found" in errors.getvalue()


@pytest.mark.parametrize("code", ["sennheiser", "shure"])
def test_subscription_command_resolves_device_and_calls_the_runner(monkeypatch, code) -> None:
    """Any integration reaches the same runner, which reads the transport off its plugin."""
    manufacturer = SimpleNamespace(pk=7, code=code)
    run = Mock()
    monkeypatch.setattr(
        command_module.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        command_module.WirelessChassis.objects,
        "get",
        Mock(return_value=SimpleNamespace(pk=17)),
    )
    monkeypatch.setattr(command_module, "run_realtime_subscriptions", run)

    command_module.Command().handle(manufacturer=code, device="device-1")

    run.assert_called_once_with(7, chassis_id=17)


def test_subscription_command_rejects_unknown_device(monkeypatch) -> None:
    manufacturer = SimpleNamespace(pk=19, code="sennheiser")
    run = Mock()
    monkeypatch.setattr(
        command_module.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        command_module.WirelessChassis.objects,
        "get",
        Mock(side_effect=command_module.WirelessChassis.DoesNotExist),
    )
    monkeypatch.setattr(command_module, "run_realtime_subscriptions", run)
    errors = StringIO()

    command_module.Command(stderr=errors).handle(manufacturer="sennheiser", device="missing")

    assert "Selected device was not found" in errors.getvalue()
    run.assert_not_called()


def test_subscription_command_redacts_runner_failures(monkeypatch, caplog) -> None:
    secret = "private-vendor-payload"
    monkeypatch.setattr(
        command_module.Manufacturer.objects,
        "get",
        Mock(return_value=SimpleNamespace(pk=10, code="sennheiser")),
    )
    monkeypatch.setattr(
        command_module,
        "run_realtime_subscriptions",
        Mock(side_effect=RuntimeError(secret)),
    )
    errors = StringIO()

    command_module.Command(stderr=errors).handle(manufacturer="sennheiser", device=None)

    assert secret not in errors.getvalue()
    assert secret not in caplog.text
    assert "details redacted" in errors.getvalue()


def test_subscription_command_reports_operator_interrupts(monkeypatch) -> None:
    monkeypatch.setattr(
        command_module.Manufacturer.objects,
        "get",
        Mock(return_value=SimpleNamespace(pk=12, code="shure")),
    )
    monkeypatch.setattr(
        command_module,
        "run_realtime_subscriptions",
        Mock(side_effect=KeyboardInterrupt),
    )
    output = StringIO()

    command_module.Command(stdout=output).handle(manufacturer="shure", device=None)

    assert "Realtime subscriptions stopped by user" in output.getvalue()
