---
title: "Regulatory coverage monitoring"
description: "How django-micboard checks band plans and channel frequencies against regulatory frequency data."
type: explanation
audience: both
---
django-micboard flags equipment that operates, or could be coordinated, on frequencies for which it holds no regulatory data. The check runs at two levels, and a third level only reports the result.

## Where the checks run

| Level | What is compared | Meaning |
| --- | --- | --- |
| Chassis | The whole band plan range (`band_plan_min_mhz` to `band_plan_max_mhz`) against the regulatory domain of the chassis location | What the chassis could be coordinated to |
| RF channel | The channel's `frequency` against the same domain | What the channel is actually doing. Coordination happens here |
| Wireless unit | Delegates to its assigned RF channel | What the field device reports |

A chassis band plan is a range of frequencies the hardware can tune to. An RF channel carries one specific frequency. A wireless unit only echoes the channel it is assigned to, so its status is "via the channel".

## Where the data comes from

The regulatory domain of a chassis is resolved from its location: `location.regulatory_domain` first, then a lookup by country code (`rf_channel_service.get_regulatory_domain_for_location`).

Domains are `RegulatoryDomain` rows (`code`, `country_code`, general frequency bounds). Each has `FrequencyBand` rows with a start and end frequency and a `band_type` of `allowed`, `restricted`, `forbidden` or `guard`. Coverage means the compared frequency, or the whole band plan range, falls inside the domain's bands. Bands can be entered in the Django admin or imported from the CEPT ECO Frequency Information System (EFIS) with `import_efis_regulations`.

## Where the checks live

- `micboard/services/hardware/chassis_regulatory_service.py`: `get_band_plan_status`, `has_band_plan_regulatory_coverage`, `get_needs_band_plan_regulatory_update` and `get_band_plan_regulatory_status`. The last returns a dictionary with `has_band_plan`, `has_coverage`, `regulatory_domain`, `band_plan_range`, `needs_update` and `message`.
- `micboard/services/hardware/rf_channel_service.py`: `get_regulatory_domain`, `has_regulatory_coverage`, `get_needs_regulatory_update` and `get_regulatory_status` (`has_coverage`, `regulatory_domain`, `operating_frequency_mhz`, `needs_update`, `message`).
- `micboard/services/hardware/wireless_unit_service.py`: `get_assigned_rf_channel` and `get_regulatory_status`, which delegate to the channel and add a `source` of `rf_channel` or `no_channel`.

The Django admin shows the result as a status column on the chassis and RF channel lists. The `audit_regulatory_coverage` command reports it for every active chassis and channel.

To act on a finding, see [Resolve missing regulatory coverage](resolve-regulatory-coverage.md). To set the band plan itself, see [Set a chassis band plan](band-plan-auto-population.md).
