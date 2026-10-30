# SNMP module

What the SNMP module does, what it talks to, and what it never does. The code is `modules/snmp/`; the tests are `tests/test_snmp_*.py` and `tests/test_snmplib.py`. This page covers only what the module adds. For the App itself (states, alerts, hold-down, settings) see [the core app page](../APP.md).

Everything here is read-only. The module only asks questions; it sends no SNMP "set" and changes nothing on any device.

## What it brings

SNMP is the standard way for servers, NAS boxes and network gear to report on themselves. The module lets MonitorBox read:

- whether a device answers, and its uptime;
- CPU and memory (devices that run net-snmp);
- disk and volume fullness;
- network interface state and speed;
- storage health on QNAP NAS boxes (pools, RAID groups, disks, shared folders);
- raw traffic counters, error counters and link state for every real network port;
- for switches, which addresses were learned behind each port and which neighbour each port hears over LLDP.

It watches things **by name** ("volume /volume1", "interface eno3"), not by number. Each time it checks, it reads the name at the remembered position, and if the name is no longer there it searches the table again. A drive or port that moves to a new position is still the same one.

## What it talks to and how

One UDP conversation per device, to the device's SNMP port (161 unless you set another). Nothing else is contacted.

- **Versions:** SNMP v2c (a community word) and v3 (a user name). The module also accepts v1 if a saved connection says so, but there is no v1 choice on screen. Only IPv4 addresses are used.
- **v3 login:** authentication none, MD5, SHA (SHA-1), SHA-224, SHA-256, SHA-384 or SHA-512; privacy none, AES-128 or DES. Privacy needs authentication. The module has its own small SNMP client written in plain Python, so nothing extra is installed in the container.
- **What is sent:** GET, GETNEXT and GETBULK requests only. A v3 conversation first sends the standard "who are you" message (no user, no password) to learn the device's engine id, then sends the real requests.
- **Timing:** each request waits 2 seconds for an answer and is tried once more (so up to about 4 seconds). A request that the device says is outside its time window is repeated up to 3 times. A table is read 40 rows at a time (up to 4000 rows).

Objects read (all standard, numeric, no MIB files needed):

| What | Object |
| --- | --- |
| Uptime, name, description | sysUpTime `1.3.6.1.2.1.1.3.0`, sysName `.1.5.0`, sysDescr `.1.1.0` |
| Interface name, description, alias | ifName `1.3.6.1.2.1.31.1.1.1.1`, ifDescr `1.3.6.1.2.1.2.2.1.2`, ifAlias `1.3.6.1.2.1.31.1.1.1.18` |
| State, speed, type, address, last change | ifOperStatus `...2.2.1.8`, ifHighSpeed `...31.1.1.1.15`, ifType `...2.2.1.3`, ifPhysAddress `...2.2.1.6`, ifLastChange `...2.2.1.9` |
| Traffic (64-bit, else 32-bit) | ifHCInOctets `...31.1.1.1.6`, ifHCOutOctets `...31.1.1.1.10`, ifInOctets `...2.2.1.10`, ifOutOctets `...2.2.1.16` |
| Errors and discards | `...2.2.1.14`, `...2.2.1.20`, `...2.2.1.13`, `...2.2.1.19` |
| Packets (for the Port errors drop share), 64-bit: received unicast, multicast, broadcast; sent unicast, multicast, broadcast | `...31.1.1.1.7`, `.8`, `.9`; `.11`, `.12`, `.13` |
| Which interface sits on which (bonds, VLANs) | ifStackStatus `1.3.6.1.2.1.31.1.2.1.3` |
| Volumes | hrStorage `1.3.6.1.2.1.25.2.3.1` (type, description, units, size, used); only "fixed disk" entries are offered |
| CPU and memory | net-snmp UCD `1.3.6.1.4.1.2021.11.11.0` (CPU idle), `...4.5.0`, `...4.6.0`, `...4.14.0`, `...4.15.0` (memory) |
| QNAP storage | QNAP MIB `1.3.6.1.4.1.55062.2.10` (pools `.7`, RAID groups `.5`, disks `.2`, shared folders `.9`) |
| Learned addresses | dot1dBasePortIfIndex `1.3.6.1.2.1.17.1.4.1.2`, dot1qTpFdbPort `1.3.6.1.2.1.17.7.1.2.2.1.2` (else dot1dTpFdbPort `1.3.6.1.2.1.17.4.3.1.2`) |
| LLDP neighbours | lldpRemTable `1.0.8802.1.1.2.1.4.1.1` (chassis id, port id, system name) |

Hardware addresses read from a device are passed on shortened (`..:dd:ee:ff`) and never in full.

## What you need to provide

- **SNMP turned on** at each device, ahead of time, and reachable on UDP port 161 from the box. How depends on the device: a setting in the admin page of a NAS or switch, or `snmpd` on Linux. See [the SNMP setup guide](../GUIDES.md).
- **v3 where you can:** a user name, an authentication type and password, and a privacy type and password. Make the user read-only on the device. For v2c, the community word (use a read-only one).
- **Other things the device must offer** for particular features: net-snmp's UCD tables for CPU and memory, the host-resources table for volumes, LLDP and the bridge address table for the switch features. Where a device lacks one, that feature says so; nothing else is affected.

Example values for a test connection: address `192.0.2.10`, v2c community `example-community-1`, v3 user `example-reader`. Passwords are saved on the box and are never shown again.

## Adds to the app

- **Check types:** Reachable (uptime), CPU and memory, Volume, Network interface, and named table rows (QNAP pools, RAID groups, disks, shared folders). Without the module the App's own checks are only ping, TCP, web and DNS, so a disk filling up or a server's network card going down is not seen, and servers and non-UniFi switches have no port watch, map or traffic graphs.
- **Discovery:** the list of what a device offers right now, with one tick per item (Settings > Servers > a server > Pick what to watch). Also the Test connection button on the connection form.
- **Set up scan:** the App itself (not the module) sends one v3 "who are you" message to port 161 of a machine you named, to list "SNMP (health, disks, network ports)" as something to add. A device that only speaks v2c shows as "not seen" but can still be added.
- **Suggestions:** when a UniFi switch is known and one saved SNMP login (the one on the UniFi gateway, or the only one) also answers on it, the App proposes "N switches answer your SNMP login" and, on Add, copies that login to a connection for each. The module's `probe` makes that test; it is retried every 30 minutes.
- **Port errors:** error, discard and link-state counters per port. A switch that is also an SNMP connection is read over SNMP instead of UniFi (every 10 seconds); an SNMP device that is not a UniFi device is read as a switch or a server (a server's cards every 30 seconds). Rules are on [the Port errors page](../PORT-WATCH.md).
- **Network map:** SNMP switches that UniFi does not list become map nodes, with ports, speeds, learned addresses and LLDP neighbours; a server's card is matched to the switch port it is plugged into by hardware address. The map reads these without a traffic sample.
- **Switch report** (Settings > Advanced > Switch report > Ask the switches): the module's `lan_report` for each SNMP connection, with traffic rates from two readings one second apart.
- **Graphs:** traffic graphs on the main screen (Settings > Graphs > Add a port graph). Only SNMP connections can be chosen. The module returns raw counters; the App makes the rates (every second while someone is looking at the page, every 10 seconds otherwise; one hour kept; at most 12 graphs). The graph tops out at the port's reported speed unless you set a top speed.
- **Power:** a system with an SNMP login counts as "the server's own system" at its address when the App guesses which UPS powers what from NUT client lists.
- **Names:** a server added by address is named after the name the device reports (sysName); renaming an SNMP connection renames the system that holds its checks.

## How it is configured

All on screens, under **Settings > Servers**:

1. **Add a server** (name and address), then choose **SNMP (health, disks, network ports)**. Or open an existing server and use **Add**.
2. Fill the form:
   - **SNMP version:** v3 (a user and passwords) or v2c (a community word). v3 is the default.
   - v2c: **Community**.
   - v3: **User**; **Login method** (SHA, SHA-256, SHA-512, SHA-224, SHA-384, MD5, None; SHA by default); **Password**; **Privacy (encryption)** (AES, DES, None; AES by default); **Privacy password**.
   - **Port** (161 is the usual).
3. **Test connection.** It asks the device what it offers and shows how long it took and what it found.
4. **Save, then pick what to watch.** Tick the items and press Apply. Network interfaces start unticked, and "system items" (mounts such as `/boot` or `/var`) are hidden until you choose Show.

Later: **Edit** changes the connection; **Pick what to watch** re-reads the device; **Rescan this server** looks for things not yet watched. The page shows how many things are watched through each connection.

Thresholds and options such as CPU warning level are not on a screen; they exist only in the saved monitoring settings (Settings > Advanced). The defaults are in the next section.

## What it alerts on and how states map

The module only reports a state for each check; the App decides when to alert (see [the core app page](../APP.md)).

**A device that cannot be reached over SNMP (no answer, wrong user or password, refused) is Unknown, never Failed.** So is anything else that stops the module getting an answer. Only a device that answered and said something is bad can be Failed or Degraded.

| Check | Healthy | Degraded | Failed | Unknown |
| --- | --- | --- | --- | --- |
| Reachable (uptime) | answers; shows the name and "up Xd Xh Xm" | | | no answer; or answers without an uptime |
| CPU and memory | always healthy. A heads-up line appears when CPU is 90% busy or more, or memory is 90% used or more | | | device has no UCD tables |
| Volume | under 85% used (a heads-up line from 75%) | 85% used or more | 95% used or more | name gone; no size reported |
| Interface | up | in a state other than up/down (testing, unknown, dormant); or up but slower than a minimum speed, if one is set | down, not present, or lower layer down | name gone |
| Table row (QNAP) | status in the OK list | status in the warning list; a status nobody listed; used space 85% or more; disk at 55 °C or more | status in the bad list; used space 95% or more | name gone; no status |

Row statuses: for QNAP pools, 0 is OK, -1 and -2 are warnings, -3, -5 and -6 are bad. Other rows use word lists: OK for good, ready, normal, ok, online, healthy, optimal, active, 0; warning for warning, degraded, rebuilding, resyncing, syncing, verifying, scrubbing, initializing; bad for error, abnormal, failed, offline, inactive, critical, faulty, missing, -1.

Port error alerts come from the Port errors item (Degraded, never Failed); see [the Port errors page](../PORT-WATCH.md).

A check normally runs every 15 seconds with a 10 second timeout in the App. A failing check is retried sooner (see the core app page).

## Known limits

- **At most 4 requests at once per device** (address and port), each device with its own four workers. More than four wait their turn there (a device such as a NAS has dozens of checks that all arrive together). A request that has waited 10 seconds, or that arrives when 300 are already waiting, is turned away: a check answers **Unknown** with "that device is still busy with earlier requests"; other calls get an error with the same words. A device that stops answering therefore holds only its own workers, never another device's.
- **The module runs 8 requests at a time in all.** One slow device can use at most 4 of the 8, but two devices that both stop answering can use all 8 until their requests time out.
- One conversation with a device at a time: requests for the same connection take turns.
- A check that needs a long table walk on a slow device can run past the App's timeout and show Unknown ("did not answer").
- IPv4 only. v3 privacy is AES-128 or DES; there is no AES-192 or AES-256.
- Names must match exactly (ignoring capitals and spaces at the ends). If two rows have the same name, the check is Unknown until you use a more specific one.
- Virtual interfaces whose names start with `veth`, `br-`, `docker`, `virbr`, `lo`, `tun` or `tap` are never offered or read as ports. That includes any real interface whose name starts with `lo`, `tun` or `tap`.
- On a device with more than 64 interfaces, slots that are not present and tunnel, loopback and VLAN interfaces are left out of discovery and the switch report (the report says how many).
- Port speeds, link drops and the map depend on what the device reports; a device without 64-bit counters is read with 32-bit ones, and without either has no traffic.
- The learned-address and LLDP data are only as good as the device's tables; a switch without them looks like a server.
- The SNMP-only map has a guessed top switch; see [the Port errors page](../PORT-WATCH.md).
- Read-only means it cannot fix, restart or silence anything on the device.

## Troubleshooting

Messages appear in the check's detail line, prefixed "SNMP:" when they come from the module.

| Message | Meaning |
| --- | --- |
| the device did not answer (no reply from SNMP) | Nothing came back. Check the address and port, that SNMP is on, that the device allows this box, and for v2c the community. |
| cannot reach the device: ... | The box has no route or the network refused. |
| the device did not identify itself (is SNMPv3 enabled?) | v3 asked, the device did not tell its engine id. |
| the device does not know that SNMPv3 user name | User name is wrong. |
| the SNMPv3 authentication password is wrong (or the hash type does not match) | Password or login method (SHA/MD5...) is wrong. |
| the SNMPv3 privacy password is wrong (or the encryption type does not match) | Privacy password or AES/DES choice is wrong. |
| the device does not support that security level | The user on the device lacks authentication or privacy that you chose. |
| the SNMPv3 reply failed its authentication check (wrong password?) | The reply did not verify. |
| could not agree the SNMPv3 time window with the device | The device's clock counter kept disagreeing. Try again. |
| the device returned an SNMP error: noSuchName / authorizationError / ... | The device refused the request with that SNMP error code. |
| an empty SNMPv3 password is not allowed / SNMPv3 privacy needs authentication too | The saved settings are incomplete. |
| unknown SNMP version / unknown authentication type / privacy type ... is not supported | The saved settings are wrong. |
| this connection has no 'host' | The connection has no address. |
| the device answered but does not report its uptime | Answers, but not sysUpTime. |
| this device does not report CPU and memory over SNMP (net-snmp's UCD tables) | Not a net-snmp device; do not watch CPU and memory here. |
| Volume/Interface 'x' is not on the device any more (it has: ...) | The name is gone or changed. Pick what to watch again. (The message says "Use Re-detect"; the button is called Pick what to watch.) |
| 'x' matches N rows; use a more specific name | Two rows share the name. |
| the device did not report the size of 'x' / a status for 'x' | The row exists but has no value. |
| (unrecognised status; tell MonitorBox what it means with ok / warn / bad) | A table row status is in no list; shown as Degraded. |
| that device is still busy with earlier requests (it is slow or not answering) | A request waited more than 10 seconds for its device's four workers; see above. |
| the device lists no interfaces | Switch report on a device with no interface table. |
| `... (file.py:123)` | An unexpected fault in the module; the file and line say where. |

From the App side: "the snmp module is not running", "the snmp module is starting" (briefly after a start) and "the snmp module did not answer: ..." all make the check Unknown. On the Test connection form, a refused v3 login reads "The device answered but refused the login. Check the user name, the passwords and the encryption types."; no answer reads "Nothing answered at that address. Check the address and port, and that the device allows MonitorBox to ask it."

## Where it lives in the code

| What | File |
| --- | --- |
| Entry point, methods, the 4-per-device cap, 8 workers | `modules/snmp/main.py` |
| Version and entry | `modules/snmp/manifest.json` |
| Checks, name lookup, discovery, port counters, switch report | `modules/snmp/checks.py` |
| SNMP client (v2c, v3, MD5/SHA, AES/DES) | `modules/snmp/snmplib.py` |
| Server page, SNMP form, Pick what to watch, Graphs, Switch report | `app/monitorbox_app/ui.py` |
| Test connection, Re-detect, graph samples, switch suggestions | `app/monitorbox_app/server.py`, `followups.py` |
| Reading ports for the watch and the map | `app/monitorbox_app/lansampler.py`, `portwatch.py`, `lanmap.py` |
| Traffic graphs | `app/monitorbox_app/graphs.py` |
| Set up scan | `app/monitorbox_app/thisbox.py` |
