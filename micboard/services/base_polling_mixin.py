"""Base polling orchestration mixin and utilities for django-micboard.

Centralizes common polling logic to eliminate duplication across services,
tasks, and integration layers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from django.utils import timezone

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


class PollingMixin:
    """Mixin providing common polling orchestration patterns.

    Use this mixin in services/tasks that need to:
    1. Poll all manufacturers
    2. Poll a single manufacturer
    3. Handle polling errors uniformly
    4. Emit signals consistently
    5. Broadcast updates
    """

    def poll_all_manufacturers_with_handler(
        self,
        *,
        on_manufacturer_polled: Callable[[Any, Manufacturer], dict[str, Any]] | None = None,
        on_error: Callable[[Manufacturer, Exception], None] | None = None,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Poll all active manufacturers with uniform error handling and signaling.

        Args:
            on_manufacturer_polled: Callback invoked after each manufacturer is polled.
                Should return dict with polling results.
            on_error: Callback invoked on error for a manufacturer.
            on_complete: Callback invoked after all manufacturers are polled.

        Returns:
            Aggregated polling results
        """
        from micboard.models import Manufacturer

        manufacturers = Manufacturer.objects.filter(is_active=True)

        results: dict[str, Any] = {
            "timestamp": timezone.now().isoformat(),
            "total_manufacturers": manufacturers.count(),
            "manufacturers": {},
            "summary": {
                "total_chassis_created": 0,
                "total_chassis_updated": 0,
                "total_wireless_units": 0,
                "total_errors": 0,
                "errors": [],
            },
        }

        for manufacturer in manufacturers:
            try:
                # Invoke handler to perform actual polling
                if on_manufacturer_polled:
                    mfr_result = on_manufacturer_polled(self, manufacturer)
                else:
                    # Default: call poll_manufacturer if it exists
                    if not hasattr(self, "poll_manufacturer"):
                        logger.warning(
                            "No on_manufacturer_polled handler and no poll_manufacturer method"
                        )
                        continue
                    mfr_result = self.poll_manufacturer(manufacturer)

                # Aggregate results
                results["manufacturers"][manufacturer.code] = mfr_result
                results["summary"]["total_chassis_created"] += mfr_result.get("devices_created", 0)
                results["summary"]["total_chassis_updated"] += mfr_result.get("devices_updated", 0)
                results["summary"]["total_wireless_units"] += mfr_result.get("units_synced", 0)

                if mfr_result.get("errors"):
                    results["summary"]["errors"].extend(mfr_result["errors"])
                    results["summary"]["total_errors"] += len(mfr_result["errors"])

            except Exception as e:
                error_msg = f"Failed to poll {manufacturer.name}: {e}"
                logger.exception(error_msg)
                results["summary"]["errors"].append(error_msg)
                results["summary"]["total_errors"] += 1
                results["manufacturers"][manufacturer.code] = {
                    "status": "failed",
                    "error": str(e),
                }

                # Invoke error handler if provided
                if on_error:
                    try:
                        on_error(manufacturer, e)
                    except Exception:
                        logger.exception("Error in on_error handler for %s", manufacturer.name)

        # Log summary
        logger.info(
            "Polling complete: %d manufacturers, %d created, %d updated, %d units, %d errors",
            results["total_manufacturers"],
            results["summary"]["total_chassis_created"],
            results["summary"]["total_chassis_updated"],
            results["summary"]["total_wireless_units"],
            results["summary"]["total_errors"],
        )

        # Invoke completion handler if provided
        if on_complete:
            try:
                on_complete(results)
            except Exception:
                logger.exception("Error in on_complete handler")

        return results

    def _validate_polling_result(self, result: dict[str, Any]) -> bool:
        """Validate polling result structure.

        Args:
            result: Dictionary with polling results

        Returns:
            True if valid, False otherwise
        """
        required_keys = {"devices_created", "devices_updated", "units_synced"}
        if not all(key in result for key in required_keys):
            logger.warning("Invalid polling result structure: %s", result.keys())
            return False
        return True

    def _emit_polling_complete_signal(
        self, manufacturer: Manufacturer, result: dict[str, Any] | None = None
    ) -> None:
        """Broadcast device polled event (replacing signals)."""
        try:
            try:
                from channels.layers import get_channel_layer

                if get_channel_layer():
                    from micboard.services.broadcast_service import BroadcastService

                    BroadcastService.broadcast_device_update(manufacturer=manufacturer, data=result)
            except ImportError:
                pass
            logger.debug("Broadcasted device update for %s", manufacturer.name)

        except Exception:
            logger.exception("Failed to broadcast device update for %s", manufacturer.name)

    def _emit_health_changed_signal(
        self, manufacturer: Manufacturer, health_status: dict[str, Any]
    ) -> None:
        """Broadcast API health change (replacing signals)."""
        try:
            try:
                from channels.layers import get_channel_layer

                if get_channel_layer():
                    from micboard.services.broadcast_service import BroadcastService

                    BroadcastService.broadcast_api_health(
                        manufacturer=manufacturer, health_data=health_status
                    )
            except ImportError:
                pass
            logger.debug("Broadcasted API health change for %s", manufacturer.name)

        except Exception:
            logger.exception("Failed to broadcast API health change for %s", manufacturer.name)

    def _standardize_health_response(self, health_data: dict[str, Any]) -> dict[str, Any]:
        """Standardize health response format across all manufacturers.

        Input formats vary by manufacturer. This normalizes to:
        {
            "status": "healthy" | "degraded" | "error",
            "timestamp": ISO string,
            "details": {...}  # Manufacturer-specific details
        }

        Args:
            health_data: Raw health response from API client

        Returns:
            Standardized health response
        """
        if not health_data:
            return {
                "status": "error",
                "timestamp": timezone.now().isoformat(),
                "details": {"error": "No health data"},
            }

        # Normalize status field
        status = health_data.get("status") or health_data.get("healthy")
        if isinstance(status, bool):
            status = "healthy" if status else "degraded"
        elif status not in ("healthy", "degraded", "error", "unknown"):
            status = "unknown"

        return {
            "status": status,
            "timestamp": health_data.get("timestamp", timezone.now().isoformat()),
            "details": {k: v for k, v in health_data.items() if k != "status"},
        }


class PollSequenceExecutor:
    """Executes a sequence of polling operations in order with error handling.

    Useful for complex polling workflows that have dependencies or phases.
    """

    def __init__(self):
        """Initialize executor."""
        self.steps: list[tuple[str, Callable[[], dict[str, Any]]]] = []
        self.results: dict[str, dict[str, Any]] = {}
        self.errors: dict[str, Exception] = {}

    def add_step(self, name: str, step_fn: Callable[[], dict[str, Any]]) -> None:
        """Add a polling step.

        Args:
            name: Step identifier
            step_fn: Callable that performs the polling step
        """
        self.steps.append((name, step_fn))

    def execute(self, *, stop_on_error: bool = False) -> dict[str, Any]:
        """Execute all steps in sequence.

        Args:
            stop_on_error: If True, stop on first error; if False, continue

        Returns:
            Aggregated results from all steps
        """
        logger.info("Starting poll sequence with %d steps", len(self.steps))

        for step_name, step_fn in self.steps:
            try:
                logger.debug("Executing poll step: %s", step_name)
                result = step_fn()
                self.results[step_name] = result
                logger.debug("Poll step %s completed successfully", step_name)

            except Exception as e:
                error_msg = f"Error in poll step {step_name}: {e}"
                logger.exception(error_msg)
                self.errors[step_name] = e

                if stop_on_error:
                    logger.warning("Stopping poll sequence due to error in %s", step_name)
                    break

        logger.info(
            "Poll sequence complete: %d successful, %d failed",
            len(self.results),
            len(self.errors),
        )

        return {
            "success": len(self.errors) == 0,
            "results": self.results,
            "errors": {k: str(v) for k, v in self.errors.items()},
            "total_steps": len(self.steps),
            "completed_steps": len(self.results),
        }


def create_polling_error_handler(
    *,
    log_to_db: bool = False,
    alert_on_error: bool = False,
) -> Callable[[Manufacturer, Exception], None]:
    """Create an error handler for polling failures.

    Args:
        log_to_db: If True, log errors to database
        alert_on_error: If True, create alerts on error

    Returns:
        Error handler function
    """

    def handler(manufacturer: Manufacturer, error: Exception) -> None:
        """Handle polling error."""
        logger.error(
            "Polling error for %s (%s): %s",
            manufacturer.name,
            manufacturer.code,
            error,
        )

        if log_to_db:
            try:
                from micboard.models import PollingError

                PollingError.objects.create(
                    manufacturer=manufacturer,
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
            except Exception:
                logger.exception("Failed to log polling error to database")

        if alert_on_error:
            try:
                from micboard.services.alerts import create_polling_alert

                create_polling_alert(manufacturer, str(error))
            except Exception:
                logger.exception("Failed to create alert for polling error")

    return handler


def create_polling_complete_callback(
    *,
    broadcast_updates: bool = True,
    run_alerts: bool = True,
) -> Callable[[dict[str, Any]], None]:
    """Create a completion callback for polling operations.

    Args:
        broadcast_updates: If True, broadcast via WebSocket
        run_alerts: If True, run alert checks after polling

    Returns:
        Completion callback function
    """

    def callback(results: dict[str, Any]) -> None:
        """Handle polling completion."""
        if broadcast_updates:
            try:
                # Could broadcast aggregated results via PollingService
                logger.debug(
                    "Broadcast updates called for %d manufacturers",
                    len(results.get("manufacturers", {})),
                )

            except Exception:
                logger.exception("Failed to broadcast polling updates")

        if run_alerts:
            try:
                # These functions need specific arguments now, or should be updated to check all
                # For now, this is a placeholder/legacy path
                logger.debug("Alert checks requested after polling")

            except Exception:
                logger.exception("Failed to run alert checks")

    return callback
