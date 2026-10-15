---
title: "Wireless vendor protocol landscape"
description: "Which wireless microphone, IEM, and RF distribution vendors expose a network protocol, and how."
---
Research for issue #322 (part of #321). The question is which manufacturers of wireless
microphones, in-ear monitors (IEMs), and RF distribution gear expose a network monitoring or
control protocol, what that protocol is, and what limits apply. The findings feed the plugin
contract and the per-vendor tracks.

Research date: October 2026. All findings come from public vendor material. Each claim cites its
source. Where only a secondary source exists, the text says so.

## Summary table

| Vendor | Protocol and transport | Public spec | Topology | Auth | Read or control | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| Shure (System API) | REST over HTTPS, plus WebSocket subscriptions | Partly. Vendor-hosted reference; download needs registration | Manager: a System API server process talks to devices | `x-api-key` header (shared key) | Both | High |
| Shure (command strings) | Plain-text ASCII over TCP port 2202 (UHF-R uses UDP) | Yes, a PDF for each product | Direct to each device | None | Both; device pushes `REP` on change and `SAMPLE` meters | High |
| Sennheiser SSCv2 | REST over HTTPS (HTTP/1.1, TLS 1.2), plus Server-Sent Events | Yes. Spec 2.3 plus an OpenAPI file for each device | Direct to each device | HTTP Basic, user `api`; off by default | Both | High |
| Sennheiser SSCv1 | JSON over UDP, default port 45; mDNS `_ssc` | Yes. Developer guide for each product | Direct to each device | None | Both; `/osc/state/subscribe` | High |
| Sennheiser Media Control Protocol (ew G3/G4, 2000) | ASCII over UDP port 53212 | Yes. TI 1254 (G4) | Direct to each device | None | Both; cyclic push driven by keep-alive | High |
| Audio-Technica (5000, 3000 Digital, 3000 N) | ASCII commands over TCP 17300, plus UDP multicast notifications on port 17000 | Yes. "IP Control Protocol Specifications" v1.1.0 | Direct to each device; one TCP client at a time | None | Both | High |
| Lectrosonics (DSQD, DR, M2T, VRMWB, VRM2WB) | Text request and response over TCP (default port 4080) or serial | Yes. Wireless Designer WebHelp, with an ABNF grammar | Direct to each device | None documented | Both; request and response only, no push | Medium-high |
| Wisycom | Ember+ (open, TCP) through Wisycom Manager (default port 9000); the MRK980 also runs Ember+ standalone | Ember+ framework is open (BSL-1.0); Wisycom's parameter tree is not published | Mostly a manager (Wisycom Manager as Ember+ provider) | None documented | Both | Medium |
| Sony (DWX) | Proprietary. Wireless Studio, Wireless Studio Mobile, and Cross Remote | No | Manager (Wireless Studio) | Unknown | Unknown to third parties | Low (gap) |
| AKG / HARMAN (DMS800, WMS4500, DMS700) | HARMAN HiQnet (proprietary); the WMS4500 and DMS700 need a HUB4000 Q | No public third-party spec found | Manager (System Architect or Audio Architect) or a hub | Unknown | Both, from HARMAN tools | Low |
| MIPRO (ACT) | ACT-BUS through an MES-100 bridge (USB or RS-232) | Not found | Bridge or manager | Unknown | Unknown | Low |

RF distribution coverage is in [RF distribution and spectrum gear](#rf-distribution-and-spectrum-gear).

## Shure

Shure has two independent paths.

### System API (manager)

- **What:** Shure describes the System API as a "Desktop and server app for controlling and
  monitoring Shure devices." It is a server process that discovers and talks to the devices,
  and clients talk only to that server.
  ([product page](https://www.shure.com/en-US/products/software/systemapi))
- **Transport:** REST under `https://<host>:10000/api/v1/...`, plus a WebSocket at
  `wss://<host>:10000/api/v1/subscriptions/websocket/create`. Clients subscribe over the
  WebSocket and then start and stop features with POST calls. REST calls need the `x-api-key`
  header; opening the WebSocket does not need the shared secret.
  ([Shure System API Server specification, "Getting Started"](https://shure.stoplight.io/docs/shure-system-api-server-specification/f4e6fa31af431-getting-started-with-system-api-server).
  That page renders client-side, so this summary comes from its search-indexed text. The
  existing `micboard/integrations/shure/` client matches it.)
- **Product families:** Shure release notes list minimum firmware for MXW (APT, transmitters,
  NCS), QLX-D (`QLXD4`), ULX-D (`ULXD4/D/Q`), and SBC chargers. They note that the ULX-D6/8
  connects only when docked in an SBC250, SBC450, or SBC850. The notes also cover the MXA, P300,
  and IntelliMix Room. I did not find an official current list that names Axient Digital or
  PSM1000; check the release notes of the System API version in use.
  ([System API release archive](https://shure.com.cn/zh-CN/support/downloads/software-firmware-archive/system-api);
  latest is 6.10.0, July 2026.)
- **Known limit:** release notes report a "deadline exceeded" error on first queries in
  networks of 100 or more devices.
- **Licensing:** the download link is registration-scoped. No EULA text was reviewed (gap).

### Command strings (direct, per device)

- **Transport:** plain-text ASCII over TCP port 2202, with the control system as the client.
  Messages look like `< GET 1 CHAN_NAME >`, `< SET ... >`, `< REP ... >` (the device reports on
  change, except metered values), and `< SAMPLE ... >` for metering at a set rate.
  (Shure command-strings PDFs for ULX-D v1.0 2022 and SLX-D v2 2020, read from mirrors of Shure
  documents. Shure's own index is at
  [shure.com/docs/commandstrings](https://www.shure.com/en-US/docs/commandstrings), but it
  renders client-side.)
- **Families:** ULX-D, QLX-D, SLX-D, Axient Digital (AD4D/AD4Q), and PSM1000 (P10T) use TCP.
  UHF-R uses UDP with a `* GET ... *` framing. The open-source Shure Micboard (MIT) speaks these
  protocols and discovers devices by listening for SLP multicast on `239.255.254.253:8427`.
  ([karlcswanson/micboard `py/device_config.py`, `py/networkdevice.py`, `py/discover.py`](https://github.com/karlcswanson/micboard))
- **Auth:** none. Anyone who can reach port 2202 can send `SET` commands, so a read-only
  integration has to enforce read-only itself.

## Sennheiser

Sennheiser has three generations. Its application note AN 1260 lists two proprietary
families: the Sound Control Protocol (SSC) and the older Media Control Protocol.
([AN 1260 v1.0, Media Control Systems](https://www.sennheiser.com/globalassets/digizuite/40534-en-an_1260_v1.0_media_control_systems_en.pdf))

### SSCv2 (current)

- **Transport:** "An SSCv2 Server MUST NOT allow HTTP (=unencrypted connections)." It requires
  HTTP/1.1 with TLS 1.2. Subscriptions start with a GET on `/api/ssc/state/subscriptions`. The
  response is `text/event-stream` with `open`, `message`, and `close` events. A
  `Content-Location` header names `/api/ssc/state/subscriptions/{sessionUUID}`, and clients
  change that resource with PUT `.../add`, PUT `.../remove`, and DELETE. Clients can read the
  protocol version at `/api/ssc/version`.
  ([SSCv2 Specification 2.3](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sscv2-specification-2.3.html))
- **Definitions:** Sennheiser publishes an OpenAPI file for each device. Spectera firmware
  1.3.0 ships "OpenAPI specification 17.0" for the base station.
  ([SSC overview](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html);
  Spectera note from trade press, April 2026)
- **Families:** Spectera, EW-DX (EM 2, EM 2 Dante, EM 4 Dante) on firmware 4.0.0 or later,
  TeamConnect Ceiling Medium, and TeamConnect Bar.
  ([SSC overview](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html))
- **Auth:** "The 3rd party media control access for EW-DX devices is deactivated by default."
  Turn it on in Control Cockpit, set a third-party password of 10 to 64 characters with mixed
  classes, and then "use the username api and configured password for your API calls."
  ([EW-DX access](https://docs.cloud.sennheiser.com/en-us/control-cockpit/control-cockpit/ew-dx-access.html))
- **Topology:** direct to each device. Control Cockpit is optional and is not a gateway for
  third parties.
- **Licensing:** no terms-of-use statement on the spec pages, only a copyright notice (gap).

### SSCv1 (legacy)

- **Transport:** JSON messages, one per UDP datagram. "The default port number is 45."
  Discovery uses the DNS-SD service type `_ssc`. Subscriptions go through
  `/osc/state/subscribe`.
  ([TI 1109 v2.2, SSC Developer's guide for Digital 6000](https://www.sennheiser.com/globalassets/digizuite/41931-en-ti_1109_v2.2_sennheiser_sound_control_protocol_digital_6000_en.pdf))
- **Families:** Digital 6000 (EM 6000, L 6000 charger), Digital 9000, SpeechLine Digital
  Wireless (rack and multi-channel receivers, CHG 2N and CHG 4N chargers), EW-D on firmware
  older than 4.0.0 (including the CHG 70N), and TeamConnect Ceiling 2. Each product has its own
  developer guide.
  ([SSC overview](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html), AN 1260)
- **Auth:** none. Control Cockpit calls the EW-DX legacy option "use at your own risk (not
  recommended)."
- **Port note:** AN 1260's port table lists `6970/UDP` against Digital 6000, while TI 1109
  sets the SSC default to 45 and expects clients to find the port through `_ssc` discovery.
  Confirm on hardware.

### Media Control Protocol (oldest)

- **Transport:** ASCII over UDP. "Devices of ew G4 series can be set and read via Ethernet at
  port 53212," using the same port for sending and receiving. The client sends a `Push` command
  with a timeout as a keep-alive. The device then sends cyclic attributes (levels and similar)
  and sends configuration attributes on change.
  ([TI 1254, Media Control Protocol ew G4](https://www.sennheiser.com/globalassets/digizuite/41944-en-ti_1254_metromediensteuerung_ewg4_en.pdf))
- **Families:** EM 300-500 G4 and SR IEM G4 on firmware 1.7.0 or later; the EM 100 G4 is not
  supported. Older docs cover the ew G3 and 2000 Series, and AN 1260 also lists ADN.
  ([G3/2000 description](https://www.sennheiser.com/globalassets/digizuite/40900-en-ewg3_2000_mediacontrolprotocoldescription_120122.pdf))
- **Auth:** none.

## Audio-Technica

- **Spec:** "IP Control Protocol Specifications, UHF Wireless Systems / Digital UHF Wireless
  Systems," v1.1.0 (2019-12-19). It covers the ATW-R5220 and R5220DAN (5000 Series), the
  ATW-DR3120 and DR3120DAN (3000 Digital), and the ATW-R3210N (3000 Series, network option).
  ([PDF](https://docs.audio-technica.com/us/wirelesssystem_ip_control_protocol_specifications_110_web_en_191217.pdf))
  A companion Syslog spec also exists.
  ([PDF](https://docs.audio-technica.com/us/wirelesssystem_syslog_spc_v1_1_0_ja_en_web_191220.pdf))
- **Transport:** "Port number TCP:17300 UDP:17000 Static. Not changable." Commands are ASCII,
  space-delimited, and terminated with CR, with a 255-byte maximum command. Message types are
  Set, Get, ACK, NAK, Answer, Information, and Request. Change notifications and level
  notifications go out as UDP multicast to a configurable group (default `225.0.0.100`). The
  host sets the level interval from 100 ms to 60 s, and the default is 100 ms.
- **Topology:** direct to each device. "Simultaneous connection is limited to 1. If this limit
  is exceeded, the connection will fail." This matters a lot: a monitoring poller would lock out
  Wireless Manager or a room control system on the same receiver. A plugin should rely on the
  multicast notifications and hold the TCP session only briefly, or not at all.
- **Auth:** none in the spec.
- **Gaps:** I found no public IP control spec for the 6000 Series (ATW-R6200 family), the newer
  3000 Series (fourth generation) beyond the R3210N, or the 5000 Series third generation. Wireless
  Manager is Audio-Technica's manager application.

## Lectrosonics

- **Spec:** the Wireless Designer WebHelp publishes a third-party control language for each
  product, with an ABNF grammar. The pages exist for the DSQD
  ([protocol](https://www.lectrosonics.com/wdsupport/WebHelp/dsqd/protocol/dsqd_cmd_proto.html)),
  DR, M2T, VRMWB, and VRM2WB (Venue 2)
  ([VRM2WB](https://www.lectrosonics.com/wdsupport/WebHelp/vrm2wb/protocol/vrm2wb_cmd_proto.html)).
- **Transport:** text request and response, used "over the serial and ethernet/TCP
  interfaces." Requests look like `!serial?<CR>`, and responses start with `OK` or `ERROR` and
  end with CRLF. `?` reads a value, `=` updates one, and actions take no data. A verbose mode
  echoes the target and value. The default TCP port is 4080, and the HTTP port is 80.
  ([DSQD network commands](https://www.lectrosonics.com/wdsupport/WebHelp/dsqd/commands/dsqd_netwk_cmds.html))
- **Push:** none. The protocol is strictly request and response, so monitoring means polling.
  DR macros can send verbose responses to a chosen port, which approximates push.
- **Auth:** none documented.
- **Gaps:** the WebHelp has no pages for the M2R IEM or the compact SR and SRc receivers, which
  have no Ethernet. I did not verify the full command list for battery and RF metering on the
  DSQD.

## Wisycom

- **Topology:** Wisycom Manager "is complete software designed to remotely monitor, control
  and reprogram Wisycom remote-controlled devices." It reaches devices over USB, Ethernet, or
  IrDA.
  ([Wisycom Manager help](https://wisycom.com/app/uploads/Wisycom-Manager-Help.pdf))
- **Ethernet-capable models (from the same help file):**
  - Receivers: MRK960, MRK980, and MRK16 (the MRK920 and MRK950 only with the Ethernet option).
  - Transmitters and IEM: MTK952, MTK952-A, MTK982, and MPA221.
  - RF distribution: MFL, MFLC, MAT244, MAT288, SPL2208, SPL2216, BFLR2, BFLT2, and BOX3
    (through the MFLC).
  - Not Ethernet: the MCR54 and MPR camera and belt units use USB or IrDA, with Bluetooth
    through the Wisycom BT app.
- **Third-party protocol:** "Wisycom Manager works as Ember+ provider." Ember+ is available for
  the MAT244, MAT288, MFL, MRK980, MTK952, MTK952A, and MTK982. The default port is 9000 and can
  be changed, and Ember+ must be turned on both in the Manager and on each device. "MRK980
  supports Ember+ as a standalone device too."
- **Ember+:** Lawo's open control protocol (S101 framing, BER-encoded Glow tree over TCP).
  Libraries are BSL-1.0. ([Lawo/ember-plus](https://github.com/Lawo/ember-plus))
- **Other ports:** Master Remote Control, which shares devices across several Manager PCs, uses
  TCP 32789. The device's remote-control flag is lost on reboot unless a show file restores it.
- **Gaps:** Wisycom does not publish its Ember+ parameter tree or the native device protocol.
  Building a plugin needs a capture from a real MRK980 or Manager. Ember+ has no auth.

## Sony

- **What's public:** DWX receivers (such as the DWR-R03D and DWR-R02DN) work with Wireless
  Studio 5.0 or later on PC, Wireless Studio Mobile, and Cross Remote with the RMU-01. The
  DWR-R03D has two Dante ports for audio.
  ([DWR-R03D product page](https://pro.sony/ue_US/products/dwx-digital-series-receivers/dwr-r03d))
- **Protocol:** I found no public third-party control spec. The operating manuals on
  pro.sony returned 403 to automated fetches, so they were not reviewed. This is the largest gap.
  Next steps are the DWR-R03D User's Guide, checked manually, and a request to Sony
  Professional for a control spec.

## Others found

- **AKG / HARMAN:** the DMS800 has "Built-in HARMAN HiQnet network remote control and
  monitoring." The WMS4500, DMS700, and IVM4 join through the HUB4000 Q. HiQnet is proprietary,
  and I found no public third-party spec. AKG's product lines are largely discontinued, so this
  is low priority. (HARMAN and AKG launch material)
- **MIPRO:** ACT receivers reach the network through the MES-100 bridge (ACT-BUS to USB or
  RS-232). I found no public protocol. (Retailer listing; low confidence.)
- **Not investigated:** Line 6, Electro-Voice, Bosch, Zaxcom, Audio Ltd, and RF Venue. Their
  current wireless lines have no known Ethernet monitoring interface, but I did not confirm
  that.

## RF distribution and spectrum gear

- **Wisycom** is the only vendor found whose antenna distribution, combiners, and RF-over-fiber
  are networked: MFL and MFLC (fiber), MAT244 and MAT288, SPL2208 and SPL2216 (splitters),
  BFLR2 and BFLT2, and BOX3. The MFL, MAT244, and MAT288 are also exposed through Ember+.
- **Shure:** the UA845UWB antenna distribution has BNC and DC connectors only, with no network.
  The AD600 and AXT600 spectrum managers have Ethernet and work with Wireless Workbench. I found
  no third-party protocol doc for the spectrum managers. (Medium confidence.)
- **Sennheiser, Audio-Technica, Lectrosonics, Sony:** I found no networked distribution or
  combiner products in their public material. I did not check every accessory, so treat this
  as low confidence.
- **Implication:** a fault in an RF distribution unit is observable on the network only for
  Wisycom gear. Elsewhere it has to be inferred from correlated RF loss across the channels the
  unit feeds.

## Findings for the plugin contract

1. **Two topologies, not one.** Shure System API, Wisycom (Ember+ through Manager), Sony, and
   AKG put a manager or server between the plugin and the devices. Sennheiser, Audio-Technica,
   Lectrosonics, and Shure command strings talk to each device directly. The contract needs an
   "endpoint" that is either an API server or a device, with discovery owned by one or the
   other.
2. **Three update models.**
   - Server push over a long-lived stream: Shure WebSocket and Sennheiser SSE.
   - Device push after a subscribe or keep-alive: Shure `REP`/`SAMPLE`, SSCv1 subscribe,
     Sennheiser G4 `Push`, and A-T UDP multicast.
   - Polling only: Lectrosonics.

   The contract should expose capabilities ("can subscribe", "can poll") rather than assume
   either model.
3. **Transport diversity.** The protocols use HTTPS REST, WebSocket, SSE, raw TCP text, UDP
   unicast, UDP multicast, and Ember+ (BER over TCP). The shared `httpx` base client covers only
   the first group. Socket transports need their own pacing, reconnect, and circuit-breaker
   support.
4. **Auth is mostly absent.** Only Shure System API (API key) and Sennheiser SSCv2 (Basic,
   off by default) authenticate. Every legacy or device-direct protocol accepts unauthenticated
   `SET` commands. Read-only on production hardware therefore has to be enforced in the plugin
   (no write methods), not by the device.
5. **Connection exclusivity.** Audio-Technica allows only one TCP client. Wisycom marks a
   device "busy" for other Manager instances. A monitor must not take a session that the
   operator's own tools need.

## Gaps and next steps

- Sony DWX: no public protocol found. Read the manuals by hand and ask Sony.
- Wisycom: the Ember+ tree is undocumented. Capture it from a spare MRK980 or from Manager.
- Shure System API: get the official device-support matrix for the current version and the
  EULA terms.
- Audio-Technica 6000 Series and fourth-generation 3000: check whether the v1.1.0 spec applies
  or a newer one exists.
- Licensing: none of the public specs reviewed state usage restrictions beyond copyright.
  Shure gates the System API download behind registration. Review each vendor's terms before
  shipping a plugin.
