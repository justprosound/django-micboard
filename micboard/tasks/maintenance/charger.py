import logging

from micboard.services.manufacturer.activation_service import ManufacturerActivationService
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


def poll_charger_data(manufacturer_id: int) -> dict[str, int | bool] | None:
    """Resolve one active manufacturer ID and delegate bounded charger polling."""
    try:
        manufacturer = ManufacturerActivationService.get_active(manufacturer_id)
        if manufacturer is None:
            logger.warning(
                "Active manufacturer with ID %s not found for charger polling task.",
                manufacturer_id,
            )
            return None

        from micboard.services.chargers.polling_service import ChargerPollingService

        return ChargerPollingService.poll(manufacturer).model_dump()
    except Exception as exc:
        logger.exception(
            "Error polling charger data for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )
    return None
