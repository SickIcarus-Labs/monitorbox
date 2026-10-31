# UniFi Network changelog

What changed in each version of this module, in plain words, newest first. The release build puts these lines in the catalog, and the Versions page shows them as "What changed". Format: `- **version** text`.

- **0.2.27** The flow log for Insights is read on its own lane, so a long flow search no longer makes the status checks wait (one could wait over 22 seconds and turn a device Unknown).
- **0.2.26** Waits up to 15 seconds for the console to answer (was 8), so a gateway busy routing a big download still gets read instead of turning everything Unknown.
- **0.2.25** Reads your UniFi gateway, switches and access points, read-only: device health, temperatures, Wi-Fi, WAN, internet and LAN status, port errors and the Insights flows.
