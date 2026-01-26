"""Multi-tenancy settings for django-micboard.

Include in your settings.py:
    from micboard.settings.multitenancy import *

Or customize individual settings as needed.
"""

from __future__ import annotations

# ==============================================================================
# MULTI-SITE CONFIGURATION
# ==============================================================================

# Enable basic multi-site mode (requires django.contrib.sites)
# When True, devices/buildings are filtered by Django Site
MICBOARD_MULTI_SITE_MODE = False

# Site ID for single-site deployments (Django default)
# SITE_ID = 1  # Set in main settings.py

# ==============================================================================
# MSP (MANAGED SERVICE PROVIDER) CONFIGURATION
# ==============================================================================

# Enable full MSP features (requires MULTI_SITE_MODE=True)
# Adds Organization and Campus models for multi-tenant isolation
MICBOARD_MSP_ENABLED = False

# Site isolation strategy
# Options:
#   'none' - No isolation (single-site, monitoring groups only)
#   'site' - Filter by Django Site
#   'organization' - Filter by Organization (requires MSP_ENABLED)
#   'campus' - Filter by Campus (requires MSP_ENABLED)
MICBOARD_SITE_ISOLATION = "none"

# ==============================================================================
# CROSS-ORGANIZATION ACCESS
# ==============================================================================

# Allow superusers to view all organizations
# If False, superusers are limited to their assigned organizations
MICBOARD_ALLOW_CROSS_ORG_VIEW = True

# Allow users to switch between organizations (if they have multiple memberships)
MICBOARD_ALLOW_ORG_SWITCHING = True

# ==============================================================================
# SUBDOMAIN ROUTING (OPTIONAL)
# ==============================================================================

# Enable subdomain-based organization routing
# Example: university-a.micboard.example.com → Organization(slug='university-a')
MICBOARD_SUBDOMAIN_ROUTING = False

# Root domain for subdomain routing
# MICBOARD_ROOT_DOMAIN = 'micboard.example.com'

# ==============================================================================
# MIDDLEWARE CONFIGURATION
# ==============================================================================

# Middleware is conditionally added based on feature flags
# Add to your MIDDLEWARE setting:
#
# if MICBOARD_MULTI_SITE_MODE or MICBOARD_MSP_ENABLED:
#     MIDDLEWARE += ['micboard.multitenancy.middleware.TenantMiddleware']

# ==============================================================================
# ADMIN INTERFACE
# ==============================================================================

# Show organization selector in admin navbar (MSP mode)
MICBOARD_ADMIN_ORG_SELECTOR = True

# Default organization for new users (optional)
# MICBOARD_DEFAULT_ORGANIZATION_ID = 1

# ==============================================================================
# DEVICE LIMITS
# ==============================================================================

# Global device limit (across all organizations)
# None = unlimited
MICBOARD_GLOBAL_DEVICE_LIMIT = None

# Warn when organization reaches X% of device limit
MICBOARD_DEVICE_LIMIT_WARNING_THRESHOLD = 0.9  # 90%

# ==============================================================================
# EXAMPLE: SINGLE-SITE CONFIGURATION
# ==============================================================================
"""
# Minimal configuration for single-site deployment
MICBOARD_MULTI_SITE_MODE = False
MICBOARD_MSP_ENABLED = False
MICBOARD_SITE_ISOLATION = 'none'
"""

# ==============================================================================
# EXAMPLE: MULTI-CAMPUS ENTERPRISE
# ==============================================================================
"""
# University with multiple campuses, single organization
INSTALLED_APPS = [
    'django.contrib.sites',
    # ... other apps
]

SITE_ID = 1
MICBOARD_MULTI_SITE_MODE = True
MICBOARD_MSP_ENABLED = True
MICBOARD_SITE_ISOLATION = 'campus'
MICBOARD_ALLOW_ORG_SWITCHING = False  # Single organization

MIDDLEWARE += ['micboard.multitenancy.middleware.TenantMiddleware']
"""

# ==============================================================================
# EXAMPLE: MSP DEPLOYMENT
# ==============================================================================
"""
# Managed service provider with multiple customers
INSTALLED_APPS = [
    'django.contrib.sites',
    'micboard.multitenancy',
    # ... other apps
]

SITE_ID = 1
MICBOARD_MULTI_SITE_MODE = True
MICBOARD_MSP_ENABLED = True
MICBOARD_SITE_ISOLATION = 'organization'
MICBOARD_ALLOW_CROSS_ORG_VIEW = False  # Strict isolation
MICBOARD_ALLOW_ORG_SWITCHING = True
MICBOARD_SUBDOMAIN_ROUTING = True
MICBOARD_ROOT_DOMAIN = 'micboard.example.com'

MIDDLEWARE += ['micboard.multitenancy.middleware.TenantMiddleware']
"""
