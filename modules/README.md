# modules

One folder per integration: `unifi-network`, `unifi-protect`, `snmp`, `nut`, `http`, `scrypted`, `portainer`, `wol`, `ping`. Each is built into an archive with a manifest, code and a settings schema, and runs as its own subprocess speaking JSON lines to the App.

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
