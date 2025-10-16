"""
Tests for micboard package structure and PyPI Django reusable app standards.

This test module validates that the micboard package meets Django reusable app standards:
- Proper package structure
- Clean imports
- Version management
- Django compatibility
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import django
import pytest


class TestPackageStructure:
    """Test Django reusable app package structure."""

    def test_package_imports(self):
        """Test that main package imports work correctly."""
        import micboard

        assert hasattr(micboard, "__version__")
        assert hasattr(micboard, "default_app_config")

    def test_models_import(self):
        """Test that models can be imported from package."""
        from micboard.models import (
            Alert,
            Channel,
            DeviceAssignment,
            DiscoveredDevice,
            Group,
            Location,
            MicboardConfig,
            MonitoringGroup,
            Receiver,
            Transmitter,
            UserAlertPreference,
        )

        # Verify all expected models are present
        expected_models = [
            Receiver,
            Channel,
            Transmitter,
            DeviceAssignment,
            Alert,
            UserAlertPreference,
            Group,
            MicboardConfig,
            DiscoveredDevice,
            Location,
            MonitoringGroup,
        ]
        assert all(model is not None for model in expected_models)

    def test_admin_imports(self):
        """Test that admin classes can be imported."""
        from micboard.admin import (
            AlertAdmin,
            ChannelAdmin,
            DeviceAssignmentAdmin,
            DiscoveredDeviceAdmin,
            GroupAdmin,
            LocationAdmin,
            MicboardConfigAdmin,
            MonitoringGroupAdmin,
            ReceiverAdmin,
            TransmitterAdmin,
            UserAlertPreferenceAdmin,
        )

        # Verify all admin classes are present
        expected_admins = [
            ReceiverAdmin,
            ChannelAdmin,
            TransmitterAdmin,
            DeviceAssignmentAdmin,
            UserAlertPreferenceAdmin,
            AlertAdmin,
            GroupAdmin,
            MicboardConfigAdmin,
            DiscoveredDeviceAdmin,
            LocationAdmin,
            MonitoringGroupAdmin,
        ]
        assert all(admin is not None for admin in expected_admins)

    def test_serializers_import(self):
        """Test that serializers can be imported."""
        from micboard.serializers import (
            serialize_channel,
            serialize_discovered_device,
            serialize_group,
            serialize_receiver,
            serialize_receiver_detail,
            serialize_receiver_summary,
            serialize_receivers,
            serialize_transmitter,
        )

        # Verify all serializers are callable
        serializers = [
            serialize_channel,
            serialize_discovered_device,
            serialize_group,
            serialize_receiver,
            serialize_receiver_detail,
            serialize_receiver_summary,
            serialize_receivers,
            serialize_transmitter,
        ]
        assert all(callable(s) for s in serializers)

    def test_shure_api_imports(self):
        """Test that Shure API client can be imported."""
        from micboard.manufacturers.shure.client import (
            ShureAPIError,
            ShureAPIRateLimitError,
            ShureSystemAPIClient,
        )
        from micboard.manufacturers.shure.transformers import ShureDataTransformer
        from micboard.manufacturers.shure.websocket import ShureWebSocketError

        # Verify all classes are present
        expected_classes = [
            ShureAPIError,
            ShureAPIRateLimitError,
            ShureDataTransformer,
            ShureSystemAPIClient,
            ShureWebSocketError,
        ]
        assert all(cls is not None for cls in expected_classes)

    def test_views_import(self):
        """Test that views can be imported."""
        from micboard.views import api, dashboard

        assert hasattr(api, "data_json")
        assert hasattr(api, "api_health")
        assert hasattr(dashboard, "index")


class TestDjangoCompatibility:
    """Test Django version compatibility."""

    def test_django_version_support(self):
        """Test that Django version is 4.2 or higher."""
        django_version = tuple(map(int, django.__version__.split(".")[:2]))
        assert django_version >= (4, 2), f"Django {django.__version__} is below minimum 4.2"

    def test_model_field_types(self):
        """Test that models use modern Django field types."""
        from micboard.models import Receiver

        # Check that GenericIPAddressField is used (not deprecated IPAddressField)
        ip_field = Receiver._meta.get_field("ip")
        assert ip_field.__class__.__name__ == "GenericIPAddressField"

    def test_no_deprecated_imports(self):
        """Test that code doesn't use deprecated Django imports."""
        # Check that django.utils.six is not imported (removed in Django 4.0)
        micboard_path = Path(__file__).parent.parent / "micboard"

        for py_file in micboard_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            content = py_file.read_text()
            assert "from django.utils import six" not in content, (
                f"Deprecated six import found in {py_file}"
            )
            assert "django.utils.six" not in content, f"Deprecated six reference found in {py_file}"


class TestAppConfiguration:
    """Test Django app configuration."""

    def test_apps_config_exists(self):
        """Test that apps.py is properly configured."""
        from micboard.apps import MicboardConfig

        assert MicboardConfig.name == "micboard"
        assert hasattr(MicboardConfig, "default_auto_field")

    def test_default_auto_field(self):
        """Test that default_auto_field is set correctly for Django 4.2+."""
        from micboard.apps import MicboardConfig

        # Django 4.2+ should use BigAutoField
        assert MicboardConfig.default_auto_field == "django.db.models.BigAutoField"


class TestURLConfiguration:
    """Test URL configuration."""

    def test_urls_importable(self):
        """Test that URL configuration can be imported."""
        from micboard import urls

        assert hasattr(urls, "urlpatterns")

    def test_url_patterns_defined(self):
        """Test that URL patterns are properly defined."""
        from micboard.urls import urlpatterns

        assert len(urlpatterns) > 0, "No URL patterns defined"

    def test_no_deprecated_url_patterns(self):
        """Test that url() is not used (deprecated in Django 4.0)."""
        # Check source code for deprecated url() usage
        import inspect

        from micboard import urls

        source = inspect.getsource(urls)
        assert "from django.conf.urls import url" not in source
        # path() or re_path() should be used instead


class TestDependencies:
    """Test package dependencies."""

    def test_required_packages_installed(self):
        """Test that required packages are installed."""
        required_packages = [
            "django",
            "channels",
            "requests",
            "websockets",
        ]

        for package in required_packages:
            try:
                importlib.import_module(package)
            except ImportError:
                pytest.fail(f"Required package '{package}' is not installed")

    def test_python_version(self):
        """Test that Python version is 3.9 or higher."""
        assert sys.version_info >= (3, 9), f"Python {sys.version} is below minimum 3.9"


class TestPackageMetadata:
    """Test package metadata for PyPI compliance."""

    def test_version_string(self):
        """Test that version string follows semantic versioning."""
        import micboard

        version = micboard.__version__
        # Check format: major.minor.patch or major.minor.patch.devN
        parts = version.split(".")
        assert len(parts) >= 3, f"Version '{version}' doesn't follow semver"

        # First three parts should be integers
        assert all(p.isdigit() or (i == 3 and "dev" in p) for i, p in enumerate(parts[:4])), (
            f"Version '{version}' has invalid format"
        )

    def test_package_structure(self):
        """Test that package has required files for PyPI."""
        package_root = Path(__file__).parent.parent

        # Check for required files
        required_files = [
            "README.md",
            "LICENSE",
            "pyproject.toml",
            "MANIFEST.in",
        ]

        for filename in required_files:
            filepath = package_root / filename
            assert filepath.exists(), f"Required file '{filename}' not found"

    def test_manifest_includes_templates(self):
        """Test that MANIFEST.in includes templates and static files."""
        package_root = Path(__file__).parent.parent
        manifest = package_root / "MANIFEST.in"

        content = manifest.read_text()
        assert "recursive-include micboard/templates" in content
        assert "recursive-include micboard/static" in content


class TestCodeQuality:
    """Test code quality standards."""

    def test_all_modules_have_docstrings(self):
        """Test that all Python modules have docstrings."""
        micboard_path = Path(__file__).parent.parent / "micboard"

        for py_file in micboard_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or py_file.name.startswith("test_"):
                continue

            content = py_file.read_text()
            # Skip empty __init__ files
            if py_file.name == "__init__.py" and len(content.strip()) < 50:
                continue

            # Check for module docstring
            assert content.strip().startswith('"""') or content.strip().startswith("'''"), (
                f"Module {py_file} missing docstring"
            )

    def test_models_have_str_methods(self):
        """Test that all models have __str__ methods."""
        from micboard import models

        model_classes = [
            models.Receiver,
            models.Channel,
            models.Transmitter,
            models.DeviceAssignment,
            models.Alert,
            models.Group,
            models.Location,
            models.MonitoringGroup,
        ]

        for model_cls in model_classes:
            assert hasattr(model_cls, "__str__"), f"{model_cls.__name__} missing __str__ method"
            # Verify it's not just inherited from Model
            assert "__str__" in model_cls.__dict__, (
                f"{model_cls.__name__}.__str__ not explicitly defined"
            )

    def test_models_have_meta_verbose_names(self):
        """Test that models have proper Meta configuration."""
        from micboard import models

        model_classes = [
            models.Receiver,
            models.Channel,
            models.Transmitter,
            models.DeviceAssignment,
            models.Alert,
        ]

        for model_cls in model_classes:
            assert hasattr(model_cls, "_meta"), f"{model_cls.__name__} missing _meta"
            meta = model_cls._meta
            assert hasattr(meta, "verbose_name"), (
                f"{model_cls.__name__} missing verbose_name in Meta"
            )
