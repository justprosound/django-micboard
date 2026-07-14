"""Regression tests for the admin-audit management command."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import Mock

from django.conf import settings
from django.test import override_settings

import pytest

from micboard.management.commands.audit_admin import Command


def _command_options() -> dict[str, object]:
    return {
        "errors_only": True,
        "quick": True,
        "check_n1": False,
        "check_unfold": False,
        "check_media": False,
        "check_search_depth": False,
        "model": None,
        "app": None,
        "exclude": None,
        "threads": 1,
    }


def test_default_audit_runs_all_model_checks() -> None:
    command = cast(Any, Command())
    command.aspect_filters_enabled = False
    command.check_unfold = False
    command.check_search_depth = False
    command.check_n1 = False
    command.check_inheritance = Mock()
    command.check_widgets = Mock()
    command.check_filters = Mock()
    command.check_search_depth_logic = Mock()
    command.check_templates_existence = Mock()
    command.check_static_optimization = Mock()
    command.check_runtime_performance = Mock()
    model = Mock()
    model_admin = Mock()
    stats: dict[str, int] = {}

    command.audit_model(model, model_admin, stats)

    command.check_inheritance.assert_called_once_with(model_admin, stats)
    command.check_widgets.assert_called_once_with(model, model_admin, stats)
    command.check_filters.assert_called_once_with(model_admin, stats)
    command.check_search_depth_logic.assert_called_once_with(model, model_admin, stats)
    command.check_templates_existence.assert_called_once_with(model_admin, stats)
    command.check_static_optimization.assert_called_once_with(model, model_admin)
    command.check_runtime_performance.assert_called_once_with(model, model_admin, stats)


@override_settings(DEBUG=True)
def test_handle_restores_debug_after_early_return() -> None:
    command = cast(Any, Command())
    command._setup_audit_environment = Mock(return_value=False)

    command.handle(**_command_options())

    assert settings.DEBUG is True


@override_settings(DEBUG=True)
def test_handle_restores_debug_after_exception() -> None:
    command = cast(Any, Command())
    command._setup_audit_environment = Mock(side_effect=RuntimeError("audit setup failed"))

    with pytest.raises(RuntimeError, match="audit setup failed"):
        command.handle(**_command_options())

    assert settings.DEBUG is True
