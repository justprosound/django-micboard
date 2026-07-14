"""Branch contracts for the public settings-service seam."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.sites.models import Site
from django.test import override_settings

import pytest

from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings.dtos import SettingsVisibilityScope
from micboard.services.settings.presentation_service import SettingsPresentationService
from micboard.services.settings.settings_service import SettingsService
from micboard.services.settings.visibility_service import SettingsVisibilityService


def test_settings_resolution_honors_each_remaining_fallback_source() -> None:
    service = SettingsService()
    service._registry = MagicMock()
    service._registry.get.return_value = "database"

    assert service.get("custom") == "database"

    service._registry.get.return_value = None
    assert service.get("POLL_INTERVAL") == 5

    service._registry.get_definition_default.return_value = "definition"
    assert service.get("definition_only") == "definition"


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=True,
)
def test_visibility_allows_cross_organization_superuser_when_site_isolation_is_off() -> None:
    scope = SettingsVisibilityService().for_user(
        user=SimpleNamespace(is_superuser=True),
    )

    assert SettingsVisibilityService.is_unrestricted(scope)


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_visibility_fails_closed_when_optional_tenant_app_is_unavailable() -> None:
    with patch(
        "micboard.services.settings.visibility_service.apps.is_installed",
        return_value=False,
    ):
        scope = SettingsVisibilityService().for_user(
            user=SimpleNamespace(is_superuser=False),
        )

    assert scope == SettingsVisibilityScope(
        organization_ids=frozenset(),
        site_ids=frozenset(),
        manufacturer_ids=frozenset(),
    )


@pytest.mark.django_db
def test_visibility_filters_apply_unrestricted_explicit_and_empty_scope_sets() -> None:
    definition = SettingDefinition.objects.create(
        key="visibility_filter_contract",
        label="Visibility filter contract",
        default_value="default",
    )
    site = Site.objects.create(domain="visibility.test", name="Visibility")
    Setting.objects.bulk_create(
        [
            Setting(definition=definition, value="global"),
            Setting(definition=definition, organization_id=11, value="organization"),
            Setting(definition=definition, site=site, value="site"),
            Setting(definition=definition, manufacturer_id=22, value="manufacturer"),
        ]
    )
    service = SettingsVisibilityService()

    unrestricted = SettingsVisibilityScope()
    assert set(
        Setting.objects.filter(service.build_filter(unrestricted)).values_list("value", flat=True)
    ) == {"global", "organization", "site", "manufacturer"}

    explicit = SettingsVisibilityScope(
        organization_ids=frozenset({11}),
        site_ids=frozenset({site.pk}),
        manufacturer_ids=frozenset({22}),
    )
    assert set(
        Setting.objects.filter(service.build_filter(explicit)).values_list("value", flat=True)
    ) == {"global", "organization", "site", "manufacturer"}
    assert set(
        Setting.objects.filter(service.build_management_filter(explicit)).values_list(
            "value", flat=True
        )
    ) == {"organization", "site", "manufacturer"}

    empty = SettingsVisibilityScope(
        organization_ids=frozenset(),
        site_ids=frozenset(),
        manufacturer_ids=frozenset(),
    )
    assert list(
        Setting.objects.filter(service.build_filter(empty)).values_list("value", flat=True)
    ) == ["global"]
    assert not Setting.objects.filter(service.build_management_filter(empty)).exists()


@pytest.mark.parametrize(
    ("identifiers", "expected"),
    [
        ({"organization_id": None, "site_id": None, "manufacturer_id": None}, "global"),
        ({"organization_id": 1, "site_id": None, "manufacturer_id": None}, "organization"),
        ({"organization_id": None, "site_id": 2, "manufacturer_id": None}, "site"),
        ({"organization_id": None, "site_id": None, "manufacturer_id": 3}, "manufacturer"),
        ({"organization_id": 1, "site_id": 2, "manufacturer_id": None}, None),
    ],
)
def test_visibility_scope_helpers_delegate_exact_scope_rules(
    identifiers: dict[str, int | None],
    expected: str | None,
) -> None:
    service = SettingsVisibilityService()

    assert service.resolve_scope(**identifiers) == expected
    if expected is not None:
        assert service.matches_definition_scope(definition_scope=expected, **identifiers)


@pytest.mark.parametrize(
    ("scope", "identifiers", "expected"),
    [
        (SettingsVisibilityScope(), (None, None, None), True),
        (
            SettingsVisibilityScope(
                organization_ids=frozenset(),
                site_ids=frozenset(),
                manufacturer_ids=frozenset(),
            ),
            (None, None, None),
            False,
        ),
        (SettingsVisibilityScope(), (1, 2, None), False),
        (SettingsVisibilityScope(organization_ids=frozenset({1})), (1, None, None), True),
        (SettingsVisibilityScope(organization_ids=frozenset({1})), (2, None, None), False),
        (SettingsVisibilityScope(site_ids=frozenset({1})), (None, 1, None), True),
        (SettingsVisibilityScope(site_ids=frozenset({1})), (None, 2, None), False),
        (SettingsVisibilityScope(manufacturer_ids=frozenset({1})), (None, None, 1), True),
        (SettingsVisibilityScope(manufacturer_ids=frozenset({1})), (None, None, 2), False),
    ],
)
def test_visibility_authorizes_only_identifiers_in_scope(
    scope: SettingsVisibilityScope,
    identifiers: tuple[int | None, int | None, int | None],
    expected: bool,
) -> None:
    organization_id, site_id, manufacturer_id = identifiers

    assert (
        SettingsVisibilityService.can_manage_scope(
            scope,
            organization_id=organization_id,
            site_id=site_id,
            manufacturer_id=manufacturer_id,
        )
        is expected
    )


def test_presentation_formats_safe_values_and_fails_closed_for_unknown_keys() -> None:
    safe = SimpleNamespace(key="API_TIMEOUT")
    unknown = SimpleNamespace(key="provider_token")

    assert SettingsPresentationService.format_value(safe, 30) == "30"
    assert SettingsPresentationService.format_value(unknown, "secret") == "••••••"
    assert SettingsPresentationService.format_value(safe, None) == "—"


def test_presentation_skips_optional_organization_lookup_when_tenancy_is_disabled() -> None:
    with patch(
        "micboard.services.settings.presentation_service.apps.is_installed",
        return_value=False,
    ):
        assert SettingsPresentationService._resolve_organization_names({1}) == {}


@pytest.mark.django_db
def test_presentation_diff_includes_global_fallback_and_site_override() -> None:
    site = Site.objects.create(domain="presentation.test", name="Presentation site")
    definition = SettingDefinition.objects.create(
        key="api_timeout",
        label="API timeout",
        scope=SettingDefinition.SCOPE_SITE,
        setting_type=SettingDefinition.TYPE_INTEGER,
        default_value="10",
    )
    Setting.objects.create(definition=definition, value="20")
    Setting.objects.create(definition=definition, site=site, value="30")

    context = SettingsPresentationService().get_diff(
        user=SimpleNamespace(is_superuser=True),
    )

    assert context["overrides"] == [
        {
            "key": "api_timeout",
            "label": "API timeout",
            "global": "20",
            "org_overrides": [],
            "site_overrides": [{"label": "Presentation site", "value": "30"}],
            "mfg_overrides": [],
        }
    ]
