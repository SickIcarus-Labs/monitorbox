# SNMP changelog

What changed in each version of this module, in plain words, newest first. The release build puts these lines in the catalog, and the Versions page shows them as "What changed". Format: `- **version** text`.

- **0.3.12** Reads servers, NAS boxes and switches over SNMP, read-only: health, disks and volumes, and network ports (errors, drops and packet counts). Each device has its own queue of requests, so a slow device cannot hold up the others.
