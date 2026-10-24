# MonitorBox

A lightweight, fast and friendly health glance at your homelab. Open it and one screen answers one question: **is everything fine?**

MonitorBox was designed to be light enough for a Raspberry Pi, and has been tested on a Raspberry Pi 5 and an Intel NUC mini PC.

<!-- screenshots go here -->

## What it does

The whole screen is the answer. **Green** means everything is fine. **Yellow** means something is down and needs attention. **Red** means something critical is down. **Blue** means something could not be checked right now (MonitorBox says "I don't know" rather than guessing). Tap anything to drill down.

- **Checks** through ICMP (ping), HTTP, SNMP, Docker containers (via Portainer), Wake-on-LAN, UPS battery backups (NUT), cameras (Scrypted), and native UniFi Network and UniFi Protect integrations.
- **Finds things for you.** Point it at a server and it detects what that server offers. After install it keeps looking, and tells you when a new container or new capability appears.
- **Alerts you** when something goes wrong, by email (any SMTP server, Gmail included) or through Home Assistant notifications. One message per root cause, not one per thing that depends on it, and one all-clear when it recovers.
- **Multiple sites.** Connect several MonitorBoxes (a home and a cabin, say) and see them all from one screen, with tabs and one notification bell. Each box keeps watching and alerting on its own, even if the link between them drops.
- **Who talks to whom.** With UniFi it works out which devices on your LAN are talking to each other, without packet capture, port mirroring or sniffing.
- **Your screen, your way.** Simplified or detailed front page, and throughput graphs you choose and size.
- **Modular and expandable.** Integrations install, update and remove on their own, and there is a framework for third-party repositories and plugins, so anyone can contribute new functionality.
- **Updates itself** if you want it to, with channels (stable, beta, dev), pinning and one-tap rollback. It tells you when the container image itself needs pulling.
- **Backup and restore that works.** Automatic backups, and a restore proven by an automated test that gives every setting a different value and compares each one afterwards.
- **Read-only.** MonitorBox never controls anything: no Docker socket, no remote control, no logging in to your systems. It asks your devices questions and never changes them. Your UPS data is read, never used to shut anything down.

## Install

You need a machine running Docker. Quick version:

1. Make a folder for MonitorBox's settings.
2. Start the container from the [compose file](docs/INSTALL.md#the-compose-file), with Portainer or plain Docker Compose.
3. Open `http://<your-machine>:8080`.

The full steps, including installing Portainer, are in the **[install guide](docs/INSTALL.md)**. Please read its "Before you start" section: a little preparation (read-only accounts, SNMP) makes the first run much smoother.

## How it is built

Three parts in one container: a tiny launcher (first run, downloads, rollback, a recovery page), the app (web page, status engine, configuration, backup, updates), and downloadable modules, one per integration, each running separately. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repositories

| Repo | Purpose |
| --- | --- |
| `monitorbox` (this one) | Source and docs |
| `monitorbox-modules` | Built releases and the three channel pointer files |

The container image is `ghcr.io/sickicarus-labs/monitorbox`. More repositories can be added from the Updates page in the app.

## Licence

MIT, see [LICENSE](LICENSE). Bundled icons, fonts and runtimes keep their own terms, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
