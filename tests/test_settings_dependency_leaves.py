"""Regression coverage for dependency-free settings policy modules."""

from __future__ import annotations

import ast
import inspect
from types import ModuleType

from django.test import SimpleTestCase

from micboard.apps import MicboardConfig
from micboard.settings import defaults, scope_policy
from micboard.settings.defaults import DEFAULT_CONFIG
from micboard.settings.scope_policy import matches_definition_scope, resolve_scope


def _imported_modules(module: ModuleType) -> set[str]:
    """Return absolute module names imported by ``module``."""
    imported_modules: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    return imported_modules


class SettingsDefaultsTests(SimpleTestCase):
    """Package defaults must not be owned by the Django startup module."""

    def test_defaults_live_outside_app_config(self) -> None:
        """Settings consumers can load defaults without importing ``micboard.apps``."""
        self.assertFalse(hasattr(MicboardConfig, "default_config"))
        self.assertFalse(hasattr(MicboardConfig, "get_config"))
        self.assertEqual(
            DEFAULT_CONFIG,
            {
                "POLL_INTERVAL": 5,
                "CACHE_TIMEOUT": 30,
                "TRANSMITTER_INACTIVITY_SECONDS": 10,
            },
        )

    def test_leaf_modules_do_not_import_django_or_other_micboard_modules(self) -> None:
        """Defaults and scope policy stay safe to import from every architecture layer."""
        for module in (defaults, scope_policy):
            with self.subTest(module=module.__name__):
                self.assertFalse(
                    any(
                        imported == "django"
                        or imported.startswith("django.")
                        or imported == "micboard"
                        or imported.startswith("micboard.")
                        for imported in _imported_modules(module)
                    )
                )


class SettingsScopePolicyTests(SimpleTestCase):
    """Exact-scope policy must remain independent from Django models."""

    def test_resolve_scope_requires_zero_or_one_target(self) -> None:
        """Zero identifiers select global; one selects its scope; mixed targets fail."""
        cases = (
            ((None, None, None), "global"),
            ((1, None, None), "organization"),
            ((None, 2, None), "site"),
            ((None, None, 3), "manufacturer"),
            ((1, 2, None), None),
            ((1, None, 3), None),
            ((None, 2, 3), None),
            ((1, 2, 3), None),
        )

        for identifiers, expected in cases:
            with self.subTest(identifiers=identifiers):
                self.assertEqual(
                    resolve_scope(
                        organization_id=identifiers[0],
                        site_id=identifiers[1],
                        manufacturer_id=identifiers[2],
                    ),
                    expected,
                )

    def test_definition_scope_must_match_resolved_target(self) -> None:
        """Definitions accept only identifiers for their declared exact scope."""
        self.assertTrue(
            matches_definition_scope(
                definition_scope="organization",
                organization_id=1,
                site_id=None,
                manufacturer_id=None,
            )
        )
        self.assertFalse(
            matches_definition_scope(
                definition_scope="organization",
                organization_id=1,
                site_id=2,
                manufacturer_id=None,
            )
        )
