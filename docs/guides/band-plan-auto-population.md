---
title: "Set a chassis band plan"
description: "Choose, detect or enter the frequency band plan of a wireless chassis."
type: how-to
audience: staff
---
A chassis has a band plan name and the minimum and maximum frequency of that band (`band_plan_name`, `band_plan_min_mhz`, `band_plan_max_mhz`). Regulatory coverage checks compare them with the frequency rules for the chassis location. Choose the way that fits your situation.

## Pick a standard band plan in the admin

1. Open the chassis in the Django admin and make sure **Manufacturer** and **Model** are set.
2. In the band plan section, use **Select Standard Band Plan**.
3. Save. The name and frequency range are filled from the plan.

The standard plans come from `micboard/fixtures/band_plans.yaml`. See [Band plan detection](api-band-plan-detection.md) for the list.

## Type a name that includes the range

Enter a name such as `G50 (470-534 MHz)` and leave the minimum and maximum empty. On save, the range is parsed from the name. If both numbers are already set, they are left alone.

## Enter everything by hand

Set the name and both frequencies yourself, for example `Custom UHF`, `470.0` and `534.0`. Nothing overwrites values you set.

## Let detection fill it in

When a chassis is saved with no band plan name, the model code is used to infer one (a code such as `G50` in `ULXD4Q-G50`). When a manufacturer API reports a `frequencyBand`, sync can resolve it the same way. See [Band plan detection](api-band-plan-detection.md).

## Set a band plan for many chassis from the shell

```python
from micboard.models.hardware.wireless_chassis import WirelessChassis

for chassis in WirelessChassis.objects.filter(
    manufacturer__code="shure", model__icontains="ULXD4Q"
):
    chassis.band_plan_name = "G50 (470-534 MHz)"
    chassis.band_plan_min_mhz = None
    chassis.band_plan_max_mhz = None
    chassis.save()  # the range is parsed from the name
```

## Add a standard band plan

Add an entry under the manufacturer in `micboard/fixtures/band_plans.yaml` and restart the application:

```yaml
manufacturer_code:
  band_key:
    name: "Display Name (470-534 MHz)"
    min_mhz: 470.0
    max_mhz: 534.0
    region: "US/EU"
```

## Check regulatory coverage afterward

See [Regulatory coverage monitoring](regulatory-coverage-monitoring.md).
