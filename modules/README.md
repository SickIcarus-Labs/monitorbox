# modules

One folder per integration: `unifi-network`, `unifi-protect`, `snmp`, `nut`, `http`, `scrypted`, `portainer`, `wol`, `ping`, plus notifiers later. Each is built into an archive with a manifest, code and a settings schema, and runs as its own subprocess speaking JSON lines to the App.

The version 3 module code is a porting reference (logic worth keeping, adapter to be rewritten). Ported from milestone M4. See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
