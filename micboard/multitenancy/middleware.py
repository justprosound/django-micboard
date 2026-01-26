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


def get_current_organization(request: HttpRequest) -> Organization | None:
    """Detect current organization for request.

    Priority:
    1. Session (user switched org via org selector)
    2. User's primary/default organization
    3. Subdomain mapping (if MICBOARD_SUBDOMAIN_ROUTING enabled)

    Args:
        request: HTTP request

    Returns:
        Organization instance or None
    """
    if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
        return None

    # Import here to avoid circular imports
    from micboard.multitenancy.models import Organization, OrganizationMembership

    # 1. Check session for organization switching
    if hasattr(request, "session"):
        org_id = request.session.get("current_organization_id")
        if org_id:
            try:
                org = Organization.objects.get(pk=org_id, is_active=True)
                # Verify user still has access
                if request.user.is_authenticated:
                    if (
                        request.user.is_superuser
                        or OrganizationMembership.objects.filter(
                            user=request.user,
                            organization=org,
                            is_active=True,
                        ).exists()
                    ):
                        return org
                    # User lost access, clear session
                    del request.session["current_organization_id"]
            except Organization.DoesNotExist:
                # Organization deleted, clear session
                del request.session["current_organization_id"]

    # 2. Check user's default/primary organization
    if request.user.is_authenticated:
        # Try user profile first (if exists)
        if hasattr(request.user, "profile") and hasattr(
            request.user.profile, "default_organization"
        ):
            org = request.user.profile.default_organization
            if org and org.is_active:
                return org

        # Fallback to first active membership
        membership = (
            OrganizationMembership.objects.filter(user=request.user, is_active=True)
            .select_related("organization")
            .order_by("-created_at")
            .first()
        )

        if membership and membership.organization.is_active:
            return membership.organization

    # 3. Subdomain detection (optional)
    if getattr(settings, "MICBOARD_SUBDOMAIN_ROUTING", False):
        host = request.get_host().split(":")[0]  # Strip port
        subdomain = host.split(".")[0]

        # Skip if not a subdomain or is 'www'
        if subdomain and subdomain != "www":
            root_domain = getattr(settings, "MICBOARD_ROOT_DOMAIN", "")
            if root_domain and host.endswith(root_domain):
                try:
                    return Organization.objects.get(slug=subdomain, is_active=True)
                except Organization.DoesNotExist:
                    pass

    return None


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
