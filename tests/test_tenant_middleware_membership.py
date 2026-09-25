"""The tenant middleware only attaches a tenant the user can still enter.

Organization and campus selections live in the session and the user profile, both of which
outlive a membership. Each is honoured only while an active membership, or unrestricted
access, still covers it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.contrib.auth import get_user_model
from django.test import override_settings

import pytest

from micboard.multitenancy.middleware import (
    _get_org_from_membership,
    _get_org_from_session,
    _get_org_from_user_profile,
    get_current_campus,
)
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("_msp"),
]


@pytest.fixture
def _msp(settings) -> None:
    settings.MICBOARD_MSP_ENABLED = True
    settings.MICBOARD_ALLOW_CROSS_ORG_VIEW = False


def _request(user: Any, **session: Any) -> Any:
    return SimpleNamespace(user=user, session=dict(session), get_host=lambda: "tenant.test")


@pytest.fixture
def tenants() -> SimpleNamespace:
    home = Organization.objects.create(name="Home", slug="home")
    foreign = Organization.objects.create(name="Foreign", slug="foreign")
    return SimpleNamespace(
        home=home,
        foreign=foreign,
        home_campus=Campus.objects.create(organization=home, name="North", slug="north"),
        foreign_campus=Campus.objects.create(organization=foreign, name="South", slug="south"),
    )


def _member(username: str, organization: Organization, **extra: Any) -> Any:
    user = get_user_model().objects.create_user(username=username)
    OrganizationMembership.objects.create(user=user, organization=organization, **extra)
    return user


def test_session_organization_is_kept_for_a_member(tenants: SimpleNamespace) -> None:
    request = _request(_member("member", tenants.home), current_organization_id=tenants.home.pk)

    assert _get_org_from_session(request) == tenants.home


def test_session_organization_is_forgotten_once_access_is_gone(tenants: SimpleNamespace) -> None:
    request = _request(_member("member", tenants.home), current_organization_id=tenants.foreign.pk)

    assert _get_org_from_session(request) is None
    assert "current_organization_id" not in request.session


def test_superuser_without_cross_org_view_needs_a_membership(tenants: SimpleNamespace) -> None:
    """A tenant-limited superuser cannot select a foreign organization through the session."""
    superuser = get_user_model().objects.create_superuser(username="root", password="unused")
    request = _request(superuser, current_organization_id=tenants.foreign.pk)

    assert _get_org_from_session(request) is None


@override_settings(MICBOARD_ALLOW_CROSS_ORG_VIEW=True)
def test_superuser_with_cross_org_view_may_select_any_organization(
    tenants: SimpleNamespace,
) -> None:
    superuser = get_user_model().objects.create_superuser(username="root", password="unused")
    request = _request(superuser, current_organization_id=tenants.foreign.pk)

    assert _get_org_from_session(request) == tenants.foreign


def test_profile_default_organization_requires_a_membership(tenants: SimpleNamespace) -> None:
    """A host project's profile default cannot outlast the membership it pointed at."""
    member = _member("member", tenants.home)

    def user_with_default(organization: Organization) -> Any:
        return SimpleNamespace(
            pk=member.pk,
            is_authenticated=True,
            is_active=True,
            is_superuser=False,
            profile=SimpleNamespace(default_organization=organization),
        )

    assert _get_org_from_user_profile(_request(user_with_default(tenants.foreign))) is None
    assert _get_org_from_user_profile(_request(user_with_default(tenants.home))) == tenants.home


def test_membership_fallback_skips_an_inactive_organization(tenants: SimpleNamespace) -> None:
    user = _member("member", tenants.home)
    retired = Organization.objects.create(name="Retired", slug="retired", is_active=False)
    OrganizationMembership.objects.create(user=user, organization=retired)

    assert _get_org_from_membership(_request(user)) == tenants.home


def test_session_campus_is_honoured_only_while_a_membership_covers_it(
    tenants: SimpleNamespace,
) -> None:
    """A campus id in the session is not trusted on its own."""
    user = _member("member", tenants.home)

    request = _request(user, current_campus_id=tenants.home_campus.pk)
    assert get_current_campus(request) == tenants.home_campus.pk

    request = _request(user, current_campus_id=tenants.foreign_campus.pk)
    assert get_current_campus(request) is None
    assert "current_campus_id" not in request.session


def test_campus_limited_membership_supplies_the_current_campus(tenants: SimpleNamespace) -> None:
    user = _member("member", tenants.home, campus=tenants.home_campus)
    request = _request(user)
    request.organization = tenants.home

    assert get_current_campus(request) == tenants.home_campus.pk


def test_anonymous_request_has_no_campus() -> None:
    anonymous = SimpleNamespace(is_authenticated=False, is_superuser=False)

    assert get_current_campus(_request(anonymous, current_campus_id=1)) is None
