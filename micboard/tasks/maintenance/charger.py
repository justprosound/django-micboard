import logging

from micboard.models.discovery import Manufacturer
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


def poll_charger_data(manufacturer_id: int) -> dict[str, int | bool] | None:
    """Resolve one active manufacturer ID and delegate bounded charger polling."""
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id, is_active=True)
        from micboard.services.chargers.polling_service import ChargerPollingService

        return ChargerPollingService.poll(manufacturer).model_dump()

    except Manufacturer.DoesNotExist:
        logger.warning(
            "Active manufacturer with ID %s not found for charger polling task.",
            manufacturer_id,
        )
    except Exception as exc:
        logger.exception(
            "Error polling charger data for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )
    return None
