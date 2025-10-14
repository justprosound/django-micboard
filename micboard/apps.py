from django.apps import AppConfig


class MicboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "micboard"
    verbose_name = "Micboard"

    def ready(self):
        """Initialize app when Django starts"""
        # Import signals to register them
        from . import signals  # noqa: F401  (import registers signal handlers)
