"""Management command to audit regulatory coverage for all devices.

Checks every active WirelessChassis and RFChannel for:
1. Assigned Regulatory Domain (via Location)
2. Configured Band Plan
3. Regulatory Coverage for Band Plan range
4. Regulatory Coverage for operating frequencies

Usage:
    python manage.py audit_regulatory_coverage [--fix]
"""

from django.core.management.base import BaseCommand

from micboard.models import RFChannel, WirelessChassis


class Command(BaseCommand):
    help = "Audit regulatory coverage for all active devices and channels"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Attempt to auto-fix missing band plans using model inference",
        )

    def handle(self, *args, **options):
        fix_mode = options["fix"]
        self.stdout.write("Starting Regulatory Coverage Audit...\n")

        # 1. Audit Chassis Band Plans
        self.audit_chassis(fix_mode)

        # 2. Audit Active RF Channels
        self.audit_channels()

        self.stdout.write("\nAudit Complete.")

    def audit_chassis(self, fix_mode):
        """Audit WirelessChassis band plans and regulatory domains."""
        chassis_qs = WirelessChassis.objects.filter(
            status__in=["online", "degraded", "provisioning"]
        ).select_related("location", "location__building__regulatory_domain", "manufacturer")

        total = chassis_qs.count()
        missing_domain = 0
        missing_plan = 0
        missing_coverage = 0
        fixed_count = 0

        self.stdout.write(f"--- Auditing {total} Active Wireless Chassis ---")

        for chassis in chassis_qs:
            status = chassis.get_band_plan_regulatory_status()

            # Check Regulatory Domain
            if not status["regulatory_domain"]:
                self.stdout.write(
                    self.style.WARNING(f"[NO DOMAIN] {chassis} (Location: {chassis.location})")
                )
                missing_domain += 1
                continue

            # Check Band Plan
            if not status["has_band_plan"]:
                if fix_mode:
                    # Attempt auto-detection from model
                    if chassis.apply_detected_band_plan():
                        chassis.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[FIXED] Set band plan for {chassis.name}: "
                                f"{chassis.band_plan_name}"
                            )
                        )
                        fixed_count += 1
                        # Re-check status
                        status = chassis.get_band_plan_regulatory_status()
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[NO PLAN] {chassis.name} ({chassis.model}) - "
                                "Could not auto-detect"
                            )
                        )
                        missing_plan += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f"[NO PLAN] {chassis.name} ({chassis.model})")
                    )
                    missing_plan += 1
                continue

            # Check Coverage
            if not status["has_coverage"]:
                self.stdout.write(
                    self.style.ERROR(
                        f"[NO COVERAGE] {chassis.name}: {status['band_plan_range']} "
                        f"not covered by {status['regulatory_domain']}"
                    )
                )
                missing_coverage += 1

        self.stdout.write("\nChassis Summary:")
        self.stdout.write(f"  Missing Regulatory Domain: {missing_domain}")
        self.stdout.write(f"  Missing Band Plan: {missing_plan}")
        self.stdout.write(f"  Missing Coverage: {missing_coverage}")
        if fix_mode:
            self.stdout.write(f"  Auto-Fixed Band Plans: {fixed_count}")

    def audit_channels(
        self,
    ):
        """Audit active RFChannel frequencies."""
        channels_qs = RFChannel.objects.filter(
            resource_state__in=["active", "reserved"], frequency__isnull=False
        ).select_related("chassis", "chassis__location")

        total = channels_qs.count()
        missing_coverage = 0

        self.stdout.write(f"\n--- Auditing {total} Active RF Channels ---")

        for channel in channels_qs:
            status = channel.get_regulatory_status()

            if not status["has_coverage"]:
                # If chassis has no domain, we already flagged it, but channel level confirms impact
                domain_code = status.get("regulatory_domain") or "NONE"
                self.stdout.write(
                    self.style.ERROR(
                        f"[ILLEGAL/UNKNOWN] {channel}: {channel.frequency} MHz "
                        f"not allowed in {domain_code}"
                    )
                )
                missing_coverage += 1

        self.stdout.write("\nChannel Summary:")
        self.stdout.write(f"  Channels with Non-Compliant/Unknown Frequencies: {missing_coverage}")
