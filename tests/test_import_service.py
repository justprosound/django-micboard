"""Focused coverage for row-scoped manufacturer imports."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from django.test import override_settings

from micboard.services.import_service import ImportService


@override_settings(
    MICBOARD_API_SERVER_ALLOWED_HOSTS=["venue-a.example.test", "venue-b.example.test"]
)
@patch("micboard.integrations.shure.client.ShureSystemAPIClient")
def test_import_servers_use_each_configured_destination_and_credential(
    client_class: MagicMock,
) -> None:
    """Multiple imports cannot silently reuse the process-global Shure credential."""
    first_context = MagicMock()
    first_context.__enter__.return_value.devices.get_devices.return_value = [{"serial": "first"}]
    second_context = MagicMock()
    second_context.__enter__.return_value.devices.get_devices.return_value = [{"serial": "second"}]
    client_class.side_effect = [first_context, second_context]
    service = ImportService()
    api_servers = {
        "venue-a": {
            "manufacturer": "shure",
            "base_url": "https://venue-a.example.test:10000",
            "shared_key": "venue-a-row-key",
        },
        "venue-b": {
            "manufacturer": "shure",
            "base_url": "https://venue-b.example.test:10000",
            "shared_key": "venue-b-row-key",
        },
    }

    with patch.object(service, "import_device", side_effect=[(True, False), (True, False)]):
        result = service.import_from_servers(
            api_servers=api_servers,
            manufacturer=object(),
            options={"dry_run": False, "full": False},
        )

    assert result == (2, 2, 0)
    assert client_class.call_args_list == [
        call(
            base_url="https://venue-a.example.test:10000",
            shared_key="venue-a-row-key",
        ),
        call(
            base_url="https://venue-b.example.test:10000",
            shared_key="venue-b-row-key",
        ),
    ]
    first_context.__exit__.assert_called_once()
    second_context.__exit__.assert_called_once()


@patch(
    "micboard.services.integrations.api_server_service.APIServerConnectionService."
    "fetch_shure_devices"
)
def test_import_servers_skip_unsupported_manufacturers(fetch_devices: MagicMock) -> None:
    """Unsupported server configurations remain safe no-ops."""
    service = ImportService()

    result = service.import_from_servers(
        api_servers={
            "dante": {
                "manufacturer": "dante",
                "base_url": "https://dante.example.test",
                "shared_key": "not-forwarded",
            }
        },
        manufacturer=object(),
        options={},
    )

    assert result == (0, 0, 0)
    fetch_devices.assert_not_called()


@patch(
    "micboard.services.integrations.api_server_service.APIServerConnectionService."
    "fetch_shure_devices"
)
def test_import_connection_failures_do_not_log_credentials(
    fetch_devices: MagicMock,
    caplog,
) -> None:
    """Credential values cannot escape through rendered integration exceptions."""
    secret = "venue-row-private-key"
    fetch_devices.side_effect = RuntimeError(f"authentication rejected for {secret}")

    result = ImportService().import_from_servers(
        api_servers={
            "venue": {
                "manufacturer": "shure",
                "base_url": "https://venue.example.test",
                "shared_key": secret,
            }
        },
        manufacturer=object(),
        options={},
    )

    assert result == (0, 0, 0)
    assert secret not in caplog.text
