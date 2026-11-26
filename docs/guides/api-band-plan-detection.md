---
title: "Band plan detection"
description: "Standard band plans and the functions that resolve a chassis band plan from API or model data."
type: reference
audience: developer
---
## Standard band plans

Defined in `micboard/fixtures/band_plans.yaml` and loaded by `micboard/models/band_plans.py`, keyed by manufacturer code and band key.

| Manufacturer | Key | Name | Region |
| --- | --- | --- | --- |
| shure | `g50` | G50 (470-534 MHz) | US/EU |
| shure | `h50` | H50 (534-598 MHz) | US/EU |
| shure | `j50` | J50 (572-636 MHz) | International |
| shure | `l50` | L50 (632-696 MHz) | Asia/Pacific |
| shure | `x52` | X52 (902-928 MHz) | US ISM/STL |
| shure | `z16` | Z16 (1.24-1.26 GHz) | Japan |
| sennheiser | `aw_plus` | Aw+ (470-558 MHz) | US |
| sennheiser | `bw` | Bw (626-698 MHz) | US |
| sennheiser | `gw` | Gw (558-626 MHz) | US |
| sennheiser | `a` | A (516-558 MHz) | Global |
| sennheiser | `g` | G (566-608 MHz) | Global |
| sennheiser | `b` | B (626-668 MHz) | Global |
| wisycom | `b1` | B1 (470-663 MHz) | Wideband |
| wisycom | `b2` | B2 (470-800 MHz) | Wideband |

## Lookup functions

All in `micboard.models.band_plans`, with keyword-only arguments.

| Function | Returns |
| --- | --- |
| `get_available_band_plans(manufacturer=)` | `(key, name)` pairs for a manufacturer |
| `get_band_plan(manufacturer=, band_plan_key=)` | The plan's dictionary (`name`, `min_mhz`, `max_mhz`, `region`), or `None` |
| `parse_band_plan_from_name(name=)` | `{"min_mhz", "max_mhz"}` parsed from a name such as `G50 (470-534 MHz)`, or `None` |
| `detect_band_plan_from_api_string(api_band_value=, manufacturer=)` | A plan name, or `None` |
| `get_band_plan_from_model_code(manufacturer=, model=)` | A plan name found from a band code in the model string, or `None` |

`detect_band_plan_from_api_string` tries, in order: an exact key match, a code match, an exact frequency-range match (such as `470-534`), and a partial key match.

## Chassis services

In `micboard/services/hardware/chassis_regulatory_service.py`:

- `detect_band_plan_from_api_data(chassis, *, api_band_value=None)` returns a `BandPlanInfo` (`name`, `min_mhz`, `max_mhz`, `source`, `message`). It tries the API value first (`source="api"`), then the chassis model (`source="model"`). With neither, `name` is `None`.
- `apply_detected_band_plan(chassis, *, api_band_value=None)` copies the detected name and range onto the chassis and returns whether detection succeeded. It does not save.
- `prepare_chassis_regulatory_fields(chassis)` runs on save. It applies device specifications, parses the range from `band_plan_name` when a name is set without a range, and infers a plan from the model code when no name is set.

```python
from micboard.services.hardware.chassis_regulatory_service import apply_detected_band_plan

if apply_detected_band_plan(chassis, api_band_value="G50"):
    chassis.save()
```

Coverage checks are described in [Regulatory coverage monitoring](regulatory-coverage-monitoring.md).
