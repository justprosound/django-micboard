"""Tenant detection middleware for MSP deployments.

Attaches organization context to requests based on:
1. Session (user switched organization)
2. User's primary organization membership
3. Subdomain mapping (optional)
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast

from django.utils.functional import SimpleLazyObject

from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.services.shared.tenant_principal import TenantPrincipal

if TYPE_CHECKING:
    from django.http import HttpRequest

    from micboard.multitenancy.models import Organization


def _principal(request: HttpRequest) -> TenantPrincipal:
    """Resolve the request user's tenant facts once per request."""
    cached = getattr(request, "_micboard_tenant_principal", None)
    if cached is None:
        cached = TenantPrincipal.resolve(request.user)
        request._micboard_tenant_principal = cached  # type: ignore[attr-defined]
    return cast(TenantPrincipal, cached)


def _may_enter(request: HttpRequest, organization_id: int) -> bool:
    """Return whether the request user holds an active membership in the organization."""
    principal = _principal(request)
    return principal.unrestricted or any(
        membership.organization_id == organization_id for membership in principal.memberships
    )


def _get_org_from_session(request: HttpRequest) -> Any:
    from micboard.multitenancy.models import Organization

    if not hasattr(request, "session"):
        return None
    org_id = request.session.get("current_organization_id")
    if not org_id:
        return None

    try:
        org = Organization._default_manager.get(pk=org_id, is_active=True)
    except Organization.DoesNotExist:
        with suppress(Exception):
            del request.session["current_organization_id"]
        return None
    if _may_enter(request, org.pk):
        return org
    # The user lost access; forget the selection.
    with suppress(Exception):
        del request.session["current_organization_id"]
    return None


def _get_org_from_user_profile(request: HttpRequest) -> Any:
    if not request.user.is_authenticated:
        return None
    profile = getattr(request.user, "profile", None)
    org = getattr(profile, "default_organization", None)
    if org is not None and getattr(org, "is_active", False) and _may_enter(request, org.pk):
        return org
    return None


def _get_org_from_membership(request: HttpRequest) -> Any:
    if not request.user.is_authenticated:
        return None
    memberships = _principal(request).memberships
    if not memberships:
        return None

    from micboard.multitenancy.models import Organization

    return Organization._default_manager.filter(pk=memberships[0].organization_id).first()


def _get_org_from_subdomain(request: HttpRequest) -> Any:
    if not micboard_settings.subdomain_routing:
        return None
    host = request.get_host().split(":")[0]
    subdomain = host.split(".")[0]

    if not subdomain or subdomain == "www":
        return None

    root_domain = micboard_settings.root_domain
    if not root_domain or not host.endswith(root_domain):
        return None

    from micboard.multitenancy.models import Organization

    try:
        return Organization._default_manager.get(slug=subdomain, is_active=True)
    except Organization.DoesNotExist:
        return None


def get_current_organization(request: HttpRequest) -> Organization | None:
    """Detect current organization for request.

    Priority is:
      1. Session (user switched org via org selector)
      2. User's primary/default organization
      3. Subdomain mapping (if MICBOARD_SUBDOMAIN_ROUTING enabled)
    """
    if not micboard_settings.msp_enabled:
        return None

    # 1. Session
    org = _get_org_from_session(request)
    if org:
        return cast("Organization", org)

    # 2. User profile or membership
    org = _get_org_from_user_profile(request)
    if org:
        return cast("Organization", org)
    org = _get_org_from_membership(request)
    if org:
        return cast("Organization", org)

    # 3. Subdomain
    return cast("Organization | None", _get_org_from_subdomain(request))


def get_current_campus(request: HttpRequest) -> int | None:
    """Detect current campus for request (if any).

    A campus selected in the session is honoured only while the user may still enter it:
    through a membership limited to that campus, an organization-wide membership in the
    campus's organization, or unrestricted access. Otherwise the campus a membership in the
    current organization is limited to applies.

    Args:
        request: HTTP request

    Returns:
        Campus ID or None
    """
    if not micboard_settings.msp_enabled or not request.user.is_authenticated:
        return None

    from micboard.multitenancy.models import Campus

    principal = _principal(request)
    if hasattr(request, "session"):
        campus_id = request.session.get("current_campus_id")
        if campus_id:
            campus = Campus._default_manager.filter(pk=campus_id, is_active=True).first()
            if campus is not None and (
                principal.unrestricted
                or any(
                    membership.covers(
                        organization_id=campus.organization_id,
                        campus_id=campus.pk,
                    )
                    for membership in principal.memberships
                )
            ):
                return int(campus.pk)
            with suppress(Exception):
                del request.session["current_campus_id"]

    org = getattr(request, "organization", None)
    if org:
        for membership in principal.memberships:
            if membership.organization_id == org.pk and membership.campus_id is not None:
                return membership.campus_id
    return None


class TenantMiddleware:
    """Middleware to attach current organization and campus to request.

    Adds:
    - request.organization: Current Organization instance (or None)
    - request.campus_id: Current Campus ID (or None)
    """

    def __init__(self, get_response: Any) -> None:
        """Store the downstream response callable."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        """Populate request with tenant context before dispatching."""
        tenant_request: Any = request
        # Attach organization as lazy object (evaluated on access)
        tenant_request.organization = SimpleLazyObject(lambda: get_current_organization(request))

        # Attach campus ID (also lazy)
        tenant_request.campus_id = SimpleLazyObject(lambda: get_current_campus(request))

        response = self.get_response(request)
        return response
