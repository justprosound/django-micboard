"""Management command for device discovery via network probing.

This command provides a thin CLI wrapper around DeviceProbeService,
allowing network administrators to discover devices via IP scanning.

Examples:
    python manage.py device_discovery discover --ips "192.168.1.1,192.168.1.2"
    python manage.py device_discovery discover --file ips.txt
    python manage.py device_discovery discover --env
    python manage.py device_discovery test --ip 192.168.1.100
"""

import json

from django.core.management.base import BaseCommand

from micboard.services import DeviceAPIHealthChecker, DeviceProbeService


class Command(BaseCommand):
    """Discover and probe devices via network scanning."""

    help = "Discover and probe devices from IP addresses (VPN, local network, etc.)"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        subparsers = parser.add_subparsers(dest="command", help="Command to run")

        # Discover subcommand
        discover_parser = subparsers.add_parser(
            "discover",
            help="Discover devices by probing IP addresses",
        )
        discover_parser.add_argument(
            "--file",
            help="File with IP addresses (one per line, # for comments)",
        )
        discover_parser.add_argument(
            "--env",
            action="store_true",
            help="Use DEVICE_IPS environment variable (comma-separated)",
        )
        discover_parser.add_argument(
            "--ips",
            help="Comma-separated IP addresses to probe",
        )
        discover_parser.add_argument(
            "--save",
            default="device_manifest.json",
            help="Save discovered devices to JSON manifest (default: device_manifest.json)",
        )
        discover_parser.add_argument(
            "--timeout",
            type=int,
            default=5,
            help="Request timeout in seconds (default: 5)",
        )
        discover_parser.add_argument(
            "--verify-ssl",
            action="store_true",
            help="Verify SSL certificates (default: False)",
        )

        # Test subcommand
        test_parser = subparsers.add_parser(
            "test",
            help="Test connectivity to a specific device IP",
        )
        test_parser.add_argument(
            "--ip",
            required=True,
            help="Device IP address to test",
        )
        test_parser.add_argument(
            "--timeout",
            type=int,
            default=5,
            help="Request timeout in seconds (default: 5)",
        )
        test_parser.add_argument(
            "--verify-ssl",
            action="store_true",
            help="Verify SSL certificates (default: False)",
        )

        # Health check subcommand
        health_parser = subparsers.add_parser(
            "health",
            help="Check health of local or remote API server",
        )
        health_parser.add_argument(
            "--api-url",
            default="http://localhost:8000",
            help="API base URL to check (default: http://localhost:8000)",
        )

    def handle(self, *args, **options):
        """Execute the requested command."""
        command = options.get("command")

        if command == "discover":
            self._handle_discover(options)
        elif command == "test":
            self._handle_test(options)
        elif command == "health":
            self._handle_health(options)
        else:
            self.stdout.write(
                self.style.WARNING(
                    "No command specified. Use 'discover', 'test', or 'health'. "
                    "Run --help for details."
                )
            )

    def _handle_discover(self, options):
        """Handle device discovery command."""
        # Initialize service
        service = DeviceProbeService(
            timeout=options["timeout"],
            verify_ssl=options["verify_ssl"],
        )

        # Determine IP source
        if options.get("file"):
            self.stdout.write(f"Discovering devices from file: {options['file']}")
            devices = service.probe_from_file(options["file"])
        elif options.get("env"):
            self.stdout.write("Discovering devices from DEVICE_IPS environment variable")
            devices = service.probe_from_env()
        elif options.get("ips"):
            ips = [ip.strip() for ip in options["ips"].split(",")]
            self.stdout.write(f"Discovering devices from {len(ips)} IP addresses")
            devices = service.probe_ips(ips)
        else:
            self.stdout.write(
                self.style.WARNING(
                    "No IP source specified. Use --file, --env, or --ips. Run --help for details."
                )
            )
            return

        # Display results
        if devices:
            self.stdout.write(self.style.SUCCESS(f"✓ Discovered {len(devices)} device(s):"))
            for device in devices:
                status = "✓ Accessible" if device["accessible"] else "⚠ Needs Auth"
                self.stdout.write(f"  - {device['ip']}: {status}")
                self.stdout.write(f"    Endpoint: {device['endpoint']}")

            # Save manifest
            service.save_discovery_manifest(options["save"])
            self.stdout.write(self.style.SUCCESS(f"✓ Saved manifest to {options['save']}"))
        else:
            self.stdout.write(
                self.style.WARNING("No devices discovered. Check IPs and network connectivity.")
            )

    def _handle_test(self, options):
        """Handle device connectivity test command."""
        service = DeviceProbeService(
            timeout=options["timeout"],
            verify_ssl=options["verify_ssl"],
        )

        self.stdout.write(f"Testing device at {options['ip']}...")
        device = service.probe_device(options["ip"])

        if device:
            self.stdout.write(self.style.SUCCESS("✓ Device is reachable:"))
            self.stdout.write(json.dumps(device, indent=2))
        else:
            self.stderr.write(
                self.style.ERROR(
                    f"✗ Could not reach device at {options['ip']}. "
                    "Check network connectivity and IP address."
                )
            )

    def _handle_health(self, options):
        """Handle API health check command."""
        checker = DeviceAPIHealthChecker(api_base_url=options["api_url"])

        self.stdout.write(f"Checking API health at {options['api_url']}...")
        status = checker.get_api_status()

        if status["healthy"]:
            self.stdout.write(self.style.SUCCESS("✓ API is healthy"))
            self.stdout.write(f"  Status Code: {status['status_code']}")
        else:
            error_msg = status.get("error", "Unknown error")
            self.stderr.write(self.style.ERROR(f"✗ API is unhealthy: {error_msg}"))
            if status.get("status_code"):
                self.stdout.write(f"  Status Code: {status['status_code']}")
