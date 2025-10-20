"""
Tests for Shure data transformers.
"""

from typing import Any, Union

from django.test import TestCase

from micboard.manufacturers.shure.transformers import ShureDataTransformer


class ShureDataTransformerTest(TestCase):
    """Test ShureDataTransformer class methods."""

    def test_transform_device_data_basic(self):
        """Test basic device data transformation."""
        api_data = {
            "id": "device1",
            "ip_address": "192.168.1.100",
            "type": "ULXD",
            "model_name": "ULX-D",
            "firmware_version": "1.2.3",
            "serial_number": "ABC123",
            "hostname": "device-host",
            "mac_address": "00:11:22:33:44:55",
            "model_variant": "V50",
            "frequency_band": "V50",
            "location": "Test Location",
            "uptime_minutes": 120,
            "temperature_c": 25,
            "channels": [
                {
                    "channel": 1,
                    "tx": {
                        "battery_bars": 3,
                        "audio_level": -20,
                        "rf_level": -50,
                        "frequency": 614.125,
                        "status": "OK",
                    },
                }
            ],
        }

        result = ShureDataTransformer.transform_device_data(api_data)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["id"], "device1")
        self.assertEqual(result["type"], "ulxd")
        self.assertEqual(result["name"], "ULX-D")
        self.assertEqual(result["firmware"], "1.2.3")
        self.assertEqual(result["serial"], "ABC123")
        self.assertEqual(result["hostname"], "device-host")
        self.assertEqual(result["mac_address"], "00:11:22:33:44:55")
        self.assertEqual(result["model_variant"], "V50")
        self.assertEqual(result["band"], "V50")
        self.assertEqual(result["location"], "Test Location")
        self.assertEqual(result["info"]["uptime_minutes"], 120)
        self.assertEqual(result["info"]["temperature_c"], 25)
        self.assertEqual(len(result["channels"]), 1)
        self.assertEqual(result["channels"][0]["channel"], 1)
        self.assertEqual(result["channels"][0]["tx"]["battery"], 3)

    def test_transform_device_data_missing_id(self):
        """Test device data transformation with missing ID."""
        api_data = {
            "ip_address": "192.168.1.100",
            "type": "ULXD",
        }

        result = ShureDataTransformer.transform_device_data(api_data)
        self.assertIsNone(result)

    def test_transform_device_data_no_channels(self):
        """Test device data transformation with no channels."""
        api_data = {"id": "device1", "type": "ULXD", "channels": []}

        result = ShureDataTransformer.transform_device_data(api_data)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["id"], "device1")
        self.assertEqual(len(result["channels"]), 0)

    def test_transform_device_data_channel_without_tx(self):
        """Test device data transformation with channel missing transmitter data."""
        api_data = {
            "id": "device1",
            "type": "ULXD",
            "channels": [
                {"channel": 1},  # No tx data
                {"channel": 2, "tx": None},
                {"channel": 3, "tx": {}},  # Empty tx data
            ],
        }

        result = ShureDataTransformer.transform_device_data(api_data)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result["channels"]), 0)  # No valid channels

    def test_transform_device_data_exception_handling(self):
        """Test device data transformation with exception handling."""
        api_data: dict = {}  # Pass an empty dict to trigger internal exception handling

        result = ShureDataTransformer.transform_device_data(api_data)
        self.assertIsNone(result)

    def test_identify_device_model_ulxd(self):
        """Test device model identification for ULX-D."""
        api_data = {"type": "ULXD", "model_name": "ULX-D Receiver", "firmware_version": "1.2.3"}

        result = ShureDataTransformer.identify_device_model(api_data)

        self.assertEqual(result["model"], "ULX-D Receiver")
        self.assertEqual(result["type"], "ulxd")
        self.assertEqual(result["firmware"], "1.2.3")
        self.assertEqual(result["raw_type"], "ULXD")
        self.assertEqual(result["raw_model"], "ULX-D Receiver")

    def test_identify_device_model_qlxd(self):
        """Test device model identification for QLX-D."""
        api_data = {"type": "QLX-D", "model_name": "QLX-D Receiver", "firmware_version": "2.1.0"}

        result = ShureDataTransformer.identify_device_model(api_data)

        self.assertEqual(result["model"], "QLX-D Receiver")
        self.assertEqual(result["type"], "qlxd")
        self.assertEqual(result["firmware"], "2.1.0")

    def test_identify_device_model_unknown(self):
        """Test device model identification for unknown type."""
        api_data = {
            "type": "UNKNOWN",
        }

        result = ShureDataTransformer.identify_device_model(api_data)

        self.assertEqual(result["model"], "Unknown")
        self.assertEqual(result["type"], "unknown")
        self.assertEqual(result["firmware"], "")
        self.assertEqual(result["raw_type"], "UNKNOWN")
        self.assertEqual(result["raw_model"], "")

    def test_identify_device_model_fallback(self):
        """Test device model identification with fallback model names."""
        # Test ULX-D fallback
        api_data = {"type": "ULXD"}
        result = ShureDataTransformer.identify_device_model(api_data)
        self.assertEqual(result["model"], "ULX-D")

        # Test QLX-D fallback
        api_data = {"type": "QLX-D"}
        result = ShureDataTransformer.identify_device_model(api_data)
        self.assertEqual(result["model"], "QLX-D")

    def test_identify_device_model_no_model_name(self):
        """Test device model identification without model_name field."""
        api_data = {
            "type": "ULXD",
            "firmwareVersion": "1.2.3",  # Alternative field name
        }

        result = ShureDataTransformer.identify_device_model(api_data)

        self.assertEqual(result["model"], "ULX-D")  # Fallback
        self.assertEqual(result["type"], "ulxd")
        self.assertEqual(result["firmware"], "1.2.3")

    def test_transform_transmitter_data_basic(self):
        """Test basic transmitter data transformation."""
        tx_data: dict = {
            "battery_bars": 4,
            "battery_charge": 85,
            "battery_runtime_minutes": 180,
            "audio_level": -15,
            "rf_level": -45,
            "frequency": 614.125,
            "antenna": "A",
            "status": "OK",
            "audio_quality": 95,
            "tx_offset": 10,
            "name": "TX1",
            "slot": 1,
            "mute": False,
            "power": "HIGH",
            "battery_type": "SB900",
            "temperature": 30,
            "rf_antenna_a": -40,
            "rf_antenna_b": -50,
        }

        result = ShureDataTransformer.transform_transmitter_data(tx_data, 1)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["battery"], 4)
        self.assertEqual(result["battery_charge"], 85)
        self.assertEqual(result["runtime"], "03:00")  # 180 minutes = 3:00
        self.assertEqual(result["audio_level"], -15)
        self.assertEqual(result["rf_level"], -45)
        self.assertEqual(result["frequency"], "614.125")
        self.assertEqual(result["antenna"], "A")
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["quality"], 95)
        self.assertEqual(result["tx_offset"], 10)
        self.assertEqual(result["name"], "TX1")
        self.assertEqual(result["slot"], 1)
        self.assertEqual(result["mute"], False)
        self.assertEqual(result["power"], "HIGH")
        self.assertEqual(result["battery_type"], "SB900")
        self.assertEqual(result["temperature"], 30)
        self.assertEqual(result["rf_antenna_a"], -40)
        self.assertEqual(result["rf_antenna_b"], -50)

    def test_transform_transmitter_data_alternative_fields(self):
        """Test transmitter data transformation with alternative field names."""
        tx_data: dict = {
            "batteryBars": 3,  # Alternative naming
            "batteryCharge": 75,
            "batteryRuntimeMinutes": 120,
            "audioLevel": -20,
            "rfLevel": -55,
            "deviceName": "TX2",  # Alternative naming
            "isMuted": True,
            "txPower": "LOW",
            "batteryType": "SB900A",
            "rfAntennaA": -35,
            "rfAntennaB": -45,
        }

        result = ShureDataTransformer.transform_transmitter_data(tx_data, 2)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["battery"], 3)
        self.assertEqual(result["battery_charge"], 75)
        self.assertEqual(result["runtime"], "02:00")  # 120 minutes = 2:00
        self.assertEqual(result["audio_level"], -20)
        self.assertEqual(result["rf_level"], -55)
        self.assertEqual(result["name"], "TX2")
        self.assertEqual(result["slot"], 2)  # Uses channel_num since slot not provided
        self.assertEqual(result["mute"], True)
        self.assertEqual(result["power"], "LOW")
        self.assertEqual(result["battery_type"], "SB900A")
        self.assertEqual(result["rf_antenna_a"], -35)
        self.assertEqual(result["rf_antenna_b"], -45)

    def test_transform_transmitter_data_minimal(self):
        """Test transmitter data transformation with minimal data."""
        tx_data: dict = {}

        result = ShureDataTransformer.transform_transmitter_data(tx_data, 1)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["battery"], 255)  # Default value
        self.assertEqual(result["audio_level"], 0)  # Default value
        self.assertEqual(result["rf_level"], 0)  # Default value
        self.assertEqual(result["frequency"], "")
        self.assertEqual(result["antenna"], "")
        self.assertEqual(result["status"], "")
        self.assertEqual(result["quality"], 255)  # Default value
        self.assertEqual(result["tx_offset"], 255)  # Default value
        self.assertEqual(result["name"], "")
        self.assertEqual(result["slot"], 1)  # Uses channel_num

    def test_transform_transmitter_data_exception_handling(self):
        """Test transmitter data transformation with exception handling.

        Provide a non-dict input (None) to force an internal exception and verify
        the transformer returns None in that case.
        """
        tx_data: Any = None  # Non-dict input to trigger internal exception handling

        result = ShureDataTransformer.transform_transmitter_data(tx_data, 1)
        self.assertIsNone(result)

    def test_map_device_type_various_formats(self):
        """Test device type mapping with various input formats."""
        test_cases = [
            ("ULXD", "ulxd"),
            ("ULX-D", "ulxd"),
            ("ULX_D", "ulxd"),
            ("ulxd", "ulxd"),
            ("QLXD", "qlxd"),
            ("QLX-D", "qlxd"),
            ("QLX_D", "qlxd"),
            ("qlxd", "qlxd"),
            ("UHFR", "uhfr"),
            ("UHF-R", "uhfr"),
            ("UHF_R", "uhfr"),
            ("uhfr", "uhfr"),
            ("AXIENT DIGITAL", "axtd"),
            ("AXIENTDIGITAL", "axtd"),
            ("AXIENT_DIGITAL", "axtd"),
            ("AXTD", "axtd"),
            ("AD", "axtd"),
            ("axtd", "axtd"),
            ("P10T", "p10t"),
            ("PSM1000", "p10t"),
            ("p10t", "p10t"),
            ("UNKNOWN", "unknown"),
            ("", "unknown"),
            (None, "unknown"),
        ]

        for input_type, expected in test_cases:
            with self.subTest(input_type=input_type):
                result = ShureDataTransformer._map_device_type(
                    str(input_type) if input_type is not None else ""
                )
                self.assertEqual(result, expected)

    def test_format_runtime_valid(self):
        """Test runtime formatting with valid inputs."""
        test_cases: list[tuple[int, str]] = [
            (0, "00:00"),
            (59, "00:59"),
            (60, "01:00"),
            (61, "01:01"),
            (120, "02:00"),
            (1439, "23:59"),  # Just under 24 hours
            (1440, "24:00"),  # Exactly 24 hours
            (1500, "25:00"),  # Over 24 hours
        ]

        for minutes, expected in test_cases:
            with self.subTest(minutes=minutes):
                result = ShureDataTransformer._format_runtime(minutes)
                self.assertEqual(result, expected)

    def test_format_runtime_invalid(self):
        """Test runtime formatting with invalid inputs."""
        test_cases: list[tuple[Union[None, int, str, list], str]] = [
            (None, ""),
            (-1, ""),
            (-100, ""),
            ("invalid", ""),
            ([], ""),
        ]

        for input_val, expected in test_cases:
            with self.subTest(input_val=input_val):
                result = ShureDataTransformer._format_runtime(
                    input_val if isinstance(input_val, int) or input_val is None else None
                )
                self.assertEqual(result, expected)
