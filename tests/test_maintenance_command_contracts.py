"""Argument-contract coverage for supported maintenance commands."""

from __future__ import annotations

from argparse import ArgumentParser

import pytest

from micboard.management.commands import archive_audit_logs
from micboard.management.commands import audit_regulatory_coverage as regulatory_command
from micboard.management.commands import import_devices as import_devices_command
from micboard.management.commands import import_efis_regulations as efis_command
from micboard.management.commands import init_settings as init_command
from micboard.management.commands import poll_devices as poll_command
from micboard.management.commands import realtime_status as realtime_command
from micboard.management.commands import set_logging_mode as logging_command


@pytest.mark.parametrize(
    "command_type",
    [
        archive_audit_logs.Command,
        regulatory_command.Command,
        import_devices_command.Command,
        efis_command.Command,
        init_command.Command,
        poll_command.Command,
        realtime_command.Command,
        logging_command.Command,
    ],
)
def test_maintenance_command_argument_contracts_parse_help(command_type) -> None:
    parser = ArgumentParser(add_help=False)
    command_type().add_arguments(parser)
    assert parser.format_help()
