# modules

One folder per integration: `unifi-network`, `unifi-protect`, `snmp`, `nut`, `http`, `scrypted`, `portainer`, `wol`, `ping`. Each is built into an archive with a manifest, code and a settings schema, and runs as its own subprocess speaking JSON lines to the App.

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).


## A module comes with its detector

A module is installed only when it is needed: when a device of its kind is added or tested (the app installs it at that moment), or when the app detects the need and proposes it. Wake-on-LAN is the one exception, because nothing can detect it. A new module is not finished until the app can detect its need (a follow-up suggestion, a discovery step) or the owner has said it cannot be detected. See ticket #98.
