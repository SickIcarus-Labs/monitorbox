# Port errors: the rules

What the Port errors item watches, how it decides, and what it never does. The code is `app/monitorbox_app/portwatch.py`; the tests are `tests/test_portwatch.py`. Everything here is read-only: counters and link state are read from UniFi and SNMP, nothing is changed on any device.

## What it reads

- **UniFi switches, gateways and other devices:** each port's error and drop counters, link-down count and up/down state, every 10 seconds.
- **SNMP:** for a switch that is also an SNMP connection, errors and drops come from the interface itself (exact, and works for non-UniFi switches). A device never mixes the two sources. An SNMP connection counts as a UniFi device when its address is the device's address, or else when one of its interfaces has the (shortened) hardware address of exactly one UniFi device, or else when its name, or the name the device reports over SNMP (sysName), is the name of exactly one UniFi device (spaces, punctuation and capitals ignored: "Switch 2" is "Switch2"); otherwise it is read as a server. **Bonds, teams, port-channels and VLAN sub-interfaces** (bond0, Po1, eth0.100) are not read as ports: they repeat the cards under them. The device's own stack table says which interfaces sit on top of which (names are only a fallback), and a card that is a member of a bond says so in the alert ("eth1 (in bond0)"). A server card counts as a port in use while its link is up; a card with no link is read quietly. **Link drops** on a server card are counted by the box: the module reads when each link last changed (and the device's uptime), and a drop is counted when the link went down, or went down and up again between two readings. A device restart resets those times and is not counted. **No UniFi needed:** an SNMP connection that is not a UniFi device is read directly, with or without a UniFi connection. If it learns addresses or hears LLDP neighbours it is a switch: its ports with a neighbour, or several addresses behind them, are links (errors, packet drops and link drops count), and its other ports are treated as clients' (only errors count). That is read with the module's switch report once at first and then every 10 minutes. A device that is not a switch is a server and every card counts. Port speeds come from the device itself, so the minimums scale with the link. **SNMP servers** (a connection that is not a UniFi device) are read every 30 seconds: each network card's errors, drops and link state.
- A server's card is matched to the switch port it is plugged into by hardware address, so each end of the cable can show what the other end sees.

## When it is on

- On by default on any box with a UniFi or SNMP login. It starts quietly while it learns.
- **Disable** on the Port errors page switches it off for good (a restart or a new login does not switch it back on). **Enable** switches it on again.
- Off means no readings are kept and the saved history is deleted.

## What counts as a problem: counters

- The lifetime total is never judged, only the change. A port is **rising** when, in the last 15 minutes, it gained at least a minimum **and** at least five times its own worst earlier 15-minute window.
- The minimums for **errors and drops scale with the link speed**, because a faster port carries more frames and the same count is a smaller share. On a 1 Gbit link: errors 20, drops 10,000. At 10 Gbit: errors 200, drops 100,000. Slower links use the lowest minimums (errors 20, drops 1,000). A port whose speed is unknown counts as 1 Gbit. Link drops need 3 on any port.
- A port needs about half an hour of readings before it is judged ("learning what is normal"). Readings are kept for 24 hours and survive a restart (saved every 5 minutes, thinned to 5-minute points, readable only by the app).
- A counter that goes backwards means the device restarted: that port's history starts again.
- Errors are watched on every port in use. **Packet drops and link drops** only count on uplinks, links between devices and server ports, never on an ordinary client's port (a laptop that sleeps, or an Apple TV in standby, is not news).
- The line says how many an hour, the receive/transmit split, how busy the port is, and the other end of the cable when there is one ("other end (label): N receive, M transmit an hour", "still learning" or "no counters"). One-sided counts are normal: the receiving side counts a bad frame.

## Packet drops are usually congestion, not a fault

A **packet drop** (not to be confused with a **link drop**, where the link itself goes down and comes back) on a port means the switch's outgoing queue for that port overflowed. That happens where a faster network feeds a slower port (a 10 Gbit server or uplink sending a burst to a 1 Gbit device): the switch drops what does not fit and the traffic slows down and recovers. It is normal on a LAN with mixed speeds, and more likely with flow control off. Errors are the better sign of a bad cable or module.

That is why packet drops only alert on uplinks, links between switches and servers, never on client ports. If a server or uplink alerts on drops and the cause is a speed step-down, you can: untick the port, or ask for a drops-only option, or enable flow control if there are no latency-sensitive applications such as gaming or VoIP (flow control turns drops into pauses, which hurts those).

**Wi-Fi servers:** link drops are far more common on Wi-Fi than on Ethernet (roaming, power saving). They are counted under the same rules as a wired card, so a Wi-Fi server that flaps more than its own usual still gets a heads-up. Hard-wire the server, or untick that link, if it is too chatty.

## What counts as a problem: links going away

- A link on an uplink, between devices, or a server card that has been **up for an hour without a break** becomes expected up (learned, no setup).
- If an expected link is down for 60 seconds, the item shows a heads-up: "link is down (was up, down for N min)". Both ends of one cable are one line.
- A link that has never been up is never expected, so the unplugged cards of a four-card server stay quiet.
- **Not coming back** (button on the Port errors page) forgets the expectation. When the link lights again it starts over and is expected again after another hour up.

**A device that sleeps keeps its history.** A Mac or laptop that sleeps takes its link down and the map stops showing the port. A port the map showed in the last 24 hours keeps what it has learned, so waking it does not start another half hour of learning. Interfaces the map never showed (leftover readings) are forgotten after 30 minutes without a new reading.

**The gateway's internet port** (the one that goes to the modem) is listed as "Internet (WAN)", counted, and watched like any uplink, with the speed UniFi reports for it.

## What it does with a problem

- The Port errors item turns **Degraded** (yellow), never Failed. Alerts use the normal Degraded rules and hold-down times.
- Each port has an **Alert on this port** tick (on by default, on the Port errors page and on the network map). Unticked ports are still read and shown, they just never raise the heads-up. Unticking one end of a link silences the other end too. The tick says whether a port may alert at all, not which problems count: on an ordinary client port (an Apple TV, a laptop) only **errors** are a problem, because dropped packets there are normal (a device in standby or asleep). On uplinks, links between switches and servers, errors, drops and link drops all count. Every port is still watched and its numbers shown either way.
- A provider that cannot be read means **Unknown**, never Failed. Observed state is never rewritten; the tick only affects alerts.

## What it counts

The page and the check count the ports in use, the ports the network map shows. Empty ports are read quietly so a port plugged in later already has history.

## Known limits

- SNMP-only boxes (no UniFi) do not yet get the map or port watch on their own, and a port reported by both UniFi and SNMP can still be counted twice (campaign ticket #292).
- UniFi's own UI does not show raw error counters; this item reads the counters it exposes.
