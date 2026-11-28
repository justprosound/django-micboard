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

**RF Channel**:
One frequency slot on a wireless chassis. Frequency coordination happens here, and a wireless
unit takes its regulatory status from the channel it is assigned to.
_Avoid_: Slot (reserved for charger slots), channel (without "RF" when a chassis is meant)

**Charger**:
A multi-bay charging station. Each charger slot can hold a unit and optionally be assigned to a
performer.

**Display Wall**:
A physical display or kiosk showing live performer, RF and battery status for a location.

### Vendor support

**Manufacturer**:
A supported hardware vendor. Shure and Sennheiser ship integrations, each a plugin under
`micboard/integrations/<code>/`.
_Avoid_: Vendor (in model and code names), brand

**Manufacturer API Server**:
A persisted connection to a vendor-side service that serves device state on behalf of the
devices, such as the Shure System API. Hostnames it may contact are limited by
`MICBOARD_API_SERVER_ALLOWED_HOSTS`.
_Avoid_: Gateway, controller

### Discovery

**Discovered Device**:
A device found by network or API discovery that is not yet part of inventory.

**Discovery Queue**:
Staging rows for discovered devices that need an operator's decision before import. See
[Device discovery workflow](docs/integration/discovery-workflow.md).

### Tenancy and monitoring

**Organization**:
The tenant that owns equipment in MSP mode. An organization has campuses and members with a role
(`viewer`, `operator`, `admin` or `owner`).
_Avoid_: Client, account

**Campus**:
A physical site of an organization, with its own buildings.
_Avoid_: Site (reserved for Django's sites framework), venue

**External Room ID**:
The key a host project uses for the same physical room in its own room inventory, stored on a
micboard Room so wireless state can be joined to the host's room data. Micboard treats it as an
opaque string and never resolves it.
_Avoid_: Room link, room FK (it is a plain key, not a database relation)

**Monitoring Group**:
A named set of users with locations and channels they monitor together. Monitoring groups narrow
what viewers and operators see; they never widen a tenant.
_Avoid_: Team

### Performers

**Performer**:
A person who wears or uses wireless equipment. Performers are domain records, never login
identities.
_Avoid_: Talent, user

**Assignment**:
The link between a performer, a wireless unit and a monitoring group, with a priority and
per-condition alert preferences. Deactivating it keeps the row and its history.
_Avoid_: Mapping, allocation
