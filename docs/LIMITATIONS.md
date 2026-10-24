# Known limitations and what is next

## Limitations today

- **Docker on Linux.** MonitorBox needs host networking to reach your devices, so it is for Docker running directly on Linux (tested on a Raspberry Pi 5 and an Intel NUC). Docker Desktop on Windows or macOS is not supported.
- **Read-only by design.** MonitorBox tells you what is wrong. It does not restart containers, fix things, or control devices. The one exception is Wake-on-LAN.
- **Container visibility needs Portainer.** MonitorBox sees your containers through Portainer, not through the Docker socket.
- **One admin password.** There is one sign-in for the box (with passkeys as another way in). There are no separate user accounts or roles.
- **No password recovery.** Forgetting the password means starting over and restoring a backup.
- **UniFi extras need UniFi.** Which devices talk to each other on your LAN comes from your UniFi gateway.
- **Each site needs its own MonitorBox.** Watching a remote site with nothing installed there is not available yet.

## Ideas for later

These are open, not promised:

- Watching port errors, drops and link flaps over time.
- Watching a remote site with no MonitorBox running there.
- Third-party plugins (the framework for other repositories exists; the plugin design is still to come).
- Learning service names and addresses from Caddy.
- Letting you arrange the main screen.

Found a bug or have an idea? Open an issue on GitHub.
