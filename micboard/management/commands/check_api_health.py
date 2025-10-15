"""Management command to check Shure System API health."""
from django.core.management.base import BaseCommand

from micboard.shure import ShureSystemAPIClient


class Command(BaseCommand):
    help = "Check Shure System API health and connectivity"  # noqa: A003

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output in JSON format",
        )

    def handle(self, *args, **options):  # noqa: ARG002
        json_output = options["json"]
        
        client = ShureSystemAPIClient()
        
        if json_output:
            import json
            health_status = client.check_health()
            self.stdout.write(json.dumps(health_status, indent=2, default=str))
        else:
            health_status = client.check_health()
            status = health_status.get("status", "unknown")
            
            if status == "healthy":
                self.stdout.write(self.style.SUCCESS(f"✓ API is healthy: {client.base_url}"))
                self.stdout.write(f"  Status code: {health_status.get('status_code')}")
            elif status == "unhealthy":
                self.stdout.write(
                    self.style.WARNING(f"⚠ API is unhealthy: {client.base_url}")
                )
                self.stdout.write(f"  Status code: {health_status.get('status_code')}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ API is unreachable: {client.base_url}")
                )
                self.stdout.write(f"  Error: {health_status.get('error')}")
            
            # Show additional health metrics
            if health_status.get("consecutive_failures"):
                self.stdout.write(
                    f"  Consecutive failures: {health_status['consecutive_failures']}"
                )
            
            if health_status.get("last_successful_request"):
                import time
                from datetime import datetime, timezone
                last_success = datetime.fromtimestamp(
                    health_status["last_successful_request"], tz=timezone.utc
                )
                self.stdout.write(f"  Last successful request: {last_success.isoformat()}")
