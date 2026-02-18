"""Tenant detection middleware for MSP deployments.

Attaches organization context to requests based on:
1. Session (user switched organization)
2. User's primary organization membership
3. Subdomain mapping (optional)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.functional import SimpleLazyObject

if TYPE_CHECKING:
    from django.http import HttpRequest

    from micboard.multitenancy.models import Organization


def _get_org_from_session(request: HttpRequest):
    from micboard.multitenancy.models import Organization, OrganizationMembership

    if not hasattr(request, "session"):
        return None
    org_id = request.session.get("current_organization_id")
    if not org_id:
        return None

    try:
        org = Organization.objects.get(pk=org_id, is_active=True)
        # Verify user still has access
        if request.user.is_authenticated:
            if (
                request.user.is_superuser
                or OrganizationMembership.objects.filter(
                    user=request.user, organization=org, is_active=True
                ).exists()
            ):
                return org
            # User lost access, clear session
            del request.session["current_organization_id"]
    except Organization.DoesNotExist:
        # Organization deleted, clear session
        try:
            del request.session["current_organization_id"]
        except Exception:
            pass
    return None


def _get_org_from_user_profile(request: HttpRequest):
    if not request.user.is_authenticated:
        return None
    if hasattr(request.user, "profile") and hasattr(request.user.profile, "default_organization"):
        org = request.user.profile.default_organization
        if org and getattr(org, "is_active", False):
            return org
    return None


def _get_org_from_membership(request: HttpRequest):
    if not request.user.is_authenticated:
        return None
    from micboard.multitenancy.models import OrganizationMembership

    membership = (
        OrganizationMembership.objects.filter(user=request.user, is_active=True)
        .select_related("organization")
        .order_by("-created_at")
        .first()
    )

    if membership and getattr(membership.organization, "is_active", False):
        return membership.organization
    return None


def _get_org_from_subdomain(request: HttpRequest):
    if not getattr(settings, "MICBOARD_SUBDOMAIN_ROUTING", False):
        return None
    host = request.get_host().split(":")[0]
    subdomain = host.split(".")[0]

    if not subdomain or subdomain == "www":
        return None

    root_domain = getattr(settings, "MICBOARD_ROOT_DOMAIN", "")
    if not root_domain or not host.endswith(root_domain):
        return None

    from micboard.multitenancy.models import Organization

    try:
        return Organization.objects.get(slug=subdomain, is_active=True)
    except Organization.DoesNotExist:
        return None


def get_current_organization(request: HttpRequest) -> Organization | None:
    """Detect current organization for request.

    Priority is:
      1. Session (user switched org via org selector)
      2. User's primary/default organization
      3. Subdomain mapping (if MICBOARD_SUBDOMAIN_ROUTING enabled)
    """
    if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
        return None

    # 1. Session
    org = _get_org_from_session(request)
    if org:
        return org

    # 2. User profile or membership
    org = _get_org_from_user_profile(request)
    if org:
        return org
    org = _get_org_from_membership(request)
    if org:
        return org

    # 3. Subdomain
    return _get_org_from_subdomain(request)


def get_current_campus(request: HttpRequest) -> int | None:
    """Detect current campus for request (if any).

    Checks:
    1. Session (user switched campus)
    2. User's membership campus restriction

    Args:
        request: HTTP request

    Returns:
        Campus ID or None
    """
    if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
        return None

    from micboard.multitenancy.models import OrganizationMembership

    # Check session
    if hasattr(request, "session"):
        campus_id = request.session.get("current_campus_id")
        if campus_id:
            return campus_id

    # Check user's membership campus restriction
    if request.user.is_authenticated and hasattr(request, "organization"):
        org = request.organization
        if org:
            membership = OrganizationMembership.objects.filter(
                user=request.user, organization=org, is_active=True
            ).first()

            if membership and membership.campus_id:
                return membership.campus_id

    return None


class TenantMiddleware:
    """Middleware to attach current organization and campus to request.

    Adds:
    - request.organization: Current Organization instance (or None)
    - request.campus_id: Current Campus ID (or None)
    """

    def __init__(self, get_response):
        """Store the downstream response callable."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        """Populate request with tenant context before dispatching."""
        # Attach organization as lazy object (evaluated on access)
        request.organization = SimpleLazyObject(lambda: get_current_organization(request))

        # Attach campus ID (also lazy)
        request.campus_id = SimpleLazyObject(lambda: get_current_campus(request))

        response = self.get_response(request)
        return response
