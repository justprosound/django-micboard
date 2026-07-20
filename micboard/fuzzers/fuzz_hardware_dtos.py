#!/usr/bin/env python3
import sys

import atheris

with atheris.instrument_imports():
    from pydantic import ValidationError

    from micboard.services.hardware.dtos import WirelessChassisWrite


def TestOneInput(data: bytes) -> None:  # noqa: N802
    fdp = atheris.FuzzedDataProvider(data)

    try:
        WirelessChassisWrite(
            manufacturer=fdp.ConsumeUnicodeNoSurrogates(20) if fdp.ConsumeBool() else None,
            api_device_id=fdp.ConsumeUnicodeNoSurrogates(20) if fdp.ConsumeBool() else None,
            ip=fdp.ConsumeUnicodeNoSurrogates(15) if fdp.ConsumeBool() else None,
            serial_number=fdp.ConsumeUnicodeNoSurrogates(20) if fdp.ConsumeBool() else None,
            mac_address=fdp.ConsumeUnicodeNoSurrogates(17) if fdp.ConsumeBool() else None,
            name=fdp.ConsumeUnicodeNoSurrogates(50) if fdp.ConsumeBool() else None,
            model=fdp.ConsumeUnicodeNoSurrogates(20) if fdp.ConsumeBool() else None,
            firmware_version=fdp.ConsumeUnicodeNoSurrogates(20) if fdp.ConsumeBool() else None,
            description=fdp.ConsumeUnicodeNoSurrogates(100) if fdp.ConsumeBool() else None,
            wmas_capable=fdp.ConsumeBool() if fdp.ConsumeBool() else None,
            licensed_resource_count=fdp.ConsumeInt(100) if fdp.ConsumeBool() else None,
            subnet_mask=fdp.ConsumeUnicodeNoSurrogates(15) if fdp.ConsumeBool() else None,
            gateway=fdp.ConsumeUnicodeNoSurrogates(15) if fdp.ConsumeBool() else None,
            network_mode=fdp.ConsumeUnicodeNoSurrogates(20) if fdp.ConsumeBool() else None,
            is_online=fdp.ConsumeBool() if fdp.ConsumeBool() else None,
            band_plan_name=fdp.ConsumeUnicodeNoSurrogates(20) if fdp.ConsumeBool() else None,
            band_plan_min_mhz=fdp.ConsumeFloat() if fdp.ConsumeBool() else None,
            band_plan_max_mhz=fdp.ConsumeFloat() if fdp.ConsumeBool() else None,
        )
    except ValidationError:
        pass  # Expected when fuzzer generates invalid data for fields
    except ValueError:
        pass  # Sometimes raised directly by specific validator logic

if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
