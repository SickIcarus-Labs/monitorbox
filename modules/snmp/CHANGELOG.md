# SNMP changelog

What changed in each version of this module, in plain words, newest first. The release build puts these lines in the catalog, and the Versions page shows them as "What changed". Format: `- **version** text`.

- **0.3.13** A NAS disk that is too warm now says so ("57 °C (hot, limit 55 °C)"), instead of showing "status Good" while Degraded. An SSD gets a higher built-in limit (70 °C) than a hard drive (55 °C), and each disk can have its own limit.
- **0.3.12** Reads servers, NAS boxes and switches over SNMP, read-only: health, disks and volumes, and network ports (errors, drops and packet counts). Each device has its own queue of requests, so a slow device cannot hold up the others.
