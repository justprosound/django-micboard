"""
Migration stub for multi-tenancy support.

This file documents the migrations needed when enabling multi-site or MSP mode.
Actual migrations should be generated via `python manage.py makemigrations`.

PHASE 1: Multi-Site Support (MICBOARD_MULTI_SITE_MODE = True)
===============================================================

Step 1: Add django.contrib.sites to INSTALLED_APPS
Step 2: Run `python manage.py migrate sites`
Step 3: Add site FK to Building model (optional, nullable, default=1)
Step 4: Run `python manage.py makemigrations micboard`
Step 5: Run `python manage.py migrate micboard`

Migration adds:
- Building.site (ForeignKey to sites.Site, default=1, null=True, blank=True)

SQL equivalent:
    ALTER TABLE micboard_building
    ADD COLUMN site_id INTEGER NULL
    REFERENCES django_site(id);

    UPDATE micboard_building SET site_id = 1;

    ALTER TABLE micboard_building
    ALTER COLUMN site_id SET DEFAULT 1;


PHASE 2: MSP Mode (MICBOARD_MSP_ENABLED = True)
================================================

Requires MICBOARD_MULTI_SITE_MODE = True

Step 1: Add 'micboard.multitenancy' to INSTALLED_APPS
Step 2: Run `python manage.py makemigrations micboard_multitenancy`
Step 3: Run `python manage.py migrate micboard_multitenancy`
Step 4: Add organization/campus FKs to Building model
Step 5: Run `python manage.py makemigrations micboard`
Step 6: Run `python manage.py migrate micboard`

Migration adds:
- Organization model
- Campus model
- OrganizationMembership model
- Building.organization (ForeignKey, null=True, blank=True)
- Building.campus (ForeignKey, null=True, blank=True)

Data migration example:
    # Create default organization
    org = Organization.objects.create(
        name='Default Organization',
        slug='default',
        site_id=1,
        is_active=True
    )

    # Create default campus
    campus = Campus.objects.create(
        organization=org,
        name='Main Campus',
        slug='main',
        is_active=True
    )

    # Update existing buildings
    Building.objects.all().update(
        organization=org,
        campus=campus
    )

SQL equivalent:
    ALTER TABLE micboard_building
    ADD COLUMN organization_id INTEGER NULL
    REFERENCES micboard_multitenancy_organization(id);

    ALTER TABLE micboard_building
    ADD COLUMN campus_id INTEGER NULL
    REFERENCES micboard_multitenancy_campus(id);

    -- Data migration would be run here

    -- Optional: Make organization_id required after data migration
    -- ALTER TABLE micboard_building
    -- ALTER COLUMN organization_id SET NOT NULL;


UNIQUE CONSTRAINTS
==================

Single-site mode:
    Building.name is globally unique

Multi-site mode:
    unique_together = [['site', 'name']]

MSP mode:
    unique_together = [['organization', 'name']]
    OR
    unique_together = [['campus', 'name']]


RECOMMENDED APPROACH
====================

To minimize downtime and maintain flexibility:

1. Keep all tenant FKs nullable initially
2. Run data migration to populate FK values
3. Only add NOT NULL constraints if strict isolation required
4. Use application-level validation (service layer) for data integrity

This allows:
- Gradual migration from single-site → multi-site → MSP
- Testing MSP features with subset of buildings
- Rollback capability if issues arise


GENERATING MIGRATIONS
======================

# After enabling MICBOARD_MULTI_SITE_MODE:
python manage.py makemigrations micboard --name add_site_support

# After enabling MICBOARD_MSP_ENABLED:
python manage.py makemigrations micboard_multitenancy --name add_organization_models
python manage.py makemigrations micboard --name add_organization_campus_fks

# Create data migration:
python manage.py makemigrations micboard --name migrate_to_default_organization --empty
# Then edit the migration file to add data migration logic
"""
