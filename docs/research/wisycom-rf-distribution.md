---
title: "Research: Wisycom combiners and splitters"
---
This note answers [#323](https://github.com/justprosound/django-micboard/issues/323): which
Wisycom combiners and splitters can be managed remotely, and what state they report. It
covers every model in Wisycom's
[Combiners & Splitters](https://wisycom.com/product-category/radiofrequency-distribution/combiners-splitters/)
category as of 2026-10-14. That's nine product pages, and the CSA121x page covers three
variants.

All sources are Wisycom's own product pages, brochures, manuals, and release notes.

## Summary

| Model | Passive or active | Direction and ports | Management interface | Monitorable by micboard |
| --- | --- | --- | --- | --- |
| CSA121A / B / T | Passive | 2:1 combiner or 1:2 splitter, 3 BNC | None | No. Inventory only |
| CSA221 | Passive | Double 2:1 combiner or 1:2 splitter, 6 BNC | None | No. Inventory only |
| CSI16T | Passive RF path, powered LED and selector logic | 16 inputs to 1, 2, or 4 outputs (combiner) | None. Front-panel selector and LEDs only | No. Inventory only |
| CSI16T2 | Passive RF path, powered selector | 16 inputs to 1 or 2 outputs (combiner) | None. Front-panel selector only | No. Inventory only |
| MAT244 | Active | Programmable matrix combiner, 8 BNC in, 4 BNC out | Ethernet 10/100. Wisycom Manager; Ember+ through Manager | Yes, through Manager-hosted Ember+ (see below) |
| MAT288 | Active | Programmable diversity matrix combiner, 8+8 BNC in, 8 BNC out | Ethernet 10/100. Wisycom Manager; Ember+ through Manager | Yes, through Manager-hosted Ember+ (see below) |
| MATF | Active | RF-over-fiber programmable matrix combiner, 8 zones (diversity) to 4 or 2 outputs | Ethernet 10/100, touchscreen, USB ("for future use"). Wisycom Manager; Ember+ in firmware v1.2.0 | Probably, over Ember+ (tree not published) |
| SPL2208 | Active | 2x2 diversity inputs to 8x2 outputs, plus cascade | Ethernet 10/100. Wisycom Manager only | Not without reverse-engineering the proprietary protocol |
| SPL2216 | Active | 2x2 diversity inputs to 16x2 outputs, plus cascade | Ethernet 10/100. Wisycom Manager only | Not without reverse-engineering the proprietary protocol |

**Bottom line:** Ember+ is the only open protocol Wisycom documents for any of these products.
It covers MAT244 and MAT288 when Wisycom Manager runs as the Ember+ provider. It also covers
MATF, whose firmware v1.2.0 notes add Ember+ support but don't say whether the device serves
it directly or through Manager. SPL2208 and SPL2216 are Ethernet-managed, but only through
Wisycom Manager's undocumented native protocol. The four passive or locally-switched models
have no data interface, so micboard can only record them for inventory and topology.

## Per-model detail

### CSA121A, CSA121B, CSA121T (passive 2-way combiner or splitter)

- **Type:** Passive wideband combiner or splitter, stripline construction, about 4 dB loss.
  It has 3 BNC-F connectors.
- **Variants:** CSA121A is DC-coupled to pass booster power (up to 1.5 A, 12 V), comes with
  a mains supply, and is rated for 125 mW. Its `-SPL` and `-CMB` sub-variants change which
  ports carry 12 V. CSA121B handles 2 W. CSA121T handles 3 W and is the "smart" variant:
  paired with an MTK952N transmitter, it lets the transmitter make up the combiner loss.
- **Management:** None. Its only active element is booster DC pass-through (CSA121A).
- **Reports:** Nothing.
- **Sources:** [product page](https://wisycom.com/product/csa121x/),
  [CSA121A brochure](https://wisycom.com/app/uploads/2022/03/CSA121A-en-b08.pdf),
  [CSA121B brochure](https://wisycom.com/app/uploads/2022/01/CSA121B-en-b04.pdf),
  [CSA121T brochure](https://wisycom.com/app/uploads/2022/01/CSA121T-en-b04.pdf),
  [Declaration of Conformity](https://wisycom.com/app/uploads/2022/12/CSI-CSA-en-DoC-v04.pdf).

### CSA221 (passive double combiner or splitter)

- **Type:** Passive, two CSA121-style 2-way sections in one housing, with 6 BNC-F
  connectors. It is DC-coupled for booster power (1.5 A) and rated for 125 mW. It has no
  power supply of its own.
- **Management:** None. **Reports:** Nothing.
- **Sources:** [product page](https://wisycom.com/product/csa221/),
  [brochure](https://wisycom.com/app/uploads/2022/03/CSA221-en-b04.pdf).

### CSI16T (smart passive 16-input transmitter combiner)

- **Type:** Passive combiner for in-ear-monitor and transmitter use, rated for 3 W per
  input. It has 16 BNC-F inputs and 6 N-F outputs. A front selector picks 16:1, 2x 8:1, or
  4x 4:1. Loss is about 6 dB (4:1), 9 dB (8:1), or 12 dB (16:1).
- **Power:** Redundant AC (90-264 V) and DC (10-28 V). The manual says *"CSI16T works without
  power supply! It works according to the latest set combiner mode."* Power drives only the
  RF-detect and LED circuitry.
- **Management:** None. It talks to MTK952N transmitters through the coax, for loss
  compensation, but it has no host interface.
- **Reports:** Front-panel LEDs only. They show RF presence per port (above 8 dBm),
  whether compensation is active per input, a "fault on the combiner path" warning (red
  flashing output LED), and AC/DC supply present and in use.
- **Sources:** [product page](https://wisycom.com/product/csi16t/),
  [user manual rev.05](https://wisycom.com/app/uploads/2022/01/CSI16T-en-u05_A5.pdf).

### CSI16T2 (smart passive 16-input combiner, second generation)

- **Type:** Passive, rated for 2.5 W per input, 400-1300 MHz. It has 16 BNC-F inputs and 3
  BNC-F outputs, with a 2-position selector (16:1 or 2x 8:1). It is DC powered (10-28 V,
  0.1 A, Hirose 4-pin).
- **Management:** The spec sheet lists the "Managing interface" as the *front-panel
  selector*. There is no network interface.
- **Reports:** Nothing remotely.
- **Sources:** [product page](https://wisycom.com/product/csi16t2/),
  [brochure](https://wisycom.com/app/uploads/2024/03/CSI16T2-en-b03.pdf).

### MAT244 (active programmable matrix combiner)

- **Type:** Active. It has 8 BNC inputs and 4 BNC outputs. Software selects the mode:
  diversity 4:2 (+7 dB), non-diversity 8:1 (+7 dB), or 8:4 (0 dB). The -X and -X1 variants
  run 150-840, 150-960, and 150-1160 MHz.
- **Management:** Ethernet 10/100 (RJ45), with DHCP or a static IP set from Wisycom
  Manager. It has an OLED display and a rotary knob. It also has a bidirectional
  data link over the input coax to Wisycom remote antennas and boosters (LFA, BFA, ADFA).
  Wisycom Manager can expose it over Ember+.
- **Reports** (from the manual's Info menu, alarm list, and the vendor feature list):
  - Identity: name, IP address, serial number, and firmware version (boot and application).
  - Temperatures: main board and RF board.
  - Supply diagnostics: Main RF 5 V, main logic 5 V, and main power 12 V rails.
  - Per input: RF level bar (A and B), booster DC on or off, booster voltage and current
    with an overload alarm, and attenuation or boost setting.
  - Alarms: high temperature, fan 1 or 2 failure, per-antenna DC overload,
    calibration-memory faults, I2C bus faults, temperature-sensor communication faults, and
    "Eth rx busy".
  - An integrated RF meter, and antenna scan (firmware 1.11 and later).
- **Firmware:** v1.13 (2021-06-14) is the latest listed.
- **Sources:** [product page](https://wisycom.com/product/mat244/),
  [brochure](https://wisycom.com/app/uploads/2019/11/MAT244-en-b05.pdf),
  [user manual](https://wisycom.com/app/uploads/MAT244_en-u03-A4.pdf).

### MAT288 (active diversity programmable matrix combiner)

- **Type:** Active. It has 8+8 BNC inputs (A and B diversity) and 8 BNC outputs. Software
  selects diversity 8:1 (+7 dB), 8:4 (0 dB), or 2x 4:2. It runs 150-1160 MHz depending on
  variant. It has redundant AC and optional DC supply.
- **Management:** Same as MAT244: Ethernet 10/100, Wisycom Manager, Ember+ through Manager,
  and coax data link to remote antennas.
- **Reports:** Everything MAT244 reports, plus separate RX-A and RX-B board temperatures.
  It also adds a *supply source* (AC or DC), an *external DC voltage* reading, and an
  *External DC low* alarm with a configurable threshold of 10.0-28 V. The per-antenna
  voltage and current diagnostics cover all 16 inputs.
- **Firmware:** v1.13 (2021-06-14) is the latest listed.
- **Sources:** [product page](https://wisycom.com/product/mat288/),
  [brochure](https://wisycom.com/app/uploads/2019/11/MAT288-en-b06.pdf),
  [user manual rev.03](https://wisycom.com/app/uploads/2024/03/MAT288_en-u03-A4.pdf).

### MATF (RF-over-fiber programmable matrix combiner)

- **Type:** Active, 170-1260 MHz. It takes up to 8 zones in diversity, mapped to 4 outputs
  or 2x 4:2. Input modules are coaxial or optical (single-mode, LC/APC or SC/APC, with up to
  6 optical modules). It has 4x BNC A and B outputs, input gain of -25 to +3 dB in 0.5 dB
  steps, a built-in spectrum scanner, a colour touchscreen, and redundant AC and DC supply.
- **Management:** Ethernet 10/100, plus touchscreen, buttons, and encoder. The USB port is
  "for future use". Wisycom Manager supports it, with major live-monitoring additions in
  v5.0.0. **Firmware v1.2.0 (2026-08-07) "Added Ember+ support"**, and Wisycom doesn't say
  whether that is native on the device or through Manager.
- **Reports** (brochure, firmware notes, and Manager v5.0.0 notes): per-input gain, booster
  voltage and current with an alarm, optical input level with high and low alarms, RF
  overload alarm, AC supply status and AC-input-loss alarm (firmware 1.1.0 and 1.2.0),
  panel temperature, diagnostic voltages, bootloader and firmware version, presets, and
  scanner data.
- **Gaps:** There is no public user manual, only a brochure, and no published Ember+ tree.
- **Sources:** [product page](https://wisycom.com/product/matf/),
  [brochure](https://wisycom.com/app/uploads/MATF-en-b04.pdf),
  [firmware release notes](https://wisycom.com/release/matf-v1-2-0/).

### SPL2208 and SPL2216 (active diversity splitters)

- **Type:** Active, 170-1260 MHz, about +5 dB input-to-output gain. Two diversity inputs
  (1A/1B and 2A/2B) each feed 8x2 (SPL2208) or 16x2 (SPL2216) BNC outputs, plus a cascade
  output. Input buttons give basic selection between the two zones. It has redundant DC
  input (10-28 V, XLR-4) and a 12 V, 500 mA booster bias on each input.
- **Management:** Ethernet 10/100 and front-panel buttons. Wisycom Manager reaches it, and
  through it, it uses the *Wisycom Remote Antenna Protocol* over coax to control LFA, BFA,
  and ADFA antennas. **The SPL22xx is not on Wisycom Manager's Ember+ list.**
- **Reports** (quick guide and brochure):
  - Per input: enabled or disabled, RF overload (above -10 dBm), and an RF level bar in
    Manager (0 dB means -20 dBm).
  - Booster bias state per input: off, on, under 10 mA, or over 500 mA and short circuit.
  - RF amplifier A and B alarm.
  - BIAS power (12 V) alarm.
  - DC1 and DC2 supply present (LEDs; it's unclear whether these reach Manager).
  - Lock state.
- **Firmware:** v1.1.0 (2024-06-19) is the latest listed.
- **Sources:** [SPL2208 page](https://wisycom.com/product/spl2208/),
  [SPL2216 page](https://wisycom.com/product/spl2216/),
  [brochure](https://wisycom.com/app/uploads/2019/02/SPL2216-SPL2208-en-b02.pdf),
  [SPL2216 quick guide](https://wisycom.com/app/uploads/ISTR-SPL2216-01_SPL2216-en-q01.pdf),
  [SPL2208 quick guide](https://wisycom.com/app/uploads/ISTR-SPL2208-01_SPL2208-en-q01.pdf).

## A protocol shared across product lines

Wisycom documents one management stack across its receivers, transmitters, and RF
distribution. It has three layers.

1. **Wisycom Manager (Windows).** This is the vendor tool for "most of Wisycom devices" over
   Ethernet, USB, IrDA, or Bluetooth. It discovers devices and sets static or DHCP IPs. Only
   one Manager at a time can hold a device; others see it as "busy". Its device-to-Manager
   protocol is **proprietary and undocumented**. Wisycom publishes no API, SDK, command
   reference, or SNMP MIB, and documents no web UI on these products.
   ([product page](https://wisycom.com/product/wisycom-manager/),
   [Help PDF](https://wisycom.com/app/uploads/Wisycom-Manager-Help.pdf))
2. **Master Remote Control.** This is a Manager-to-Manager feature on TCP port 32789
   (changed from 8000 in v4.0.0). It lets secondary PCs monitor or control devices that the
   primary PC holds. It covers MAT244, MAT288, SPL2208, SPL2216, MRK16, MRK950, MRK960,
   MRK980, MCR54, MTK952, MTK982, MFL, MFLC, BFLT2, BFLR2, and MPA221. It is not a
   third-party interface, and the device flag resets on reboot.
   ([Help PDF](https://wisycom.com/app/uploads/Wisycom-Manager-Help.pdf),
   [v4.0.0 release note](https://wisycom.com/app/uploads/WisycomManager-v4.0.0-Release-Note.pdf))
3. **Ember+ (open, Lawo).** Wisycom Manager 4.0.0 and later can act as an **Ember+
   provider**, on TCP port 9000 by default, for MAT244, MAT288, MFL, MRK980, MTK952,
   MTK952A, and MTK982. Ember+ must be enabled both in Manager and on each device. The
   **MRK980 receiver also serves Ember+ standalone**, enabled in firmware v2.6, and MATF
   gained Ember+ in firmware v1.2.0. Wisycom does not publish the Ember+ tree or parameter
   paths, but Ember+ trees are self-describing, so a consumer can walk them.
   ([Help PDF](https://wisycom.com/app/uploads/Wisycom-Manager-Help.pdf),
   [MRK980 firmware notes](https://wisycom.com/release/mrk980-v2-6/),
   [MATF firmware notes](https://wisycom.com/release/matf-v1-2-0/),
   [Ember+ specification](https://github.com/Lawo/ember-plus/wiki))

The *Wisycom Remote (Antenna) Protocol* is a separate data link carried over the RF coax.
MAT244, MAT288, MATF, SPL22xx, and MRK16 use it to talk to LFA, BFA, and ADFA antennas and
boosters. It is internal to the RF chain and not reachable from the IP network except
through Manager.

**What this means for micboard:** if micboard ever supports Wisycom, Ember+ is the one
documented, open path. It reaches both receivers (MRK980 standalone) and the managed RF
distribution (MAT244, MAT288, and MATF). For everything except the MRK980 and possibly the
MATF, it needs a Wisycom Manager instance running as the provider. SPL2208 and SPL2216
have no documented path that micboard could use.

## Confidence and gaps

- **High confidence:** the passive or active classification, port counts, and which models
  have Ethernet. These come straight from vendor spec sheets.
- **High confidence:** the Ember+ device list and port 9000 default for Manager. These come
  from the Help PDF and the v4.0.0 release note.
- **Medium confidence:** what each model reports *remotely*. Manuals list what the front
  panel shows and what the alarms are. That Manager or Ember+ exposes the same set is
  likely, but no parameter list is published.
- **Gap:** there is no public Ember+ tree for any Wisycom device. Confirming parameter paths
  needs a live device or a Manager instance with the provider enabled.
- **Gap:** whether MATF's Ember+ is native or Manager-hosted is unconfirmed, and there is
  no MATF user manual.
- **Gap:** the native Ethernet protocol, as used by discovery, polling, and "busy"
  locking, is undocumented. Nothing public covers SNMP, HTTP, or syslog on any model in
  this category.
- **Gap:** the SPL22xx DC1 and DC2 supply status is shown on LEDs, but the documents don't
  say whether it reaches Manager.
