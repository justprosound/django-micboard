"""Tenant isolation contracts for the optional sortable admin integration."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.db import IntegrityError
from django.test import RequestFactory, override_settings
from django.urls import reverse

import pytest

from micboard.models.hardware.charger import Charger
from tests.factories.base import UserFactory
from tests.factories.hardware import ChargerFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory

pytestmark = pytest.mark.django_db


class ReadReplicaRouter:
    """Route reads to an absent replica so unsafe reorder reads fail loudly."""

    def db_for_read(self, model: object, **hints: object) -> str | None:
        return "absent_replica" if model is Charger else None

    def db_for_write(self, model: object, **hints: object) -> str:
        return "default"


def _sortable_url() -> str:
    model_admin = admin.site._registry[Charger]
    return reverse(f"admin:{model_admin._get_update_url_name()}")


def _tenant_charger(*, organization, order: int) -> Charger:
    building = BuildingFactory(organization_id=organization.pk)
    location = LocationFactory(building=building)
    return ChargerFactory(location=location, order=order)


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_sortable_admin_rejects_mixed_tenant_reorder_without_partial_write(
    django_client,
) -> None:
    """A submitted foreign primary key cannot alter either tenant's order."""
    own_organization = OrganizationFactory()
    foreign_organization = OrganizationFactory()
    user = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    user.user_permissions.add(Permission.objects.get(codename="change_charger"))
    OrganizationMembershipFactory(
        user=user,
        organization=own_organization,
        campus=None,
        role="admin",
    )
    own_charger = _tenant_charger(organization=own_organization, order=1)
    foreign_charger = _tenant_charger(organization=foreign_organization, order=2)
    django_client.force_login(user)

    response = django_client.post(
        _sortable_url(),
        {"updatedItems": [[own_charger.pk, 10], [foreign_charger.pk, 99]]},
        content_type="application/json",
    )

    assert response.status_code == 400
    own_charger.refresh_from_db()
    foreign_charger.refresh_from_db()
    assert own_charger.order == 1
    assert foreign_charger.order == 2


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_sortable_admin_allows_exact_admin_scope_and_denies_read_only_role(
    django_client,
) -> None:
    """Tenant admins reorder owned rows while viewers with model perms remain read-only."""
    organization = OrganizationFactory()
    charger = _tenant_charger(organization=organization, order=1)
    user = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    user.user_permissions.add(Permission.objects.get(codename="change_charger"))
    membership = OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role="admin",
    )
    django_client.force_login(user)

    response = django_client.post(
        _sortable_url(),
        {"updatedItems": [[charger.pk, 7]]},
        content_type="application/json",
    )

    assert response.status_code == 200
    charger.refresh_from_db()
    assert charger.order == 7

    membership.role = "viewer"
    membership.save(update_fields=["role"])
    response = django_client.post(
        _sortable_url(),
        {"updatedItems": [[charger.pk, 11]]},
        content_type="application/json",
    )

    assert response.status_code == 403
    charger.refresh_from_db()
    assert charger.order == 7


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
    DATABASE_ROUTERS=[f"{__name__}.ReadReplicaRouter"],
)
def test_sortable_admin_authorizes_and_writes_on_primary_database(django_client) -> None:
    """A read router cannot split reorder authorization from the primary write."""
    organization = OrganizationFactory()
    charger = _tenant_charger(organization=organization, order=1)
    user = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    user.user_permissions.add(Permission.objects.get(codename="change_charger"))
    OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role="admin",
    )
    django_client.force_login(user)

    response = django_client.post(
        _sortable_url(),
        {"updatedItems": [[charger.pk, 8]]},
        content_type="application/json",
    )

    assert response.status_code == 200
    charger.refresh_from_db(using="default")
    assert charger.order == 8


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_sortable_admin_disables_globally_ranked_page_move_actions(monkeypatch) -> None:
    """Tenant changelists cannot invoke adminsortable2's global page movers."""
    organization = OrganizationFactory()
    user = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    user.user_permissions.add(Permission.objects.get(codename="change_charger"))
    OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role="admin",
    )
    for order in range(1, 4):
        _tenant_charger(organization=organization, order=order)

    request = RequestFactory().get("/admin/micboard/charger/", {"p": 2})
    request.user = user
    model_admin = admin.site._registry[Charger]
    monkeypatch.setattr(model_admin, "list_per_page", 1)
    monkeypatch.setattr(model_admin, "enable_sorting", True)

    actions = model_admin.get_actions(request)

    assert {
        "move_to_exact_page",
        "move_to_back_page",
        "move_to_forward_page",
        "move_to_first_page",
        "move_to_last_page",
    }.isdisjoint(actions)


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_sortable_admin_rejects_malformed_batches_and_rolls_back_write_errors(
    django_client,
    caplog,
) -> None:
    """Malformed or failed reorder batches never partially update stored ranks."""
    organization = OrganizationFactory()
    charger = _tenant_charger(organization=organization, order=1)
    user = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    user.user_permissions.add(Permission.objects.get(codename="change_charger"))
    OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role="admin",
    )
    django_client.force_login(user)
    url = _sortable_url()
    private_value = "private-sortable-value\nforged-log-entry"

    assert django_client.get(url).status_code == 405
    invalid_payloads = (
        [],
        {},
        {"updatedItems": []},
        {"updatedItems": [[charger.pk]]},
        {"updatedItems": [[charger.pk, 2], [charger.pk, 3]]},
        {"updatedItems": [[charger.pk, None]]},
        {"updatedItems": [[private_value, 2]]},
    )
    for payload in invalid_payloads:
        response = django_client.post(
            url,
            json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400

    assert private_value not in caplog.text
    assert "forged-log-entry" not in caplog.text
    assert "ValueError: error details redacted" in caplog.text

    with patch.object(Charger._default_manager, "using") as using:
        using.return_value.bulk_update.side_effect = IntegrityError("rank collision")
        response = django_client.post(
            url,
            json.dumps({"updatedItems": [[charger.pk, 10]]}),
            content_type="application/json",
        )
    assert response.status_code == 400
    charger.refresh_from_db()
    assert charger.order == 1
