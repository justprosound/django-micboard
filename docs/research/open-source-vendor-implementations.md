---
title: "Open-source implementations of wireless vendor protocols"
description: "What open-source projects already implement for Shure, Sennheiser, Audio-Technica, Lectrosonics, Wisycom, Sony, AKG, and MIPRO, and what django-micboard can borrow."
---
Research for issue #342 (part of #321). It builds on
[the vendor protocol landscape](https://github.com/justprosound/django-micboard/blob/research/vendor-protocol-landscape/docs/research/vendor-protocol-landscape.md)
(issue #322), which covers the vendors' own specs. This page covers what open-source code already
speaks those protocols, under which license, and what django-micboard can reuse.

Research date: October 2026. All sources are public GitHub repositories, read through the GitHub
API without running any of their code. Dates are each repository's last commit on its default
branch. On Bitfocus repositories that is often a dependabot bump, so "last human commit" is given
where it differs.

**License rule.** django-micboard is AGPL-3.0-or-later. MIT, BSD, Apache-2.0, LGPL,
GPL-2.0-or-later, GPL-3.0(-or-later), and AGPL-3.0 code can be incorporated with attribution.
GPL-2.0-only cannot. A repository with no license grants no reuse rights; only the facts in it
(command names, port numbers, behaviour) can inform our own code.

**Read-only rule.** django-micboard only reads from devices. Write and control commands are listed
here so that each plugin's read-only allowlist (`PluginTraits`, ADR-015) can block them.

## Summary

| Vendor | Best reusable source | License | Fixtures worth taking | Biggest gotcha |
| --- | --- | --- | --- | --- |
| Shure (command strings) | willcgage/wirelessboard `py/shure_protocol.py`; Bitfocus `shure-wireless`; open-avc drivers | MIT | wirelessboard characterization tests; Bitfocus PR #66 SLX-D+ transcripts | `METER_RATE` is a `SET`; QLX-D firmware 2.2.11+ locks up if a metering client vanishes |
| Shure (System API) | jbeale/companion-module-shure-systemapi | MIT | its System API v1.8 mock server | System API exposes no RF, frequency, or antenna data |
| Sennheiser SSCv1 | Bitfocus `sennheiser-ewdx` and `sennheiser-digital6000` | MIT | status-code and warning tables in `digital6000/src/errors.js` | EW-DX 4.x needs "Legacy Mode"; `identify` is triggered by a null value |
| Sennheiser SSCv2 | Bitfocus `sennheiser-spectera` | MIT | none | Basic auth user is `controlSennheiser` on Spectera, self-signed TLS |
| Sennheiser MCP (G3/G4) | s0600204-LiSP-Plugins/senn-rx-monitor | GPL-3.0-or-later | none (ewd-network-bridge demo replies are unlicensed) | `Push` keep-alive must be renewed before it lapses |
| Audio-Technica | Bitfocus `audiotechnica-digitalmixer` (envelope, multicast); wirelessboard PR #103 (wireless fields) | MIT | PR #103 tests; digitalmixer `tests/` | One TCP client per receiver; PR #103 is not hardware-validated |
| Lectrosonics | none licensed for wireless | n/a | none | Only unlicensed Venue code exists; DSQD and DR have no public code |
| Wisycom | Ember+: bob-integration ember_reader (Python); kuhfuss/emberplus (Go) for test vectors | GPL-3.0-or-later; AGPL-3.0-only | kuhfuss `s101/codec_test.go` byte vectors | The Wisycom Ember+ tree is not published anywhere; the MAT native port allows one client |
| Sony DWX | none | n/a | none | No public code or spec |
| AKG / HARMAN | generic HiQnet docs (RTI-Developers/hiqnet) | MIT | none | Nothing targets AKG wireless |
| MIPRO | none | n/a | none | Nothing found |

No Home Assistant core integration exists for any of these vendors. The only relevant HACS
integrations are brianegge/homeassistant-shure-wireless (Shure) and jessygoldfinger/HA-EmberPlus
(Ember+).

## Shure

### Shared wire grammar

Every Shure project below agrees on this grammar for the command-string protocol on TCP 2202:

- Commands are `< GET x PROP >` and `< SET x PROP value >`. Device-level properties omit `x`
  (`< GET MODEL >`), and `x=0` means all channels.
- Replies are `< REP x PROP value >`, metering is `< SAMPLE x ALL ... >`, and a refused command
  returns `< REP ERR >`. A message ends at `>`.
- Strings come back in `{...}`, space-padded to a fixed width. Numbers are zero-padded.
- UHF-R uses UDP to port 2202, frames with `*` (`* GET 1 CHAN_NAME *`), replies with `REPORT`,
  and starts metering with `* METER x ALL nnn *` (units of about 30 ms).
- PSM1000 (P10T) replies with `REPORT`, and clients terminate commands with `\r\n`.
- The device pushes a `REP` whenever any non-metered property changes, whatever changed it.
  `SAMPLE` frames flow only while `METER_RATE` is above zero.
- Raw-value offsets: `AUDIO_GAIN` +18; AD and SLX-D audio and RSSI +120; ULX-D `RX_RF_LVL` +128
  and `AUDIO_LVL` +50; battery temperature +40.
- Sentinels: 255 means unknown. `TX_BATT_MINS` uses 65535 unknown, 65534 calculating, and 65533
  communication warning. Chargers use 65529 full, 65533 calculating, and 65534 error for time to
  full.

Sources: [Bitfocus `src/internalAPI.js`](https://github.com/bitfocus/companion-module-shure-wireless/blob/master/src/internalAPI.js),
[open-avc ULX-D driver](https://github.com/open-avc/openavc-drivers/blob/main/audio/shure_ulxd.avcdriver),
[chargers HELP.md](https://github.com/bitfocus/companion-module-shure-chargers/blob/main/companion/HELP.md).

**`METER_RATE` is a `SET`.** Micboard, every Bitfocus Shure module, the Home Assistant
integration, and most other clients send `SET ... METER_RATE` on connect. A read-only plugin has
two options: allowlist exactly `SET <n> METER_RATE <digits>` as the one permitted write, or skip
metering and rely on pushed `REP` lines plus `GET` polling, as the open-avc drivers do.

### karlcswanson/micboard (the original Micboard)

- **Repo:** <https://github.com/karlcswanson/micboard>. MIT, compatible.
- **Activity:** last commit on `master` 2019-10-11; branch `0.8.7` 2021-05-29. Unmaintained.
- **Families** ([`py/device_config.py`](https://github.com/karlcswanson/micboard/blob/master/py/device_config.py)):
  `uhfr` (UDP), `qlxd`, `ulxd`, `axtd` (AD4D and AD4Q), and `p10t` (PSM1000). No SLX-D upstream.
- **Commands** ([`py/networkdevice.py`](https://github.com/karlcswanson/micboard/blob/master/py/networkdevice.py)):

  | Type | On connect | Poll every 10 s |
  | --- | --- | --- |
  | uhfr | `* GET {ch} CHAN_NAME *`, `* GET {ch} BATT_BARS *`, `* GET {ch} GROUP_CHAN *` | `* GET {ch} CHAN_NAME *`, `* GET {ch} TX_BAT *`, `* GET {ch} GROUP_CHAN *` |
  | qlxd, ulxd | `< GET {ch} ALL >` | `< GET {ch} CHAN_NAME >`, `< GET {ch} BATT_BARS >` |
  | axtd | `< GET {ch} ALL >` | `< GET {ch} CHAN_NAME >`, `< GET {ch} TX_BATT_BARS >` |
  | p10t | `< GET {ch} CHAN_NAME >\r\n`, `< GET {ch} FREQUENCY >\r\n` | `< GET {ch} CHAN_NAME >\r\n` |

- **Writes:** it sends `< SET {ch} METER_RATE 00100 >` (UHF-R: `* METER {ch} ALL 003 *`) on every
  connect. `disable_metering()` exists, but its `atexit` hook is commented out
  ([`py/shure.py`](https://github.com/karlcswanson/micboard/blob/master/py/shure.py)), so metering
  stays on after Micboard exits.
- **Session:** a `select()` loop with 0.2 s ticks. A connected device drops to disconnected after
  5 s without data, which relies on the 100 ms `SAMPLE` stream. Connect times out after 2 s, and
  reconnects follow after 20 s.
- **Discovery** ([`py/discover.py`](https://github.com/karlcswanson/micboard/blob/master/py/discover.py)):
  passive listen for SLP on `239.255.254.253:8427`, then a lookup of the `cd:` token in
  `dcid.json`. That file was converted from Shure's `DCIDMap.xml`, which ships in the Shure Update
  Utility, so the repository's MIT license probably does not cover it. Do not copy it.
- **Firmware quirks:**
  - QLX-D firmware 2.2.11 and later locks up completely (front panel and network) if a client that
    enabled `METER_RATE` disappears without closing. Reported to Shure in 2018 and unfixed; the
    workaround is rolling back to 2.1.5
    ([`docs/qlxd.md`](https://github.com/karlcswanson/micboard/blob/master/docs/qlxd.md)).
  - UHF-R over UDP fails inside Docker (issue #17), and UHF-R runtime can stick at 65535 (issue
    #16).
  - SLX-D needs "remote commands" enabled on the receiver. Without metering, the 5 s watchdog
    makes the connection flap (issue #47).
- **Fixtures:** none from hardware. `js/demodata.js` is synthetic.
- **Forks:** [s0600204/micboard](https://github.com/s0600204/micboard) (MIT, 2026-10-05) adds an
  untested `slxd` type and power-lock parsing. [willcgage/wirelessboard](https://github.com/willcgage/wirelessboard)
  (MIT, 2026-10-16) is the active successor; see below.

### Bitfocus Companion modules (all MIT)

**[companion-module-shure-wireless](https://github.com/bitfocus/companion-module-shure-wireless)**
(last human commit 2024-08-02):

- Families: ULXD4/D/Q, QLXD4, AD4D/AD4Q, SLXD4/D.
- Connect: `< GET 0 ALL >`, then `< SET 0 METER_RATE <ms> >` (default 5000, minimum 50).
- Keepalive: `< GET 1 METER_RATE >` every 30 s. Any line containing `METER_RATE` re-arms a 60 s
  timer, and the module reconnects if it expires.
- `SAMPLE` field positions: ULX/QLX `[3]` antenna, `[4]` RF−128, `[5]` audio−50. AD `[3]` quality,
  `[4]` audio LED, `[5]` peak−120, `[6]` RMS−120, `[7]` antenna, `[9]`/`[11]` RF−120. SLX
  `[3]` peak, `[4]` RMS, `[5]` RSSI. Comments at `internalAPI.js` lines 24–133 list the `REP` keys
  per family.
- Writes to block ([`src/actions.js`](https://github.com/bitfocus/companion-module-shure-wireless/blob/master/src/actions.js)):
  `CHAN_NAME`, `AUDIO_MUTE`, `AUDIO_GAIN` (including `INC`/`DEC`), `FREQUENCY`, `FLASH`,
  `SLOT_RF_OUTPUT`, `SLOT_RF_POWER_MODE`, `METER_RATE`.
- Quirks from issues: SLX-D refuses command strings until Controller Access is enabled (#39);
  QLX-D can enter an error state that needs a power cycle, so the maintainer advises a long meter
  interval or none (#21); QLX-D has no explicit transmitter-off, so it is inferred from
  `TX_TYPE UNKN` or bars 255 (#14); battery temperature should be raw−40, and the code adds 40
  (#62).
- **Open PR #66** (SLX-D+, verified on hardware with firmware 2.0.38.9;
  [protocol notes](https://github.com/mairginter/companion-module-shure-wireless/blob/feat/slxd-plus/docs/SLXDplus-protocol.md)):
  `< GET 0 ALL >` returns `< REP ERR >`, but per-channel `GET N ALL` works. `LINK_STATUS` needs the
  slot argument and returns lowercase `online`/`offline`. `LINK_TX_MODEL` does not exist; use
  `SLOT_TX_MODEL`. RSSI is one value, not per antenna. A trailing `*` on `FW_VER` means a failed
  self-test. Extra writes to block: `REM_PAIR`, `LINK_TX_REBOOT`, `NET_SETTINGS` (reboots),
  `ENCRYPTION_MODE`, `DEVICE_ID`, `GROUP_CHANNEL`. It ships `tests/regression.test.mjs`.
- **Open PR #77** (ANX4) reuses the AD grammar with `NUMBER_CHANNELS_LICENSED` and
  `AVAILABLE_CHANNELS`. Users report battery fields read NaN until transmitter firmware is updated.

**[companion-module-shure-psm1000](https://github.com/bitfocus/companion-module-shure-psm1000)**
(last human commit 2024-08-29): P10T only. Connect sends `< GET DEVICE_NAME >`, then per channel
`CHAN_NAME`, `AUDIO_IN_LVL`, `GROUP_CHAN`, `FREQUENCY`, `RF_TX_LVL`, `RF_MUTE`, `AUDIO_TX_MODE`,
and `AUDIO_IN_LINE_LVL`, each `\r\n`-terminated, then `SET n METER_RATE`. It parses `REPORT` only.
Writes to block: `CHAN_NAME`, `AUDIO_IN_LVL`, `FREQUENCY`, `RF_TX_LVL`, `RF_MUTE`,
`AUDIO_TX_MODE`, `AUDIO_IN_LINE_LVL`.

**[companion-module-shure-mxw](https://github.com/bitfocus/companion-module-shure-mxw)**
(2025-05-26): MXWAPT2/4/8 and MXWANI4/8. When `TX_AVAILABLE` becomes `YES` it queries
`TX_STATUS`, `TX_DEVICE_ID`, `BATT_RUN_TIME`, `TX_BATT_CHARGE`, `BATT_HEALTH`, `BUTTON_STS`,
`LED_STATUS`, `TX_TYPE`, and `BP_MIC_SELECT`. It handles `REP PRI ...` and ignores `REP SEC ...`.
Writes to block: `CHAN_NAME`, `AUDIO_GAIN`, `FLASH`, `UNLINK`.

**[companion-module-shure-chargers](https://github.com/bitfocus/companion-module-shure-chargers)**
(2026-09-07): SBRC and SBC220/240/441/840M. Connect sends `< GET 0 ALL >`; no keepalive. Keys
include `BATT_DETECTED`, `BATT_STATE`, `BATT_CHARGE`, `BATT_HEALTH`, `BATT_CYCLE`,
`BATT_TIME_TO_FULL`, `BATT_ERROR`. Writes to block: `STORAGE_MODE`, `FLASH`, `DEVICE_ID`, `REBOOT`.

### Other Shure projects

| Project | License | Last commit | What to note |
| --- | --- | --- | --- |
| [willcgage/wirelessboard](https://github.com/willcgage/wirelessboard) | MIT | 2026-10-16 | Micboard successor with a vendor seam ([`py/shure_protocol.py`](https://github.com/willcgage/wirelessboard/blob/main/py/shure_protocol.py)). Adds `slxd` and `slxdplus`. Stops metering with `METER_RATE 00000`. Best fixture source: [`py/tests/test_shure_protocol_characterization.py`](https://github.com/willcgage/wirelessboard/blob/main/py/tests/test_shure_protocol_characterization.py), with per-model `SAMPLE` lines. |
| [open-avc/openavc-drivers](https://github.com/open-avc/openavc-drivers) | MIT | 2026-10-15 | AD, ULX-D, QLX-D, SLX-D/SLX-D+, MXW drivers. Push-only, metering opt-in. Read-only liveness with `< GET MODEL >` every 30 s (QLX-D: `< GET DEVICE_ID >`). QLX-D has no `x=0`, so use `GET 1 ALL`. Ships documentation-based simulators (`shure_axient_digital_sim.py`, `shure_network_sim.py`). |
| [brianegge/homeassistant-shure-wireless](https://github.com/brianegge/homeassistant-shure-wireless) | MIT | 2026-10-10 | HACS integration for SLX-D, ULX-D, QLX-D, AD, AXT400. Avoids `GET 0 ALL` ("not supported on SLXD4D+"). Still sends `SET 0 METER_RATE 30000`. SLP and zeroconf `_shure._tcp` discovery; SLP payload fixture in `tests/test_discovery.py`. |
| [Cornerstone-Production/Stage-Utility](https://github.com/Cornerstone-Production/Stage-Utility) | GPL-3.0-or-later | 2026-10-06 | TCP keepalive plus a 60 s `GET 1 METER_RATE` heartbeat. Notes, verified on an SBC220, that chargers answer `GET 1 METER_RATE` and `GET 0 <field>` with `REP ERR`, so it uses `GET DEVICE_ID`. |
| [chris-ritsen/network-audio-controller](https://github.com/chris-ritsen/network-audio-controller) | Unlicense | 2026-10-13 | AD and P10T. Resets `METER_RATE 0` on shutdown. Finds devices through Dante. |
| [jbeale/companion-module-shure-systemapi](https://github.com/jbeale/companion-module-shure-systemapi) | MIT | 2026-08-27 | The only open client of the Shure System API. Reads `GET /api/v1/devices` and per-device sub-resources; WebSocket subscriptions. Writes to block: `PATCH` (mute, name, gain), `POST .../identify/start`, `POST .../reboot`. Its [mock server](https://github.com/jbeale/companion-module-shure-systemapi/tree/main/tools/mock-server) models System API v1.8 and states it has **no RF, frequency, or antenna data**. |
| [AVISPL/dal-infrastructure-management-shure-systemon](https://github.com/AVISPL/dal-infrastructure-management-shure-systemon) | MIT | 2026-09-28 | SystemOn REST client with JSON response fixtures for MXWAPT8, SBC850, and others under `src/test/resources/shure/responces/`. |
| [philipb232/node-red-contrib-shure-ad4](https://github.com/philipb232/node-red-contrib-shure-ad4) | Apache-2.0 | 2022-03-22 | Minor. |
| wtapper89/ChurchBoard | MIT | 2026-09-08 | Opens a connection per poll and sets `METER_RATE 100` without turning it off: the pattern behind the QLX-D lockup. Do not copy. |
| stagehacks/Cue-View | conflicting (GPL-2.0 file, CC BY-SA in package.json) | 2026-05 | Not reusable. |
| jdnelson19/RF-Ranger and several others | no license | — | Facts only. |

## Sennheiser

### Media Control Protocol (ew G3, G4, 2000), ASCII over UDP 53212

**[s0600204-LiSP-Plugins/senn-rx-monitor](https://github.com/s0600204-LiSP-Plugins/senn-rx-monitor)**
(GPL-3.0-or-later, 2026-01-25) is the most complete monitor
([`mcp_server.py`](https://github.com/s0600204-LiSP-Plugins/senn-rx-monitor/blob/master/mic_rx_monitor/servers/mcp_server.py)):

- One UDP socket bound to port 53212. Every 1 s it sends `Push 1 100 0` (1 s duration, 100 ms
  interval). If nothing arrives within that window it reports lost connection. `Push 0 0 1`
  requests a one-shot configuration dump.
- Parsed lines: `Name`, `Frequency`, `Squelch`, `RF1 <lvl> <peak>`, `RF2 <lvl> <peak>`, `RF`,
  `AF <lvl> <peak>`, `Bat <n|?>`, `Msg ...`, `Config`. Datagrams not starting with an uppercase
  letter are ignored.
- Discovery: multicast to `224.0.0.251:8133` from local port 8134 with a fixed binary blob
  containing `[servicecommand]devinfo\r\n`; replies come from source port 8133
  ([`mcp_discovery.py`](https://github.com/s0600204-LiSP-Plugins/senn-rx-monitor/blob/master/mic_rx_monitor/discovery/mcp_discovery.py)).
- README: firmware 1.7.0 or later is required; EM 100 G3/G4 and G2 cannot be monitored.

**[bitfocus/companion-module-sennheiser-evolutionwireless](https://github.com/bitfocus/companion-module-sennheiser-evolutionwireless)**
(MIT, 2026-10-13) covers the G4 SR IEM transmitter; EM parsing is a TODO and the author had no
networked receiver (issue #1). It sends `Push 60 <rate> 3` and renews every 60 s, exactly at
expiry, and queries bare keywords (`Frequency`, `Name`, `Sensitivity`, `Equalizer`, `Mode`).

**[jamesremuscat/ewd-network-bridge](https://github.com/jamesremuscat/ewd-network-bridge)** (no
license, 2023-08-11) emulates a G4 receiver for EW-D gear. It shows the device side: a `Push`
is echoed, then one `\r`-terminated line per attribute. Use only as a description of reply shape.

`Push <duration_s> <interval_ms> <mode>` mode values seen in use: 0 cyclic metering, 1 one-shot
configuration, 3 both. This comes from usage, not a spec.

**Writes to block:** `Mute`, `Name`, `Frequency`, `Sensitivity`, `Mode`, `AfOut`, `Equalizer`,
`Squelch <v>`, and any `#±n` nudge. Rule: allow only `Push ...` and bare keywords with no
arguments.

### SSCv1, JSON over UDP (EW-DX legacy mode, Digital 6000, SpeechLine)

Common rules: a read sets the leaf to `null`, for example
`{"device":{"identity":{"version":null}}}`. A write sets it to a value. Subscriptions use
`{"osc":{"state":{"subscribe":[{"#":{...}, <tree of nulls>}]}}}` and cancel with
`"#":{"cancel":true}`. The `#` key must come first or the subscription fails
([Specialelektronik `SscCommon.cs`](https://github.com/Specialelektronik/Sennheiser/blob/master/SIMPL%20SHARP/Specialelektronik.Products.Sennheiser.SscLib/SscCommon.cs)).

**[bitfocus/companion-module-sennheiser-ewdx](https://github.com/bitfocus/companion-module-sennheiser-ewdx)**
(MIT, 2026-10-10), EW-DX EM 2, EM 2 Dante, EM 4, and CHG 70N
([`src/ewdx.ts`](https://github.com/bitfocus/companion-module-sennheiser-ewdx/blob/main/src/ewdx.ts),
[`src/ewdxReceiver.ts`](https://github.com/bitfocus/companion-module-sennheiser-ewdx/blob/main/src/ewdxReceiver.ts)):

- UDP port 45, from an ephemeral local port. Binding to local port 45 failed with EACCES on Linux
  (issue #8).
- Static reads: `/device/identity/version`, `/device/identity/serial`, `/device/frequency_code`,
  network interfaces and MACs; CHG 70N `/device/identity/product`.
- Subscriptions with `lifetime: 10` (rx) or `60`, all renewed every 9 s. `/device/name` is read
  every 5 s as a ping, and a 2 s reply timeout marks the device disconnected.
- Subscribed trees: `rxN` (`warnings`, `divi`, `frequency`, `name`, `gain`, `mute`,
  `sync_settings.*`), `mates.txN` (`battery.{gauge,type,lifetime}`, `capsule`, `mute`,
  `warnings`, `type`, `trim`), meters `m.rxN.{divi,rsqi}`, and CHG 70N `bays` (`bat_gauge`,
  `bat_health`, `bat_cycles`, `bat_timetofull`, `state`, `warnings`).
- `warnings` is an array of strings such as `Aes256Error` and `AfPeak`; `rsqi == 0` means no
  signal.
- Writes to block: `/device/restart`, `/device/{name,location,brightness,lock,encryption,link_density_mode}`,
  `/device/identification/visual`, `/device/network/**`, `/rxN/{mute,name,gain,frequency}`,
  `/rxN/identification/visual`, `/rxN/sync_settings/*`, and CHG 70N `bays.identify` and
  `bays.sync_settings`.
- Firmware: EW-DX 4.0.0 or later answers SSCv1 only with "Legacy Mode" enabled (HELP.md). SSCv2 on
  4.0 covered only part of v1 (issue #5). Writing `sync_settings/mute_config` while the
  transmitter was muted locked up the receiver until firmware 4.1.1 (issue #12).

**[bitfocus/companion-module-sennheiser-digital6000](https://github.com/bitfocus/companion-module-sennheiser-digital6000)**
(MIT, 2026-09-29), EM 6000, EM 6000 Dante, L 6000:

- Port from mDNS `_ssc._udp` (TXT `Model=EM6000` or `L6000`), manual default 6970. Each message
  carries `"osc":{"xid":<id>}` and replies with another xid are dropped. Sends are spaced 5 ms.
- Identity: `{"device":{"identity":{"product":null,"vendor":null,"version":null}}}`.
- Subscriptions `"#":{min, max, lifetime:20, count:1000}`, renewed every 19 s; meters default to
  250 ms. EM 6000 trees: `mm`, `rxN.{audio_mute,name,encryption,active_warnings,active_status}`,
  `rxN.skx.{type,name,battery,capsule,...}`, `device.warnings`. L 6000:
  `slotN.subslotM.{led,accu_detection,accu_parameter}`.
- Meter decoding: `mm[ch]` = `[rf1, rf1peak, rf2, rf2peak, div1, div2, lqi, af, afpeak]`;
  RF dBm = (v − 255) / 2; AF dBFS = (v + 1) / 2 − 128. `skx.battery` = `[percent, minutes]`, and
  an empty array means no transmitter. Its LQI formula is wrong (yields only 0 or 100).
- [`src/errors.js`](https://github.com/bitfocus/companion-module-sennheiser-digital6000/blob/main/src/errors.js)
  holds the full SSC status-code table (200 to 503, including 310 subscription terminates and
  454 address not found) and the EM 6000 and L 6000 warning tables. Reusable as enums.
- Writes to block: `sys.{booster,brightness}`, `audio.outN.level_db`,
  `rxN.{audio_mute,encryption,name,carrier,active_bank_channel}`, `rxN.sync_settings.*`.
- **Guard warning:** `rxN.identify` is sent with a `null` value yet triggers identify. A guard that
  treats every null-valued message as a read lets it through, so `identify` must be denied by path.
- Bug to avoid: the EM 6000 cancel message misspells `subscribe`, so cancels never take effect.

**[Specialelektronik/Sennheiser](https://github.com/Specialelektronik/Sennheiser)** (MIT, C#,
2020-09-09) covers SpeechLine Digital Wireless, SL MCR DW, CHG 4N, and TCC2. Subscriptions use
lifetime 60 s, renewed every 29 s, with offline after 58 s of silence. Known issues: the SL MCR DW
stops accepting subscriptions after repeated reconnects until rebooted; error replies are
sometimes malformed JSON; MCR returns `bat_state` where `bat_lifetime` is documented.

Others: [jj-wohlgemuth/pyssc](https://github.com/jj-wohlgemuth/pyssc) (MIT, Python, SSCv1 over
TCP 45 with zeroconf `_ssc._tcp`; written for Neumann speakers),
[AVISPL TCC2 driver](https://github.com/AVISPL/dal-avdevices-microphone-sennheiser-tcc2) (MIT),
[gw-de/osc2ssc](https://github.com/gw-de/osc2ssc) (MIT). stoatworks-labs/MicWizard and RFutils
(MIT) use guessed paths marked unverified that contradict every working client; do not borrow.

### SSCv2, HTTPS REST plus SSE (Spectera; EW-DX 4.x in v2 mode)

**[bitfocus/companion-module-sennheiser-spectera](https://github.com/bitfocus/companion-module-sennheiser-spectera)**
(MIT, 2026-10-02; [`src/api.ts`](https://github.com/bitfocus/companion-module-sennheiser-spectera/blob/main/src/api.ts)):

- HTTPS 443 with Basic auth, user `controlSennheiser` (the EW-DX docs name the user `api`), and
  unverified TLS for self-signed certificates. Requests are serialized 20 ms apart.
- `GET /api/ssc/version` returns `{schema, protocol}`; the module expects schema 18.1 and warns on
  mismatch.
- Session: `GET /api/ssc/state/subscriptions` with `Accept: text/event-stream`; wait up to 15 s for
  `event: open` carrying `sessionUUID`; `PUT /api/ssc/state/subscriptions/{uuid}/add` with a JSON
  array of paths (`/api/rf/channels`, `/api/rf/antennas`, `/api/mts/paired/all`, `/api/health/*`,
  `/api/device/{identity,state,site}`, `/api/audio/metering`, ...); then initial GETs of the same.
- Liveness: `GET /api/device/state` every 5 s; reopen the stream after 60 s without events;
  backoff 500 ms × 2ⁿ capped at 30 s; `DELETE` the subscription on disconnect.
- Mobile-device fields: `batteryFillLevel`, `batteryRuntime`, `batteryLow`, `rssi`, `micLqi`,
  `dominantAntenna`, `interference.severity`, `versionMismatch`.
- Writes to block: `PUT` on audio inputs, outputs, RF channels, antennas, and paired devices;
  `POST`/`PUT`/`DELETE` on `/api/audio/links`. Guard rule: allow `GET` everywhere, and `PUT` or
  `DELETE` only under `/api/ssc/state/subscriptions/**`.
- Firmware: base station 1.4.1 or later required; 1.4.0 broke the connected state of mobile
  devices (module CHANGELOG 1.1.0).

The `sennheiser-adn-mediactrl` and `sennheiser-teamconnect-ceiling` Bitfocus modules are empty
templates. Sennheiser's own GitHub organisations publish no SSC examples or OpenAPI files. No
Sennheiser module ships captured device traffic.

## Audio-Technica

No Bitfocus module targets the ATW-R5220, ATW-DR3120, or ATW-R3210N. Three Bitfocus modules use
the same A-T IP-control envelope and are the reference for it (all MIT):

- **[companion-module-audiotechnica-digitalmixer](https://github.com/bitfocus/companion-module-audiotechnica-digitalmixer)**
  (2026-10-01, a real release). TCP 17300 plus UDP multicast notifications on
  `225.0.0.100:17000`. HELP.md notes some models ship with `239.0.0.100` and that notifications
  are off by default on the device. It joins the group with raw `dgram`, filters by sender IP
  (several devices can share a group), tears the link down when replies stop (a pulled cable
  leaves the socket open), and pipelines commands, dropping to one in flight on NAK 90 (busy).
  Error codes: 01 syntax, 02 invalid command, 03 divided-message error, 04 parameter, 90 busy, 92
  busy saving, 93 busy extension mode, 99 other. Notifications carry an `MD` prefix, and divided
  messages use `CS`/`CE` in place of `NC`. Fixtures: `tests/notices.spec.ts`, `tests/fake-tcp.ts`,
  `tests/command-queue.spec.ts`.
- **[companion-module-audiotechnica-system20](https://github.com/bitfocus/companion-module-audiotechnica-system20)**
  (System 20 PRO, TCP 17200). Frame: `cmd SP handshake SP id SP "00" SP "NC" SP params CR`, with
  handshake `O` for get and `S` for set. Naming: `g*` get, `s*` set, `r*` request or action,
  `n*` notification. One command in flight.
- **companion-module-audiotechnica-esw** (ESW, TCP 17200): `package.json` says MIT but the repo
  has no LICENSE file. Battery and charger field layouts for `glevelbatttx` and `glevelbatt`.
- Inconsistency: digitalmixer reads the NAK code at token 2, system20 and ESW at token 5. Settle it
  with a capture.

**Wireless-specific code** exists only in
[willcgage/wirelessboard draft PR #103](https://github.com/willcgage/wirelessboard/pull/103) (MIT,
updated 2026-10-12), `py/audio_technica_protocol.py`, which issue #93 grounds in A-T's spec v1.1.0:

- Models: ATW-R5220 and R5220DAN, ATW-DR3120 and DR3120DAN, ATW-R3210N.
- Reads: `gprch O 0000 00 NC <rx>\r` and `garlv O 0000 00 NC <rx>\r`. Notifications `nstch`,
  `narlv`, `nprch`, `nstmt`, `nstpw` arrive as `MD n... 0000 00 NC ...`.
- `garlv` field indices: TX audio 1, RX audio 2, antenna A 3, antenna B 5, antenna select 7, TX
  lock 20, battery bucket 25 (0–4 in 20 % steps), frequency 26 (9-digit Hz). RSSI is −96 to
  −45 dBm.
- Fixtures: `py/tests/test_audio_technica_protocol.py`, spec-derived `garlv` and `gprch` lines,
  including one split across two reads.
- Caveats: not validated on hardware. It polls every 4 s instead of using the multicast
  notifications. The reply to `garlv` with no transmitter on is unknown.

**Guard:** allow `g*` commands with handshake `O`. Block `s*` (handshake `S`), all `r*`, and
`sitlv`, which sets the level-notification interval and is therefore a write. The multicast
listener is passive. Hold the single TCP session briefly or not at all, because a receiver accepts
one client.

## Lectrosonics

No licensed open-source code speaks a Lectrosonics wireless receiver. Searches for DSQD, DR,
VRM2WB, VRMWB, Wireless Designer, and the command names returned nothing usable.

- **dcsim0n/PocketVenueRN** (no license, 2020-08-22) monitors Venue WB, Venue 2, Duet M2T, and D2
  over TCP 4080. Facts: reads look like `rxname(n) ?\r` (space before `?`), `*` means all
  channels, and replies are `OK {a,b,...}\r\n` or `OK "str"\r\n`. VRM2WB reads include `id ?`,
  `rxblock(n) ?`, `txblevel(*) ?` (battery voltage), `txbatt(*) ?`, `rxlink(*) ?` (pilot),
  `rmeter(*) ?` (RF), `rxfreq(*) ?` (kHz), `rxpresent(*) ?`, `rxalevel(*) ?`. VRWB uses
  `block`, `bvolts`, `signal`, `mhz`, `level`. Writes: `rxscan(n)=`, `rxalevel(n)=`, `rxfreq(n)=`,
  `mhz(n)=`, `txbatt(n)=`, `rxname(n)=`. It opens one TCP connection per command, one at a time,
  with a 1 s timeout.
- **dcsim0n/venue-server** (no license, 2020-04-06) is a Venue protocol simulator. Design reference
  only.
- **[bitfocus/companion-module-lectrosonics-aspen](https://github.com/bitfocus/companion-module-lectrosonics-aspen)**
  (MIT) is a DSP mixer, but confirms the grammar on TCP 4080: `!ingn(*)?\n` reads, `!ingn(3)=45\n`
  writes, replies `OK ...` or `ERROR` with CRLF.

**Guard:** allow only commands ending in `?`. Block anything with `=` or a `tog` suffix. The DSQD
and DR vocabulary must come from Lectrosonics' WebHelp, not from open-source code.

## Wisycom

- **[bitfocus/companion-module-wisycom-mat](https://github.com/bitfocus/companion-module-wisycom-mat)**
  (MIT, 2026-09-13) covers the MAT244 and MAT288 only, and **does not use Ember+**. It speaks a
  native binary protocol on TCP 2101 with an optional 8-character password. HELP.md: "The MAT only
  supports one TCP connection at a time. This module cannot be used in parallel with Wisycom
  Manager." For django-micboard this means MAT units should be read through Wisycom Manager's
  Ember+ provider, not directly.
- Frame (`src/api.ts`, `src/enum.ts`): `0xC0 | SRC | DST | TOKEN | SIZE | STATUS | CMD | [SUBCMD] |
  payload | XOR checksum | 0xC1`, with `0x7D` byte stuffing. PC address `0xFE`, device `0x00`.
  Commands include ID `0x02`, SERIAL `0x03`, APP_VER `0x06`, STATUS `0x0D`, TEMP `0x2F`, VOLTAGE
  `0x44`, and ANTENNA `0x5D` (sub-commands for matrix, gain, boost diagnostics).
- Read and write share opcodes: an empty payload reads, a payload writes. A guard must check opcode
  and payload together. Always-write commands: SAVE_PAR `0x59`, MESSAGE `0x2B`, CLEAR `0x0E`,
  AUTO_STATUS `0x5C`, CLOSE `0x01`.
- Quirks: AUTO_STATUS is `0x5C` although the vendor document says `0x5A` ("PCAP says otherwise").
  The module sends CLEAR automatically when events are pending, which changes device state; a
  read-only port must not copy that.
- Fixtures: `src/api.test.ts` builds synthetic frames. Its values include a real-looking serial;
  do not reuse them.
- No other public Wisycom implementation exists. **The Wisycom Ember+ tree is not documented in
  any public source**; it must be learned by crawling with GetDirectory against real gear and
  recorded as scrubbed fixtures.

## Ember+ for a read-only Python consumer

Glow facts from Lawo's [`GlowDtd.asn1`](https://github.com/Lawo/ember-plus/blob/master/EmberLib.net/EmberLib.Glow/Documentation/GlowDtd.asn1):
command numbers are subscribe 30, unsubscribe 31, getDirectory 32, invoke 33. Parameter access is
none 0, read 1, write 2, readWrite 3.

**What a read-only consumer sends:** commands 30, 31, and 32 inside an empty Node, QualifiedNode,
QualifiedParameter, or QualifiedMatrix shell, plus S101 keepalive requests and responses.
**What the guard blocks:** any Parameter or QualifiedParameter (APPLICATION 1 or 9) carrying
`contents` (a SetValue); any Matrix or QualifiedMatrix (APPLICATION 13 or 17) carrying
`connections`; and command 33 or an Invocation (APPLICATION 22). The safest design is an encoder
that can only build the allowed shapes, plus a decode-and-check of every outbound frame.

PyPI still has no Ember+ package (`emberplus`, `ember-plus`, `pyemberplus`, `s101`, and similar
names all return 404).

| Project | License, compatible? | Last commit | Notes |
| --- | --- | --- | --- |
| scy/pyemberplus | — | — | Does not exist (404). `scy/ember-plus` is a BSL-1.0 C++ fork of Lawo's library, last commit 2020-06-09. |
| [jessygoldfinger/HA-EmberPlus](https://github.com/jessygoldfinger/HA-EmberPlus) | MIT, yes | 2026-02-20 (one commit) | Python asyncio, `ember.py` 1,203 lines. S101 with CRC and escaping, keepalive replies. Gaps: no multi-packet reassembly, qualified elements only, no REAL, no Matrix, finds end-of-contents by scanning for the first `00 00` (wrong when nested), omits the Root wrapper. Exposes bool and int writes. |
| [bob-integration/bobitools-plugin-ember_reader](https://github.com/bob-integration/bobitools-plugin-ember_reader) | GPL-3.0, yes | 2026-10-10 | Python consumer, `ember_client.py` 616 lines. Multi-packet S101 reassembly, CRC-16/X-25, Root wrapper, long-form tags, REAL. Gaps: no indefinite-length BER, blocking sockets, no keepalive reply, detects end of response by 0.3 s of silence. |
| [bob-integration/bobitools-service-emberplus](https://github.com/bob-integration/bobitools-service-emberplus) | GPL-3.0, yes | 2026-10-10 | Python **provider** (`emberplus_glow.py`, 920 lines), not a consumer. Its encoder rejects indefinite lengths. |
| [johannes-kuhfuss/emberplus](https://github.com/johannes-kuhfuss/emberplus) | AGPL-3.0-only, yes (ported files stay AGPL-3.0-only) | 2026-08-29 | Go, about 5,000 lines plus 8,300 lines of tests. The most complete consumer: definite and indefinite lengths, all Glow types, both S101 framings, multi-packet, mandatory keepalive replies. README: GetDirectory establishes update traffic, so directory polling is unnecessary and Subscribe is needed only for streams and matrices. Byte vectors in `s101/codec_test.go`. |
| [Sofie-Automation/sofie-emberplus-connection](https://github.com/Sofie-Automation/sofie-emberplus-connection) | MIT, yes | 2026-08-10 | TypeScript reference consumer (npm `emberplus-connection`). Keepalive every 10 s with a 500 ms response limit, request timeout 3 s, reconnect after 5 s, default port 9000, frame cap 4 MB and message cap 16 MB. |
| [bitfocus/companion-module-generic-emberplus](https://github.com/bitfocus/companion-module-generic-emberplus) | MIT, yes | 2026-10-02 | Patches emberplus-connection 0.3.1 to fix indefinite-length end-of-contents in matrices ("Expected 0xa0: got 0x0"), allow unlimited reconnects, and drop an extra getDirectory on subscribe. |
| [dewiweb/emberplus_rust](https://github.com/dewiweb/emberplus_rust) | MIT or Apache-2.0 | 2026-01-26 | Rust. Its command numbers disagree with the DTD; do not trust it. |
| [Lawo/ember-plus](https://github.com/Lawo/ember-plus) | BSL-1.0, yes | 2025-10-22 | C++ and C# reference and spec. No Python. |

**Recommendation.** Write a small asyncio consumer in django-micboard. Seed it from bob-integration's
`ember_client.py` (GPL-3.0, Python, closest primitives), and use kuhfuss/emberplus and
emberplus-connection as behavioural references. Take test vectors from kuhfuss
`s101/codec_test.go` (an indefinite-length GetDirectory, escaping, and a multi-packet split).
Fill the gaps ourselves: indefinite-length BER (Lawo-based providers emit it), non-qualified
Node and Parameter with number paths, Matrix decode, a read pump that answers keepalives, and size
caps. HA-EmberPlus (MIT) is legal to borrow but structurally weaker. Porting the Go library is
legal but would make those files AGPL-3.0-only.

## Sony, AKG / HARMAN, and MIPRO

- **Sony DWX:** no open-source code and no Bitfocus module. Searches for DWR-R03D, DWR-R02, DWR-S03D,
  and "Wireless Studio" returned only frequency tables and manual mirrors.
- **AKG / HARMAN:** no project targets the DMS800, WMS4500, or HUB4000. Generic HiQnet stacks exist:
  [RTI-Developers/hiqnet](https://github.com/RTI-Developers/hiqnet) (MIT, 2026-06-10) documents TCP
  3804 for commands and UDP 3804 for meters, a Discovery message on connect and as keepalive, and
  notes that "older devices (AKG, dbx, JBL, older Crown)" use an enumeration subscription type
  rather than a bitmask. Wireshark's `packet-hiqnet.c` (GPL-2.0-or-later) lists message IDs. Writes
  a HiQnet guard would block: `0x0100` MultiParamSet, `0x0101` MultiObjectParamSet, `0x0102`
  ParamSetPercent, `0x010e` SetAttributes, `0x0124` Store, `0x0125` Recall, `0x0129` Locate, and
  `0x0006` SetAddress. EMATech/HiQontrol and rutledgek/HiQNet are GPL-3.0 libraries.
- **MIPRO:** nothing found for ACT-BUS or the MES-100.

Band-plan data for every vendor, including A-T, Lectrosonics, Sony, AKG, and MIPRO, is in
[berkon/wireless-microphone-analyzer](https://github.com/berkon/wireless-microphone-analyzer)
`frequency_data/vendor_bands/` (MIT).

## Findings for the plugin contract and simulator

1. **Every vendor that can be monitored has open code to borrow, except Lectrosonics.** Shure,
   Sennheiser, and A-T have MIT clients; Wisycom has an Ember+ path. Sony, AKG, and MIPRO have
   nothing.
2. **The read-only guard cannot be "verb equals GET".** Shure metering is a `SET`; Sennheiser
   `identify` is a null-valued read shape; Wisycom MAT and Ember+ use one opcode for read and
   write. Each plugin's allowlist must be written per protocol, as the guard rules above show.
3. **Exclusive sessions are common.** A-T receivers and Wisycom MAT accept one TCP client, and
   QLX-D locks up if a metering client vanishes. Prefer push channels (A-T multicast, Shure `REP`,
   Ember+ GetDirectory updates) over held sessions, and always turn metering off on shutdown.
4. **Captured hardware fixtures barely exist.** Most fixtures are spec-derived or synthetic. Only
   Bitfocus PR #66 (SLX-D+) and Stage-Utility's charger notes are hardware-verified. That supports
   ADR-015's verified and unverified tiers, and means the simulator has to be built from our own
   captures for anything marked verified.

## Borrow table

| Vendor | What to reuse | From where | License |
| --- | --- | --- | --- |
| Shure | Command-string transport and parser shape, per-model `SAMPLE` layouts, characterization fixtures | willcgage/wirelessboard `py/shure_protocol.py` and `py/tests/` | MIT |
| Shure | `REP` key inventory per family, write list for the guard | Bitfocus `shure-wireless` `src/internalAPI.js`, `src/actions.js`; `shure-psm1000`, `shure-mxw`, `shure-chargers` | MIT |
| Shure | SLX-D+ facts and regression transcripts | Bitfocus `shure-wireless` PR #66 branch | MIT |
| Shure | Read-only liveness (`GET MODEL`, `GET DEVICE_ID`), push-only model, simulators | open-avc/openavc-drivers | MIT |
| Shure | SLP discovery parsing and fixture | brianegge/homeassistant-shure-wireless `discovery.py`, `tests/test_discovery.py` | MIT |
| Shure | System API mock and endpoint list | jbeale/companion-module-shure-systemapi `tools/mock-server/` | MIT |
| Sennheiser | SSCv1 subscription trees, renewal timing, write list | Bitfocus `sennheiser-ewdx` | MIT |
| Sennheiser | SSC status codes, warning enums, `mm` meter decoding | Bitfocus `sennheiser-digital6000` `src/errors.js`, `src/parseResponse.js` | MIT |
| Sennheiser | SSCv2 SSE session, heartbeat, and reconnect state machine | Bitfocus `sennheiser-spectera` `src/api.ts` | MIT |
| Sennheiser | MCP keep-alive, line parser, discovery on 8133 | senn-rx-monitor | GPL-3.0-or-later |
| Sennheiser | SpeechLine and MCR paths, firmware quirks | Specialelektronik/Sennheiser | MIT |
| Audio-Technica | Envelope, NAK table, multicast listener, dead-link watchdog, fixtures | Bitfocus `audiotechnica-digitalmixer` | MIT |
| Audio-Technica | `garlv`/`gprch` field indices and fixtures | wirelessboard PR #103 `py/audio_technica_protocol.py` | MIT |
| Lectrosonics | Nothing licensed; grammar confirmation only | Bitfocus `lectrosonics-aspen`; vendor WebHelp | MIT (grammar only) |
| Wisycom | Ember+ consumer seed | bob-integration/bobitools-plugin-ember_reader | GPL-3.0 |
| Wisycom | Ember+ test vectors and behaviour | johannes-kuhfuss/emberplus `s101/codec_test.go`; sofie emberplus-connection | AGPL-3.0-only; MIT |
| Wisycom | MAT native frame map (only if native access is ever needed) | Bitfocus `wisycom-mat` | MIT |
| Sony | Nothing | — | — |
| AKG / HARMAN | HiQnet framing and message IDs, if ever needed | RTI-Developers/hiqnet | MIT |
| MIPRO | Nothing | — | — |
| All | Band-plan data | berkon/wireless-microphone-analyzer | MIT |

## Gaps

- Lectrosonics DSQD and DR, Sony DWX, AKG wireless, and MIPRO have no open implementation.
- The Wisycom Ember+ tree needs a crawl of real gear.
- A-T wireless code has not been validated against hardware.
- No project publishes captured traffic from Sennheiser hardware.
