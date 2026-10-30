# MonitorBox documentation

## Start here

- [Install guide](INSTALL.md): the compose file and first run.
- [Setup guides](GUIDES.md): read-only accounts and SNMP before you start.
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security and privacy](SECURITY.md)
- [Known limitations](LIMITATIONS.md)

## How MonitorBox works

- [The core app](APP.md): what it checks by itself, how modules plug in, states, confirmation, alerts, settings, updates, backups, sites, logs, and where the data lives.
- [Capabilities map](CAPABILITIES.md): which modules each feature needs, and what each module adds.
- [Port errors](PORT-WATCH.md): the rules for the Port errors item.
- [Architecture](ARCHITECTURE.md): how it is built. The [design log](DESIGN-LOG.md) holds the reasoning behind changes, oldest first; where the two disagree, the architecture page is current.
- [Screenshots](SCREENSHOTS.md)

## Modules

| Module | What it is for |
| --- | --- |
| [UniFi Network](modules/unifi-network.md) | Gateway, switch and access point health, VPN tunnels, the network map, Busiest client |
| [UniFi Protect](modules/unifi-protect.md) | Cameras, recorder and drives |
| [SNMP](modules/snmp.md) | Servers, NAS and switches: disks, CPU, memory, network cards, traffic graphs |
| [NUT](modules/nut.md) | UPS status and power alerts |
| [Portainer](modules/portainer.md) | Containers |
| [Scrypted](modules/scrypted.md) | Cameras and live video |
| [Wake on LAN](modules/wol.md) | Waking a machine |

Ping, port, web and DNS checks are part of the core app, not modules.
