---
title: "Research: Line 6, Electro-Voice, Bosch, Zaxcom, Audio Ltd, and RF Venue"
---
This note answers [#344](https://github.com/justprosound/django-micboard/issues/344): do
the vendors left out of the
[vendor protocol landscape](https://github.com/justprosound/django-micboard/issues/322)
expose network monitoring for their current wireless, IEM, or RF distribution products?
For each vendor it records whether a network interface exists, the protocol, whether the
protocol is publicly documented, which product families have it, and which open-source
projects already implement it.

Sources are vendor product pages, manuals, and API guides wherever they could be
retrieved. Where only a dealer page or open-source code was available, the claim says so.
Research date: 2026-10-15.

## Summary

| Vendor | Network interface | Protocol | Public spec | Families | Open-source implementations | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| Line 6 | None | n/a. USB is for firmware updates only | n/a | None (Relay G10/G10S current; XD-V discontinued) | None | High |
| Electro-Voice | None on current products | n/a. Legacy REV used CAN bus through IRIS-Net | n/a | None (R300, RE3 current) | None | High (current), low (legacy REV) |
| Bosch (now Keenfinity) | Yes, DICENTIS Wireless access point | HTTP REST with JSON, login plus long-poll (`/api/login`, `/api/seats`, `/api/speakers`, ...) | Partly. Only a vendor knowledge-base article and the device's own `REST_API.html` test page. No published reference | DICENTIS Wireless (DCNM-WAP with DCNM-WD/WDE/WDD devices). Wired DICENTIS uses a WebSocket API instead | Bitfocus Companion `bosch-dicentis` (MIT), Q-SYS plugin (MIT) | Medium |
| Zaxcom | Yes, only on the RX-8D (Dante option) through the Zaxcom GUI Bridge | Proprietary, over the RX-8D's Dante/PoE Ethernet port to a Raspberry Pi based bridge that serves a web UI | No | RX-8D chassis with MRX modules. Others use RS422 and ZaxNet (2.4 GHz), not IP | None | Medium |
| Audio Ltd / Sound Devices | Yes, Astral ARX8/ARX16/ARX32 (formerly A20-Nexus family) | Proprietary browser web app over HTTP. AstralComm to DiGiCo consoles is also proprietary. Dante for audio only | No | Astral ARX receivers. Audio Ltd A10 is discontinued and only had Dante audio on the A10-RACK | None | Medium-high |
| RF Venue | Yes, Spectrum Recorder and 4 ZONE-Network | Spectrum Recorder: documented HTTP REST API (`/api/v1/Sweep/...`). 4 ZONE-Network: web UI only. RF Explorer PRO: USB serial | Yes for Spectrum Recorder (UG-00002) and RF Explorer. No for 4 ZONE-Network | Spectrum Recorder, 4 ZONE-Network, RF Explorer PRO. All DISTRO and COMBINE units are unmanaged | RF Explorer libraries (LGPL-3.0). Vendor's Python example client for the Spectrum Recorder | High (Spectrum Recorder), medium (others) |

**Bottom line:** two of the six vendors have something micboard can monitor today using
public documentation:

- **RF Venue Spectrum Recorder:** a documented, unauthenticated HTTP API for spectrum
  sweeps. It is spectrum data, not device telemetry for receivers.
- **Bosch DICENTIS Wireless:** a REST API that reports per-seat battery and connection
  state. It is only partly documented, but two MIT-licensed integrations show the
  endpoints.

Sound Devices Astral and the RF Venue 4 ZONE-Network are networked but only expose a
vendor web UI. Zaxcom exposes IP control only through its own bridge appliance. Line 6 and
Electro-Voice have no network monitoring on any current product.

## Line 6

- **Current wireless products:** Line 6's wireless page lists only the Relay G10 and G10S
  guitar systems ([line6.com/wireless](https://line6.com/wireless/)). Neither has a
  network or computer-control interface on that page.
- **XD-V series:** the XD-V75 is discontinued ("XD-V75 is no longer made",
  [legacy page](https://line6.com/legacy/xdv75hh)). Its Pilot's Guide labels the rear
  USB port "USB Connector – for firmware updates", and the only other use it describes
  is updating older RF1 transmitters to RF2 from a connected computer
  ([XD-V75 Pilot's Guide, Rev i](https://l6c-acdn2.line6.net/data/6/0a064339457b54fa0539221bf/application/pdf/XD-V75%20Pilot's%20Guide%20(%20Rev%20i%20).pdf)).
  Firmware updates use the Line 6 Monkey application over mini-USB
  ([Line 6 KB](https://kb.line6.com/kb/live/how-to-update-the-relay-g90-and-xd-v70-75-receiver)).
- **Protocol:** none. No Ethernet, no remote monitoring, no control API.
- **Open source:** no Bitfocus Companion module or other project found.
- **Verdict:** not integrable. Inventory only.

## Electro-Voice

Electro-Voice is part of Keenfinity Group, the former Bosch security and communications
business that Triton bought in a deal closed on 2025-07-01
([audioXpress](https://audioxpress.com/news/bosch-group-sells-electro-voice-dynacord-rts-and-telex);
[PE Insights](https://pe-insights.com/triton-completes-e1bn-carve-out-from-bosch-launches-keenfinity-group/)).

- **Current wireless products:** EV's site lists two wireless families, R300 and RE3
  ([products.electrovoice.com](https://products.electrovoice.com/na/en/re3-rx)).
- **RE3-RX connections:** balanced XLR and unbalanced 1/4" outputs, BNC antennas with
  booster power, and DC in. No network port. Frequency scan and sync to the transmitter
  are local features
  ([RE3-RX product page](https://products.electrovoice.com/ap/en/re3-rx);
  [RE3-RX datasheet](https://goknight.com/content/documentation/RE3-RX_RE3_Diversity_Receiver_Datasheet_51_en_67530057995%20(1).pdf)).
- **IRIS-Net:** EV's control platform lists matrices, amplifiers, wall controllers, and
  touch panels as supported hardware. No current wireless receiver is on the list
  ([IRIS-Net](https://products.electrovoice.com/r/iris-net)).
- **Legacy only:** the discontinued EV REV UHF system could be connected to a PC through
  an N8000 controller in IRIS-Net V2.1.1 (2009)
  ([FOH, 2009-08-10](https://fohonline.com/?p=95759)). A dealer source says REV used CAN
  bus through a UCC-1 converter. That claim wasn't checked against a primary source.
- **Open source:** none found.
- **Verdict:** not integrable for current products.

## Bosch (DICENTIS, now Keenfinity)

Bosch has no wireless microphone line. The relevant product is DICENTIS Wireless, a
Wi-Fi conference system whose battery-powered discussion devices (DCNM-WD, DCNM-WDE,
DCNM-WDD) connect to a DCNM-WAP access point. DICENTIS stayed with the business that
became Keenfinity, so current documentation is moving from `boschsecurity.com` to
`keenfinity-group.com`.

### DICENTIS Wireless (DCNM-WAP): REST API

- **Protocol:** HTTP with JSON. A Keenfinity knowledge-base article, "RESTful API
  programing on a DICENTIS Wireless DCNM-WAP", says the WAP accepts GET, PUT, POST, and
  DELETE. It recommends long-polling instead of plain polling, says a keepalive is needed
  every 10-30 seconds, and advises against third-party API clients connecting over Wi-Fi.
  It points developers to a test page on the device, `http://<wap>/REST_API.html`, and
  says to use browser developer tools to discover further commands
  ([Keenfinity knowledge base](https://knowledge.keenfinity-group.com/conference-systems/article/restful-api-programing-on-a-dicentis-wireless-dcnm)).
  At the time of writing that URL returned 404 and the Confluence mirror was locked, so
  this summary relies on the search-engine extract.
- **Endpoints seen in open-source clients:** `POST /api/login` with a JSON body of
  `username`, `password`, and `override`. Then `GET /api/system`, `/api/system/status`,
  `/api/seats`, `/api/speakers`, and `/api/waiting`, plus `POST /api/speakers` and
  `DELETE /api/speakers/{id}` for control
  ([Q-SYS plugin source](https://github.com/JClaerebout/Q-SYS-Plugin-Bosch-Dicentis-Wireless);
  [Companion module `main.js`](https://github.com/bitfocus/companion-module-bosch-dicentis)).
- **Monitoring data:** each element of `/api/seats` carries `id`, `name`,
  `batteryStatus`, `connected`, and `prio` (Q-SYS plugin, `funcParceSeats`). That gives
  battery and link state per wireless device, which maps onto micboard's existing
  battery and online fields. No RF level or signal-quality field shows up in either
  client. The WAP's own web UI has a "Battery & Signal" page, so the API may expose more
  than the clients use. That is unverified.
- **Auth:** username and password, with a session from `/api/login`. The default admin
  user is `admin`.
- **Read-only fit:** the monitoring calls are GETs. The login call's `override` flag
  takes over an existing session, which needs checking against the single-session rules
  in the [live test lane decision (#329)](https://github.com/justprosound/django-micboard/issues/329)
  before any live testing.

### DICENTIS wired: Conference protocol and API

- **Protocol:** JSON over secure WebSocket, introduced in software V3.2
  ([Bosch press release](https://www.boschsecurity.com/au/en/news/press-room/dicentis-touch-panels/)).
  The Companion module connects to `wss://<server>:31416/Dicentis/API`.
- **Documentation:** Bosch ships the API and Conference Protocol reference as CHM help
  files with the DICENTIS software download. These are not on the open web.
- **Relevance:** wired DICENTIS devices have no batteries or RF links. This is meeting
  and microphone control, not wireless monitoring, so it is out of scope for micboard
  beyond noting that it exists.

### Open source

| Project | License | Covers |
| --- | --- | --- |
| [bitfocus/companion-module-bosch-dicentis](https://github.com/bitfocus/companion-module-bosch-dicentis) | MIT | Wired WebSocket API and DCNM-WAP REST (`/api/login`, `/api/seats`, `/api/speakers`) |
| [JClaerebout/Q-SYS-Plugin-Bosch-Dicentis-Wireless](https://github.com/JClaerebout/Q-SYS-Plugin-Bosch-Dicentis-Wireless) | MIT | DCNM-WAP REST, including seat battery and connection status |

Both are MIT-licensed, so either can be incorporated with attribution.

**Verdict:** integrable for battery and connection monitoring of DICENTIS Wireless
devices, as a direct-to-device HTTP polling plugin. The tier would be *unverified* until
tested on hardware, because the API reference isn't published.

## Zaxcom

- **Product families:** stand-alone receivers (QRX200, QRX235, RX200, URX100, DCiRX),
  MRX module receivers (MRX214, MRX414) in the RX-4, RX-8, RX-12, and RX-12R chassis,
  plus recorders such as Nova 2 with built-in receiver slots
  ([RX-12R](https://zaxcom.com/product/rx-12r/); [Nova 2](https://zaxcom.com/product/nova-2/)).
- **ZaxNet:** a 2.4 GHz RF network that carries timecode, IFB audio, and remote control of
  transmitters (frequency, gain, power, transport). It is not IP
  ([What is ZaxNet](https://zaxcom.com/learn/zaxnet/)).
- **Most receivers have no network port.** The RX-12R lists USB and RS422 for digital I/O
  and no Ethernet ([RX-12R](https://zaxcom.com/product/rx-12r/)). Nova 2 lists no
  Ethernet ([Nova 2](https://zaxcom.com/product/nova-2/)).
- **RX-8D (Dante option):** an RJ45 Dante port with 30 W PoE. Zaxcom says the option
  "facilitates remote location and control"
  ([RX-8](https://zaxcom.com/product/rx-8/);
  [RX-8 announcement](https://zaxcom.com/zaxcom-introduces-the-new-rx-8-an-mrx-receiver-module-interface-with-dante-and-poe/)).
- **Zaxcom GUI Bridge (ZGB):** a Raspberry Pi based appliance with RJ45, Wi-Fi hotspot,
  USB, HDMI, and RS422. It serves a browser UI at `http://zaxcom.local`. It
  "automatically connect[s] to any networked RX-8D via its ethernet port". Its RX-8 screen
  shows receiver frequency, modulation, RF strength and antenna phase, transmitter ID and
  name, transmitter battery, audio meters, and transport status. It also drives
  transmitters over RS422 and programs URX and VRX units over USB
  ([ZGB manual, 2024-01-09](https://zaxcom.com/wp-content/uploads/2022/01/GUI-Bridge_Jan_9_2024.pdf);
  [ZGB product page](https://zaxcom.com/product/zgb/)).
- **Protocol:** the RX-8D to ZGB link and the ZGB web UI's backend are undocumented and
  proprietary. The RS422 command set isn't published either.
- **Open source:** none found.
- **Verdict:** the telemetry micboard wants exists on RX-8D systems, but only behind a
  proprietary protocol. Integration would need reverse-engineering the ZGB web backend
  or the RX-8D network protocol. Not integrable from public sources.

## Audio Ltd / Sound Devices

Audio Limited (UK) was bought by Sound Devices in 2018
([audioXpress](https://audioxpress.com/news/sound-devices-expands-astral-wireless-products-for-live-sound-markets)).
Its A10 system is discontinued
([Sound Devices discontinued Audio Ltd](https://www.sounddevices.com/?p=131950);
[Trew Audio A10-RX](https://www.trewaudio.com/product/audio-ltd-a10-rx/)). Its
successor, the A20 line, was renamed **Astral** in September 2025: A20-Nexus Go became
ARX8, A20-Nexus became ARX16, and A20-SuperNexus became ARX32, with no hardware changes
([Pinknoise Systems](https://pinknoise-systems.eu/es/blogs/all-blogs/sound-devices-name-changes);
[Mixdown](https://mixdownmag.com.au/news/major-updates-for-sound-devices-8-series-and-astral-wireless/)).

### A10 (discontinued)

- **A10-RACK:** two RJ45 ports for Dante audio (up to eight channels) and USB for
  firmware and serial access. Routing is done in Audinate's Dante Controller. No control
  or monitoring protocol for the A10-RX receivers is documented
  ([Sound Devices store](https://store.sounddevices.com/product/a10-rack/)).
- A10-TX transmitters are controlled over Bluetooth from a phone app. That is not a
  network interface.

### Astral ARX8 / ARX16 / ARX32

All facts in this section are from the Astral ARX16 User Guide v8.30
([guides.sounddevices.com/astral-arx16](https://guides.sounddevices.com/astral-arx16/)).

- **Interfaces:** two RJ45 ports and one SFP port, each assignable to Dante, Control, or
  both. Port 1 takes PoE+. DHCP or static IP for each network.
- **Control:** "The Astral ARX16 supports both Dante and IP control." IP control gives
  the browser web app, RF Mirror Mode (a backup unit mirrors a primary over IP), and
  Astral Outpost NexLink antennas.
- **Web app data:** a home view of all channels, RSSI A/B meters and RF history per
  channel, a TX list with transmitter battery level and NexLink status, RTSA spectrum
  with CSV export, audio metering, and system info (model, firmware, serial).
- **Limits:** "Only one web client is supported." An optional web password is available.
- **AstralComm:** "a proprietary protocol specifically designed to send and receive
  macro commands between Sound Devices Astral devices and one or more DiGiCo consoles
  over a network". It is for DiGiCo SD and Quantum consoles only.
- **Protocol:** the web app's backend API isn't documented. No public API, SDK, or
  third-party control documentation was found.
- **Open source:** none. The only Sound Devices Companion module,
  `companion-module-sounddevices-pixnet`, is for PIX video recorders, not wireless.

**Verdict:** the hardware exposes every metric micboard wants over IP, but only through
an undocumented web app that allows one client at a time. That one-client limit would
conflict with a user who has the web app open. Not integrable from public sources. Worth
asking Sound Devices whether the web app API is stable enough to publish.

## RF Venue

RF Venue makes antennas, distribution, and combiners. Audio-Technica distributes it in
North America, Canada, and EMEA, and sells an Audio-Technica branded Spectrum Recorder
([RF Venue blog](https://www.rfvenue.com/blog/audio-technica-europe-adds-rf-venue-essentials);
[SCMS listing](https://www.scmsinc.com/audio-technica-spectrum-recorder-network-and-usb-spectrum-data-recorder.html)).

### Unmanaged products

DISTRO4, DISTRO5 HDR, DISTRO9 HDR, 4 ZONE (non-network), COMBINE4, COMBINE6 HDR,
COMBINE8, Optix Series 3, antennas, and filters have no data interface on their product
pages or spec sheets ([all products](https://www.rfvenue.com/all-products);
[DISTRO9 HDR](https://www.rfvenue.com/all-products/distro9hdr)). An earlier DISTRO9 HDR
bundle with a "REMOTE" spectrum-analyzer LAN card and WaveTower software is no longer
sold ([Adlib](https://www.adlib.co.uk/product/rf-venue-distro9-hdr-antenna-distribution-system-with-remote-network-card)).
These fit micboard's RF Distribution Unit model as unmanaged units (inventory and
topology only), like the passive Wisycom models.

### Spectrum Recorder: documented REST API

- **Hardware:** RJ45 with PoE "for GUI access and/or network-based scan retrieval",
  USB-A for a thumb drive, and USB-C power. The browser GUI is at
  `rfvenuespecrec.local` (mDNS). The device can also be mounted as a network drive to
  read its CSV files
  ([SR User Guide UG-00001 rev B](https://www.rfvenue.com/hubfs/Spectrum%20Recorder%20Firmware%20and%20Assets-%202025%20update/UG-00001%20rev%20B%2c%20SR%20User%20Guide.pdf)).
- **API (firmware 3.2 or later):** all of the following is from the
  [SR API User Guide UG-00002 rev A](https://www.rfvenue.com/hubfs/Spectrum%20Recorder%20Firmware%20and%20Assets-%202025%20update/UG-00002%20rev%20A%2c%20SR%20API%20User%20Guide.pdf)
  ([product page](https://www.rfvenue.com/all-products/spectrum-recorder)).
  - `GET /api/v1/Sweep/GetSweep`: the latest realtime sweep, about every 20 s. Only
    available through the API.
  - `GET /api/v1/Sweep/GetSweep24Avg`, `GetSweep24Max`, `GetSweep24Active`: 24-hour
    average, max hold, and activity.
  - `GET /api/v1/Sweep/GetConfig`: an empty body. Headers carry RBW, start and stop
    frequency, input stage, serial, model, firmware, date, time zone, location, and file
    count.
  - `POST /api/v1/Sweep/UpdateFrequency/{start MHz}/{stop MHz}/{step kHz}`: a write.
    micboard's read-only guard must block it.
  - **Encoding:** the body is a base64 string of a GZip-compressed byte array, checked
    against the `X-CRC32` header. Each byte becomes dBm = byte / -2.0 (activity:
    dB = byte / 2.0), giving 0.5 dB resolution and up to 50,000 points.
  - **Transport:** plain HTTP on port 80. The guide mentions no authentication.
- **Open source:** the guide references a vendor Python example,
  `spectrum_recorder_api_client.py`, that implements every call. It isn't on a public
  repository with a stated license, so treat it as a reference only.
- **Verdict:** integrable. It is a direct-to-device, poll-only HTTP source of spectrum
  data, not receiver or transmitter telemetry. It fits a spectrum or RF-environment
  capability rather than the receiver plugin contract.

### 4 ZONE-Network: web UI only

- An antenna combiner with four diversity zones, an RJ45 LAN port, and USB-A. The
  browser UI at `rfv4zone.local` gives per-zone enable/disable, attenuation, DC bias, 16
  presets, and settings (IP, MAC, firmware, hostname)
  ([4ZONE-Network manual DFU-00005 rev B](https://www.rfvenue.com/hubfs/4Zone%20Network%202025/4%20Zone-Network%20Manual/DFU-00005%20rev%20B%2c%204ZONE-Network%20Manual%20(2).pdf);
  [product page](https://www.rfvenue.com/all-products/4-zone)).
- **Protocol:** no API is documented. The web UI's backend is undocumented.
- **Verdict:** an RF Distribution Unit (combiner direction) that is networked but has no
  public protocol. Record it as managed-capable, but monitor it only if RF Venue
  publishes an API.

### RF Explorer PRO (USB)

- RF Venue sells the RF Explorer PRO handheld analyzer, which connects over USB-C
  ([product page](https://www.rfvenue.com/all-products/rf-explorer-pro)). The RF Explorer
  serial protocol is published by its maker, and libraries exist for Python, .NET, and
  Raspberry Pi as a USB-to-network bridge
  ([RFExplorer-for-Python](https://github.com/RFExplorer/RFExplorer-for-Python),
  LGPL-3.0, which is compatible with AGPL-3.0-or-later).
- **Verdict:** possible as a spectrum source through a host-attached bridge, but outside
  micboard's network-device model. Low priority.

## Gaps

- **DICENTIS Wireless API reference:** the Keenfinity knowledge-base article was
  unreachable when checked. The full endpoint list (for example, whether RF or signal
  data is exposed) is known only from two open-source clients and the article's search
  extract. The CHM help files from the DICENTIS software download might include it.
- **Sound Devices Astral web app API:** undocumented. Whether it is a stable REST or
  WebSocket API, and whether the one-client limit applies to API clients too, can only be
  found by inspecting a unit or asking Sound Devices.
- **Zaxcom RX-8D and ZGB protocol:** undocumented. Zaxcom hasn't said whether the RX-8D
  network control is anything other than a private link to the ZGB.
- **RF Venue 4 ZONE-Network:** no API documentation. Its web UI backend would need
  inspection.
- **Electro-Voice REV (legacy):** the CAN bus and UCC-1 detail comes from a dealer
  summary, not a primary source. This doesn't matter much, because REV is long
  discontinued.
- **Line 6 Relay G10S:** no manual was checked. The product page and the absence of any
  network port on the G10/G10S were the basis for the verdict.
