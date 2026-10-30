# Capabilities map: which modules each feature needs

The App itself only pings, opens ports, fetches web pages and asks DNS servers ([the core app page](APP.md)). Everything else on the screen exists because a module feeds it. This page answers two questions: **what does this feature need?** and **what does this module add?**

Each module page has an "Adds to the app" section with the detail. A module is installed when something needs it (Wake on LAN is the one exception and is installed on every new box).

## Feature to modules

| Feature | Needs | Notes |
| --- | --- | --- |
| Ping, port, web and DNS checks, the built-in Internet group, alerts, history, backups, sites | nothing | Core app |
| Health of a UniFi gateway, switch or access point, VPN tunnels, device temperatures | [UniFi Network](modules/unifi-network.md) | |
| Disk, CPU, memory, volume and network-card checks on a server, NAS or switch | [SNMP](modules/snmp.md) | |
| Container and Docker environment status | [Portainer](modules/portainer.md) | The Docker socket is deliberately not used |
| UPS status (the Power group) | [NUT](modules/nut.md) | |
| One alert when the power goes, instead of one per server | NUT | Needs the systems to be marked as powered by the UPS (the app guesses; you confirm) |
| Camera health, recorder and drive checks | [UniFi Protect](modules/unifi-protect.md) and/or [Scrypted](modules/scrypted.md) | |
| Camera pictures | UniFi Protect and/or Scrypted | A camera both report is shown once, from Protect |
| Live video | [Scrypted](modules/scrypted.md) only | Protect cameras show snapshots only |
| Port errors, drops and link-down alerts ([rules](PORT-WATCH.md)) | UniFi Network and/or SNMP | UniFi reads UniFi devices; SNMP reads any switch or server |
| Network map | UniFi Network and/or SNMP | SNMP switches that UniFi does not list are added to the map |
| Busiest client | UniFi Network | Wired clients from port readings, Wi-Fi clients from the gateway's flow log |
| Traffic graphs on the main screen | SNMP | Only SNMP connections can be chosen; the graph's detail panel can use UniFi flows |
| Switch report and flow look (Settings, Advanced) | SNMP (switch report), UniFi Network (flow look) | |
| Public (WAN) address shared with paired sites | UniFi Network (best), otherwise a public address page | See the multi-site section of the core app page |
| Wake a machine | [Wake on LAN](modules/wol.md) | The one module that sends something rather than only reading |
| Suggestions in "Found more you can add" | whichever module is connected | E.g. a UniFi login suggests Protect; Portainer suggests Scrypted and UniFi containers |

## Module to features

| Module | Adds |
| --- | --- |
| **UniFi Network** | Device, health, tunnel and temperature checks; the network map; Port errors for UniFi devices; Busiest client; gateway flow log; the WAN address; the setup "UniFi gateway" row; suggestions for Protect and for your SNMP login on UniFi switches |
| **UniFi Protect** | Camera, recorder, storage and drive checks; the Cameras card pictures; camera addresses used to find the switch port a camera is on |
| **SNMP** | Reachable, CPU and memory, volume, network interface and table-row checks; Port errors and map nodes for non-UniFi switches and for servers; traffic graphs; switch report |
| **NUT** | UPS checks; the Power group and Power page; power guesses; "affected by the UPS" explanations; urgent power alerts |
| **Portainer** | Environment and container checks; containers as services; "runs on" links; environment power; suggestions for new containers |
| **Scrypted** | Camera checks and pictures; the only source of live video; camera discovery |
| **Wake on LAN** | The Wake button and its status line |

## With a module absent

| Missing | What disappears | What keeps working |
| --- | --- | --- |
| UniFi Network | UniFi device and tunnel health, UniFi-fed map, Busiest client, flow look, UniFi port counters | SNMP can still read ports and build map nodes for devices that speak SNMP |
| SNMP | Server and NAS disk, CPU, memory and interface checks; graphs; SNMP-read ports | UniFi still reads UniFi ports and feeds the map |
| UniFi Protect | Protect camera health, recorder and drive checks, Protect pictures | Scrypted cameras still appear |
| Scrypted | Live video; Scrypted-only cameras | Protect cameras still show snapshots |
| NUT | The Power group, power guesses, one-alert-per-power-cut | Servers still alert on their own, separately |
| Portainer | All container views | Everything else |
| Wake on LAN | The Wake button | Monitoring is unaffected |

A module that is installed but cannot reach its device makes its checks **Unknown**, never Failed.

## Where two modules overlap

- **A switch port that UniFi and SNMP both report.** A device is never read both ways. An SNMP connection that is the same device as a UniFi one is read over SNMP (exact counters, and it works for non-UniFi switches); otherwise the UniFi readings are used. The match is by address, then by interface hardware address, then by name. The map draws a matched switch once. Details in [Port errors](PORT-WATCH.md).
- **A camera that Protect and Scrypted both report.** Matched by name, ignoring capitals. It is listed once, with its picture from Protect and live video from Scrypted. If one source says it is down and the other says it is fine, it shows as Degraded, not Down, and alerts treat it as one camera.
- **The same server in more than one place.** A system with an SNMP login counts as that server's own system when the app guesses which UPS powers what; a Portainer environment follows the power of the machine it runs on and is not offered separately on the Power page.
