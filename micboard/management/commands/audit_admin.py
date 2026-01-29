import gc
import logging
import os
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.db import connections

logger = logging.getLogger(__name__)

# Constants
HTTP_OK = 200
QUERY_COUNT_WARNING = 15
QUERY_COUNT_FAIL = 50
SQL_PREVIEW_LEN = 150
TUPLE_LEN = 2
MIN_FIELDSETS_FOR_TABS = 2
MIN_TABS_FOR_GROUPING = 5


def run_audit_worker(model, model_admin, options):
    """Worker function for ThreadPoolExecutor.

    Runs in a separate thread.


    """
    try:
        # Re-instantiate the command to check logic

        cmd = Command()

        # Hydrate options

        cmd.check_flags = options.get("check_flags", {})

        cmd.check_n1 = cmd.check_flags.get("n1", False)

        cmd.check_unfold = cmd.check_flags.get("unfold", False)

        cmd.check_media = cmd.check_flags.get("media", False)

        cmd.check_search_depth = cmd.check_flags.get("search_depth", False)

        cmd.aspect_filters_enabled = any(cmd.check_flags.values())

        cmd.quick_mode = options.get("quick_mode", False)

        # Mock thread locals for the command logic

        cmd._thread_local = threading.local()

        cmd.model_buffer = []  # Fallback

        app_label = model._meta.app_label

        model_name = model._meta.model_name

        stats = cmd._initialize_stats()

        stats["models_scanned"] = 1

        # Setup user and request

        cmd.admin_user = None  # Ensure it is initialized

        if not cmd._setup_audit_environment(create_clients=False):
            return (
                [],
                False,
                {
                    "error": "Failed to setup audit environment (user/client creation)",
                    "app_label": app_label,
                    "model_name": model_name,
                },
            )

        cmd._thread_local.buffer = []

        cmd._thread_local.has_issues = False

        cmd._thread_local.client = cmd._get_client()

        cmd._thread_local.request = cmd.factory.get("/")

        cmd._thread_local.request.user = cmd.admin_user

        cmd.log(f"\n--- {app_label}.{model.__name__} ---")

        cmd.audit_model(model, model_admin, stats)

        return (cmd._thread_local.buffer, cmd._thread_local.has_issues, stats)

    except Exception as e:
        # Return error info so main process can log it

        return (
            [],
            False,
            {
                "error": str(e),
                "app_label": model._meta.app_label,
                "model_name": model._meta.model_name,
            },
        )

    finally:
        # Clean up DB connections for this thread

        from django.db import reset_queries

        reset_queries()

        connections.close_all()

        # Force garbage collection to free up memory from large query logs or objects

        gc.collect()


class Command(BaseCommand):
    help = "Audits the Django Admin for Unfold compliance, N+1 issues, and configuration best practices."
    _thread_local = threading.local()

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            type=str,
            help="Filter by app label",
        )
        parser.add_argument(
            "--model",
            type=str,
            nargs="+",
            help="Filter by model name (e.g. Charger or micboard.Charger)",
        )
        parser.add_argument(
            "--exclude",
            type=str,
            nargs="+",
            help="Exclude models by name",
        )
        parser.add_argument(
            "--errors-only",
            action="store_true",
            help="Only show models with errors or warnings",
        )
        parser.add_argument(
            "--quick",
            action="store_true",
            help="Skip individual object checks (Add/Change views) to speed up audit",
        )
        parser.add_argument(
            "--check-n1",
            action="store_true",
            help="Only check for N+1 query issues (skips other checks)",
        )
        parser.add_argument(
            "--check-unfold",
            action="store_true",
            help="Only check Unfold compliance (inheritance, widgets, filters)",
        )
        parser.add_argument(
            "--check-media",
            action="store_true",
            help="Only check for deprecated Media classes",
        )
        parser.add_argument(
            "--check-search-depth",
            action="store_true",
            help="Check for deep FK lookups in search_fields",
        )
        parser.add_argument(
            "--threads",
            type=int,
            default=(os.cpu_count() or 1) * 4,
            help="Number of threads for parallel auditing (default: CPUs * 4)",
        )

    def handle(self, *args, **options):
        self.errors_only = options.get("errors_only")
        self.quick_mode = options.get("quick")
        self.model_buffer = []
        self.has_model_issues = False

        # Store aspect-specific check flags
        self.check_flags = {
            "n1": options.get("check_n1"),
            "unfold": options.get("check_unfold"),
            "media": options.get("check_media"),
            "search_depth": options.get("check_search_depth"),
        }
        self.check_n1 = self.check_flags["n1"]
        self.check_unfold = self.check_flags["unfold"]
        self.check_media = self.check_flags["media"]
        self.check_search_depth = self.check_flags["search_depth"]

        # If any specific check is enabled, only run those
        self.aspect_filters_enabled = any(self.check_flags.values())

        if not self.errors_only:
            self.stdout.write("Starting Micboard Admin Audit...")
            self.stdout.write("===============================")

        # Force DEBUG=False to prevent memory leaks from query logging
        from django.conf import settings

        self._original_debug = settings.DEBUG
        settings.DEBUG = False
        if self._original_debug:
            self.stdout.write("Forcing DEBUG=False for audit duration (memory safety).")

        if not self._setup_audit_environment():
            return

        # 1. Check Index & Settings
        target_models = options.get("model")
        if not target_models:
            self.check_index()
            # We need a dummy stats for these global checks
            global_stats = self._initialize_stats()
            self.check_settings_config(global_stats)

        # 2. Iterate models
        from django.contrib import admin

        registry = admin.site._registry
        if not registry:
            self.stdout.write("No models registered in admin.")
            return

        target_app = options.get("app")
        max_workers = options.get("threads")
        stats = self._initialize_stats()

        # Prepare tasks
        self.tasks = []
        target_exclude = options.get("exclude")

        for model, model_admin in registry.items():
            if self._should_skip_model(model, target_app, target_models, target_exclude):
                continue
            self.tasks.append((model, model_admin))

        if not self.tasks:
            self.stdout.write("No models matched the filter.")
            return

        if not self.errors_only:
            self.stdout.write(f"Auditing {len(self.tasks)} models using {max_workers} threads...")

        self._run_audit_pool(max_workers, stats)

        self.print_summary(stats)

        # Restore DEBUG setting
        settings.DEBUG = self._original_debug

    def _run_audit_pool(self, max_workers, stats):
        """Execute audit tasks in parallel using ThreadPoolExecutor."""
        # Prepare picklable options usually stored on self
        worker_options = {
            "check_flags": self.check_flags,
            "quick_mode": self.quick_mode,
        }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_model = {}
            for model, model_admin in self.tasks:
                future = executor.submit(
                    run_audit_worker,
                    model,
                    model_admin,
                    worker_options,
                )
                future_to_model[future] = model

            for future in as_completed(future_to_model):
                model = future_to_model.pop(future)
                try:
                    res_buffer, res_has_issues, res_stats = future.result()

                    # Check for worker-level error
                    if "error" in res_stats:
                        self.stderr.write(
                            self.style.ERROR(
                                f"\n[CRITICAL ERROR] Worker failed for {res_stats['app_label']}."
                                f"{res_stats['model_name']}: {res_stats['error']}"
                            )
                        )
                        continue

                    # Aggregate stats
                    for key, value in res_stats.items():
                        stats[key] += value

                    # Print buffer if needed
                    if not self.errors_only or res_has_issues:
                        for line in res_buffer:
                            self.stdout.write(line)

                except Exception as e:
                    app_label = model._meta.app_label
                    self.stderr.write(
                        self.style.ERROR(
                            f"\n[CRITICAL ERROR] Failed to audit {app_label}.{model.__name__}: {e}"
                        )
                    )
                    logger.exception("Audit worker failed")

    def _setup_audit_environment(self, *, create_clients=True):
        """Set up user and factory for auditing."""
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from django.test import Client, RequestFactory

        user_model = get_user_model()
        username = "audit_admin_user"

        try:
            if not user_model.objects.filter(username=username).exists():
                self.admin_user = user_model.objects.create_superuser(
                    username, "audit@example.com", "password"
                )
            else:
                self.admin_user = user_model.objects.get(username=username)
        except Exception as e:
            self.stderr.write(f"Failed to setup user: {e}")
            return False

        if "testserver" not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

        self.factory = RequestFactory()

        if create_clients:
            self._global_client = Client()
            self._global_client.force_login(self.admin_user)
            self._global_request = self.factory.get("/")
            self._global_request.user = self.admin_user

        return True

    @property
    def client(self):
        if hasattr(self._thread_local, "client"):
            return self._thread_local.client
        return getattr(self, "_global_client", None)

    @property
    def request(self):
        if hasattr(self._thread_local, "request"):
            return self._thread_local.request
        return getattr(self, "_global_request", None)

    def _get_client(self):
        from django.test import Client

        client = Client()
        client.force_login(self.admin_user)
        return client

    def log(self, message, style=None):
        buffer = getattr(self._thread_local, "buffer", self.model_buffer)

        if style:
            if style in (self.style.WARNING, self.style.ERROR):
                if hasattr(self._thread_local, "has_issues"):
                    self._thread_local.has_issues = True
                else:
                    self.has_model_issues = True
            formatted_message = style(message)
        else:
            formatted_message = message

        buffer.append(formatted_message)

    def _initialize_stats(self):
        return {
            "models_scanned": 0,
            "n_plus_one_warnings": 0,
            "n_plus_one_fails": 0,
            "unfold_compliant": 0,
            "unfold_non_compliant": 0,
            "widget_warnings": 0,
            "widgets_optimized": 0,
            "filters_optimized": 0,
            "search_warnings": 0,
            "template_errors": 0,
            "media_warnings": 0,
            "list_fullwidth_warnings": 0,
        }

    def _should_skip_model(self, model, target_app, target_models, target_exclude=None):
        app_label = model._meta.app_label
        model_name = model.__name__
        full_name = f"{app_label}.{model_name}"

        if target_app and app_label != target_app:
            return True

        if target_exclude:
            if model_name in target_exclude or full_name in target_exclude:
                return True

        if target_models:
            match = model_name in target_models or full_name in target_models
            return not match

        return False

    def check_index(self):
        self.model_buffer = []
        self.has_model_issues = False
        try:
            resp = self.client.get("/admin/")
            if resp.status_code != HTTP_OK:
                self.log(f"[FAIL] Admin Index: {resp.status_code}", style=self.style.ERROR)
            else:
                self.log("[PASS] Admin Index")
                content = resp.content.lower()
                if b"unfold" in content:
                    self.log("       - Unfold theme detected")
                else:
                    self.log(
                        "       - Unfold theme markers NOT detected in index",
                        style=self.style.WARNING,
                    )
        except Exception as e:
            self.log(f"[ERROR] Admin Index: {e}", style=self.style.ERROR)

        if not self.errors_only or self.has_model_issues:
            for line in self.model_buffer:
                self.stdout.write(line)

    def audit_model(self, model, model_admin, stats):
        run_all = not self.aspect_filters_enabled

        if run_all or self.check_unfold:
            self.check_inheritance(model_admin, stats)
            self.check_widgets(model, model_admin, stats)
            self.check_filters(model_admin, stats)

        if run_all or self.check_search_depth:
            self.check_search_depth_logic(model, model_admin, stats)

        if run_all:
            self.check_templates_existence(model_admin, stats)

        if run_all or self.check_n1:
            self.check_static_optimization(model, model_admin)
            self.check_runtime_performance(model, model_admin, stats)

    def check_inheritance(self, model_admin, stats):
        try:
            from unfold.admin import ModelAdmin as UnfoldModelAdmin

            is_unfold = isinstance(model_admin, UnfoldModelAdmin)
            if is_unfold:
                self.log("  [CONF] Inherits from UnfoldModelAdmin: YES")
                stats["unfold_compliant"] += 1
            else:
                self.log(
                    f"  [CONF] Inherits from UnfoldModelAdmin: NO ({type(model_admin).__name__})",
                    style=self.style.WARNING,
                )
                stats["unfold_non_compliant"] += 1
        except ImportError:
            self.log("  [CONF] Unfold NOT installed", style=self.style.ERROR)

    def check_widgets(self, model, model_admin, stats):
        overrides = getattr(model_admin, "formfield_overrides", {})
        if overrides:
            optimized_widgets_count = 0
            for override_dict in overrides.values():
                widget = override_dict.get("widget")
                if widget and str(widget.__module__).startswith("unfold.widgets"):
                    optimized_widgets_count += 1
            if optimized_widgets_count > 0:
                self.log(f"  [WIDG] Unfold widgets used: {optimized_widgets_count}")
                stats["widgets_optimized"] += 1

    def check_filters(self, model_admin, stats):
        list_filter = getattr(model_admin, "list_filter", [])
        unfold_filters = 0
        for f in list_filter:
            if isinstance(f, type) and f.__module__.startswith("unfold.contrib.filters"):
                unfold_filters += 1
        if unfold_filters > 0:
            self.log(f"  [FILT] Unfold filters used: {unfold_filters}")
            stats["filters_optimized"] += 1

    def check_static_optimization(self, model, model_admin):
        list_display = getattr(model_admin, "list_display", [])
        list_select_related = getattr(model_admin, "list_select_related", False)
        list_prefetch_related = getattr(model_admin, "list_prefetch_related", [])

        relational_fields_in_list = []
        for field_name in list_display:
            if not isinstance(field_name, str):
                continue
            try:
                field = model._meta.get_field(field_name)
                if field.is_relation and (field.many_to_one or field.one_to_one):
                    relational_fields_in_list.append(field_name)
            except Exception:
                continue

        if relational_fields_in_list:
            if not list_select_related and not list_prefetch_related:
                self.log(
                    f"  [PERF] Relational fields in list_display {relational_fields_in_list} but NO optimization set.",
                    style=self.style.WARNING,
                )

    def check_runtime_performance(self, model, model_admin, stats):
        from django.urls import reverse

        app_label = model._meta.app_label
        model_name = model._meta.model_name

        try:
            url = reverse(f"admin:{app_label}_{model_name}_changelist")
            from django.db import connection, reset_queries
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as ctx:
                resp = self.client.get(url)

            num_queries = len(ctx.captured_queries)
            if resp.status_code == HTTP_OK:
                status_msg = f"[PERF] List View Queries: {num_queries}"

                # Pre-analyze for duplicates
                sql_counts = Counter(q["sql"] for q in ctx.captured_queries)
                duplicates = [(sql, count) for sql, count in sql_counts.items() if count > 1]
                duplicates.sort(key=lambda x: x[1], reverse=True)

                if num_queries > QUERY_COUNT_FAIL:
                    self.log(f"  {status_msg} - HIGH QUERY COUNT DETECTED!", style=self.style.ERROR)
                    stats["n_plus_one_fails"] += 1
                    self.analyze_queries(ctx.captured_queries, limit=10, duplicates=duplicates)
                elif num_queries > QUERY_COUNT_WARNING:
                    self.log(f"  {status_msg} - WARNING", style=self.style.WARNING)
                    stats["n_plus_one_warnings"] += 1
                    self.analyze_queries(ctx.captured_queries, limit=5, duplicates=duplicates)
                else:
                    self.log(f"  {status_msg}")
            else:
                self.log(f"  [FAIL] List View: {resp.status_code}", style=self.style.ERROR)
        except Exception as e:
            self.log(f"  [ERROR] Performance check failed: {e}", style=self.style.ERROR)
        finally:
            reset_queries()

    def analyze_queries(self, queries, limit=5, duplicates=None):
        """Analyze captured queries for duplicates."""
        self.log("       Query Analysis:")

        if duplicates is None:
            # Count duplicates based on SQL structure
            sql_counts = Counter(q["sql"] for q in queries)
            duplicates = [(sql, count) for sql, count in sql_counts.items() if count > 1]
            duplicates.sort(key=lambda x: x[1], reverse=True)

        if duplicates:
            self.log(
                f"       Found {len(duplicates)} duplicated query types.", style=self.style.WARNING
            )
            for _i, (sql, count) in enumerate(duplicates[:limit]):
                short_sql = sql[:SQL_PREVIEW_LEN] + "..." if len(sql) > SQL_PREVIEW_LEN else sql
                self.log(f"       {count}x: {short_sql}")

    def check_templates_existence(self, model_admin, stats):
        from django.template import TemplateDoesNotExist
        from django.template.loader import get_template

        from micboard.utils.dependencies import HAS_ADMIN_SORTABLE, HAS_UNFOLD

        for attr in ["change_list_template", "change_form_template"]:
            template_name = getattr(model_admin, attr, None)
            if template_name:
                # SKIP: adminsortable2 templates when Unfold is active (known conflict)
                if HAS_UNFOLD and HAS_ADMIN_SORTABLE and isinstance(template_name, (list, tuple)):
                    if any("adminsortable2" in str(t) for t in template_name):
                        continue
                if HAS_UNFOLD and HAS_ADMIN_SORTABLE and isinstance(template_name, str):
                    if "adminsortable2" in template_name:
                        continue

                # Handle lists/tuples of templates (Django supports fallbacks)
                templates = (
                    template_name if isinstance(template_name, (list, tuple)) else [template_name]
                )
                found = False
                for t in templates:
                    try:
                        get_template(t)
                        found = True
                        break
                    except (TemplateDoesNotExist, Exception):
                        continue

                if not found:
                    self.log(f"  [TEMP] {attr} NOT FOUND: {template_name}", style=self.style.ERROR)
                    stats["template_errors"] += 1

    def check_search_depth_logic(self, model, model_admin, stats):
        search_fields = getattr(model_admin, "search_fields", [])
        if any("__" in f for f in search_fields):
            self.log("  [SRCH] Deep search lookups: YES")
        elif search_fields:
            self.log("  [SRCH] Shallow search only.", style=self.style.WARNING)

    def print_summary(self, stats):
        self.stdout.write("\n\n===============================")
        self.stdout.write("       AUDIT SUMMARY")
        self.stdout.write("===============================")
        self.stdout.write(f"Total Models Scanned:   {stats['models_scanned']}")
        self.stdout.write(f"Unfold Compliant:       {stats['unfold_compliant']}")
        self.stdout.write(f"Unfold Non-Compliant:   {stats['unfold_non_compliant']}")
        self.stdout.write(f"N+1 Warnings (>15 q):   {stats['n_plus_one_warnings']}")
        self.stdout.write(f"N+1 Failures (>50 q):   {stats['n_plus_one_fails']}")
        self.stdout.write(f"Template Errors:        {stats['template_errors']}")
        self.stdout.write("===============================")

    def check_settings_config(self, stats):
        from django.conf import settings

        self.log("\n--- Settings Configuration ---")
        unfold_settings = getattr(settings, "UNFOLD", {})
        if not unfold_settings:
            self.log("  [FAIL] UNFOLD settings not found!", style=self.style.ERROR)
        else:
            self.log("  [PASS] UNFOLD settings found")
