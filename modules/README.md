# modules

One folder per integration: `unifi-network`, `unifi-protect`, `snmp`, `nut`, `scrypted`, `portainer`, `wol` (plus `hello`, a sample for module authors). Ping, port, web and DNS checks are built into the app, not modules. Each is built into an archive with a manifest, code and a settings schema, and runs as its own subprocess speaking JSON lines to the App.

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).


## A module comes with its detector

A module is installed only when it is needed: when a device of its kind is added or tested (the app installs it at that moment), or when the app detects the need and proposes it. Wake-on-LAN is the one exception, because nothing can detect it. A new module is not finished until the app can detect its need (a follow-up suggestion, a discovery step) or the owner has said it cannot be detected. See ticket #98.


## Each module keeps its own changelog

`modules/<id>/CHANGELOG.md` lists what changed in each version of that module in plain words, newest first, one line per change: `- **0.3.12** What changed.` Add a line with every version bump. The release build copies the line for each version into the catalog, and Settings, Versions shows it as **What changed** (the same way as for the app). The file is not part of the module's archive, so editing a note never needs a new module version. The first line of a module's changelog is a short description of what it does.
