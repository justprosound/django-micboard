"""Behavioral coverage for thin realtime subscription commands."""

from __future__ import annotations

from argparse import ArgumentParser
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.management.commands import sse_subscribe as sse_command
from micboard.management.commands import websocket_subscribe as websocket_command


@pytest.mark.parametrize("command_type", [sse_command.Command, websocket_command.Command])
def test_subscription_command_argument_contracts(command_type) -> None:
    parser = ArgumentParser(add_help=False)
    command_type().add_arguments(parser)

    assert parser.format_help()


@pytest.mark.parametrize("module", [sse_command, websocket_command])
def test_subscription_command_rejects_missing_manufacturer(monkeypatch, module) -> None:
    monkeypatch.setattr(
        module.Manufacturer.objects,
        "get",
        Mock(side_effect=module.Manufacturer.DoesNotExist),
    )
    errors = StringIO()

    module.Command(stderr=errors).handle(manufacturer="missing", device=None)

    assert "Manufacturer 'missing' not found" in errors.getvalue()


def test_sse_command_resolves_device_and_calls_service(monkeypatch) -> None:
    manufacturer = SimpleNamespace(pk=7, code="sennheiser")
    chassis = SimpleNamespace(pk=17)
    run = Mock()
    monkeypatch.setattr(sse_command.Manufacturer.objects, "get", Mock(return_value=manufacturer))
    monkeypatch.setattr(sse_command.WirelessChassis.objects, "get", Mock(return_value=chassis))
    monkeypatch.setattr(sse_command, "run_sse_subscriptions", run)

    sse_command.Command().handle(manufacturer="sennheiser", device="device-1")

    run.assert_called_once_with(7, chassis_id=17)


def test_websocket_command_resolves_device_and_calls_service(monkeypatch) -> None:
    manufacturer = SimpleNamespace(pk=8, code="shure")
    chassis = SimpleNamespace(pk=18)
    run = Mock()
    monkeypatch.setattr(
        websocket_command.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        websocket_command.WirelessChassis.objects,
        "get",
        Mock(return_value=chassis),
    )
    monkeypatch.setattr(websocket_command, "run_shure_websocket_subscriptions", run)

    websocket_command.Command().handle(manufacturer="shure", device="device-2")

    run.assert_called_once_with(8, chassis_id=18)


def test_websocket_command_rejects_non_shure_manufacturer(monkeypatch) -> None:
    manufacturer = SimpleNamespace(pk=9, code="other")
    run = Mock()
    monkeypatch.setattr(
        websocket_command.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(websocket_command, "run_shure_websocket_subscriptions", run)
    errors = StringIO()

    websocket_command.Command(stderr=errors).handle(manufacturer="other", device=None)

    assert "only supported for Shure" in errors.getvalue()
    run.assert_not_called()


@pytest.mark.parametrize(
    ("module", "service_name", "manufacturer"),
    [
        (
            sse_command,
            "run_sse_subscriptions",
            SimpleNamespace(pk=19, code="sennheiser"),
        ),
        (
            websocket_command,
            "run_shure_websocket_subscriptions",
            SimpleNamespace(pk=20, code="shure"),
        ),
    ],
)
def test_subscription_commands_reject_unknown_device(
    monkeypatch,
    module,
    service_name: str,
    manufacturer,
) -> None:
    run = Mock()
    monkeypatch.setattr(module.Manufacturer.objects, "get", Mock(return_value=manufacturer))
    monkeypatch.setattr(
        module.WirelessChassis.objects,
        "get",
        Mock(side_effect=module.WirelessChassis.DoesNotExist),
    )
    monkeypatch.setattr(module, service_name, run)
    errors = StringIO()

    module.Command(stderr=errors).handle(manufacturer=manufacturer.code, device="missing")

    assert "Selected device was not found" in errors.getvalue()
    run.assert_not_called()


@pytest.mark.parametrize(
    ("module", "service_name", "manufacturer"),
    [
        (sse_command, "run_sse_subscriptions", SimpleNamespace(pk=10, code="sennheiser")),
        (
            websocket_command,
            "run_shure_websocket_subscriptions",
            SimpleNamespace(pk=11, code="shure"),
        ),
    ],
)
def test_subscription_commands_redact_service_failures(
    monkeypatch,
    caplog,
    module,
    service_name: str,
    manufacturer: SimpleNamespace,
) -> None:
    secret = "private-vendor-payload"
    monkeypatch.setattr(
        module.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(module, service_name, Mock(side_effect=RuntimeError(secret)))
    errors = StringIO()

    module.Command(stderr=errors).handle(manufacturer=manufacturer.code, device=None)

    assert secret not in errors.getvalue()
    assert secret not in caplog.text
    assert "details redacted" in errors.getvalue()


@pytest.mark.parametrize(
    ("module", "service_name", "manufacturer", "message"),
    [
        (
            sse_command,
            "run_sse_subscriptions",
            SimpleNamespace(pk=12, code="sennheiser"),
            "SSE subscriptions stopped by user",
        ),
        (
            websocket_command,
            "run_shure_websocket_subscriptions",
            SimpleNamespace(pk=13, code="shure"),
            "WebSocket subscriptions stopped by user",
        ),
    ],
)
def test_subscription_commands_report_operator_interrupts(
    monkeypatch,
    module,
    service_name: str,
    manufacturer: SimpleNamespace,
    message: str,
) -> None:
    monkeypatch.setattr(
        module.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(module, service_name, Mock(side_effect=KeyboardInterrupt))
    output = StringIO()

    module.Command(stdout=output).handle(manufacturer=manufacturer.code, device=None)

    assert message in output.getvalue()
