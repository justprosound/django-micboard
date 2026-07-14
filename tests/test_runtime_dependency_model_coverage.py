"""Runtime configuration and optional-dependency contract coverage."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured

import pytest

import micboard
from micboard.apps import MicboardConfig
from micboard.models import device_specs
from micboard.utils import dependencies


def _app_config() -> MicboardConfig:
    return MicboardConfig("micboard", importlib.import_module("micboard"))


def test_app_config_requires_startup_before_config_access() -> None:
    """Callers get an actionable failure before Django runs app startup."""
    with (
        patch.object(MicboardConfig, "_resolved_config", None),
        pytest.raises(RuntimeError, match="not yet initialized"),
    ):
        MicboardConfig.get_config()


@pytest.mark.parametrize(
    "key", ["POLL_INTERVAL", "CACHE_TIMEOUT", "TRANSMITTER_INACTIVITY_SECONDS"]
)
def test_app_config_rejects_non_numeric_and_non_positive_values(key: str) -> None:
    """Every generic timing setting enforces the same positive-number contract."""
    app_config = _app_config()

    with pytest.raises(ImproperlyConfigured, match="must be a number"):
        app_config._validate_configuration({key: "slow"})
    with pytest.raises(ImproperlyConfigured, match="must be positive"):
        app_config._validate_configuration({key: 0})

    app_config._validate_configuration({key: 0.5})


def test_app_config_skips_background_registration_without_huey() -> None:
    """An application without the optional task extra remains startup-safe."""
    app_config = _app_config()
    with patch("micboard.utils.dependencies.huey_is_configured", return_value=False):
        app_config._register_background_tasks()


def test_app_config_registers_every_native_huey_entrypoint() -> None:
    """Startup decorates the complete task inventory through one native-Huey seam."""
    app_config = _app_config()
    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
        patch("micboard.utils.dependencies.register_huey_task") as register,
    ):
        app_config._register_background_tasks()

    assert register.call_count == 12
    assert {call.args[0].__name__ for call in register.call_args_list} == {
        "poll_charger_data",
        "check_manufacturer_api_health",
        "check_realtime_connection_health",
        "check_selected_api_server_connections",
        "start_sse_subscriptions",
        "start_shure_websocket_subscriptions",
        "cache_all_discovery_candidates",
        "run_discovery_sync_task",
        "run_manufacturer_discovery_task",
        "poll_api_server_device",
        "poll_manufacturer_devices",
        "refresh_selected_chassis",
    }


def test_app_config_context_processor_advice_handles_host_shapes(caplog) -> None:
    """Startup advice tolerates absent, invalid, and repeated template configuration."""
    app_config = _app_config()
    backend = "django.template.backends.django.DjangoTemplates"
    caplog.set_level(logging.INFO, logger="micboard.apps")

    with patch("django.conf.settings", SimpleNamespace()):
        app_config._recommend_context_processors()
    assert "no TEMPLATES configured" in caplog.text

    caplog.clear()
    templates = [
        "invalid",
        {"BACKEND": backend, "OPTIONS": "invalid"},
        {"BACKEND": "other", "OPTIONS": {}},
        {"BACKEND": backend, "OPTIONS": {}},
        {"BACKEND": backend, "OPTIONS": {}},
    ]
    with patch("django.conf.settings", SimpleNamespace(TEMPLATES=templates)):
        app_config._recommend_context_processors()
    assert caplog.text.count("micboard.context_processors.api_health") == 1

    caplog.clear()
    configured = [
        {
            "BACKEND": backend,
            "OPTIONS": {"context_processors": ["micboard.context_processors.api_health"]},
        }
    ]
    with patch("django.conf.settings", SimpleNamespace(TEMPLATES=configured)):
        app_config._recommend_context_processors()
    assert "recommends adding" not in caplog.text


def test_app_config_middleware_advice_handles_absent_and_complete_hosts(caplog) -> None:
    """Middleware advice is diagnostic only and never mutates host settings."""
    app_config = _app_config()
    caplog.set_level(logging.INFO, logger="micboard.apps")

    with patch("django.conf.settings", SimpleNamespace()):
        app_config._recommend_security_middleware()
    assert "no MIDDLEWARE configured" in caplog.text
    assert "django.middleware.security.SecurityMiddleware" in caplog.text

    caplog.clear()
    middleware = ["django.middleware.security.SecurityMiddleware"]
    with patch("django.conf.settings", SimpleNamespace(MIDDLEWARE=middleware)):
        app_config._recommend_security_middleware()
    assert "recommends adding" not in caplog.text


def test_filter_builder_has_a_safe_optional_dependency_fallback(monkeypatch) -> None:
    """Importing filters without django-filter yields inert placeholder classes."""
    from micboard import filters

    monkeypatch.setattr(filters, "HAS_DJANGO_FILTER", False)
    chassis_filter, unit_filter = filters._build_filter_classes()

    assert chassis_filter is unit_filter
    assert chassis_filter.__name__ == "UnavailableFilter"


def test_dependency_detection_covers_uninstalled_and_pre_setup_apps(monkeypatch) -> None:
    """Optional Django integrations require both importability and host configuration."""
    monkeypatch.setattr(dependencies, "is_installed", Mock(return_value=False))
    assert dependencies.is_django_app_configured("missing") is False

    monkeypatch.setattr(dependencies, "is_installed", Mock(return_value=True))
    monkeypatch.setattr(dependencies, "settings", SimpleNamespace(configured=False))
    assert dependencies.is_django_app_configured("available") is False

    monkeypatch.setattr(
        dependencies,
        "settings",
        SimpleNamespace(configured=True, INSTALLED_APPS=["broken.config", "target"]),
    )
    monkeypatch.setattr(dependencies.apps, "apps_ready", False)
    monkeypatch.setattr(dependencies, "import_string", Mock(side_effect=ImportError))
    assert dependencies.is_django_app_configured("available", "target") is True

    monkeypatch.setattr(
        dependencies,
        "settings",
        SimpleNamespace(configured=True, INSTALLED_APPS=["other.Config", "target"]),
    )
    monkeypatch.setattr(dependencies, "import_string", Mock(return_value=object()))
    assert dependencies.is_django_app_configured("available", "target") is True


def test_dependency_detection_accepts_app_config_classes(monkeypatch) -> None:
    """Pre-setup detection resolves an AppConfig class to its configured app name."""
    monkeypatch.setattr(dependencies, "is_installed", Mock(return_value=True))
    monkeypatch.setattr(
        dependencies,
        "settings",
        SimpleNamespace(configured=True, INSTALLED_APPS=["example.Config"]),
    )
    monkeypatch.setattr(dependencies.apps, "apps_ready", False)
    monkeypatch.setattr(dependencies, "import_string", Mock(return_value=MicboardConfig))

    assert dependencies.is_django_app_configured("micboard") is True


def test_huey_detection_and_registration_fail_closed(monkeypatch) -> None:
    """Task registration reports every missing native-Huey prerequisite."""
    dependencies.register_huey_task.cache_clear()
    monkeypatch.setattr(dependencies, "is_installed", Mock(return_value=False))
    assert dependencies.huey_is_configured() is False

    monkeypatch.setattr(dependencies, "is_installed", Mock(return_value=True))
    monkeypatch.setattr(dependencies, "settings", SimpleNamespace(configured=False))
    assert dependencies.huey_is_configured() is False

    monkeypatch.setattr(dependencies, "huey_is_configured", Mock(return_value=False))
    with pytest.raises(RuntimeError, match="Native Huey is not configured"):
        dependencies.register_huey_task(lambda: None)
    dependencies.register_huey_task.cache_clear()


def test_package_metadata_has_a_source_checkout_fallback(monkeypatch) -> None:
    """An unpackaged source tree exposes a stable PEP 440 fallback version."""
    monkeypatch.setattr(
        importlib.metadata,
        "version",
        Mock(side_effect=PackageNotFoundError),
    )
    reloaded = importlib.reload(micboard)
    assert reloaded.__version__ == "0+unknown"

    monkeypatch.undo()
    importlib.reload(micboard)


def test_device_spec_loader_handles_optional_yaml_and_resource_failures(monkeypatch) -> None:
    """Fixture loading degrades predictably when its optional dependency or file is absent."""
    monkeypatch.setattr(device_specs, "HAS_YAML", False)
    assert device_specs._load_device_specifications() == {}

    monkeypatch.setattr(device_specs, "HAS_YAML", True)
    monkeypatch.setattr(device_specs.importlib.resources, "files", Mock(side_effect=OSError))
    assert device_specs._load_device_specifications() == {}


def test_device_spec_loader_normalizes_empty_documents(monkeypatch) -> None:
    """An empty YAML document becomes an empty registry instead of None."""
    resource = Mock()
    resource.joinpath.return_value.read_text.return_value = ""
    monkeypatch.setattr(device_specs.importlib.resources, "files", Mock(return_value=resource))
    monkeypatch.setattr(device_specs.yaml, "safe_load", Mock(return_value=None))

    assert device_specs._load_device_specifications() == {}


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        (None, "ULXD4Q", None),
        ("shure", None, None),
        ("missing", "ULXD4Q", None),
        ("SHURE", "ULX-D 4Q", {"models": ["ULXD4Q"], "channels": 4}),
        ("shure", "unknown", None),
    ],
)
def test_device_spec_lookup_normalizes_identity(
    manufacturer: str | None,
    model: str | None,
    expected: dict | None,
    monkeypatch,
) -> None:
    """Model lookup is optional-safe and ignores case, spaces, and hyphens."""
    monkeypatch.setattr(
        device_specs,
        "DEVICE_SPECIFICATIONS",
        {"shure": {"ulxd": {"models": ["ULXD4Q"], "channels": 4}}},
    )
    assert device_specs.get_device_spec(manufacturer=manufacturer, model=model) == expected


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ({"channels": 8}, 8),
        ({"channels": "16"}, 16),
        ({"channels": object()}, 4),
        (None, 4),
    ],
)
def test_channel_count_normalizes_fixture_values(spec, expected: int, monkeypatch) -> None:
    """Channel counts accept numeric strings and fail closed on malformed fixture values."""
    monkeypatch.setattr(device_specs, "get_device_spec", Mock(return_value=spec))
    assert device_specs.get_channel_count(manufacturer="vendor", model="model") == expected


@pytest.mark.parametrize(
    ("spec", "role", "dante"),
    [
        ({"role": "transceiver", "dante": 1}, "transceiver", True),
        ({"role": 5, "dante": 0}, "receiver", False),
        (None, "receiver", False),
    ],
)
def test_device_role_and_dante_defaults(spec, role: str, dante: bool, monkeypatch) -> None:
    """Malformed or absent fixture metadata preserves conservative hardware defaults."""
    monkeypatch.setattr(device_specs, "get_device_spec", Mock(return_value=spec))
    assert device_specs.get_device_role(manufacturer="vendor", model="model") == role
    assert device_specs.get_dante_support(manufacturer="vendor", model="model") is dante
