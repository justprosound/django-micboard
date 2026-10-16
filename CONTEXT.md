# django-micboard

Monitors wireless microphone, in-ear monitor, and RF infrastructure hardware across vendors, and
shows operators the live state of every channel they are responsible for.

## Language

### Hardware

**Wireless Chassis**:
A rack-mounted base station with an RF role of receiver, transmitter, or transceiver, hosting
RF channels that field units connect to.
_Avoid_: Receiver (when the role is unknown), base, device

**Wireless Unit**:
A field device carried by a performer (bodypack, handheld, or IEM pack) that connects to an RF
channel on a wireless chassis.
_Avoid_: Transmitter (ambiguous with the chassis role), mic, beltpack

**RF Distribution Unit**:
Rack infrastructure that moves RF between antennas and wireless chassis without being an RF
endpoint itself; its direction is either combiner or splitter.
_Avoid_: Antenna distribution (implies splitting only), antenna splitter, combiner (as the
general term)

**Combiner**:
An RF Distribution Unit that merges several transmitter outputs onto one antenna.
_Avoid_: Antenna combiner, multicoupler

**Splitter**:
An RF Distribution Unit that feeds one antenna's signal to several receivers.
_Avoid_: Antenna distribution, active antenna splitter

**Distribution Port**:
One input or output on an RF Distribution Unit, optionally linked to the wireless chassis it
feeds or is fed by.
_Avoid_: Channel (reserved for RF channels on a chassis)

**Managed** (RF Distribution Unit):
An RF Distribution Unit that exposes a network interface micboard can read; an unmanaged unit
is tracked for inventory and topology only.
_Avoid_: Active (an active splitter can still be unmanaged)

### Vendor support

**Device Manager**:
Vendor software or hardware that sits between micboard and a vendor's devices and serves their
state on their behalf, such as Shure System API or Wisycom Manager.
_Avoid_: API server, gateway, controller

**Inventory-only**:
A manufacturer with no integration, whose devices are recorded by hand and never polled; they
appear in inventory and RF topology but are shown as not monitored.
_Avoid_: Unsupported, manual vendor, passive vendor

**Verified Vendor**:
A vendor whose integration is tested against captured fixtures recorded from real hardware.
_Avoid_: Supported, certified

**Unverified Vendor**:
A vendor whose integration is built from published documentation and hand-written fixtures,
with no capture from real hardware yet.
_Avoid_: Experimental, beta

**Captured Fixture**:
A scrubbed recording of real device traffic for one scenario, committed as test data.
_Avoid_: Cassette, snapshot, recording (for the committed file)

**Hand-written Fixture**:
Test data written from vendor documentation rather than recorded from a device.
_Avoid_: Mock, fake (as the general term)

### Deployment and tenancy

**Cell**:
One micboard deployment pinned to a jurisdiction, with its own database and storage.
_Avoid_: Region (reserved for the tenancy level), instance

**Portal**:
A Django Site: a hostname with its own branding through which users reach micboard.
_Avoid_: Site (ambiguous), tenant

**Provider Organization**:
An organization that manages other organizations as an MSP.
_Avoid_: Reseller, parent tenant

**Customer Organization**:
An organization whose equipment is monitored, optionally under a provider.
_Avoid_: Client, sub-tenant

**Region**:
An optional, nestable grouping of campuses within a customer organization.
_Avoid_: Zone, area

**Campus**:
A physical site with its own buildings and networks; Edge Listeners attach to a campus.
_Avoid_: Site, venue (as the general term)

**Edge Listener**:
A micboard process deployed on a campus that observes isolated RF and media segments and sends
normalized state to central over one outbound link.
_Avoid_: Agent, satellite, probe, collector (as the general term)

**Segment Collector**:
The part of an Edge Listener that observes exactly one isolated network segment from its own
network namespace.
_Avoid_: Sniffer, bridge

### Events and performers

**Performer**:
A person who wears or uses wireless equipment during an event.
_Avoid_: Talent, user

**Event**:
A scheduled occasion at a location, with a time window and a crew, during which assignments
apply.
_Avoid_: Show, gig, booking

**Assignment**:
The link between a performer and a wireless unit for a half-open time window.
_Avoid_: Mapping, allocation

**Handoff**:
Moving a wireless unit from one performer to another by closing one assignment window and opening
the next.
_Avoid_: Swap (reserved for replacing a pack), reassignment

**Meter Freshness**:
How recently a channel produced a meter sample, tracked separately from connection liveness.
_Avoid_: Online, connected

### Media networks

**Media Endpoint**:
A device on a Dante, AES67, or ST 2110 network that sends or receives media flows.
_Avoid_: Node (ambiguous with NMOS nodes), device (as the general term)

**Media Flow**:
One announced stream of audio or video from a sender, identified by its SDP or NMOS
description.
_Avoid_: Stream (as the general term), channel

**Flow Leg**:
One receiver's subscription to a media flow.
_Avoid_: Route, patch

**PTP Domain**:
A set of devices sharing one Precision Time Protocol clock hierarchy.
_Avoid_: Clock group, sync domain

**Grandmaster**:
The clock a PTP domain currently follows as its time reference.
_Avoid_: Master clock, leader

**Dante Domain**:
A Dante network area defined by Dante's own management, as distinct from a PTP domain.
_Avoid_: Dante network (as the general term)

**Flow Probe**:
An opt-in observer that joins an audio flow to measure packet loss, never a video flow.
_Avoid_: Sniffer, tap

**Probe Clock**:
An opt-in PTP follower run by micboard to measure clock offset.
_Avoid_: Slave clock, reference clock

**Expected Flow**:
A media flow an operator declares must be present, whose absence raises an alert.
_Avoid_: Required stream
