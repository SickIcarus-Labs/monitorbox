# MonitorBox 4

A small, fast, good-looking appliance that answers one question when you open it: **is the homelab fine?**

> MonitorBox 4 is a ground-up rewrite.

The whole screen is the answer. Soft green says **Everything is fine**. Yellow says **Something's down** (needs attention, not critical). Blue says **Something needs a look** (can't be checked right now). Red says **Everything is fucked.** (a critical item is down). Tap anything to drill down.

## Goals

1. **Install once.** A simple compose file that rarely or never changes. The app updates itself, with no `docker pull`.
2. **Status at a glance.**
3. **Light, fast, pretty.** Not another Netdata.
4. **Modular.** Integrations install, update and remove on their own.
5. **Simple and reliable.** Few moving parts, clear failure modes.
6. **Dev, beta and stable channels** that are one-file moves.
7. **Backup and restore that actually work**, proven by an automated round-trip test.
8. **Cheap CI.**
9. **Polished first experience:** real onboarding and a good config UI.
10. **Keep coverage:** UniFi, SNMP, NUT, HTTP, Scrypted, Portainer, Wake-on-LAN.
11. Later: alerting (one alert per root cause) and multiple sites. Eventually: publishable.

## Shape

Three parts in one container: a tiny **Launcher** (first run, downloads, rollback, recovery page), one **App** (web UI, status engine, config, backup, updates), and downloaded **Modules** (one per integration, each its own subprocess).

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## Repositories

| Repo | Purpose |
| --- | --- |
| `monitorbox` (this one) | All source and docs |
| `monitorbox-modules` (public) | Built archives and the three channel pointer files |

The container image is `ghcr.io/sickicarus-labs/monitorbox`. Other repositories can be added on the Updates page of the app (see issue #264).

## Status

MonitorBox 4 is in active development. A full install guide is coming; until then see [docs/INSTALL.md](docs/INSTALL.md).

## Licence

MIT, see [LICENSE](LICENSE). Bundled icons, fonts and runtimes keep their own terms, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
