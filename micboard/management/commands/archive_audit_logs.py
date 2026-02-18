"""Management command to archive and prune audit logs."""

from django.core.management.base import BaseCommand

from micboard.services.maintenance.audit import AuditService


class Command(BaseCommand):
    help = "Archive old activity logs and prune sync/api health logs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--retention-days",
            type=int,
            default=None,
            help="Override retention days (default from MICBOARD_CONFIG)",
        )
        parser.add_argument(
            "--activity-only",
            action="store_true",
            help="Archive activity logs only (skip sync/api health pruning)",
        )

    def handle(self, *args, **options):
        retention_days = options.get("retention_days")
        activity_only = options["activity_only"]

        self.stdout.write("Starting audit log archiving...")

        activity_result = AuditService.archive_activity_logs(retention_days=retention_days)
        self.stdout.write(
            self.style.SUCCESS(
                f"Archived {activity_result['archived']} activity logs to {activity_result['file']}"
            )
        )

        if not activity_only:
            sync_count = AuditService.prune_service_sync_logs(retention_days=retention_days)
            health_count = AuditService.prune_api_health_logs(retention_days=retention_days)

            self.stdout.write(self.style.SUCCESS(f"Pruned {sync_count} service sync logs"))
            self.stdout.write(self.style.SUCCESS(f"Pruned {health_count} API health logs"))

        self.stdout.write(self.style.SUCCESS("Audit log archiving complete"))
