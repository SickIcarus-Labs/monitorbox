# MonitorBox: how it is built

A short, current description of the design. The reasoning behind individual changes, oldest first, is in the [design log](DESIGN-LOG.md); where the two disagree, this page is the current one.

## 1. Three parts, one container

```
Docker host (host network)
 └─ one container
     ├─ Launcher  (in the image, tiny)  first run, folders/permissions, downloads, starts the App, rolls back, recovery page
     ├─ App       (one program)         web UI and API, scheduler, status engine, alerts, config, backup/restore, updates
     └─ Modules   (downloaded, one each) UniFi Network, UniFi Protect, SNMP, NUT, HTTP, Scrypted, Portainer, Wake-on-LAN, ping
```

Only the launcher is in the image. The App and every module download into `/config` and update in place. The launcher stays tiny because it is the one part that must never break.

**Module protocol:** the App starts each module as its own subprocess and exchanges JSON lines over stdin/stdout. A crash takes down only that module. Modules are written in Python or Node.

**What is not a module:** the app shell, onboarding, backup and restore, and the alert senders (email and Home Assistant), which are part of the App.

## 2. Status screen

| Colour | Headline | Means |
| --- | --- | --- |
| Green | Everything is fine | all healthy (an optional quiet heads-up line can sit under it) |
| Yellow | Something's not right | something answers, but not properly (degraded), and nothing is down |
| Red | Something's down | something is actually down |
| Blue | Something needs a look | something cannot be checked right now |

Red has one more, rarer, headline for when something *critical* is down. Precedence: red, yellow, blue, green. Critical means core infrastructure (servers, core network gear, WAN/DNS, router); onboarding proposes it and you can change it. Dark theme; every state is also shown as text, never colour alone.

A provider outage (UniFi, Portainer, a server not answering) shows as **Unknown** (blue), never as failed. Observed state is never rewritten; suppression only affects alerts.

A status change reaches the screen within about two seconds (pushed, no polling). With every integration running, the whole container uses roughly 280 to 330 MB of memory.

## 3. Compose and disk layout

One host-networked container (Wake-on-LAN and LAN discovery need it), `read_only`, `cap_drop: ALL` plus `NET_RAW` (ping), a `/config` bind mount, and `/tmp` as a tmpfs with no size limit.

```
/config
  launcher/  releases/  current/  previous/   versions and links; switching a version is changing a link
  config/    monitorbox.json + revision history
  data/      per-module state; app/ (password record, last readings, port history)
  backups/   never included in a backup
  logs/
```

## 4. Releases and channels

A source repository and a public releases repository (built archives and pointers only). A **channel is one pointer file** (`channels/dev|beta|stable.json`) naming the exact App and module versions with URL and sha256, and the container-image version the release was built for. `dev` moves automatically on merge; `beta` and `stable` move only through the manual **Promote channel** workflow (dev to beta, beta to stable, or a rollback to an earlier commit's pointer).

Updates: download, verify the checksum, snapshot data, activate, watch health, keep or roll back automatically. Older software never starts against a newer database.

The container image is separate from the App and changes rarely. The launcher records its own image version at start-up; if a release was built for a newer image than the one running, the App says so (bell, Updates page and Settings line) and the owner pulls the new image. Any new image ships with a bump of the launcher's `VERSION`, even with no code change.

Other releases repositories can be added on the Updates page; a built-in one cannot be switched off.

## 5. Configuration

One file, `monitorbox.json`, holding intent only (history is in `config/history.jsonl`; the latest readings are cached under `data/app/`). Every edit goes through validate, diff, revision-conflict check, atomic apply and undoable history. A bad edit can never take the app down: it keeps running on the last good version and shows the exact error. A system owns its checks, wake settings and criticality; connections hold credentials and endpoints once; disks and interfaces are listed by **name** and the SNMP module looks up the current index (re-detect on failure) so a drive layout change self-heals. Discovered services and cameras are stored only as decisions.

Everything is editable in the app. Secrets are stored in plain text in the file (mode 0600) by design, masked in the UI and never logged, so protect the config folder. The admin password is never in the file.

## 6. Backup and restore

One code path, two outputs: **config backup** (`monitorbox.json`, nightly) and **full backup** (config plus data, optionally packages, weekly). Restore: validate, stop modules, stage, migrate in staging, atomic swap, start, check health; on failure the original is put back. The launcher serves a recovery page that works with the App down.

**Release gate:** an automated round trip that gives every credential a distinct value and compares each one after the restore, plus a real check against a fake device that accepts only the right credential.

## 7. Monitoring, dependencies and alerts

States: healthy, degraded, failed, unknown (and pending, before a first result). A thing marked expected down shows grey but keeps its observed state. The App keeps a dependency map from what you declare, what integrations discover (containers depend on their host, cameras on Scrypted and the network path) and the UniFi topology (device, switch port, switch, uplink). **One alert per root cause:** dependents are marked "affected by" it and stop raising their own alarms, while still displaying what is actually observed. Alerts use hold-down times, recovery notices, deduplication, storm and flap damping, and expected-down marks (maintenance windows and silences do not exist yet). Messages go by email (any SMTP server) or to Home Assistant.

**Port errors.** A built-in item that watches switch port counters and link state from UniFi and SNMP for rising errors, drops and links that go away. Read-only, Degraded never Failed. The rules are in [PORT-WATCH.md](PORT-WATCH.md).

## 8. Several sites

A full MonitorBox per site. One (the main one) is paired with the others and can manage them; control goes **one way only**. Sites talk over a separate site port (default 8443, off until enabled) using TLS with a pre-shared key made at one-time pairing, so only one port needs forwarding and no certificates are involved. If the link drops, each site keeps watching and alerting on its own. Because the link runs over a private address, a silent link alone proves nothing, so the sites also tell each other their public addresses (over the same link, in the poll) and judge a silent link by pinging that address from outside the tunnel: the address answers = Degraded, it does not and this box's own internet is fine = Down, this box's own internet is down too = Unknown. A gateway that reports a private WAN address (double NAT or a UniFi glitch) means "cannot tell": nothing is shared. See `wanaddr.py` and `peer.py`.

## 9. Tests and CI

Pull requests: unit tests, schema checks and browser tests, path-filtered so only what changed is tested. Merge to main: build what changed and move `dev`. The image builds only when the launcher or Dockerfile changes. Promotion is manual only.

A version check (`tools/check_versions.py`) fails a pull request that changes the App without bumping its `VERSION`, a module without bumping its manifest `version`, or the launcher or Dockerfile without bumping the launcher `VERSION`. Published versions are immutable, so without it the mistake would only show after merge, as a failed publish.
