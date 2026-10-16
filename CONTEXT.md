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
