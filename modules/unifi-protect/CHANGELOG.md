# UniFi Protect changelog

What changed in each version of this module, in plain words, newest first. The release build puts these lines in the catalog, and the Versions page shows them as "What changed". Format: `- **version** text`.

- **0.1.7** Waits up to 15 seconds for the console to answer (was 8), so a gateway busy routing a big download still gets read instead of turning every camera Unknown.
- **0.1.6** Reads UniFi Protect, read-only: every camera's state, the recorder and its recording space, each drive's temperature and health, and a still picture of each camera.
