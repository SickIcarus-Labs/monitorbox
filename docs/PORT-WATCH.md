# Port errors: the rules

What the Port errors item watches, how it decides, and what it never does. The code is `app/monitorbox_app/portwatch.py`; the tests are `tests/test_portwatch.py`. Everything here is read-only: counters and link state are read from UniFi and SNMP, nothing is changed on any device.

## What it reads

- **UniFi switches, gateways and other devices:** each port's error and drop counters, link-down count and up/down state, every 10 seconds.
- **SNMP:** for a switch that is also an SNMP connection, errors and drops come from the interface itself (exact, and works for non-UniFi switches). A device never mixes the two sources. **SNMP servers** (a connection that is not a UniFi device) are read every 30 seconds: each network card's errors, drops and link state.
- A server's card is matched to the switch port it is plugged into by hardware address, so each end of the cable can show what the other end sees.

## When it is on

- On by default on any box with a UniFi or SNMP login. It starts quietly while it learns.
- **Disable** on the Port errors page switches it off for good (a restart or a new login does not switch it back on). **Enable** switches it on again.
- Off means no readings are kept and the saved history is deleted.

## What counts as a problem: counters

- The lifetime total is never judged, only the change. A port is **rising** when, in the last 15 minutes, it gained at least a minimum (errors 20, drops 1,000, link drops 3) **and** at least five times its own worst earlier 15-minute window.
- A port needs about half an hour of readings before it is judged ("learning what is normal"). Readings are kept for 24 hours and survive a restart (saved every 5 minutes, thinned to 5-minute points, readable only by the app).
- A counter that goes backwards means the device restarted: that port's history starts again.
- Errors and drops are watched on every port in use. **Link drops** only count on uplinks, links between devices and server ports, never on an ordinary client's port (a laptop that sleeps is not news).
- The line says how many an hour, the receive/transmit split, how busy the port is, and the other end of the cable when there is one ("other end (label): N receive, M transmit an hour", "still learning" or "no counters"). One-sided counts are normal: the receiving side counts a bad frame.

## What counts as a problem: links going away

- A link on an uplink, between devices, or a server card that has been **up for an hour without a break** becomes expected up (learned, no setup).
- If an expected link is down for 60 seconds, the item shows a heads-up: "link is down (was up, down for N min)". Both ends of one cable are one line.
- A link that has never been up is never expected, so the unplugged cards of a four-card server stay quiet.
- **Not coming back** (button on the Port errors page) forgets the expectation. When the link lights again it starts over and is expected again after another hour up.

## What it does with a problem

- The Port errors item turns **Degraded** (yellow), never Failed. Alerts use the normal Degraded rules and hold-down times.
- Each port has an **Alert on this port** tick (on by default, on the Port errors page and on the network map). Unticked ports are still read and shown, they just never raise the heads-up. Unticking one end of a link silences the other end too.
- A provider that cannot be read means **Unknown**, never Failed. Observed state is never rewritten; the tick only affects alerts.

## What it counts

The page and the check count the ports in use, the ports the network map shows. Empty ports are read quietly so a port plugged in later already has history.

## Known limits

- SNMP-only boxes (no UniFi) do not yet get the map or port watch on their own, and a port reported by both UniFi and SNMP can still be counted twice (campaign ticket #292).
- UniFi's own UI does not show raw error counters; this item reads the counters it exposes.
