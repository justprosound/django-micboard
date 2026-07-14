# Multi-tenancy migrations

django-micboard ships Django-generated migrations for both the core `micboard` app and the
optional `micboard_multitenancy` app. Host projects must apply the shipped migration graph; they
must not generate package migrations locally.

After adding `micboard.multitenancy` to `INSTALLED_APPS`, apply all pending migrations:

```bash
uv run --no-sync python manage.py migrate
```

`Building.organization_id` and `Building.campus_id` are nullable, indexed integer identifiers.
They intentionally avoid making the core app depend on foreign keys to the optional multi-tenancy
app. When MSP mode is enabled, application validation ensures a campus belongs to the selected
organization.

For future package schema changes:

1. Change the Django models.
2. Generate migrations through Django's `makemigrations` command.
3. Review and test the generated migration on clean and existing databases.
4. Commit a new migration; never edit or delete migration history.

The repository's pre-commit checks reject edits to existing migration files, verify the
Django-generated header on new migrations, and detect model changes without migrations.
