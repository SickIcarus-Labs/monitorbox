# Exposing MonitorBox safely, and privacy

## Keep it off the internet if you can

MonitorBox is meant for your own network. The safest way to reach it from outside is a VPN to your home network. Do not forward its web port straight to the internet.

If you do want it reachable from outside:

1. Put it behind a **reverse proxy that provides HTTPS** (Caddy, Nginx Proxy Manager, Traefik or similar). MonitorBox itself speaks plain http.
2. When the proxy tells MonitorBox the connection is HTTPS, MonitorBox marks its sign-in cookie `Secure` and sends the HSTS header. First-time setup is refused through the proxy, so a reset box cannot be claimed from the internet: do the first setup from your own network.
3. Sign in with a **passkey** if you can. Passkeys need an HTTPS address.
4. Use **Sign out** on any device that is not yours (Settings, This box).

## What protects it

- A password is required before anything else. There is no default password.
- Too many wrong passwords from one address lock that address out for a while, and the pause grows. A burst of wrong attempts from many addresses through the proxy pauses outside sign-in for a few minutes; people at home are not affected.
- Each device that signs in gets its own random key. The box stores only a hash of it.
- Passkey sign-in is supported.
- Inside the container MonitorBox runs as root, but with every capability dropped except the one ping needs (NET_RAW), a read-only filesystem and no-new-privileges.
- MonitorBox is **read-only** towards what it watches: it does not mount the Docker socket, does not control anything, and does not log in to your systems to run commands. The one thing it can send is a Wake-on-LAN packet, when you tap the button.

## Where updates come from

The app and its modules are downloaded from the `monitorbox-modules` repository on GitHub and run inside the container, where they can see the passwords and tokens you give them. Each download is checked against a SHA-256 fingerprint, which catches a damaged download; it does not prove who published it, because the fingerprint is published next to the file. You are trusting that repository, and any repository you add on the Updates page. This is why automatic updating is **off** by default: you choose when to update. Only add repositories you trust.

## The site port (several sites)

If you connect sites over the internet, only the **site port** (8443 by default) needs to be forwarded. Connections to it are encrypted and need a key made at pairing; visitors without it get nothing, and repeated failed attempts from one address lock it out. Do not forward the web port for this.

## Privacy: what the box contacts

MonitorBox has no accounts, no analytics and no telemetry. It contacts only:

- **GitHub**, to check for updates and download them (the `monitorbox-modules` repository, and any repository you add on the Updates page). You can switch automatic checking off in Settings, Updates.
- **Whatever you set up yourself:** your devices, Portainer, UniFi, your mail server, your Home Assistant.
- **The internet checks**, if you keep them: setup can add pings and name lookups to public servers (Cloudflare 1.1.1.1 and Google 8.8.8.8) to tell whether your internet is up. Remove them if you do not want that.

Your container runtime separately pulls the image from `ghcr.io` when you install or update it.

What MonitorBox keeps is in your config folder: settings, history and backups. Passwords and tokens you give it are stored there, so protect that folder like any other that holds credentials, and use read-only accounts wherever you can.
