# MonitorBox 4: architecture summary

Condensed from the living design document (a shared doc, draft 2 plus later decisions). Where this file and an issue disagree, the newer decision wins; update this file when a decision changes.

## 1. Three parts, one container

```
Docker host (host network)
 └─ one container
     ├─ Launcher  (in the image, tiny)  first run, folders/permissions, downloads, starts the App, rolls back, recovery page
     ├─ App       (one program)         web UI + API, scheduler, status engine, alerts, config, backup/restore, module updates
     └─ Modules   (downloaded, one each) UniFi, SNMP, NUT, HTTP, Scrypted, Portainer, WOL, ping, notifiers
```

Only the launcher is in the image. The App and every module download into `/config` and update in place. The launcher stays tiny because it is the one part that must never break.

**Module protocol:** the App starts each module as its own subprocess and exchanges JSON lines over stdin/stdout (check request in; state, summary, metrics, timing out). A crash takes down only that module. Python or Node.

**Not modules:** app shell, onboarding, backup/restore. A module supplies cards, detail pages and settings forms from a fixed UI kit (status card, gauge, list, chart, camera, form), drawn by the App in one style.

## 2. Status screen

| Screen | Banner | Means |
| --- | --- | --- |
| Soft green | Everything is fine | all healthy |
| Yellow | Something's down | something non-critical is down or degraded |
| Blue | Something needs a look | something cannot be checked |
| Red | Everything is fucked. | a critical item is down |

Precedence: red, yellow, blue, green. Critical means core infrastructure (servers, core network gear, WAN/DNS, router); onboarding proposes it and the owner can change it. Dark theme; every state is also shown as text, never color alone.

Targets (to measure on the Pi and an iPad): first paint under 1 s, a status change on screen within about 2 s (pushed, no polling), idle container under about 200 MB RAM, one probe loop per target.

## 3. Compose and disk layout

One host-networked container (Wake-on-LAN needs it), `read_only`, `cap_drop: ALL` plus `NET_RAW`, `/config` volume, `/proc` and `/sys` read-only, `/tmp` tmpfs with **no size limit** (v3 lesson). To verify in M1: first-run folder setup under `cap_drop: ALL` may need a `user:` mapping.

```
/config
  launcher/  releases/  current/  previous/   versions and links; switching a version is changing a link
  config/    monitorbox.json + revision history
  data/      per-module state; app/monitorbox.db (SQLite)
  backups/   never included in a backup
  logs/
```

## 4. Releases and channels

Private source repo plus a public releases repo (built archives and pointers only). A **channel is one pointer file** (`channels/dev|beta|stable.json`) naming the exact App and module versions with URL and sha256 (a `signature` field is reserved). `dev` moves automatically on merge; `beta` and `stable` move only through the manual **Promote channel** workflow (dev to beta, beta to stable, or a rollback to an earlier commit's pointer). Updates: download, verify checksum, snapshot data, activate, watch health, keep or roll back automatically. Older software never starts against a newer database.

## 5. Configuration

One file, `monitorbox.json`, holding intent only (live state and history are in SQLite). Every edit, visual or raw JSON, goes through validate, diff, revision-conflict check, atomic apply and undoable history. A bad edit can never take the app down: it keeps running on the last good version and shows the exact error. A system owns its checks, wake settings and criticality; connections hold credentials and endpoints once; disks and interfaces are listed by **name** and the SNMP module looks up the current index (re-detect on failure) so a drive layout change self-heals. Discovered services and cameras are stored only as decisions. Secrets are plaintext in the 0600 file by the owner's choice, masked in the UI, never logged, with an "export without secrets" option. The admin password is never in the file.

Everything is editable in the app: a system's Wake-on-LAN MAC addresses are plain fields, and **Re-detect** re-reads disks and volumes.

## 6. Backup and restore

One code path, two outputs: **config backup** (`monitorbox.json`, nightly) and **full backup** (config plus data, optionally packages, weekly). Restore: validate, stop modules, stage, migrate in staging, atomic swap, start, check health; on failure the original is put back. The launcher serves a recovery page that works with the App down. **Release gate:** an automated round trip with a distinct value for every credential, compared after restore, plus a real check against a fake device that accepts only the right credential. (v3's export wrote one credential value into two servers' entries and its tests never noticed.)

## 7. Monitoring, dependencies and alerts

States: healthy, degraded, failed, unknown, disabled; freshness is separate. The App keeps a dependency map from what the owner declares, what integrations discover (containers depend on their host, cameras on Scrypted and the network path) and the UniFi topology (device, switch port, switch, uplink). One alert per root cause: dependents are marked "affected by" it and stop raising their own alarms, while still displaying what is actually observed. Planned reboots/maintenance work the same way, with a timer, and alert only if the system has not returned when it ends. Alerts use hold-down times, recovery notices, deduplication, maintenance windows and silences; notifiers are modules.

## 8. Multi-site

A full install per site, federated over HTTPS with one-time pairing. If the link drops each site keeps working and peers show it as Unknown.

## 9. CI budget

Pull requests: lint, unit tests, schema checks, path-filtered, minutes. Merge to main: build what changed and move `dev`. Nightly or on demand: integration boot test on a blank volume (install from a test channel, backup/restore round trip, update and rollback). Image builds only when the launcher changes. Promotion is manual only.

Version check (pull requests): `tools/check_versions.py` fails a PR that changes `app/monitorbox_app/` without bumping `VERSION`, or changes a `modules/<id>/` folder without bumping the `version` in that module's `manifest.json`. Published versions are immutable, so without it the mistake only shows after merge, as a failed dev publish (0.81.5).

## 10. Build order

| Step | Scope |
| --- | --- |
| M0 | repos, labels, release pointers and promote workflow, CI skeleton (done) |
| M1 | launcher + App skeleton + hello module + channels; blank `/config`, install, update, roll back, compose never touched |
| M2 | status screen with ping/TCP/HTTP checks and the dependency map (mock the four states first; mockups exist) |
| M3 | backup and restore with the release gate |
| M4 | port WOL, SNMP (by-name volumes), NUT, UniFi; fix the WOL/SNMP regression on the real server |
| M5 | onboarding wizard and config UI |
| M6 | Scrypted and Portainer |
| M7 | alerting |
| M8 | multi-site |
| M9 | cutover from v3, only with the owner's approval |

## 11. Decisions

Language Python (Node in the image for Scrypted). Private source plus public releases repo. One pointer file per channel. sha256 now, signature reserved. A full install per site. UI, onboarding and backup live in the App. Old repos are renamed `_old` at launch; MonitorBox 3 reads its module index from the old modules repo, so no repo is renamed or replaced until cutover.

## Backup and restore (M3)

- One code path: `launcher/monitorbox_launcher/backup.py`. The App makes backups through it (the launcher tells it where via `MB_LAUNCHER_PATH`); the launcher restores through it, so a restore works with the App down. Launcher protocol 3.
- A backup is one `.tgz` with a `manifest.json` (kind, created, App version, SHA-256 of every file). `config` = `config/` + `data/app/auth.json` (nightly, keep 14). `full` = also `data/app/` and `releases/` with the `current`/`previous` link names (weekly, keep 4). Manual and uploaded ones are never pruned. Files are mode 0600: they hold credentials.
- Restore: validate everything first (checksums, only expected paths, no links, no `..`) and touch nothing if anything is wrong; keep a `pre-restore` safety backup; move current files aside, move the new ones in (journalled in `restore/journal.json`); start the App; only when it is healthy delete the old files. If it will not start, or the launcher dies mid-restore, the old files are put back (`undo()`, safe to repeat).
- Recovery page (launcher, while the App is down): list stored backups, upload one, restore. Asks for the admin password when one exists; open on a wiped box (nothing to protect).
- The release gate is `tests/test_backup_roundtrip.py` (every credential distinct, compared one by one after back up -> wipe -> restore, plus a fake device that accepts only its own credential) and `tests/test_backup_e2e.py` (real launcher and App, including restore with the App down). **Rule for M4+: every integration keeps its credentials in `config/monitorbox.json` under `connections`, so the gate covers them.** Backups live inside the volume, so the owner downloads a copy elsewhere.

## Module checks and connections (M4a)

- A node's check can be `{"type":"module","module":"<id>","connection":"<id>","check":"<name>","params":{...}}`. The App asks the module over the JSON-lines protocol: `check` with `{check, params, connection}`; the module answers `{state: healthy|degraded|failed|unknown, detail}`.
- **A module problem is Unknown, never Failed.** If the module is missing, crashed, silent or errors out, the check reads "cannot be checked" (blue). Only a module that really talked to the device may say `failed`. A crashed module is restarted (every 10 s at most).
- `degraded` (it answers, but not properly: UPS on battery, disk nearly full) shows as yellow, never red, even on a critical item (result flag `warn`).
- `connections` in `config/monitorbox.json` hold how to reach a device (`id`, `module`, host, logins). **All credentials live here**, so backups and the round-trip gate cover them. The Settings editor shows secret-looking fields (pass, secret, token, key, community) as dots and keeps the stored value unless a new one is typed; secrets are never copied into the revision history.
- Shared credentials are fine (two servers with one login); the gate has a test for them.

## Wake on LAN (M4b)

- A system (leaf node) can carry `"wake": {"macs": [...], "broadcast": "192.168.77.255", "port": 9, "timeout": 960, "retry": 30}`. MACs are ordinary per-system settings, edited in the Monitoring editor, any spelling accepted and stored as `aa:bb:cc:dd:ee:ff`.
- The **Wake** button (system drawer) sends one magic packet per MAC through the `wol` module, resends every `retry` seconds, and **confirms by running the system's own checks** until they pass or `timeout` is reached. The result ("is up", "did not answer", "wol module is not running") is pushed to every open screen and kept for two minutes. A second press while one is running does nothing.
- Wake is a deliberate owner action, not monitoring: it needs a signed-in session and the `X-MB` header like every change.

## SNMP by name (M4c)

Module `modules/snmp` (0.1.0), pure standard library: its own SNMP client (`snmplib.py`: v2c, and v3 with
MD5/SHA-1/SHA-2 authentication and AES-128 privacy; DES is not supported). No new dependency or privilege.
The crypto is checked against the published AES, CFB and RFC 3414 test vectors.

- **Checks by name (issue #10).** A check says `volume /volume1` or `interface eno3`, never a raw OID with an
  index. The module caches name → index, but every poll reads the name back with one small GET; if it moved or
  vanished it searches the name column again. A name that is truly gone reads Unknown and lists what the device
  has now. Kinds: `uptime`, `resources` (CPU, memory), `volume` (warn 85 %, fail 95 %), `interface`
  (optional `min_speed_mbps`) and `row` (any table row by name; presets `qnap-pool`, `qnap-raid`, `qnap-disk`,
  `qnap-volume`, or your own columns with `ok`/`warn`/`bad` value lists). An unrecognised status is Degraded,
  never silently green.
- **Unreachable or wrong login = Unknown**, never Failed.
- **Re-detect.** `POST /api/detect {connection}` asks the module's `discover` method what the device offers now
  (Settings → Re-detect). Read-only.
- **Connections** hold all SNMP credentials (`community`, `authPassword`, `privPassword`), so the backup gate covers them.
- **Concurrency.** `ModuleProcess` now has a reader thread that hands each answer to its caller by id, and the
  snmp module answers on a thread pool, so one slow device does not hold up the others.

## UPS via NUT (M4d)

Module `modules/nut` (0.1.0), standard library only. **Read-only**: it sends only `LIST UPS` and `LIST VAR <ups>`
(a test fails if anything else is ever sent). It never logs in, sets, runs a UPS command or triggers a shutdown.

- Connection: `{"id","module":"nut","host","port":3493}`. One connection serves every UPS on that server; the UPS name is
  a check parameter (`{"check":"ups","params":{"ups":"networkups"}}`).
- States: `OL` healthy; `OB`/`RB`/`OVER`/`BYPASS`/`ALARM`/discharging, charge below 50 % (not charging), load 80 % or more,
  or runtime under 5 minutes → Degraded; `LB`/`FSD`/`OFF` → Failed. Server unreachable, unknown UPS or stale driver data →
  Unknown, never Failed.
- Re-detect lists the UPSes; Watch puts each in its own node in the **Power** group (not under the server that hosts NUT).

## UniFi (M4e)

Module `modules/unifi-network` (renamed from `unifi` in 0.2.0; old configs are migrated on read), standard library only. **Read-only**: one login POST (UniFi OS `/api/auth/login`, or a classic
controller's `/api/login`), then GETs of `stat/device` and `stat/health` only; the client refuses any other path and a test
fails if anything else ever reaches the controller. It never adopts, restarts, provisions or blocks anything.

- Connection: `{"id","module":"unifi-network","base_url":"https://192.168.77.1","username","password","site":"default","verify_tls":false}`.
  Use a **local read-only account**. The certificate is not verified by default because controllers are self-signed.
- Checks: `device` (`name` or `mac`, optional `min_uplink_mbps`; shows the wired uplink, i.e. the LAN topology), `devices`
  (roll-up of every adopted device, or `names`), `health` (`subsystem`: wan, lan, wlan, www, vpn).
- VPN tunnels: `tunnel` (`name`) checks one VPN client or site-to-site tunnel. Tunnels are **discovered, not configured**: the
  list comes from the controller's network settings (`rest/networkconf`, purposes `vpn-client` and `site-vpn`) and the live status from
  `v2/vpn/connections`, as the v3 module did. Re-detect lists whatever exists now; a removed tunnel reads Unknown. Connected → Healthy;
  disconnected or paused in UniFi → Failed; a controller that reports no status → Unknown. The coarse `health vpn` summary is no longer
  suggested (it said "error" while every tunnel was up).
- States: connected → Healthy; disconnected / inform error / adoption failed → Failed; upgrading, provisioning, heartbeat
  missed, pending, isolated, an uplink that is down or slower than `min_uplink_mbps` → Degraded. Controller unreachable,
  login refused, unknown device or site → Unknown, never Failed. A refused login is not retried for a minute so a wrong
  password cannot lock the account. An available firmware update is shown but is not a problem.
- Re-detect lists devices with their uplinks; Watch puts everything in one **UniFi** node in the **Network** group with rule
  `any` (one dead switch makes the node Degraded, not Failed). Suggestions may carry `rule` for the node they create.

## M5 decisions (owner, Oct 14; mockups reviewed)

- **Browser, phone and iPad are equals.** Every screen is built fluid and checked at phone width (390 px), tablet (768 px) and desktop; a browser test fails on sideways scrolling.
- **Main screen has two views, the owner's choice of default:** *Summarized* (one tile per group) and *Detailed* (each check on the page, tap for detail). The choice is per device (a phone and an iPad can differ), stored in the browser, switchable on the main screen and in Settings.
- **First launch detects the box itself** as well as the network: the gateway and DNS, and which services this machine offers (SNMP, NUT, Docker/Portainer and so on), so they can be offered as ready-made connections.
- **History is kept for 30 days and is part of backups** (graphs, status strip, last problem). Retention is fixed at 30 days for now.
- **Forms, not JSON:** add/edit a device as a form generated from the module's schema, with *Test connection* in plain words and an *Advanced: edit as JSON* escape. Reaching a device by MIB upload stays on the SNMP list.
- Build order: 5a Every-check view + preference (done) -> 5b connection forms with Test connection -> 5c history store + graphs + backup -> 5d *expected down* and Stop watching from the sidebar -> 5e first-run wizard with self-detection -> 5f settings hub.

## Web checks (M4f)

HTTP stays a **built-in check type** (no module: it needs no credentials and no device vocabulary).
`{"type":"http","url":"http://192.168.77.13:8989/","expect":[200],"insecure":true,"contains":"Sonarr"}`:
`expect` lists the allowed status codes (default 200 to 399; a login page answering 401 can be the healthy answer),
`insecure` skips certificate checks for self-signed LAN services, and `contains` (case-insensitive, first 256 KB) says
which app must be answering, so a login page or another app on the same port does not read as healthy.

## Watch in batches (Re-detect)

Suggestions carry an optional `batch` (Disks, Volumes, Interfaces, UPS, ...), `node` and `group`, and `system: true` for
internal mounts (hidden until asked for). The UI offers Watch all / Stop watching all per batch; the server applies a batch
in **one** saved revision (`POST /api/watch`, `/api/unwatch` with `items`).

## Servers, services and Test connection (M5b)

- **A server is a machine, found by its address; nothing in the saved files changes.** Settings > Servers groups the saved connections by address (and any system that has wake settings), so Monitor at .5 shows SNMP, battery backup and Wake on LAN together, and UniFi is a service of the machine at its address. Rename and address changes on a server's page are applied to all of its connections and to the one system that holds its checks.
- **Services are described by data:** `SVC` in `ui.py` lists each module's form fields (label, kind, when it shows). SNMP, UniFi and NUT have forms; the whole-file JSON editor stays under Advanced. Chosen over module-supplied schemas because it needs no module release; a module can supply its own later.
- **A server is saved when its first service is saved** (a name and address alone are not). Wake on LAN belongs to the server's system node; one is made with a ping check when the server has none, so a wake can be confirmed.
- **Names:** the name typed for a server is also what the main screen calls it (`add_watches` and `save_connections` apply it; renaming is skipped when a server's checks are spread over several systems).
- **Test connection** (`POST /api/connections/test`) runs the module's read-only `discover` with the settings typed in the form, before anything is saved. A secret still shown as dots is filled in from the saved copy of the same id; for an unsaved device it is refused. Errors are turned into plain sentences (`plain_error`) with the raw message under "Technical detail". No password is ever returned.
- Still to do in M5: the *Pick what to watch* screen (today it is the Re-detect list), MIB upload for SNMP, removing a server's checks together with the server.

### Pick what to watch (M5b4)

A checklist, not one button per item: tick what should appear, then Apply (one `watch` call and one `unwatch` call at most, so one saved revision each). Items already watched start ticked. The first time for a connection, everything except system items and the "Network interfaces" batch starts ticked, because devices have many interfaces nobody cares about (a gateway: just uptime, CPU and memory). Per-batch All/None.

### History (M5c)

`config/history.jsonl` keeps 30 days as state changes only (`{t, n, s}`), written by the monitor loop; a small `history.hb` heartbeat marks the last time the App ran, so a gap longer than 150 s reads Unknown for every node (never Healthy, never Failed). Pruning keeps the state each node was in when the window starts. It lives under `config/`, so config and full backups both carry it (tested with distinct values after the round trip). `GET /api/history?node=ID` returns segments, seconds per state, availability = (healthy+degraded)/(healthy+degraded+failed) with Unknown left out, and the outage count. The side panel shows a strip and a sentence per node. Graphs of numeric values (CPU, temperatures) are not stored yet.

The length shown in the side panel (1 hour, 1 day, 1 week, 1 month) is a per-device setting kept in the browser like the Summarized/Detailed switch; `GET /api/history?node=ID&seconds=N` clips to it (60 s up to the 30-day window). Storage is always 30 days.

### Expected down and Stop watching (M5d)

`monitoring.expectedDown` is a list of system ids (built-in checks included). The engine leaves every observed state alone and adds `expected` (marked) and `muted` (marked, or failing only because something marked is down) to each node. Muted nodes stay out of the banner, the attention list and the card tallies; a group where everything is muted shows as "Expected down"; a marked system that is actually up is just healthy. The same flag is what alerting (M7) will use to stay quiet. `POST /api/expected {id, expected}` sets it; `POST /api/stopwatching {id}` removes a system's checks, prunes `dependsOn`/`children`/`expectedDown` that pointed at it and drops a group left empty. Connections are never touched, so the system can be picked again from its server page. Built-in internet checks can be marked expected down but not removed here.

### First-run setup and box self-detection (M5e)

Right after the admin password is created the UI opens `#/setup` (also reachable from Settings > Servers > "Detect this box and my network"). `GET /api/thisbox` (`thisbox.py`, stdlib only) reports hostname, own address, default gateway (routing table), DNS servers (resolv.conf, loopback and IPv6 skipped) and which services answer on this box's own address: SNMP via one SNMPv3 engine-discovery message (no user, no community, so nothing is guessed; v2c-only agents show as "not seen" and can still be added by hand), NUT on 3493, Portainer on 9443/9000. It never uses the Docker socket and sends nothing to other machines. `POST /api/network {gateway, dns[]}` adds a `gateway` node (Network, critical), one `dns-<ip>` node per server and, with two or more, a `dns` aggregate (rule any); ids that exist are left alone, so repeating it changes nothing, and the built-in Internet nodes hang under `gateway` automatically. Found services hand over to the Servers page with a draft server for this box and the service form opened, where Test connection and Pick what to watch already exist. Portainer is only reported until M6.

### Settings hub (M5f)

`#/settings` is a landing page of six tiles, each with a one-line live summary: Display, Servers, What is watched, Backups, Updates and versions, This box. A tile opens `#/settings/<section>` (display, servers, watched, backups, updates, box); an unknown section shows the hub. The grid is fluid (one column on a phone, up to three on a desktop). Each page only contains its own elements, so code that updates the revision counters or JSON editors (`setRev`, `syncCfg`) checks that they are on screen first. Re-detect now lives inside Servers, next to "Pick what to watch", which is what fills it. The first-run setup hands over to `#/settings/servers`.

## M6a Portainer

Container visibility comes from Portainer's authenticated API, never the Docker socket (which is effectively root on the host).
One connection to the Portainer **server** covers every environment it manages (its own host and each agent); an agent has no
API of its own that MonitorBox uses. Setup tells them apart: a server answers its public status page, an agent only accepts
connections on port 9001, so an agent-only box gets a note pointing at its server.

- **Read-only.** The module sends GET requests only, to `/api/endpoints` and each environment's `docker/containers/json`.
  Anything else is refused in code. The token is sent as `X-API-Key`, is masked in the editor, and is never echoed in errors or logs.
  Portainer CE has no read-only role, so the token carries the rights of its Portainer user: use a dedicated user.
- **States.** Running, and healthy or without a health check: Healthy. `(unhealthy)` or restarting: Failed. Paused: Degraded.
  Exited, dead or created: Failed, unless the owner ticks "allow stopped". An environment Portainer reports down fails its
  environment check while its containers read Unknown. A missing container or environment, an unreachable Portainer or a refused
  token: Unknown, never Failed.
- **Shape.** Each environment becomes an "<Env> Portainer" node. Each container becomes a node "<Title> (<Env>)" in group
  Services that depends on its environment (`requires`) and carries `service` details (title, env, container, stack, icon, url)
  for the services list. Stacks are recorded in `service.stack` so the directory can collapse them.
- **Web checks.** For published ports that answer HTTP(S) the module also offers an `http` check on the same node, so a container
  that is up while its web page is broken shows as Degraded. A 401/403 counts as alive. These checks carry the `connection` so
  Pick, watching and removal treat them with the container. Off-site environments are included for now.
- **Pick.** Items are grouped by "<Env> · <stack>"; stopped containers are listed but not ticked.

## M6b Services directory

A **Services** button on the main screen (shown only when some node carries `service` details) opens a slide-over list like v3's.
It is drawn entirely in the browser from `/api/status`; no new endpoint.

- Grouped by server (`service.env`), sorted by title. Containers of a stack with two or more members fold into one row
  ("scrob · 2 services") whose dot is the worst member's state; tapping opens it. A stack of one is an ordinary row.
- Icon: the App serves its own bundled set from `app/monitorbox_app/icons/<name>.svg` (lifted from v3; see its NOTICE.md) at
  `/icons/<name>.svg`; nothing is fetched from the internet. An unknown name (or a failed load) shows an initials tile.
  Adding an icon means dropping an SVG in that folder. A few aliases (home-assistant, overseerr...) map to bundled names.
- Link: the icon and a ↗ button open `service.url` in a new window (`target=_blank rel="noopener noreferrer"`), only for http(s)
  urls. Tapping the rest of a row opens that service's checks and history.
- `service.icon` and `service.url` can be corrected in the monitoring JSON editor; edits survive re-adding from Pick.

## Brand and Pick by environment (0.23.0)

- **Brand.** MonitorBox's own mark is the v3 lighthouse, lifted unchanged from the v3 UI source (see `app/monitorbox_app/brand/NOTICE.md`).
  It is the header logo, `/favicon.svg` and `/favicon.ico`, the iPad home-screen icon (`/apple-touch-icon.png`) and the installable-app
  icons in `/manifest.webmanifest` (192, 512 and maskable 512). These routes are public because a browser asks before sign-in.
- **Pick groups by environment.** Suggestions that carry `env` (Portainer) are drawn under a top "Environments n of m" list, each
  collapsed and ticked as a whole; opening one shows its stacks and containers as before. The environment's own tick is its
  environment check: unticking clears everything inside it, ticking it restores the environment plus the running services.

### Publishing rule (learned the hard way)

Any change to files under `modules/<id>/` needs a bump of that module's `manifest.json` version in the same PR: the build refuses to
republish a version whose content differs ("already published with different content"), and then nothing is published at all,
including the App. The Publish dev job runs bash with `pipefail`, so that refusal turns the job red instead of being hidden.
After a merge, confirm `channels/dev.json` in the releases repo names the new App version.

## Dashboard: one fold per environment (0.25.0)

The Detailed Services card groups Portainer services by environment. Each environment is one collapsed row ("Bay Harbor - Anchor3 · 20 services · all good"); inside, services show their short title (no "(Env)" suffix), and a stack of two or more containers folds again. An environment with a problem opens by itself. Long names wrap onto a second line instead of truncating. Display only: node names, states and alerts are unchanged.

## One Services panel (0.25.1)

The Services card and the Services button in the header open the same side panel. It lists services by environment (with the environment's own status line first), folds multi-container stacks, and a tap on a row opens its history, checks and buttons right under it (the same detail block the other cards' panels use). Stack names get the same tidy-up as container names. The panel keeps its scroll position when the page redraws on a status update (it used to jump to the top).

## Services polish (0.26.0)

- The header Services button is gone; the Services card opens the one panel.
- Icons are picked by the page from `/icons/index.json` (the bundled names): the image name first, then the container, title and stack names, exact names before any word of a name. A stack row wears its app's icon. About 90 more homelab icons are bundled (same sources as before, see icons/NOTICE.md).
- A redraw keeps the side panel element and replaces only rows that changed, so icons no longer blink on each status update.
- Containers on the host network publish no ports, so the Portainer module (0.1.2) tries the app's usual web port (a short table) and offers the link only if something answers. A link can also be set or changed by hand on any service ("Set link", `/api/service-link`).
- Service lines drop "running" and "healthy" (the dot says it) and keep the uptime or the problem.

## Web pages by hand and admin links (0.27.0)

Settings > Servers > Add a web page watches any page: a server's admin console, a gateway login, an app that is not a container. It joins an existing system (one more check, so a dead page reads Degraded, not Down) or becomes a system of its own. Optional: the link to open if it differs from the address, text the page must contain, expected status codes, and trusting the device's own certificate (https only).

A system can carry a `link` (an admin page); the detail panel shows "Open" for it, and "Set link / Change link" works on any system, not only Portainer services (those keep their address in `service.url`). Endpoints: `/api/web-page`, `/api/service-link`.

## Pick polish (0.28.0)

- A service's link opens the app's own front page where that differs from the checked address (Plex `/web`, Pi-hole `/admin/`); the web check still tests the plain address. Edited links are never overwritten.
- Saved status lists are compact: `["200-399", 404]` instead of 200 numbers. The app reads both forms; the Portainer module is unchanged for this, so a newer module never hands an older app something it cannot read.
- Picking again saves a link or icon found for a service that is already watched (before, a Pick that added no new check saved nothing).

## An honest banner (0.29.0)

The headline says what is true:
- **Red, "Everything is fucked."**: something critical is down.
- **Red, "Something's down"**: something is actually down, but nothing critical depends on it. An actual down is red.
- **Yellow, "Something's not right"**: something answers, but not properly (degraded), and nothing is down.
- **Blue, "Something needs a look"**: MonitorBox cannot check something (unchanged).
- **Green**, with an optional quiet **Heads-up** line.

A check can carry a *notice*: "this is fine, but you may want to know". A module returns `{"state": "healthy", "notice": true}`; the App keeps it as a flag on the result (it never changes a state), shows the text amber on its row (the light stays green) and puts it in the Heads-up line under a green headline. The SNMP `resources` check uses it: a server running hot at 90% CPU is doing its job, not failing (SNMP module 0.1.4). A full disk, a UPS on battery and a link running below its expected speed are still degraded. An older App ignores the flag and simply shows the check as healthy.

Demo scenarios: green, headsup, yellow, down, blue, red.

## UniFi Protect (0.30.0)

Module `modules/unifi-protect` 0.1.0, standard library only. **Read-only**: one login POST (`/api/auth/login`), then GETs of the Protect `bootstrap` (the recorder and every camera) and one camera's
`snapshot`; the client refuses any other path, camera ids are checked before they go into a URL, and a test fails if anything else (or any PUT, PATCH or DELETE) ever reaches the console. No streams, no settings, no control.

- Connection: `{"id","module":"unifi-protect","base_url":"https://192.168.77.1","username","password","verify_tls":false}`. Use a **local user that can only view Protect**. Not verified against the real console yet: the field names follow the UniFi OS Protect API and are read defensively, so a missing field reads as "not reported", never as a failure.
- Checks: `camera` (`name`), `cameras` (roll-up, optional `names`), `nvr` (the recorder and its version), `storage` (recording space and disk health). Re-detect suggests all of them in one **Cameras** node (group Cameras, rule `any`, so one offline camera makes the node Degraded, not Failed).
- States: offline → Failed (the console itself says so); connecting, updating firmware, being adopted, or set to record all the time but not recording → Degraded. A camera set to record on motion is fine while idle, and "recording off" is the owner's choice. A recorder that is nearly full is **normal** (it overwrites the oldest video), so fullness is only shown; a disk that reports itself unhealthy is Failed. A console that cannot be reached, or a refused login, is Unknown, never Failed; a refused login is not retried for a minute.
- **Source-neutral camera shape.** The module also answers `cameras` (a list of `{id, name, model, state, detail, recording, lastSeen, motion, source, snapshot}`) and `snapshot` (`{id}` -> `{mime, data}` base64). Any later camera source (Scrypted) returns the same fields, so the App's Cameras view does not care where a camera comes from. The App's Cameras card uses them (below).

## Cameras card (0.31.0)

Tapping the **Cameras** card opens its panel with a picture of every camera above the usual health rows. `GET /api/cameras` asks every saved connection of a camera-source module (`App.CAMERA_SOURCES`, only `unifi-protect` now; Scrypted joins later) for its `cameras` and merges them; a source that fails is named in `errors` and does not hide the others. `GET /api/camera-snapshot?conn=&id=` asks that source's module for one picture and returns the image bytes; it only works for a saved camera source, and the module validates the camera id before it goes into a URL.

- Pictures refresh every 10 seconds while the panel is open and the tab is visible (in place, so nothing blinks); a camera the console reports offline is not asked for one and says "Offline" with when it was last seen. Tapping a picture makes it full width.
- Nothing is recorded or stored: a picture is fetched, shown and forgotten. Live video (WebRTC) and the all-cameras wall are separate, later pieces.

## Scrypted (0.32.0) and Update all

Module `modules/scrypted` 0.1.0, **Node** (Scrypted's official client library, `@scrypted/client`, is JavaScript and is the only supported way to read its cameras). The container image therefore carries the `node` binary (and nothing else of Node: no npm, no build tools); an image without it simply shows this module as "not running". The module ships its packages inside its archive: `tools/build_release.py` runs `npm ci --omit=dev --ignore-scripts --no-bin-links` from the module's `package-lock.json` at build time (same lock, same archive; `--skip-node-packages` is for tests). Versions are pinned to the ones the working MonitorBox 3 bridge used.

- **Read-only**: the module logs in, lists devices, reads a device's name, type, interfaces and online flag, and takes one picture (`takePicture`, converted to JPEG). It never starts a stream, sets anything or calls any other device method; a test with a fake client fails if anything else is ever called. A refused login is not retried for a minute; an unreachable Scrypted or a refused login is Unknown, never Failed.
- Connection: `{"id","module":"scrypted","host" or "base_url","port":10443,"username","password","verify_tls":false,"exclude":"names, separated by commas"}`. Use a Scrypted user that is **not an admin** and has only the Camera and VideoCamera interfaces of the cameras (MonitorBox 3 needed an admin because its restricted account had not been given those interfaces; whether a restricted account is enough is what Test connection now tells you in words).
- Checks: `server` (Scrypted answers and shows this account cameras), `cameras` (roll-up), `camera` (`name`; only a real `online: false` is offline, no flag is not). Re-detect suggests one **Scrypted** node in the **Cameras** group (0.1.1: the server and roll-up in an Overview batch, plus one tickable `Camera <name>` row per camera in a Cameras batch, like Protect, so you choose what to watch; exclusions apply). **Test connection** also takes one picture, so a limited account that can see cameras but not photograph them says exactly that.
- It answers the same source-neutral `cameras` and `snapshot` methods as Protect. `GET /api/cameras` now merges sources in a fixed preference order (`App.CAMERA_SOURCES`: Protect, then Scrypted); a camera two sources both report (same name) shows once, from the preferred source, with the other in `alsoIn`. Live video (WebRTC) is the next piece: the module already reports which cameras can stream (`live`).
- Test fake: the real client is not installable in the build sandbox, so tests use `tests/fake_scrypted_client.mjs`, written to follow exactly the calls the old, working bridge made.

**Update all** (Settings, Updates): when more than one update is waiting, one button installs the modules one after another and the App last (it restarts). `POST /api/apply-all`; one module failing does not stop the rest and the message says what happened.

### Side panel updates in place (0.32.1)

The side panel used to be swapped for a new element whenever any number in it changed (a check's response time, say), which is what made it blink and what made `test_the_drawer_is_not_rebuilt_under_a_scrolling_finger` pass or fail on timing alone (it passed about one run in four once more modules were installed). New content now goes into the same `.drawer` element, so the panel is never replaced, only its contents; the test also changes the content on purpose and requires the same element.

## Polish (0.32.3)

The network module now calls itself **UniFi Network** (0.2.1), matching UniFi Protect. A camera picture the person enlarged stays enlarged when the panel refreshes itself (the enlarged set is kept by connection and camera id, not on the element that gets redrawn).

## Backups copy each file once

`backup.create` copies every file once into a private snapshot (`backups/.tmp-snap-*`, removed afterwards) and takes both the checksum and the archive from that copy. Before, it hashed the live file and read it again for the archive, so a file the App rewrote in between (modules.json while modules update) gave a backup whose checksum did not match and restore refused it as damaged.

## Side panel changes only what changed (0.32.4)

Response times in the check rows change on every poll, so the panel's HTML differed every few seconds and was rebuilt (visible as a blink, and the camera pictures were re-created). `drawDrawer` now compares the new markup with the panel and changes only the text, attributes or elements that differ (`morphKids`), so unchanged parts, including the pictures, are the same elements as before.

## Camera pictures once a second, and a wider side panel (0.33.1)

- **Pictures** refresh about once a second per camera: the page asks for a camera's next picture one second after the last arrived, at most three at a time (`pollPics`), and swaps it in from a blob. **No connection is kept open per camera.** 0.33.0 tried a multipart stream per camera (`/api/camera-stream`), but a browser allows only about six connections to one host, so with more cameras than that most stayed blank; that route and its Pictures/Live switch were removed (this is why Live is not offered until real video exists: WebRTC through Scrypted, one shared setup channel for the whole page).
- **Wider panel**: a **Wider** / **Narrower** button (as wide as the screen) and a drag handle on the panel's left edge (pointer events, so touch works); the width is remembered. The picture grid's columns are `minmax(clamp(200px, 31%, 560px), 1fr)`, so the pictures grow with the panel.

## Live video through Scrypted (0.34.0, scrypted 0.2.0)

Live video is real WebRTC, the way MonitorBox 3 did it, and **MonitorBox never carries the video**: Scrypted and the browser connect to each other (ICE/DTLS/SRTP on the LAN); MonitorBox only passes the setup messages.

- **Module** (`modules/scrypted`): `live_open {connection, id, session, options}` finds the camera, requires the `RTCSignalingChannel` interface (otherwise a plain reason: give the Scrypted user that interface, view only) and calls `startRTCSignalingSession` with a session object whose `createLocalDescription` / `setRemoteDescription` / `addIceCandidate` are forwarded to the browser as unasked lines `{"event":"live","session","message":{"type":"call",...}}`; `live_input` carries the browser's answers (`result`, `candidate`); `live_close` calls `endSession`. 10 views at most, 30 s to start, 10 min per view (the page then starts it again). Read-only guard: the fake Scrypted in tests records every call and only login, reads, `takePicture` and the signaling session are allowed.
- **App**: `ModuleProcess` routes unasked `event` lines to whoever listened for that session id (`listen`); a module that dies ends its sessions. `GET /api/live/events?client=` is ONE server-sent-event channel per open page, shared by every camera (a browser allows only about six connections to this box, which is also why pictures are polled and not streamed); `POST /api/live/open`, `/api/live/input`, `/api/live/close`. Only Scrypted connections can go live; the channel closing (page closed, noticed within a second) ends its sessions. `/api/cameras` adds `liveVia {connection, id}` to a camera Scrypted can stream, even when Protect is the source shown, so Protect cameras that are also in Scrypted go live through Scrypted.
- **Page**: Pictures | Live switch (remembered), **Go live / Stop live** per camera in Pictures, in Live every camera Scrypted can stream goes live (the old 1 / 4 / All choice was removed in 0.34.2); cameras without Scrypted show snapshots. Views are started one at a time, 350 ms apart. A failed view says why under the camera and offers **Try live again**; the picture keeps showing. Live views stop while the page is hidden and when the panel closes. UniFi's own RTSP streams are not used: a browser cannot play RTSP, and Scrypted already turns it into WebRTC.
- `tests/test_ui_syntax.py` checks the page script parses (a duplicate name once blanked the whole page).

## The side panel is never taken out of the page (0.34.1)

`#dr` (the side panel) is a sibling of `#m` (the main page), not inside it. Before, every refresh of the main page removed the panel from the page and put it back, which stops a playing video, closes an open menu and made the cameras look like they refreshed every few seconds. Pages that take the whole window (Settings, Set up, login) call `mpage()`, which closes the panel first. History bars are only rewritten when their content changed.

## Snapshots, always-all live, no "not reported" text (0.34.2)

The camera panel switch reads **Snapshots / Live**. Live always starts every camera Scrypted can stream; the "Live at once" 1/4/All choice is gone (it worked, but All is what people use). A Scrypted camera that is listed and not reported offline is shown as "online": if Scrypted can hand over a snapshot or stream, the camera is up. Only a real `online: false` means offline.

## Restart a plugin, restart the App, factory reset (0.35.0)

- ~~**Restart one plugin** (`POST /api/modules/restart {id}`): the Modules table starts a fresh process of the active version and stops the old one. It logs in again, so new permissions or changed devices are seen. The App, other plugins and settings are untouched. Button: **Restart** beside each running plugin under Settings, Updates and versions.~~ Removed in 0.80.6: restarting MonitorBox is quick, so there is one restart button.
- **Restart MonitorBox** (`POST /api/app/restart`): the App exits with code 75 and the launcher starts it again. No launcher or image change.
- **Factory reset** (`POST /api/factory-reset {confirm:"RESET"}`): after the App has stopped it deletes everything in `config/` (settings, history) and the password, then the launcher starts it again at the setup screen. (Changed in 0.80.6: installed modules are now removed too, see below.) Installed software and `backups/` were kept on purpose: nothing needs downloading, and a mistake is undone by restoring a backup.

## First launch: password first, then start fresh or restore (0.36.0)

A box with no password asks for one, signs you in straight away (before, "Create" led to a second sign-in screen), and then shows **Start fresh** (the Set up page that looks at this box and its network) or **Restore a backup**. Restore needs you signed in like any other action; no endpoint is open without a password. A restore brings back settings and history but **keeps the password the box has now**: before asking the launcher to restore, the App copies `data/app/auth.json` to `auth.keep`, and puts it back at the next start.

There is no password recovery. Forgetting it means starting over, then restoring a backup or running the setup again. For someone locked out, a file named `factory-reset` in the config folder on the box does what the Factory reset button does (settings, history and password go; installed software and backups stay) when the App next starts, so it needs access to the box itself.

Next (not built): the guided discovery cascade, where each login you give reveals more things to tick, and a Discoveries inbox for things that appear later.

## Third-party plugins: decisions so far (design only, nothing built)

- Plugins may reach devices themselves (a Cisco plugin instead of UniFi). The owner approves each plugin at install and sees what it asks to reach; users carry responsibility for what they install. There is no review or "verified" programme.
- **Authors host their own plugins** (their own repository, site or release page). MonitorBox's repositories do not host or store third-party code. A plugin is installed from a URL plus a checksum; MonitorBox shows both before installing, pins the version, and never updates it silently.
- Still to settle: the permission declaration (hosts/ports it may reach, which connection secrets it receives), process isolation so a plugin sees only its own connection's secrets, and the plugin interface staying read-only by construction.

## Found more you can add: the first discovery cascade (0.37.0)

`GET /api/followups` proposes what follows from what is already connected (`followups.py`; nothing here is a network scan):

- **UniFi Network -> Protect**: a UniFi console usually runs Protect on the same address with the same login. One tap (`POST /api/followups/add`) copies the address and login on the box (the secret never reaches the browser), saves the new connection, reads it, and watches everything the module suggests by default (the cameras and the recorder). The connection gets its own id and the original is untouched.
- **Declared server answering on Scrypted's port (10443) -> Scrypted**: one plain TCP connect to that one port on addresses you have already declared. Scrypted needs a login of its own, so this proposal opens the Add-a-server form with the address filled in.

The proposals appear on the Set up page and at the bottom of Settings, Servers, and disappear once added. Next in the cascade: Portainer environments to servers, and more modules' follow-ups, using the same list.

## Portainer feeds the cascade, and a Discoveries count (0.38.0)

- **Portainer -> Scrypted / UniFi Network**: the portainer module's discover result (the container list Portainer already gives) is read for containers whose image or name is Scrypted or UniFi; the proposal uses the address the container answers on (else its environment's address) and opens the Add-a-server form. Portainer is asked in the background (up to 40 s) and cached ten minutes; until it has answered `GET /api/followups` says `pending: true` and the page asks again every 3 s. A Portainer evidence proposal replaces an open-port one for the same address.
- **Discoveries count**: the main screen's top bar shows **Discoveries N** whenever something can be added; it opens Settings, Servers, where the "Found more you can add" box lists them. The count refreshes after sign-in and every ten minutes. Nothing is ever added without a tap.
- **Not now** (`POST /api/followups/dismiss`) hides a proposal for good (`config/dismissed-followups.json`, so it is in backups and cleared by a factory reset).

## Set up is a guided page with a way back (0.39.0)

Found when the owner tested a fresh box: Set up only knew this box, each "Set up" dropped you on the Servers page with no clear way back, and other servers (Anchor3, Granite) and UniFi, Portainer or Scrypted were never offered.

- **Set up page**: This box (named from the machine's own hostname) -> **Your other servers** (name + address, then `GET /api/thisbox?host=` looks at that machine: SNMP v3 answer, NUT, Portainer, Scrypted's port, a UniFi console's front page, and its MAC from the ARP table for Wake on LAN) -> Your network (the gateway is fingerprinted too, so a UniFi gateway offers UniFi Network) -> Found more you can add -> Finish. Servers added here are remembered for the visit (session storage) and any server that already has a connection is listed and looked at too; a service that is already connected reads "set up".
- **Way back**: opening a form from Set up shows **Back to Set up** at the top of the Servers page until you leave it; coming back reloads the page so finished items show as set up. The MAC found is prefilled when you choose Wake on LAN.
- Scan results: Scrypted, UniFi Network and UniFi Protect only appear when found. Probing stays bounded: only addresses the person typed or already connected, one connect or one GET each. The look is parallel, so a machine takes a couple of seconds.
- **Display settings** (Summarized/Detailed, history length, panel width) live in each browser, not in backups; they are not restored by either kind of backup.

## Last step of setup: "Did we miss anything?" (0.40.0)

Set up now ends with **Finish: did we miss anything?** (`#/setup/review`): a summary of every server and what is connected to it, then every kind of connection (SNMP, battery backup, Portainer, UniFi Network, UniFi Protect, Scrypted, and a web page) with an **Add** button. Choosing one asks **which server is it on** (any known server, or another address with a name), opens that server's form with **Back to the review** on top, and returns to the review so the new connection shows. **Open the main screen** ends setup. Everything here is also available later under Settings, Servers.

## One-page inline setup (0.41.0)

Set up (`#/setup`) is one page and never navigates away. Each server (this box first, then any added by address) is a card; a scan row (SNMP, NUT, Portainer, Scrypted, UniFi...) has **Set up/Edit**, which opens the same form and pick list the Servers page uses *in place* under that row (`inlineOpen`, one editor `#ied` at a time, state in `window._inline`). Saving and picking write immediately; **Done** (or finishing a form) closes it and the card shows what is set up. A server with everything done folds to one line with **Edit**. UniFi Network offers Protect with "same login" (`followups/add`, `protect:<id>`). Each card has by-hand extras: ping an address (`POST /api/ping`, bound to the server's node), watch a web page, or any other connection kind. An "Add a server" box scans a new address (`GET /api/thisbox?host=`); Portainer environments are proposed as servers (`kind:"server"` follow-ups). **Save and finish** opens the read-only summary (`#/setup/review`) with **Edit** (back) and **Save and launch** (main screen). The Servers page will adopt the same card later (uniformity pass).

## Setup fixes after the first real run (0.41.1)

The owner's run of 0.41.0 on the Pi found: Add with the same login failed after an earlier "Not now" (an explicit Add now ignores dismissals); Apply and Done were two buttons (one now); "Add anyway" was offered for services that were not seen (not-seen rows are hidden, except a plain note such as the Portainer agent one); Scrypted showed twice and a watchtower container was taken for Scrypted (the Set up page no longer repeats what a server's card already shows; `watchtower` containers are skipped); Set up on a Portainer-proposed server navigated away (it now adds the server card in place); the Add-a-server box moved below Your network and every card has an editable name (a reverse lookup fills it when it can); the scan now also finds a machine's own web page on 443 or 80 and offers to watch it (`web` row, `Watch it`); and the gateway is no longer listed as a server (it is under Your network). The pick list shows each interface's status and speed and each volume's use beside its tick. Picking several things from one device used to make one system per check when the device had no ping check; they now share one system, and an install that already has the split is folded on the next Apply.

## Every server starts with a reachability check (0.41.2)

`POST /api/server {name, host}` (`monconfig.ensure_server`) creates the server's system with a ping check first, or a TCP check on the first usual port that answers when the machine ignores pings (22, 80, 443, 9443, 9000, 3493, 161, 10443). A server that already has a ping or TCP check on its address is left alone. The Set up page calls it for this box and for each server it adds; everything picked afterwards joins that system. Renaming a server card renames its system.

## Setup flow order and the Protect fix (0.41.3)

Set up now reads top to bottom: **Your network** (folds to one line once watched and its UniFi console is set up; Edit reopens it), **Your servers** (each folds when done), what was **found** from them (servers Portainer manages and so on; a proposal for a machine that also has a server proposal is dropped, since adding the server scans it), **Add another server**, then Save and finish. Fixes: the UniFi forms save the console as `host`, which the Protect proposal ignored (it only looked for `base_url`), so "Add with the same login" always said "no longer available"; the Protect copy now carries `host`. Secret fields are drawn as dots in a plain text box so Safari does not offer a strong password; the pick step has a single Save. SNMP's detect answer carries `sysName`, which names a server that was added by address (only when no name was typed or found).

## A system can hold 300 checks (0.41.4)

Picking everything on a NAS (63 shared folders, disks, ports) plus its ping went over the old 60-checks-per-system limit once all of a server's checks were kept in one system, and Apply failed with "needs 1 to 60 checks". The limit is now 300 (`MAX_CHECKS`).

## Server names stick (0.41.5)

A name typed on a server card is saved to the server's connections, its system on the main screen and the Set up memory (before, only the last was updated, and the connections' old name won on the next load, so the name went back to the address). The card shows the saved name, else the system's, else the connection's. `/api/detect` for SNMP returns `sysName`; when the installed SNMP module is older and does not report it, the App reads it from the uptime check's text ("Granite: up 3d…"). A server that is still called by its address takes that name automatically once SNMP answers.

## Display choices live on the box (0.42.0)

The main screen view (Summarized/Detailed), the history window, the side-panel width and the camera mode are saved in `config/display.json` (`GET/POST /api/display`, validated), so every backup, config or full, carries them and a restore brings them back. Each browser still keeps its own choice in its local storage (a phone and an iPad can differ); a browser that has never chosen starts from the box's. Changing a choice saves it to the box a moment later.

## Choosing the update channel on a new box (0.42.1)

The welcome page (right after the password) now asks which updates the box should follow: Stable, Beta or Dev, with the box's current channel ticked (it comes from the image's `MB_CHANNEL`, default dev). The choice uses the same `POST /api/channel` as Settings, Updates. A restored backup brings back its own choice.

## Edge agents and the agent note (0.42.2)

Portainer edge agents call the server, so they have no address. The Portainer module (0.1.4) no longer borrows the Portainer server's own address for them (it used to look for web pages there); their environments carry `edge: true` and an empty address, and their containers are still listed through Portainer. Edge agents are not offered as servers; the Set up page says Portainer manages them. On a box that runs a Portainer agent, once a Portainer server is connected the note says it is managed by that server and already covered. Not tested against a real edge agent (the owner runs none); the fake Portainer covers the shape.

## 0.42.3: attention list names the failing check

When a system has several checks, each "Needs attention" row now says which check is the problem ("Disk 2: 99% full") instead of only the system name. One-check systems read as before. The Services tile already lists which services are down, so it is unchanged.

## 0.42.4: removing a server removes its checks

Settings → Servers → Remove this server now stops watching each of the server's systems first (the same call as "Stop watching"), then deletes its connections and wake settings. Before, it refused while anything was still watched. Other servers are untouched.

## 0.42.5: earlier heads-ups

Two quiet lines under the green headline, neither changes a state. A volume at 75% used or more says so before the existing 85% (degraded) and 95% (failed) lines (`notice` parameter, default 75). A ping that answers at 200 ms or slower three times in a row says the link is slow (`slow_ms` on the check). A UPS on battery already turns its system yellow, so it has no extra heads-up. SNMP module 0.1.7.

## 0.43.0: Settings → Servers opens in place

A server on Settings → Servers now expands inside the list (Open / Close), like the cards on Set up, instead of switching to a separate page. The expanded card holds name and address, its services, Add buttons and Remove. Editing a service or wake settings still takes over the panel and returns to the list with the card open. A server that is not saved yet (Add a server → Next) still uses its own page with a back button. `serverBody(x)` builds the card contents for both. The old "‹ All servers" button is now "Close" on the card; the browser test was updated for that rename only.

## 0.43.1: Servers page actions

Add a server, Add a web page and Rescan all servers sit in their own block under the list (a divider, so they no longer read as part of the last server). "Detect this box and my network" became Rescan all servers, and each open server has Rescan this server. A rescan forgets what Set up saw, tells Set up about the servers (it remembers them in the browser session) and opens Set up, which looks again; Rescan this server scrolls to that server's card. The Re-detect box is gone: Pick what to watch already does that job, and the hidden connection id it uses stays in the page. Two browser tests that typed a connection id into the Re-detect box now start from the same place Pick what to watch does.

## 0.44.0: throughput graphs (first slice)

**What the owner sees.** Settings → Graphs lists the graphs on the main screen and adds one by choosing an SNMP server, then one of its interfaces (name, up/down, speed). Rename, reorder and remove are there too. The main screen shows a Traffic strip under the tiles: one card per graph, download (green) and upload (blue), with 1 min / 5 min / 15 min / 1 hour. Everything saves at once.

**How it works.** The SNMP module (0.2.0) has a `sample` method that reads raw octet counters by interface *name* (64-bit counters, 32-bit as a fallback). It keeps nothing. `graphs.py` in the App turns two readings into bits per second (rollover of 32-bit counters counted, a counter reset skipped), keeps the last hour in memory, and sets the pace: one reading a second while a browser has asked for `/api/graphs/data` in the last 15 s, every 10 s otherwise. The list lives in `config/graphs.json`, so backups carry it (round-trip test with distinct values). Up to 12 graphs. A history older than the last hour, and anything before a restart, is not kept: the graphs start filling again after a restart.

**Not in this slice.** The busiest-client graph (needs the UniFi client list), UniFi-only WAN counters (the gateway is read over SNMP like the servers), client-to-client traffic (ticket #127), longer history.

## 0.44.1: graph scale and names

The top of a traffic graph is the interface's rated speed (ifHighSpeed, carried by the module's `sample` answer, SNMP module 0.2.1), with the half-way and zero marks down the left edge and "N ago" / "live" under it. If traffic ever passes the rating (a bond that reports one member's speed), the top grows to fit. A device that reports no speed falls back to a rounded top. The server picker in Settings → Graphs shows the name the main screen uses, not the connection's internal id.

## 0.44.2: the gateway's WAN port in the graph picker

SNMP lists every interface of a UniFi gateway but cannot say which is the WAN. The UniFi Network module (0.2.2) has a `wan_ports` method that reads `stat/device` and returns the WAN interface names (the `wan1`/`wan2` blocks and WAN-named ports in the port table, merged by interface name). `POST /api/graphs/wan {connection}` finds the UniFi Network login on the same address as the SNMP connection and asks it. Settings → Graphs then shows those interfaces first with a blue WAN tag and the public IP, and suggests the name "WAN <interface>". With no UniFi login on that address nothing is tagged. The field names follow UniFi's documented device JSON and are covered by the fake controller; the first real gateway is the real check.

## 0.44.3: WAN tag and a top speed the owner can set

The WAN tag now reads "WAN" / "WAN 2" (UniFi names the port after its interface, which repeated the name beside it). `wan_ports` also returns the speed the link negotiated (UniFi module 0.2.3). A port's rated speed is often more than the line behind it (an SFP+ port rated 10 Gbit/s, negotiated at 5, on a 2.5 Gbit/s fibre plan), so each graph can carry an optional `maxMbps` that sets the top of the graph. Settings → Graphs has a Top speed button per graph (empty goes back to the link's own speed); adding a WAN graph asks once for the plan speed, prefilled with what the port negotiated. The value is a whole number from 1 to 1,000,000 and is refused otherwise.

## 0.44.4: memory

The owner saw 372 MB against the 200 to 256 MB goal. Two causes. (1) The "memory in use" number was the container's cgroup `memory.current`, which also counts the kernel's file cache (logs, module files, backups). That cache is given back whenever something else needs memory, so it is not use. The number now subtracts it (`sysinfo.py`, `cacheMb` is reported too). (2) Every installed module started with the App, each a Python interpreter of 11 to 22 MB, plus the Node bridge for Scrypted at about 44 MB. Now only modules that a saved connection uses start with the App (`Modules.wanted`); any other starts the first time a check, call or live view asks for it (`_revive`), and the Versions page shows it as "idle until something uses it". A module that is installed or updated still starts at once. If the config cannot be read, everything starts as before.

## 0.45.0: alerts, first slice (Home Assistant webhook)

Design decisions from the owner: alert on **Failed and Degraded only** (not Unknown, not heads-up notices); each site's box alerts on its own; the off-site box also watches the main site, so a dead main site still gets reported (a later slice). Home Assistant first; the sender is one function, so email and ntfy can be added beside it. A user without Home Assistant would use email.

`alerts.py` reads the engine's own `attention` list, so the rules stay in one place: one alert per root cause, nothing for expected-down or muted nodes, nothing for things that only fail because a dependency does. A problem is sent after it has lasted `delaySeconds` (default 60, 0 to 3600); it is followed by one "back" message after 30 s of staying healthy. Degraded to down (or back) while open sends an update. Unknown never alerts and never counts as an all-clear: a node that goes Unknown while open keeps its alert open. Turning alerts off forgets open alerts, so turning them on announces whatever is wrong at that moment.

Delivery: `POST` JSON to the Home Assistant webhook (`title`, `message`, `event` = problem | recovered | test, `state`, `name`, `group`, `site`, `critical`, `detail`, `at`). A failed delivery is retried (5 s, 15 s, 45 s, up to 5 minutes apart) for 30 minutes and the Alerts screen shows the last result in plain words. Home Assistant answers 200 even when no automation listens on a webhook id, so the Test button can only say "Home Assistant accepted it". Open alerts and undelivered messages live in `config/alerts-state.json`, so a restart or update neither repeats a problem nor loses a waiting message. Settings are in `config/alerts.json` (mode 0600; backups carry both). The webhook address works like a password: it is never returned by the API (only whether it is set and its host:port), never logged, and never put in an error message. A missing webhook in a save keeps the stored one. Alerts read the live monitor snapshot, never the demo scenario.

API: `GET /api/alerts`, `POST /api/alerts {enabled, site, delaySeconds, homeAssistant:{webhook}}`, `POST /api/alerts/test`. UI: Settings → Alerts. Site name defaults to the host name.

Known gaps, in the order we plan to close them: (1) the off-site box watching the main site and the main box watching it back, with a heartbeat, so a dead MonitorBox or a dead site is reported by the other; (2) a second sender (email) used when the first cannot deliver, which is the answer to "Home Assistant itself is down"; (3) reminders and quiet hours.

## 0.45.1: Alerts screen follow-ups

Changes the owner asked for after trying 0.45.0. The webhook address is now shown to the signed-in owner in a plain text box (the earlier "never returned by the API" rule is dropped: hiding it made typos impossible to spot; it is still never logged or put in an error message, and the file stays mode 0600). The screen follows the order of use: 1 address, 2 test, 3 turn alerts on (disabled until an address is saved), then site name and delay. The test button saves a changed address first, so it always tests what is on screen. The number input had no dark style (white text on white); number inputs now share the other inputs' style. The long example address no longer pushes the page wider than a phone. The success message of the test says where to look (the automation's Traces in Home Assistant) when nothing reaches the phone.

Several phones: MonitorBox sends one message to Home Assistant and Home Assistant decides who gets it. The automation lists one notify action per device (each with `continue_on_error: true` so an offline device does not stop the others). MonitorBox does not read Home Assistant's device list; that would need a Home Assistant access token and adds nothing the automation does not already do.

## 0.45.2: a trailing space in the pasted address

The first real test alert was accepted by Home Assistant but never ran the automation: the address saved from the iPad ended in `%20` (a pasted trailing space written out as letters), which made it a different webhook ID. Home Assistant answers 200 to any webhook ID, so nothing showed as an error. Saving now drops trailing whitespace and trailing `%20` (`alerts._clean_url`), with a regression test.

## 0.46.0: alerts through a Home Assistant account

The setup the owner asked for: make a user in Home Assistant, give it to MonitorBox, MonitorBox does the rest. No automation, no webhook id, no YAML.

`ha.py` is the whole Home Assistant client and asks Home Assistant for exactly two things: `GET /api/services` (the phones and tablets that have the Home Assistant app show up as `notify.mobile_app_<device>`) and `POST /api/services/notify/<device>`. A device name must start with `mobile_app_` and be plain letters, digits and underscores, so no other service can be named; the "monitoring is read-only, nothing is controlled" rule is kept by this code. (A Home Assistant user token can itself do more, and Home Assistant only partly limits non-admin users, so the guide asks for a user made only for MonitorBox, not an administrator, set to "Can only log in from the local network". The owner can remove its sign-in in that user's profile at any time.)

Signing in uses Home Assistant's documented OAuth page flow. Connect sends the browser to `<ha>/auth/authorize` with `client_id` = MonitorBox's own address (taken from the browser's `Origin`) and `redirect_uri` = `<origin>/ha-callback`; the owner signs in on Home Assistant's own page as the MonitorBox user; Home Assistant sends the browser back to `/ha-callback?code=…&state=…`; MonitorBox trades the code at `POST /auth/token` and keeps only the refresh token. The password is never typed into or stored by MonitorBox. Access tokens (30 minutes) live in memory, are renewed a minute early, and are renewed once on a 401. The callback is public because the browser arrives from another address without a session cookie (SameSite=Strict); the random one-time `state`, created by the signed-in owner's Connect and valid ten minutes, is the proof. The page it returns then moves the browser on to `/#/settings/alerts` from MonitorBox's own page, so the session cookie is sent again. A long-lived token pasted by the owner is the fallback (not renewed, never shown back). Restoring a backup onto a box with a different address cannot reuse the refresh token (its client id no longer matches): the screen then says "Home Assistant no longer accepts MonitorBox's sign-in" with a Connect again button; the ticked devices are kept.

All phones and tablets start ticked; the owner unticks the ones that should not get alerts (`POST /api/alerts/ha/devices`). A message goes to every ticked device; a device that fails (removed in Home Assistant, offline) is named in the plain-language error and only that device is retried, so the others never get it twice. A sign-in that stopped working keeps the messages waiting (30 minutes) and shows Connect again. Message content: `title`, `message`, a `tag` per system (the "back" message replaces the "down" one on the phone), and for Down only `push.interruption-level: time-sensitive`, `ttl: 0`, `priority: high`. Degraded and "back" are normal priority. Critical alerts (which override silent mode) are not used.

The webhook from 0.45 still works and is used only while Home Assistant is not connected. Disconnect revokes the refresh token at Home Assistant (best effort) and forgets everything; alerts turn themselves off when the last way to send is removed. Routes: `POST /api/alerts/ha/begin`, `GET /ha-callback`, `GET|POST /api/alerts/ha/devices`, `POST /api/alerts/ha/token`, `POST /api/alerts/ha/disconnect`. Tests use `tests/ha_fake.py`, a stand-in Home Assistant (sign-in redirect, token, services, notify) with fake credentials, in unit tests and in a browser test of the whole Connect, tick, test, expire, Disconnect round trip.

## 0.47.0: sites (slice 1: pairing and pass-through)

Several MonitorBoxes, one pane of glass, like Portainer's environments. Every site runs a full MonitorBox, so each keeps working and alerting if the others go dark. One box (the main one) is paired to the others and manages them; **control only goes one way**: the main box holds a key for each site it manages, a managed box holds no key to the main one, and it cannot be told to pair or manage anything else (`sites*`, `site/*` are never passed on, so there is no chaining or loop-back). Sign-in/setup/logout and the long-lived streams (`stream`, `live/*`) are not passed either (slice 4 will do live video and graphs properly).

**Transport (`peer.py`).** A separate *site port* (default 8443, off until enabled) so that only one port is forwarded on a router and the box works over a public address or DDNS name as well as over a VPN; nothing assumes the other site's gateway can be pinged. It speaks TLS 1.2 with a pre-shared key (Python 3.13 `ssl` TLS-PSK, cipher `PSK`, ECDHE-PSK in practice): no certificates, no openssl, no new dependency, no image change, forward secrecy. A visitor without a key fails the handshake and gets nothing. Failed handshakes are counted per address; ten in a minute shut that address out for ten minutes. The PSK server callback gets the identity and returns the key (empty bytes refuses); identity is not exposed on the socket, so it is kept in a thread-local during the handshake and attached to the connection.

**Pairing.** The box to be managed shows a one-time 25-character code (about 125 bits, ten minutes, one use even if the attempt fails) under identity `pair`. The main box connects with it and calls `POST /peer/pair`; the managed box makes a manager id and a random 256-bit key, returns them, and the code is dead. Afterwards the main box connects as identity `m:<id>` with the long-term key. "Remove" on the main side tells the managed box to forget it (`/peer/bye`); the managed box can also cut a manager off at any time (it then sees "pair the sites again", state `refused`). Keys are in `config/sites.json` (mode 0600, inside the backup, never returned by an API).

**Pass-through.** The main box's `/api/site/<id>/<rest>` (GET and POST, body streamed) becomes `/peer/api/<rest>` on the managed box, which repeats it against its own API on loopback with an internal session token and `X-MB`, as if its owner were signed in. A site that cannot be reached answers 502 `{unreachable:true}`; the UI treats that as *Unknown*, never as a failed check.

**Link state.** A poller asks every paired site for `/peer/hello` and `/peer/api/status` every 10 s and keeps `{state: linked|unknown|refused, error, lastSeen, version, banner}`. Not answering is "unknown, last heard N min ago", not down.

Settings → Sites: name of this site, sites managed from here (add with address + code, rename, remove), "Let a main MonitorBox manage this one" (site port on/off, port, code, who manages it, stop being managed). Tests: `tests/test_sites.py` (two real Apps: pairing, single-use code, private keys, pass-through read and write, blocked paths, strangers and wrong keys, lockout, revocation, dead site, bad input, the Settings page at 420 px) and the backup round trip in `test_backup_e2e.py`. Next: site tabs and the "All sites" line (slice 2), mutual TCP watching of the site port (slice 3).

## 0.48.0: site tabs and the "All sites" line (slice 2)

When at least one site is paired, a tab row sits above every screen: this box first, then each paired site, each with a dot in its banner colour (grey = unknown). Picking a tab sets `SITE` (kept per device in localStorage); `api()` then sends everything except `health|state|display|sites|login|logout|setup` to `/api/site/<id>/…`, so Servers, Graphs, Alerts, Backups, Updates, Settings and the rest are that site's own. The main screen of a remote site polls `status` every 3 s instead of the event stream (streams are not passed through). Snapshot URLs, camera snapshots and backup upload/download go through the same prefix. Not yet across sites: live camera video (cameras show snapshots) and Settings → Sites (hidden on a remote tab).

The "All sites" line is the worst of every tab, built from the link poller's banners (refreshed every 10 s): "All sites are fine", or each site that needs attention with its headline. A site that does not answer is shown as "Unknown · last heard N min ago" and its screen says "<site> is not answering from here … keeps running and alerting on its own", never as down or failed. Test: `test_sites.Sites.test_tabs_show_each_site_and_a_silent_site_is_unknown_never_down` (two real Apps, 420 px browser).

## 0.48.1: sites need a name

The first tabs showed computer names (Monitor, Aurora) because a site's name defaulted to its hostname. Starting a pairing and adding a site now both require the site to be named (Settings → Sites, "Name of this site"; the page saves what is typed when the buttons are pressed), so the tabs, "Managed by …" and the "All sites" line use the owner's names. A box with no name still shows its computer name until it is named.
## unifi-network 0.2.4: what UniFi's Internet verdict is based on

The first Tidewater install showed `UniFi Internet: Internet warning · 0 ms` (Degraded) while UniFi's own screen showed the line healthy. MonitorBox only relays the controller's `www` health status, so the check now also lists the fields that verdict is built from (drops, uptime, speed-test state and any other plain fields, never MACs, addresses or traffic counters) to show why they disagree. The state mapping is unchanged until we know what the controller reports.

## unifi-network 0.2.5: a summary with nothing behind it is Unknown

Tidewater's UniFi Internet check stayed Degraded (`Internet warning · 0 ms · drops 3 · uptime 0 · speedtest ping 0`) for an hour after its cause, a failing SLA ping target, was removed and UniFi's own screens showed Passing; MonitorBox's own Internet checks were fine throughout. UniFi's old `www` health summary was stale. A `warning` with neither latency nor uptime is now Unknown (shown, never degrades the banner or alerts), with UniFi's words kept in the detail. A warning with latency or uptime behind it still counts and `error` is never softened; a real outage still fails the WAN, ping and DNS checks. Cost: a lone failing SLA target now reads as Unknown here rather than Degraded.

## 0.48.2: switching site tabs forgets the other site's screens

The page kept what it had fetched (the graph list, alert settings, camera list, setup data) in globals and only loaded the graph list once, so after a tab switch the main screen showed the previous site's graphs and a site's graph list could be saved over the other's. `setSite` now clears all of it, so each tab loads its own. Regression test: `test_each_sites_graphs_stay_its_own_when_switching_tabs`.

## 0.48.3: Unknown does not force a roll-up open

A roll-up line ("16 of 17 good · 1 need a look") opened by itself for anything not healthy, so one Unknown line (UniFi's Internet summary with nothing behind it, a site-to-site tunnel UniFi does not report) kept a whole card expanded on a green board. It now opens by itself only for Failed or Degraded; Unknown is still counted in the roll-up text and opens on tap.

## 0.49.0: live camera video across sites (over a route the browser can use)

The Tidewater tab can now go live. The live setup channel (`GET live/events`, an event stream) and `live/open|input|close` are passed through like every other call (`peer.BLOCKED` no longer lists `live/`); the page sends them to `/api/site/<id>/live/…` (`livePost` and the event stream use `U()`), and switching tabs first stops every live view and closes the channel (`liveReset`), so a view never talks to the wrong site. A response of unknown length (an event stream) is relayed as it arrives, and the relay ends within a second of whoever asked going away (`peer.relay`, `client_gone`; http.client hands its socket to a close-delimited response, so the 1 s timeout is set through `resp.fp.raw`), which closes the channel on the managed box. Test: `test_the_live_camera_channel_passes_through_and_ends_with_the_page`.

**What this does and does not cover.** Only the setup messages (the WebRTC offer, answer and candidates) travel over the site link. The video itself still goes straight between the browser and Scrypted at the managed site, so it works when the browser can reach that Scrypted by UDP: over the site-to-site VPN, yes; over a public address with only the site port forwarded, no. For that case the next piece relays the media over the site link (a UDP relay with the candidates rewritten), which is not built yet; until then a view that cannot connect fails with the usual plain reason and the camera keeps showing snapshots.

## unifi-network 0.2.6: Internet check falls back to the gateway

When UniFi's legacy Internet summary (`stat/health` www) says `warning` with no latency and no uptime, the check now reads the gateway's own WAN blocks (`wan1`/`wan2` up, `uptime_stats` latency), which is what UniFi's current screens use. Any WAN up is healthy, every WAN down is failed, no gateway data stays Unknown. UniFi's own words stay in the detail. A real `error` from UniFi is never softened.

## 0.49.1: removing a group takes the systems inside it

Renaming a Portainer environment leaves its old group ("local") and the systems under it watching an environment that no longer exists, and a connection that checks still use cannot be removed. "Stop watching" on a group now offers to remove the group and every system inside it (`/api/stopwatching` with `children: true`, `remove_node(..., with_children=True)`). Connections stay.

## 0.49.2: "Remove all" on an environment in the Services list

0.49.1's group removal had no button where the stale Portainer environment is actually shown. The Services list now has **Remove all** on each environment heading. It stops watching the environment's systems one by one (a group left empty goes by itself).

## 0.49.3: removing a service always works

"Remove this service" (and "Remove this server") used to refuse while any check still used the connection, so a broken service could not be removed and set up again. `POST /api/config/connection/remove` (`monconfig.remove_connection`) now removes the connection and the checks that use it in one go. A system left with no checks goes with them, and so does a group left empty. The JSON editor still refuses to orphan checks, because there the person is editing by hand.

## 0.49.4: saving a Portainer connection cleans up environments that are gone

Saving an edited Portainer connection re-reads its environments (`/api/detect`). If systems are watched under an environment Portainer no longer has (renamed or deleted), the page asks once and stops watching them. A failed or empty look never removes anything, so a Portainer outage still means Unknown, not a clean-up.

## 0.50.0: live video from a managed site travels through the site link

Before, a page on the main box (Bay Harbor) showing a managed site's (Tidewater's) cameras still had its video flow straight between the browser and Scrypted, which needs the browser to reach Scrypted: fine over a site-to-site VPN, not over a router port map. Now the video is relayed:

- Browser <-> a UDP port on the main box <-> a raw stream inside the TLS-PSK site link (an upgraded `GET /peer/udp?s=<view id>`, each packet framed with a 2-byte length) <-> a UDP port on the managed box <-> Scrypted. Only the site port needs forwarding. The packets are STUN, DTLS and SRTP belonging to the browser and Scrypted, and are never read or changed, so the video stays encrypted end to end.
- Setup messages are rewritten so each end only learns a relay address: the managed box (`live_open(relay=True)`, asked for only by a managing box) strips Scrypted's ICE candidates from what goes to the browser (answering Scrypted's `addIceCandidate` calls itself) and puts its relay port in what goes to Scrypted; the main box puts its own relay port into the SDP it hands the browser (`relay_events`). One transport (BUNDLE) is assumed.
- The managed box aims its relay at Scrypted's own address from the candidates Scrypted offered (the one at the connection's host if there is one) and corrects it from the first STUN packet that arrives. The main box learns the browser's address from the first packet.
- The relay is always used for a managed site's cameras (one route to test, the same on a VPN and a WAN). A managed box too old to know about relays answers without `relay`, and the view is then direct as in 0.49.
- Cost: each view's video passes through both boxes, a few Mbit/s a view, up to the existing 10 views.
- Bug fixed on the way: the relayed event stream of 0.49.0 died at its first idle second (Python refuses every read after one timeout); it now survives idle periods.
- Not covered by tests here: real WebRTC through real Scrypted. Tests use stand-ins for Scrypted and the browser (UDP sockets and recorded setup messages), and prove the addresses are swapped, packets flow both ways, and both ports close with the view.

## 0.50.1: live video says "Live" only when a picture is there, asks for tile-sized streams, and can be measured

First real try of 0.50.0 over the site link, a whole panel of a managed site's cameras at once: some tiles showed a picture, some were black but said "Live", one kept reconnecting, and two hit the 10-view limit.

- "Live" now means a frame is on screen (the video's `playing` event). Connected without a picture says "Waiting for the picture…", and after 20 s fails with "The connection is up but no picture has arrived", so a black tile is never labelled Live.
- The page tells Scrypted the size of a tile (640x360 at 1x) instead of the iPad's screen, so Scrypted can choose a lighter stream. Ten full-size streams through two Python relays and Scrypted's own encoding was the likeliest cause of the black tiles.
- `TCP_NODELAY` on the relay stream so a packet is not held back to be joined with the next.
- `GET /api/live/relays` (and `/api/site/<id>/live/relays` for the other box) shows, per relayed view, how many packets and bytes went each way, how many were dropped for want of somewhere to send them, and whether the stream and Scrypted's address are known. That tells a stalled relay from a stalled Scrypted.

## 0.50.2: the media relay runs on one thread per view, and its numbers are one tap away

Second real try: pictures started, then every view dropped after a few seconds ("The live connection was lost"). The relay read and wrote one TLS stream from two threads at once and used a blocking send with a one-second limit, so under real video load it lost packets and then died. A test that pushes about 30 Mbit/s each way through the site link reproduced it (1,100 of 3,000 packets arrived, then errors); it now passes.

- `Pipe.serve` is one non-blocking loop per view (select over the UDP port and the stream). Packets waiting for a slow stream are capped at 256 KB and the newest are dropped instead of delaying everything behind them.
- The camera panel has a **Live details** button in Live mode. It shows the relay numbers of this box and, on another site's tab, of that site too. (Typing `/api/live/relays` into the address bar answered "sign in" on the owner's iPad, so the page now asks for it itself.)

## 0.50.3: live picture quality: Light, Balanced (default), Sharp

0.50.1 told Scrypted every tile was 640x360 at 1x, which was a guess at what had overloaded the relays. With the relay fixed (0.50.2) that is too low: the page now sends the real size of a tile and the screen's pixel ratio (an iPad tile is about 600 px wide at 2x), so Scrypted picks a stream that fits a tile sharply without sending the full-screen stream to every one.

The camera panel's Live mode has a quality choice (kept per device in `mb-camq`): Light asks Scrypted for 640x360, Balanced for the tile's real size, Sharp for the whole screen's size. Changing it restarts the live views.

## 0.50.4: Live details appear in the panel, not in an alert

An alert freezes the page; on the iPad the videos stopped on a frame when it was closed. The details are now a block in the camera panel (with Refresh and Hide). From the owner's first readout of 0.50.2: eight relayed views for about a minute carried roughly 3.6 Mbit/s in total from Scrypted, with 0 to 2 dropped packets each: the relay is not the limit. At Sharp quality the same eight views carried about 17-25 Mbit/s and a few dropped under 1% of packets (the cap on packets waiting for the stream, hit by keyframe bursts), so that cap is raised from 256 KB to 1 MB (about 0.3 s at 25 Mbit/s).

## 0.51.0: each pairing is a watched system (mutual watching)

- A box that manages a site gets a system "<Site> link" (check type `site`); a managed box gets "Managed by <name>" (check type `manager`). Both sit in the group "Sites".
- They follow the pairings: `Server.sync_site_nodes()` runs at start and whenever a pairing is added, renamed or removed (`peer.on_change`), through `monconfig.sync_nodes`, which only writes when something changed and never touches the owner's own systems.
- A silent peer is **Unknown, never Failed**: "<Site> is not answering from here" (the link check reads the 10 s poll). A manager that has not been in touch for 90 s is also Unknown. Because they are ordinary checks, the usual alerting (through each box's own Home Assistant) applies, so Tidewater can raise its own alert when Bay Harbor goes quiet.

## portainer 0.1.5: Pi-hole's web check tests `/admin/`

A watchtower update to Pi-hole 6 left its bare address answering 404 while the app was fine. New Pi-hole web checks (`CHECK_PATHS`) test the front page `/admin/` instead. Watches saved earlier keep their old address: edit the URL to end in `/admin/`, or remove them and re-add from Portainer.


## 0.51.1: a web check's address can be edited

Open a system, press **Edit address** beside a web check, type the new address. `POST /api/check-url {id, check, url}` (`monconfig.set_check_url`) changes only the URL; the check starts fresh and keeps its other settings. Built-in and module checks do not get the button.

Same release: Rename, Change link and Edit address ask in a box inside the page (`askText`) instead of the browser's pop-up, which iPad Safari can silently refuse (Change link did nothing there). Other pop-ups (confirmations, graph names) are unchanged.

A service with exactly one web check has one **Change address** button that sets both the watched page and the link its row opens; with several web checks, each has **Edit address** and the link keeps its own button. Where the two differ the buttons read **Edit monitored address** and **Change opened link**.

## 0.51.2: "Managed by" follows the managing box's current name

A managed box stored the name its manager had when pairing (its computer name if no site name was set yet). The main box now sends its current name with each 10 s poll (`X-MB-Name`), and the managed box updates the stored name and the "Managed by <name>" system.

## 0.52.0: alerts by email

Owner's call: email is wanted as another way to alert next to Home Assistant, not only a fallback, and Gmail should work. Both ways are used together: every message goes to each way that is set up, and a way that already took a message is not asked again when the other one is retried (`item["via"]`), so one slow sender never causes a repeat from the other.

`mailer.py` is plain SMTP from the standard library (no new dependency): server, port, security (STARTTLS, SSL or none) and user/password are all optional beyond the server, from and to. Certificates are verified. Gmail is a preset button on the Alerts screen (smtp.gmail.com, 587, STARTTLS); it needs an **app password** (2-Step Verification on), not the normal password. Google's OAuth route was considered and left out: for a personal account it needs a Google Cloud project, and refresh tokens of apps in testing mode expire after 7 days. Errors are one plain sentence (wrong login, with the app-password hint for Gmail; refused address; unknown server; timeout) and never contain the password.

Settings live in `config/alerts.json` (mode 0600, in backups) under `email`. The API never returns the password (`passwordSet` only); a save without one keeps the stored password; `{"email": {"clear": true}}` forgets it all. Alerts can be turned on with email alone, and turn themselves off when the last way to send is removed. The test button reports each way separately. The Alerts screen is now: 1 Home Assistant, 2 Email, 3 Try it, 4 Turn alerts on. Tests use `tests/smtp_fake.py`, a stand-in mail server with fake credentials.

## 0.53.0: one persistent header

`#hdr` is a sticky bar above every page once signed in (hidden on the sign-in page). Left to right: the MonitorBox mark (tap goes to the main screen), the site tabs, the bell, the version (tap opens Updates) and the Settings cog. It replaces the brand, gear and Discoveries button that only the main screen had.

- Site tabs live in `nav.tabs`, which scrolls sideways (`overflow-x:auto`, swipe or drag, soft fade at the right edge). A redraw keeps the scroll position, and switching site centres the chosen tab. `renderTabs()` is now a wrapper over `renderHeader()`, which skips redrawing when nothing it shows has changed.
- The bell lists two things: new things found on the network (`followups`) and an update that is ready (`versions`: `needsApply`, not already failed). `hdrPoll` asks every 60 s and on a site switch, through the site-aware `api`, so the bell and version follow the site being looked at. Tapping an item goes to the page that handles it; Esc, an outside tap or navigation closes it.
- Under 700 px the version and the word "MonitorBox" leave the bar; the version shows as a small line at the foot of the main screen.
- The bar's bottom line takes the state colour through `--accl`.
- Tests: `tests/test_header_browser.py`. `test_sites.py` now selects `#hdr`; `test_portainer_e2e.py` finds the find through the bell instead of `#disc`.

## 0.54.0: the Beacon look

A visual change only; no behaviour changed.

- Fonts: Sora (headlines, card titles) and Figtree (everything else), bundled in `app/monitorbox_app/brand/` as variable TTFs under the SIL Open Font License (licence files beside them, source noted in `NOTICE.md`). They are served by the box at `/brand/sora.ttf` and `/brand/figtree.ttf`, so the page never calls a font host (the box works with no internet, and nothing leaks). System fonts are the fallback. No new dependency: the files are static assets, about 170 KB, cached for a day.
- The beam: `body::before`, a fixed light cone from the top-left corner, coloured by `--beam` per state (`body[data-s]`). The state glow behind the page and the header's accent line already followed the same state.
- Headline: `headHtml()` wraps the last word in `<em>`, which takes the state colour with a soft glow.
- Attention rows get the state-tinted gradient and outline; cards get the lighter gradient, larger radius and a group icon (`CI`/`cIco()`, matched by card name, none shown for names it does not know).
- Not done yet from the mockup: the stat tiles and the 24 h strip on each card.

## 0.55.0: stat tiles and the 24 h bar

Completes the Beacon look from the mockup.

- Three tiles under the headline: checks healthy (leaf checks, not aggregates and not muted), things that need attention (the length of the engine's attention list) and sites watched (this box plus linked sites).
- Each card gets a bar of 24 hourly slices. `GET /api/history?strip=<node,node,...>` returns `{since, now, hours, buckets}`; `History.strip()` gives each slice the worst state any of the card's nodes had in it (failed > degraded > healthy; unknown only when nothing better is known; null before any record exists, drawn as a faint stub). It reads the same 30-day state-change log as the per-node bars, so nothing new is stored. The page asks once a minute per card, keeps the answer across redraws, and hides the bar until history exists. Demo scenarios have no history, so they show none.

## 0.56.0: sign-ins that last

Before, a sign-in lived only in the App's memory with a 7-day cookie, so every update or restart signed everyone out.

- Each device that signs in gets its own random token. The browser holds the token in an HttpOnly, SameSite=Strict cookie (one year); the box keeps only its SHA-256 in `data/local/sessions.json` (mode 0600). It sits outside `config/` and `data/app/` on purpose: a backup covers those, and a restore must never hand live sign-ins to another box.
- A sign-in is valid for 90 days after it was last used; using it slides the expiry forward (written about once a day). The 50 most recent are kept.
- Each record carries a short fingerprint of the current password hash. Changing or resetting the password therefore ends every saved sign-in. Signing out on one device removes only that device's record.
- This box's internal token for its own site port stays in memory (`Auth.sessions`) and is never saved.
- Tests: `tests/test_auth_sessions.py`.
## 0.56.1: the bell hears about updates sooner

The bell reads the box's last fetch of the release channel, and the box refetched only every 6 hours, so a new version could take hours to show. The box now checks every 30 minutes (one small pointer file; `MB_CHECK_SECONDS` still overrides), and opening the Updates page or pressing Check refreshes the bell at once. Installing remains manual unless auto-update is on.

## 0.56.2: the bell closes on a tap anywhere else

The outside-tap listener used `click`, and iPad Safari sends no click for a tap on plain page background, so the bell only closed by tapping its own button. It now listens for `pointerdown` (capture phase), which every browser sends. A tap on the bell button still toggles it, and a tap inside the bell leaves it open.
## 0.57.0: tap a slice of a card's bar to see what happened

Each slice of the 24 h bar on a card opens a sheet listing what was not healthy in that hour: the check's name, Down / Degraded / Could not be checked, how long, and from when to when. `GET /api/history?trouble=<node,...>&from=<epoch>&to=<epoch>` returns those stretches, clipped to the window and oldest first (`History.trouble()`, at most 300, with a count of the rest). The whole bar is the tap target (the slice is found from the tap position), so slices stay easy to hit on a phone. It closes with Close, Esc or a tap away. The history log keeps when a state changed, not why, and the sheet says so.

## nut 0.1.1: optional user name and password

Some NUT servers (a NAS's built-in one, say) answer a read only to a known user and say `ERR ACCESS-DENIED` otherwise. The Battery backup connection now has optional User and Password fields. When a user is set, `USERNAME` and `PASSWORD` go ahead of the read on the same connection, and nothing else is added: still only `LIST UPS`, `LIST VAR` and `GET VAR`, never `LOGIN` (which attaches a client to the UPS), `SET`, `INSTCMD` or `FSD`. With no user set nothing extra is sent, as before. The password is a secret like the others (hidden in the editor, kept on a save that sends the dots back, included in backups). An ACCESS-DENIED answer now says what to do: add a login, or check the one entered. If the server refuses on the caller's address instead of a login, it needs to allow the box in its own settings; a login will not help.

## 0.58.0: the bell covers every site

The bell used to show only the site you were looking at. Once a minute (and on login, site switch and Updates check) `hdrPoll` now asks this box and every site whose link is `linked` for `versions` and `followups`, through the existing pass-through (`/api/site/<id>/…`); no change on the other site. Results are kept per site in `hdrSites`. The badge is the sum; with more than one site each item is prefixed with the site name ("Tidewater: Update 0.58.0 is ready"). A site that is not answering adds nothing (silence stays Unknown, and its tab already shows it). Tapping an item switches to that site (`setSite`) and opens the page that handles it. Problems like "Plex is slow" stay out: that is the alerts' job. Read-only, no new dependency or privilege.

## 0.59.0: confirm a failure before calling it Down

Some things blip: Flaresolverr, for instance, briefly fails Docker's own health check while it is busy, and the Portainer check reports exactly what Docker says. A timeout would not help there, so the wait is a general rule. Down is shown only after a check has failed **N times in a row and for at least S seconds**. Site-wide default: `monitoring.confirm` `{failures, seconds}` (Settings → Display); per system: `confirmFailures` and `confirmSeconds` on the node (they win). Default 2 and 60 since 0.65.1 (it was 1 and 0, off); 1 and 0 can still be set to turn the wait off. The count and the clock reset on any success or Unknown. While waiting, a healthy thing stays healthy and carries a notice line ("failed just now, confirming (2 of 4 in a row…)"), so history and alerts, which read states, never see it; a thing that was not healthy keeps showing what was observed, and a first-ever result stays "Checking". Unknown is never held back. The existing quick second look (hold-down) still happens first. Implemented in `monitor.py` (`_grace`), validated in `monconfig.py`. Per-system values are edited in the monitoring JSON for now; there is no per-system form yet.

## 0.60.0: a time zone for each box

Each site has its own time zone (an IANA name such as America/Chicago), kept as `timezone` in `config/display.json` (so backups carry it). `GET/POST /api/timezone` is site-aware, so on Bay Harbor the Tidewater tab edits Tidewater's. Settings → Display has a list; the first time it is opened with nothing set it takes the device's zone and saves it, and it can be changed there at any time. The box applies it to its own process (`TZ` + `tzset`, at start and on save) so clock text it writes itself follows it, and the screens show history times (`tfmt`, the trouble sheet) in the zone of the site being viewed. Saving display choices keeps the zone (they share the file, but the zone is not a display choice). A name the box does not know is refused with a sentence. History and results are still stored in UTC; only what is shown and written changes. The image's time-zone data was not checked in this change; if a zone is refused as unknown on the Pi, the image lacks tzdata.

## 0.61.0: choose what the history bars show

Settings → Display has three ticks (Down, Degraded, Unknown) for the bars, per site, any combination or none. Stored as `barshow` in `config/display.json` (`GET/POST /api/barshow`, site-aware); the history endpoints apply it themselves (`History.strip(show=)`, `History.trouble(show=)`), so the trouble sheet lists only what the bar shows. It is a display choice and nothing is erased: an unticked Down or Degraded counts as healthy in the bar, an unticked Unknown as no record, and none ticked hides the bars. Saving display choices keeps `timezone` and `barshow`.

## 0.62.0: the History page

Settings → History lists every stretch when something was not healthy, for the site being viewed, newest first: range buttons (1 day, 1 week, All = the 30 days kept), a custom From/To date range (dates are read in the site's time zone), and Down/Degraded/Unknown ticks. `GET /api/history?events=1&from=&to=&states=` returns `History.trouble` over every node ever recorded (newest 500 kept, with a count of older ones) plus a `names` map from the running config. "Clear history…" (in-page confirmation) calls `POST /api/history/clear`, which empties the log and the in-memory state; the next pass writes every node's current state as a fresh start. It is per site (site-aware like the other settings), and an older backup still holds what it held. The page says plainly that history records when something changed, not why. The bar tick-boxes do not affect this page; it has its own.

## 0.62.1: Edit monitoring for one system (#173)

A system's page has an **Edit monitoring** button (not on built-in systems or groups). It opens one in-page editor for that system's own monitoring settings; for now that is the grace period, failures in a row and seconds. Each box shows what the system uses now, and an empty box means "use this site's setting" (Settings → Display; that is "no wait" until the site setting has been changed), with the live numbers shown. `POST /api/confirm {id, failures, seconds}` (`monconfig.set_confirm`) stores `confirmFailures` / `confirmSeconds` on the system, or removes the one that is null; the usual validation applies, a bad value is explained in the editor and nothing is saved. More per-system settings can be added to this editor later. The JSON route still works.

## 0.63.0: web admin pages are found and offered (#176)

The follow-ups ("Found more you can add", also the bell) now include web pages. `followups.web_targets` collects the addresses MonitorBox already knows: the gateway and DNS servers (as configured, plus what this box sees in its route table and resolv.conf) and each declared server, private addresses and typed names only (never 1.1.1.1 or 8.8.8.8). `thisbox.identify_web` asks each of them on ports 443, 80, 8443 and 8080 (GET only, certificates not checked, no login, any answer counts, even a login wall or an error page): `/admin/` first, and a Pi-hole is recognised by its page; a UniFi console by its page; anything else is named by its title. The router is offered as "Router admin page" whatever the brand. Hosts that already have a web check, an opened link or a service URL are not offered again. Offers appear as `how: "webpage"` suggestions and are added with one tap (`add_web_followup`): the router and a DNS server's page join the system they already have, so ping is the primary check and a silent page reads Degraded, not Down; any other page becomes a system of its own in Services. The look is done in the background every 10 minutes and cached (the bell polls every minute), and nothing is added without a tap. Not built: Pi-hole API numbers (needs a login) and a whole-subnet sweep (#177).

## 0.64.0: faster Settings, fair memory numbers, site-time display (#180)

Opening Settings used to make seven requests one after another, including a forced check with the update server, and repeated them on every Settings page. Now `settingsData()` asks for everything in one parallel round, forces the update check only on the Updates page, and reuses the answer for 20 seconds per site. Any write (`api` with a body) clears the cache. A "Loading settings…" line shows at once. `rsTok` drops a slow answer that arrives after the person has moved on.

Memory: each process is measured by its fair share (PSS from `/proc/<pid>/smaps_rollup`, falling back to VmRSS), so Bay Harbor (Pi, no memory cgroup, sum of processes) and Tidewater (container total) become comparable.

Update-check, backup and alert times on screen use the site time zone (`lt()`). Backup file-name stamps are made by the launcher and stay UTC for now.

## 0.64.1: a machine's other web pages are still offered (#176)

Coverage of "already watched" is now by address and port (`followups.watched_origins`), not by host. Before, a machine with Portainer already watched (Aurora, 192.168.1.9) never had its Pi-hole on port 80 offered. Exactly the page already watched is skipped; other pages on the same machine are offered.
## Backups carry the site name

New backups are named `monitorbox-<site>-<kind>-<stamp>-<label>.tgz` (for example `monitorbox-bay-harbor-config-20261019-060828-manual.tgz`), so files from several MonitorBoxes can be told apart on a tablet's Downloads list. The site part is the name set under Settings → Sites, made safe for a file name (lower case, letters and digits joined by dashes, 30 characters at most); with no name set the old shape is kept. The manifest also records `site`. Backups are made by the launcher, which is part of the container image, so this takes effect when the image is rebuilt and the container recreated; an App update alone does not change it. Old backups keep their names and restore as before.

The stamp in the file name is the box's own time (the zone set in Settings > Display, read by `backup.local_stamp`), UTC when none is set or the zone cannot be read. The manifest's `created` stays UTC; that is what orders and prunes backups. Launcher code: it takes effect after the image is rebuilt and the container recreated (0.64.2).

## 0.65.0: the performance view (#180)

Settings > This box > Performance. `perfstats.py` keeps, in memory only, the last 200 timings of each kind of request (`GET /api/state`, `site:/state` for a request passed on to another site) and of each module call (`<module>.<method>`, recorded in `Modules.call`). Streams and the perf endpoint itself are not counted. `GET /api/perf` (signed in) returns those summaries (count, average, p95, max), each process's fair-share memory (`sysinfo.processes`, modules named from the registry) and the container total. "Measure this site" also times six requests from the browser (median of 3), starting with `health`, which does no work and so shows the link itself. The page is site-aware: on the Tidewater tab every request goes through Bay Harbor, so the numbers include the hop. "Copy" gives a plain-text block to paste for review. An older site answers without timings and the page says so.
## 0.65.1: the grace period is on by default

The site-wide grace is now 2 failures in a row lasting 60 seconds unless the owner has set another value (`monitor.DEFAULT_CONFIRM`). The owner ran 2/60 on both sites for a day and it removed the false Down blips (Flaresolverr, Pi-hole after an update). Settings > Display shows 2 and 60 when nothing is set, and saving 2 and 60 stores nothing (it is the default); 1 and 0 is stored and turns the wait off.

## 0.65.2: backups are listed once, and the Updates page opens at once (#180)

The performance view showed `GET /api/backups` taking about 2.1 s on Bay Harbor (0.35 s on Tidewater): the launcher's `list_backups` opens every archive to read its manifest, and Settings asked on every first open. `backups.listing()` in the App now keeps the answer until the backups folder changes (names, sizes and times), reads it once at start and again after each automatic backup, and hands out copies. The launcher is unchanged.

The Updates page used to wait for a forced look at the update server before it drew. It now draws at once from what is known and then asks (`UPDCHK`, at most once in 30 s), refreshing when the answer arrives. The bell's "update available" link goes there, which is why it felt like the old slow Settings.

The Updates page never uses the 20-second Settings cache (what is waiting can change at any moment, and a test caught the stale list); every other Settings page still does.

## 0.65.3: History is the truth; the confirmation setting only changes what is shown

Before, a failure still inside its grace period was held back from History too (and a confirmed Down was recorded from the moment of confirmation, a minute late). Now `Monitor.raw` keeps what each check actually answered and `record_history` evaluates that, so History has every failure when it happened. The grace period (`results`) feeds only the screen, the banner and alerts, so the project rule holds: observed state is never rewritten and suppression only affects what is shown.

- **Bars and lists hide brief blips when drawn.** `History.strip` and `trouble` take `min_seconds` (node id to seconds: `Monitor.grace_seconds`, the system's `confirmSeconds` else the site's). A Down or Degraded stretch shorter than that (or still going and younger than that) counts as healthy in the bars and is left out of lists, or listed with `"brief": true` when `?brief=1` is asked (History page tick "Show brief blips", off by default). It is worked out when read, so the same setting also quiets blips recorded in the past, and "no wait" (1 failure, 0 seconds) makes the bars match History exactly. Timelines and availability still count every second.
- **Degraded is held like Down.** A warning must last the same failures and seconds before it shows (notice "warning just now, confirming…"); a warning that clears inside the wait never reaches the screen or alerts.
- **Quiet start-up.** For `STARTUP_QUIET` (90 s) after the App starts, "could not be checked" is not written to History: modules are still logging in, and a restart is not something that happened to the systems.
- The Updates page refreshes after its check only if the check found something different; otherwise only the "Checked …" time changes, in place.

## 0.66.0: new things from every connection (#183)

"Found more you can add" now also offers new things that appear on any connection (Portainer containers, cameras, UniFi devices, SNMP volumes, UPSes). `App._sweep_run` asks every connection's module `discover` in the background every 30 minutes (Portainer reuses its own cached answer), one at a time and read-only. `followups.new_items` keeps what is not watched yet and is not an opt-in extra (default false, a system-level item or a network interface) and not already known. "Known" is `config/seen-items.json`, per connection: the first time a connection is seen, everything it offers is recorded as known (so skipped containers and cameras are not offered again and again); later arrivals become one proposal per connection (`how: "items"`, id `new:<connection>:<hash of the labels>`, so a later arrival is a new proposal). Add all watches them the way Re-detect does by default (`add_watches`) and marks them known; Not now also marks them known, so only later arrivals come back. A connection that cannot be reached is skipped and keeps its last answer: a silent source proposes nothing and never reads as missing. Re-detect on the Servers page still shows everything, known or not.

## 0.67.0: tap a traffic graph for a longer history (#184, piece 1)

Tapping a graph on the main screen opens the side panel (the same `.drawer` shell the drill-down uses, marked `gp`) with a bigger graph, the last 15 minutes by default, and now / average / peak for in and out. No new data is kept: `graphs.py` already holds the last hour per graph (`KEEP_SECONDS = 3600`), and the panel asks `graphs/data?seconds=N` once a second while it is open, so an hour is the longest either window can be (this is not meant to be a general time-series tool). Two display choices, saved on the box like the history length so a backup brings them back and a device that has never chosen takes the box's: `gwin` (main screen, default 5 min) and `gpanel` (panel, default 15 min), each one of 1, 5, 15, 30 or 60 minutes; anything longer is refused. They are set in Settings, Display, "Traffic graphs"; the buttons on the main screen and in the panel change the same two values. Only one side panel is open at a time: opening a system's drill-down or the services list closes the graph panel and the reverse. Pieces 2 and 3 of #184 (where the traffic goes: gateway flows, and LAN peers inferred from per-port rates) build on this panel and are tracked separately.

## 0.68.0: switch report (#191, first slice)

Before designing the LAN map (#191) we need to see what real switches say, so this slice only looks. Both modules gain a read-only `lan_report` method: `unifi-network` copies a fixed list of fields per device and port (state, speed, rate, errors, how many addresses are learned behind a port, LLDP neighbours, the uplink and which device it reaches); `snmp` reads interface names and labels, speeds, two 64-bit counter readings a second apart (so a rate), errors and discards, the learned-address count per port (Q-BRIDGE, else BRIDGE, mapped to interfaces through dot1dBasePortIfIndex) and the LLDP neighbour on each port. A part a device does not offer is named in `notes`, never an error. Ports that are down are counted, not listed. Secrets cannot ride along (UniFi: only listed fields are copied; SNMP: nothing from the connection is returned) and MAC addresses are shortened to their last three bytes (`..:dd:ee:ff`), enough to tell devices apart. The UniFi report also lists the names (never values) of the other fields the controller sends, to show what else there is to build on. `GET /api/lan/report` (signed in) asks every UniFi and SNMP connection, four at a time; a source that does not answer is named with the reason and the rest still come back. Settings, Advanced, "Switch report": Ask the switches, then Copy the full JSON. Module versions: `snmp` 0.2.2, `unifi-network` 0.2.7.

## 0.68.1: switch report names who is on each port (#191)

The first Bay Harbor report showed the whole tree is available from UniFi alone (every device's uplink with the port number at both ends, per-port speed, rate, errors and link aggregation), but not which device sits on which port. So the UniFi report now also reads the client list (`stat/sta`, one more GET on the read-only allowlist; the test that proves the module only logs in and reads now lists it) and gives each client's name, address, whether it is wired, the switch and port (or access point), and its rates, with the controller's own rx/tx names so the direction can be checked against the port's own counters rather than assumed. A login that may not read clients still gets the rest, with a `clientsNote`. Ports also carry `mac_table_count`, `link_down_count` (flaps), `stp_role` and the last address seen (shortened). The SNMP report adds each interface's own address (ifPhysAddress, shortened) so a server can be matched to the switch port it is plugged into, and leaves out container and tunnel interfaces (counted in `virtualPorts`). Module versions: `snmp` 0.2.3, `unifi-network` 0.2.8.

## 0.68.2: History says why (#191 follow-up)

History recorded when something was not healthy, not why, so a blip such as a container that went Down for 20 seconds could not be explained afterwards. Each state-change line in `config/history.jsonl` that is not healthy now also carries `w`: what the check reported when the stretch began (the node's `detail`, at most 160 characters; healthy lines carry none). `History.record(states, why)` writes it, `History.why` holds it keyed by (time, node), a restart reloads it and the 30-day trim keeps the reasons of what it keeps. `trouble()` adds `why` to each item, and the History page and the tapped-slice popup show it under the line. The reason is what the raw check said, so a stretch hidden by the confirmation wait is explained too. Older lines have no reason and list as before (the popup's note now says so). A test that checked the old popup note ("when, not why") was changed on purpose, since that sentence is no longer true.

## 0.69.0: the network map (#191)

A new page, `#/map` (button "Network map" on the main screen), shows the gateway at the top, every UniFi switch and access point below the device it hangs off, and for each switch the ports in use with who is on them. `app/monitorbox_app/lanmap.py` builds it from the switch report (0.68.x), so it reads nothing new: `GET /api/lan/map` asks every UniFi and SNMP connection for its `lan_report` (SNMP with `wait: 0`, since the map needs layout, not a second counter reading) and `lanmap.build` turns the answers into nodes. The tree is the controller's own uplinks, with the port at both ends of each link; a device whose parent is not a UniFi device is a root. A link's rates are its uplink port's own counters, and an endpoint's are its switch port's (the client list's rates are not used: they run far below the counters). Rates are from the point of view of the thing further from the gateway: down is traffic going to it, up is traffic from it; a switch that gave no port counters shows "no traffic figures", not zero. Ports that are bonded (the controller's `aggregated_by`) are one endpoint with their traffic added and their speeds summed. An endpoint is named from the wired client on it, or as a server when its card address matches one of the SNMP hosts' (ifPhysAddress, also matched against the last address the port saw). Ports that lead to another device and the uplink are not listed as endpoints. A device the controller shows as anything but connected or disconnected (provisioning, upgrading) reads Degraded on the map; that is the controller's word, not a monitored state. Errors and drops are shown beside a link or port when non-zero; watching them for growth is #194. The page re-reads every 10 seconds while open. Only UniFi devices are mapped for now: SNMP-only switches and the peer view build on this. Module version: `snmp` 0.2.4.

## 0.69.1: the map keeps opened port lists open

The map redraws itself every 10 seconds, which closed any "N ports in use" list the owner had opened. The page now remembers which switches are open (`mapOpen`, reset when the page is opened) and redraws them open. Regression test in `tests/test_graphs_e2e.py`.

## 0.70.0: switches that answer the saved SNMP login (#191)

The box now offers to add each UniFi switch as an SNMP connection, reusing a login the owner already saved, so the map and switch report can read every port.

- **Source login:** the SNMP connection on the UniFi gateway (or on the UniFi console's address), else the only SNMP connection. With several and no match nothing is tried: guessing logins on devices can lock accounts.
- **Candidates:** switches (`type usw`) from the UniFi connection's `discover`, not already an SNMP host. Access points and the gateway are not offered. (`unifi-network` 0.2.9 adds `type` to its device list.)
- **Probe:** the `snmp` module (0.2.5) has a `probe` method: one quick read of the device's name, never raises, keeps no session. Four at a time in the background, retried every 30 minutes or when the switch list changes. The page is told `pending` meanwhile so it asks again.
- **Offer:** one follow-up ("N switches answer your SNMP login"), `how: snmp-switches`, shown in the same "Found more you can add" box on the main screen and in setup. Nothing is added until the owner taps. The id changes with the set, so a dismissed offer does not hide a later switch.
- **Add:** one SNMP connection per switch, the login copied on the box (never sent to the browser). Connections only, no watches: UniFi already watches the switches' state.

## 0.70.1: the map ties devices together by address, not name

Real sites name a switch and an access point the same ("Living Room"). The map matched parents by name, so such devices became their own parent and the page could loop. `unifi-network` 0.2.10 adds each device's shortened address (`mac`) to the report; the map uses it as the node id and resolves parents by the uplink's `toMac`. A name that is not unique and has no address is left unattached rather than guessed, and the page refuses to draw a loop.

## 0.71.0: where does a port's traffic go (#191)

Tap "where does it go?" on a port in the network map to see which other ports its traffic most likely reaches, as **likely** or **possible**. It is an estimate from rates, never a record of conversations, and the page says so.

- **History:** `lansampler.py` reads every switch port about every 10 seconds into `portpeers.PortSeries` (last hour, in memory, a few MB). One UniFi request lists every device's ports and rates; a switch that is also an SNMP connection (matched by address) is read over SNMP instead (`snmp` 0.2.7 `counters`: every interface in a few column reads, with the port's description). UniFi switches describe each port with the same name UniFi uses ("Port 10"), so readings are keyed by (device id, UniFi port name), the ids the map uses (`lanmap.device_ids`).
- **Matching:** `portpeers.likely` compares the focus port's incoming traffic with every other port's outgoing traffic (and the reverse), per 10-second bin over the chosen window (5 min, 15 min or 1 hour, never more). Pearson correlation of at least 0.7 is "likely", at least 0.5 "possible"; fewer than two minutes of shared readings, a flat port or a quiet port gets a plain "not enough" instead of a guess. Bonded ports are added together, as on the map.
- **Candidates:** every port on the map (named by who is on it), plus "anything beyond the link to X" and "anything behind Y" for the focus switch's own links. Switches with no readings are named in the answer so its completeness is visible.
- **Endpoint:** `GET /api/lan/peers?node=&port=&win=` (signed in), answered from the map the page last loaded.
- **Not built yet:** acting on any of this (root-cause alert grouping is separate), inference across sites.

## 0.71.1: "where does it go" tuned on real traffic

Real use showed two false leads. (1) A port carrying a thousandth of a 4 Gbit/s transfer still matched in shape: a port must now carry at least 2% of the device's traffic to be named. (2) Quiet chatter (discovery pings) is copied to every port, so three or more ports each showing about as much as the device sent are reported once as "broadcast or multicast", not as three destinations; a link that carries everything and a split between two real destinations are not mistaken for it. The wording is now from the port's point of view ("sends to X", "receives from X").

**For the user documentation at launch:** a properly named LAN makes traffic inference much better. Name every device in the UniFi client list (and, on switches, give ports meaningful names), because the map and "where does it go" read those names; an unnamed device shows as a bare address or as UniFi's own best guess (which can be confidently wrong, such as an "iPad" on a 100 Mbit wired port that is really a music player), so it cannot be told apart in an answer. Say this plainly in the guide for the network map and for "where does it go".

## 0.74.1: matching fixes for the flows list

First real use of 0.74.0: the WAN graph "could not be matched" and a two-NIC server's graph was matched through the connection's address. The map knows the gateway by the address UniFi lists for it (its WAN side), while the SNMP login is on its LAN address: a graph whose connection has the same address as a UniFi login (or the gateway on the map) is now the gateway's graph (`followups.host_of`). An interface graph is matched by that interface's own MAC (what the SNMP report said when the map was last built, kept in `App.last_sources`), so the 10G and the 2.5G card of one server are different ports; with no MAC it falls back to the connection's address. Local rates now read "up to": a peer's rate is its own port's rate capped at the device's, so several peers can show the same number. The internet row says "via the gateway" and the layout has a gap before the rates.

## 0.74.0: one flows list under every graph (#184, #205)

Tapping any graph opens the side panel; under its graph is one list, "Where its traffic goes", biggest first, local and internet mixed (no separate section). `GET /api/lan/flows?graph=<id>&win=<s>` (signed in; 60 s to an hour, the panel's window) builds it in `App.lan_flows`:
- **Which device a graph is about.** Busiest client: its current leader (a port on the map). An interface graph: the map port whose client address equals the graph's connection address (map port rows now carry `macs` and `ips` of the clients on them). A connection to the gateway's own address (the WAN graph): the clients using the internet most. A connection set up by hostname, or one that is not on the map, cannot be matched and the panel says so (the map matches by address).
- **Local entries** are the port-history inference (`portpeers`, unchanged: likely/possible, a match percentage) with a bandwidth: the candidate port's own rate, never more than the device's (`bps`). It is an estimate and labelled as one.
- **Internet entries** come from the gateway: `unifi-network` 0.2.15 `client_usage` (`GET v2/api/site/<site>/traffic` over the window: bytes up and down per client, all applications added together, the biggest 30, addresses shortened) turned into bits per second by `App.gateway_usage` (cached 20 s per window). A device's row is the sum of its own clients (by address). The gateway counts internet traffic and traffic between networks, not what stays on one switch.
- **What is not available:** the flows look showed the per-flow list is Forbidden to the read-only login, the application and category names are not available to it (the name-list routes only return more usage), and the official integration API wants an API key, so none are used: there are no per-destination flows and no application names yet. Not done: wifi clients taking the Busiest crown (#205).

## 0.73.3: the flows look, third round (#184)

Round two: the official integration API (`integration/v1/...`) answers 401 "Missing Credentials" to the session login (it wants an API key, a broader permission than the read-only login, so it is ruled out), and `traffic/applications` and `traffic/categories` answer 400, which means they are routes that wanted something else, but the error text was hidden. Round three drops the integration API, tries those two with the same `start`/`end` window as `traffic`, and keeps error messages whole (`mask`: MACs shortened, public IPv4 addresses hidden). If these still do not yield names, the choices are a bundled name table or showing UniFi's own numbers.

## 0.73.2: the flows look, second round (#184)

First real answers from the owner's gateway: `GET v2/api/site/<site>/traffic` works with the read-only login (per-client usage by application, wired and wifi, with bytes up and down; applications and categories are numeric ids). `GET .../traffic-flows` is 405 and both `POST` searches are 403 Forbidden for that login, so per-flow data needs a higher-privileged login; the decision is to build on the per-client usage and not ask for one. What is missing is the names of the numeric application and category ids. Round two adds only more GETs to the look (all in `LOOK_ALLOWED`): `traffic/applications`, `traffic/categories`, and the official integration API's `integration/v1/sites` followed, only if it returns a site id, by that site's `dpi/applications` and `dpi/categories`. If none of them answers with the session login, the names will need either a bundled table or an API key, which is the owner's call.

## 0.73.1: the flows look (#184, piece 2, first slice)

Like the switch report before the map, this slice only looks. UniFi does not publish the API behind Insights → Flows (UniFi Network 9.1+, a gateway with storage), so `unifi-network` gains `flows_look` (module 0.2.12): it asks the gateway four questions and reports each answer's status and shape only: `GET v2/api/site/<site>/traffic` (the per-client, per-app usage that is documented by other projects), `GET .../traffic-flows`, and two `POST .../traffic-flows` searches (a fixed small body, and an empty one so a refusal names what it wanted). **The privilege, and why:** these POSTs are the only requests besides the login that are not GETs. They are searches of the flow list; they create and change nothing, and the paths and methods are fixed in `unifilib.LOOK_ALLOWED`. Only this method can send them; the normal reads still refuse anything not on their own list. Answers pass through `shape` and `scrub`: field names, types, counts and two examples; MACs shortened, public addresses hidden, long text replaced by its length. `GET /api/lan/flows-look` (signed in) and Settings → This box → "Flows look" (Ask the gateway, Copy). Next: build the flows list from what the real answers look like, in the same side panel as Busiest client.

## 0.73.0: tap Busiest client for its flows (#191)

The Busiest client graph is a normal-size card. Tapping it opens the same side panel the interface graphs use, with the leader's graph and, below it, where its traffic goes (`/api/lan/peers`, worked out at most every 5 s and shared with the panel's window choice). There is no second tap; the old inline "where does it go?" is gone from the front page (the map keeps its own). Next: the same panel for the interface graphs, and gateway flows beside the LAN flows (#184).

## 0.72.1: Busiest client is a graph you add (#191)

The 0.72.0 box was hard-coded on the front page. It is now an entry in `config/graphs.json` (`{"kind": "busiest", "id": "busiest", "title": ...}`), added in Settings → Graphs like any other graph, so it moves, renames and removes with them, and backups carry it. At most one; it needs no SNMP connection or interface. `Graphs.tick` skips it, and the page polls `/api/lan/busiest` only while it is in the list. It is not on by default: an install that had 0.72.0 adds it once.

## 0.72.0: the Busiest client box (#191)

A box on the front page names the chattiest wired device right now, shows a graph of how busy it has been (same window selector as the traffic graphs, an hour at most), says who held the top spot before, and has the same "where does it go?" tap as the map.

- **Steady name:** `busiest.py` ranks every device port on the map by its last minute of traffic (in plus out; bonded ports added). A challenger must be at least 1.5 times busier than the leader, and above 1 Mbit/s, for three readings in a row (30 s) to take over; the leader keeps the crown down to half the floor and loses it only after a minute below that. Under the floor nobody is named ("The wired LAN is quiet").
- **Where the names come from:** the sampler reads ports every 10 s; a background loop rebuilds the map every 5 minutes (`App.map_loop`) so names and ports are fresh without the map page open. `GET /api/lan/busiest?seconds=` (signed in) is what the page polls every 5 s.
- **Wired only for now:** UniFi's per-client wifi rates run far below the real traffic. Wifi clients and internet traffic are #205.
- **Also fixed:** the "where does it go" note names a switch as having no readings only when none of its ports has one.


## 0.74.2: the flow search needs the login's CSRF token

MonitorBox 3 read Insights → Flows with one `POST …/v2/api/site/<site>/traffic-flows` (empty body) over the same username/password login, and it sent the `X-Csrf-Token` the controller returns at login. The 0.73 probes sent only the cookie, so UniFi OS answered 403, which looked like a missing permission but is most likely the missing token. `unifilib.Client` now keeps the token from the login and sends it on every non-GET request (the flow search is a read-only search, still on the `LOOK_ALLOWED` list). The fake controller now hands out the token and answers 403 to a POST without it, so `test_unifi`/`test_flows_look` fail if the header is dropped. The next Flows look shows whether the read-only login can read per-flow data; the destinations list is built only if it can.

## 0.75.0: real destinations from the gateway's flow log

With the CSRF token (0.74.2) the read-only login can run the flow search behind Insights → Flows: `POST …/v2/api/site/<site>/traffic-flows` with `{timestampFrom, timestampTo, pageNumber, pageSize}`. Each record names the source device and address, the destination address and (when UniFi knows it) domain, zone (`External`, `Internal`, `Gateway`), direction (`outgoing`, `incoming`, `local`), service and bytes.

- **Module (`unifi-network` 0.2.17):** `Client.flows(seconds)` pages through up to 2000 newest records (200 per page, 50 if the controller refuses big pages) and caches them; `unifichecks.flow_summary` adds them up per (source, destination, direction), counting a flow only for the part inside the window, names destinations by domain else address, shortens MACs. The module method is `flows`.
- **App:** `App.flow_rows(seconds)` (cached 20 s) and `App.flow_entries`. The WAN/gateway graph lists internet destinations with who is using them (`cdn.example (Phone, TV and 1 more)`); a device graph lists what that device talks to and who talks to it, matched by MAC or address from the map. Entries from the log are marked `seen` (the panel says "seen by the gateway", no "up to"). If the log cannot be read the old behaviour remains (clients for the gateway graph, one "internet and other networks" total for a device) and `why` carries the reason.
- **Limits:** the gateway only logs traffic it routes, so switch-local traffic still comes from the port-history estimate. A flow is counted when UniFi reports it, so a very long download shows up in steps. Bytes `rx`/`tx` were first read from the source's side; that was wrong, see 0.79.4.

## 0.75.1: tidier list, and the Busiest line agrees with the device's own graph

- The flows list leaves out the vague "anything beyond the link to X" / "anything behind X" guesses and a device's chatter with its own gateway (already in the totals).
- Busiest: the name and the figure in words still come from the 60 s port average, but the **line** is now the latest port reading (not smoothed). When the leader is a device that also has a graph on the main screen (an SNMP interface matched to the same map port, `App.graph_port`), the line from the moment it took the lead is that graph's own readings, so the two agree (`App.busiest_data`, `source` in the reply). Next: let the ranking itself use the flow log and SNMP rates (#205).

## 0.76.0: Busiest client counts wifi clients (#205)

The Busiest ranking now has two sources. Wired devices still come from their switch port's readings (60 s average, which already includes their internet traffic). Wifi clients, and any device without a port reading, come from the gateway's flow log: `App.flow_loop` keeps the last minute of flows fresh every 20 s (`App.minute_flows`, only when a UniFi login exists) and `busiest.flow_endpoints` turns them into candidates, skipping any MAC that is already on a wired port so nothing is counted twice. The same name steadiness applies (1 Mbit/s floor, 1.5x challenger for 3 ticks, 60 s quiet). A wifi leader has no switch port, so its panel list is its own flows from the log. Known limits: the log counts traffic the gateway routes (internet and between networks), and a flow is counted as it reports in, so a wifi client's figure is lumpier than a wired port's. SNMP rates are already inside the port readings; an SNMP host that is not on any mapped port is still not a candidate.

## 0.77.0: alert storms, flapping and a UPS on battery (#191 follow-on)

Alerts already speak once per root cause (dependents are marked "affected by"). Three more guards cover what the dependency map cannot know yet:

- **Storm guard.** Three or more new problems within 60 s start a storm (`STORM_COUNT`, `STORM_WINDOW` in `alerts.py`). Members are not announced one by one: after the usual delay (if at least three are still down) one message says "N things went down at once" and names them (critical first). New problems within 5 minutes of the last join are added quietly; one update follows when it settles. When every member is back, one "everything is back". If most clear before the delay, the storm dissolves and what is left is announced the ordinary way. State lives in `config/alerts-state.json`, so a restart neither repeats nor loses it.
- **Flap damping.** A node that opens a problem three times in ten minutes gets one "keeps going down and coming back" message, then silence (no down/back pairs) until it has been steady for ten minutes, then one "steady again".
- **UPS on battery.** A NUT check reporting "on battery", "low battery" or "shutting down" is sent at once (no delay), as time-sensitive, and is never counted in a storm or damped as a flap. The words come from the NUT module's own status words (a test fails if they drift). Power is the case where the alert may not get out, so it goes first.

Next, as agreed with the owner: optional power links (which UPS powers which server), pre-ticked where NUT's client list makes it likely, editable in Settings → Servers; a UPS-down then reads "3 servers behind it".

## 0.77.1: the Busiest card refreshes every second

The front-page Busiest client card asked for its data every 5 s while the other graphs ask every 1 s, so it lagged and then caught up. It now polls every second, one request at a time (`bzBusy`), like the side panel.

## 0.78.0: power links (which UPS powers which system)

A system (the node holding a server's checks) can carry `poweredBy: [ids of UPS nodes]` (optional; an empty list means "none, and do not guess"). The engine uses it as a second kind of root cause: when a system is Failed, Degraded or Unknown while a UPS it is powered by is Failed, or Degraded and running on battery / low / shutting down (`engine.POWER_URGENT`, the NUT module's own words), the system is "affected by" the UPS, so the alert is one message for the UPS ("also affected: …"), not one per server. A UPS on battery is only Degraded, which the ordinary dependency rule ignores, hence the extra rule. Observed states are untouched.

**Guessing.** `App.power_scan` (every 10 minutes, `power_loop`, or `GET /api/power?refresh=1`) asks each watched UPS's NUT server who is attached (`LIST CLIENT <ups>`, read only; nut module 0.1.2, method `clients`) and links a client address to a watched system only when it is exactly one system: the system holding an SNMP login at that address (the server's own one, as on the server page), else the single ping/TCP system there. A client of the NUT server itself says 127.0.0.1, meaning the NUT server's own machine. Ambiguous addresses (two systems at one address) and addresses nobody watches are not guessed. Guesses live in memory (`monitor.power_guess`) and apply only to systems with no `poweredBy` of their own.

**Owner's word wins: the Power page.** Settings → Power lists one heading per UPS with the systems on it, then the systems not yet on any UPS ("Also on it?"). Every watched leaf system is offered, ping-only ones included (not built-in, not a container, not a UPS, no `service`, no `dependsOn`). Pre-ticked guesses are marked "guessed". A system is on one UPS at a time: once ticked under one it is no longer offered under another, and `monconfig.set_powered_by` stores `[ups]` (or `[]` for "none, and do not guess"). `GET /api/power` returns `{ups, systems:[{id, name, group, ups, from: set|guess|none}], notes}`; `POST /api/power {system, ups|null}` saves and returns the same. If two UPSes both claim an address, nothing is guessed.

**Stay explained.** `alerts.py` keeps the systems on a UPS quiet while that UPS has an urgent alert open and for `POWER_GRACE` (10 minutes) after it closes, even while the UPS itself is Unknown (e.g. it went down with the same power cut), so a server that shut down cleanly on battery does not raise a second alert on the way. A system down with no UPS trouble stays Red with its own alert. Planned maintenance (a commanded shutdown) is not detected yet.

### 0.78.1

The Power page lists only the systems on each UPS. Systems on none wait once in "Not on a backup here" with a dropdown (a system watched from here but on another site's power is simply left there). A link to another MonitorBox (`site`/`manager` checks) is never offered.

### 0.78.2

A Portainer environment (the node `<name> Portainer`) runs on a machine, so it has that machine's power and is not offered on the Power page. `power_scan` matches the environment's address from Portainer's own answer (`pt_cache`; the power loop asks once if nothing has) to the one watched system at that address, giving `follow {env node: system}`; `Monitor._eval_nodes` gives the environment its machine's `poweredBy` (over any older answer of its own, and only when the machine has one). The page lists the followers in a line under the UPS lists. An environment no watched system answers for stays on the page to be ticked.

### 0.78.3

A Portainer environment that cannot follow its machine says why on the Power page (`why` on the system row): Portainer has not answered yet; it lists no environment of that name; an edge agent has no address; no address given; the address it gives has no watched system; or several watched systems share it. Also, the power loop re-asks Portainer when its last answer was empty.

## 0.78.4: the heads-up line says it once (#196)

The line under "Everything is fine" no longer repeats itself or shows the confirming counts. `engine.heads_up` turns each notice into plain words (`engine.plain_notice`: "warning just now, confirming (2 of 2 in a row, 16 s of 60 s): Aggregation provisioning" becomes "Aggregation provisioning, confirming"), drops a repeat inside one system, and lets systems that say the same thing share a line ("UniFi and Aggregation: ..."). Only the banner line changes; a system's own detail still carries the full wording and the counts. Observed state is untouched.

## 0.79.0: the Advanced page (#226, step 1)

Settings gains **Advanced**, last in the list, for the tools made for developing and troubleshooting. They are moved, not rewritten (same element ids and handlers): the network map (opened from a button there; the main screen's button is gone, and the map's Back returns to Advanced), Monitoring (JSON) (was the "What is watched" page; an old `#/settings/watched` link lands on Advanced), Connections (JSON) (was inside Servers), Performance, Switch report and Flows look (were on This box) and Preview the screens (was on Display). This box keeps the version, memory, restart, factory reset and sign out. Nothing is removed. Next steps in #226: Time zone to This box, "Confirm a failure first" to Alerts, history-bar colours to History, graph windows to Graphs, then a wording pass.

## 0.79.1: four settings move to the page about them (#226, step 2)

Display was mixing what this device shows with what the site does. Now: **Time zone** is on This box; **What the history bars show** is on History; **Confirm a failure first** is on Alerts (it is the wait before something counts as down); **Traffic graphs** (how much time they show) is on Graphs, beside which graphs there are. Display keeps the main-screen view and history length. The blocks and their loaders moved unchanged (same ids); a test pins each setting to its page and checks it still loads there.

## 0.79.2: CI fix (no change for users)

0.79.0 and 0.79.1 never published: a browser test lost its "skip without Playwright" decorator in an edit, and CI (which has no Playwright) failed it, so the publish gate held the release. The decorator is back, and 0.79.2 carries everything in 0.79.0 and 0.79.1. Lesson kept: check the PR's own CI result, not only a local run, before merging; local runs have Playwright and CI does not.

## 0.79.3: wording, Display and Servers (#226, step 3)

Plain-words text for Display (what Summarized and Detailed are; how far back the history bar reaches) and Servers (open a server to see what is watched and how it is reached; the empty state; what Rescan does). The hub's one-line descriptions that went stale after the moves in 0.79.1 are corrected (Display no longer lists "preview screens"; History, Graphs, Alerts and This box say what they now hold). Text only; no behaviour changes.

## 0.79.4: download and upload were swapped on flow-derived rows (bug)

The gateway's flow record names its two byte counts from the far end's side: `bytes_tx` is what the far end sent, which is what the device received. `flow_summary` had them the other way round, so "Where its traffic goes" rows, the Busiest tracker and the "sends to" peer rows showed downloads as uploads (found on a downloader that appeared to upload to its news servers). Fixed in one place, `flow_summary`; `flow_entries` already follows it. Port speeds were never affected. Regression test: `test_a_download_reads_as_down_for_the_device_that_pulled_it`. One real record seen earlier was ambiguous, so the owner confirms on live Usenet traffic that a news row's down roughly matches the downloader's port down.

## 0.79.5: a container is offered once, where it runs (bug)

A Portainer server and the agent on the machine where a stack runs both list its containers, so a new stack was offered twice ("Add all" on each connection). `followups.one_home` matches containers by (machine address, container name), using the environment's address (or the connection's own address for a local environment). A container is not offered if any connection already watches it or has had it answered; otherwise it is offered on the connection whose own address is the machine it runs on. Regression tests in `tests/test_followups.py`.

## 0.79.6: bell wording for new things

The bell said "1 new thing found" for an offer of three things, and named the server rather than the machine. It now counts things (a proposal's `labels`), says "On <machine>", and the offer text drops the machine name every label repeats ("Container x on Box" listed under Box reads "Container x").

## 0.79.7: the bell shows the new wording, and offers name the machine (bug)

0.79.6's bell wording never appeared: the header kept only each offer's `title`, dropping `labels` and `on`. It now keeps them (browser test goes through the real loader). An offer for Portainer containers also names the machine they run on (`followups.machine_of`: the server declared at that address, else Portainer's environment name) instead of the Portainer server that reported them.

## 0.79.8: "not matched to anything" in Where its traffic goes

A device's panel could list far less than its port carried (a downloading server: 78 Mbit/s in, about 50 named): the gateway logs only what it routes, and the switch-port estimate names only ports that rise and fall with the device. `portpeers.likely` now also returns `total` (what the device received and sent, averaged over the window) and `App.unmatched` adds one row, scope `unmatched`, for what the list does not explain (shown only when it is at least 100 kbit/s and a tenth of the total; the estimates can overlap, so it is never negative). Observed numbers are unchanged; it only says out loud what is missing. Note the list is an average over the window, so a graph's peaks sit well above its figures.

## 0.79.9: containers on an edge agent are not said to run on the Portainer server (bug)

An environment with no address (an edge agent, which calls Portainer) was assumed to be the Portainer server's own machine, so its containers were offered "on Granite". `followups.runs_at` now keys such a container by its environment, and `machine_of` names the machine by the declared server whose name the environment's name contains ("Bay Harbor - Anchor3" holds "Anchor3"), else by Portainer's environment name. The 0.79.5 test fixture gave a local environment no address, which real discovery never does (it carries the Portainer host); the fixture now matches.

## 0.79.10: the offer really names the machine (bug)

0.79.7 and 0.79.9 still said "on Granite": `machine_of` compared whole (address, container) keys, so two containers on one machine counted as two places and it gave up. It now compares addresses. The unit tests only had one container; there is now an end-to-end test (`PortainerOfferNames`) that runs the real sweep with a Portainer server reporting several new containers for another machine, both by address and as an edge agent.

## 0.79.11: devices that move together (#191 follow-up)

Many look-alike flows (a recorder pulling from eleven cameras, a host with many VMs) match no single port, though their total follows the device closely. `portpeers.together` grows a group from the best-matching port, or from ports already known to be alike, adding one only while the total follows the device more closely (by at least 0.03), never letting the total exceed 115% of what the device carried, and offering the group only when it beats its best member by 0.05 and reaches the "possible" threshold. The members are then not listed again. A group is named "your cameras (N combined)" when it grew from known camera ports, else "N devices together (names)". Nothing about cameras is required: camera ports (`App.camera_ports`, found by MAC or address from every camera source; the UniFi Protect module now reports `mac` and `host`, 0.1.1) only seed the search, and other kinds of known-alike devices can seed it the same way. Tests include 20 trials of unrelated random ports (never a group) and recovery of four real parts among thirty noisy ones.

## 0.80.0: Busiest client filters (#232)

The Busiest client graph carries an optional `filter` in `config/graphs.json` (so backups carry it), validated by `graphs.clean_filter` and storing only what differs from the defaults: `wired`, `wifi`, `servers` ticks (all on), `floorMbps` (1, was a fixed constant) and `exclude`, a list of `{mac | id, name}`. `busiest.allowed` applies it before the leader is chosen: a device on a switch port is wired, one only the gateway's flow log sees is the wifi side, a server is a port the map knows as a monitored server. Exclusions match by MAC in any notation (colons, dots, case) or, for a port with no MAC, by endpoint id; they show by name. A leader that gets filtered out is simply replaced, using the existing rules (60 s average, 1.5x challenger for 3 ticks, 60 s quiet). Only the card changes: port history, health, alerts and other graphs are untouched. Set in Settings → Graphs under the card; "Hide this client" on the card's panel adds the current leader.

## 0.80.1: wording, History and Alerts (#226, step 4)

History: the brief-blips tooltip pointed at Settings, Display for the confirmation time, which moved to Alerts; the history-bars box is now "Colours in the history bars" with plainer text. Alerts: clearer opening text and "Confirm a failure first"; a single system's own setting is reached with the **Edit monitoring** button on that system, never by editing JSON. Four stale code comments that named Display now name the page the setting lives on. The browser test that finds the moved box by its heading was updated on purpose.


## 0.80.2: wording, Graphs (#226, step 5)

Settings, Graphs now says "port" instead of "interface", explains the one-hour memory and the "graph tops out at" speed in plain words, and the Busiest client filters read as a short list of choices ("Hidden from this card", "Don't show devices using less than"). No behaviour changed; three browser-test selectors follow the new text on purpose.

## 0.80.3: wording, Power (#226, step 6)

Settings, Power: plainer intro (a system is ticked for you only when the backup itself says it is plugged in), "No systems are on it yet", "Not on a backup yet", "best guess" instead of "guessed". No behaviour change.

## 0.80.4: wording, Sites (#226, step 7)

Settings, Sites: clearer intro, "running MonitorBox" and "Can't reach it right now" (still Unknown underneath, only the words changed), "No other sites yet", the address line names the site port, and the port/pairing sentences read in plain order. No behaviour change.

## 0.80.5: wording, Backups (#226, step 8)

Settings, Backups: "settings" instead of "config" and "MonitorBox" instead of "App" in the intro and the list, plainer restore and delete questions, a clearer empty state. The stored backup kind is still `config`; only the label changed. No behaviour change.

## 0.80.6: wording, Updates and versions, This box, Advanced (#226, step 9) and two behaviour changes

Wording: "MonitorBox" instead of "App" in the Settings header, the update list and the memory line; "Installed software"; a one-line explanation of dev, beta and stable under the channel box; plainer This box and Advanced text, with "Here there be dragons." above the JSON editors and a pointer to **Edit monitoring** for one system's settings.

Behaviour, both asked for by the owner:
- **Per-module restart is gone** (button, `POST /api/modules/restart`, `Modules.restart`). Restarting MonitorBox is quick and covers it. A test checks the route no longer answers.
- **Factory reset also removes installed modules** (`releases/modules/` and `data/app/modules.json`, done by `wipe_settings`, so the forgotten-password `factory-reset` file does the same). Backups stay. On the next start `first_run_sync` downloads the channel's modules again, fresh (latest, no pins, no failed marks). Needs the release server to be reachable; offline, modules stay missing until it is. The e2e test plants a stale module folder and checks it is gone while the channel's modules come back.

Automatic updates are unchanged and work on dev, beta and stable (the channel only decides what is on offer). The round is now `App.auto_step()` so `tests/test_auto_update_channels.py` can prove it for all three channels, and that pinned, failed and switched-off items are left alone.

## 0.80.7: Advanced page layout (#226 follow-up)

The page intro was sharing a box with the network map button. Now: the Advanced heading, its description, "Here there be dragons.", then one section each (Network map with its own text, Performance, Switch report, Flows look, Preview the screens), and the two JSON editors last. No behaviour change.

## 0.81.0: safe to open over the internet, step 1 (#245)

New `security.py` and Settings → **Sign-in and security** (`config/security.json`, so backups carry it: `trustedProxies`, `publicHost`). Default: no trusted proxy, so a plain install behaves as before.
- **Who is asking:** forwarded headers (`X-Forwarded-For`, `-Proto`, `-Host`) are believed only when the connection itself comes from a listed proxy, and only the last forwarded address (the one the proxy added) counts. Anyone else sending those headers is just a direct visitor.
- **Lockout:** five wrong passwords from one address, then 60 s, doubling to 15 min; a quiet address is forgotten after 15 min; success clears it. If 30 wrong tries arrive through the proxy within 10 minutes from any addresses, outside sign-in pauses 5 min (direct home visits never do). A locked address is refused before any password hashing (no CPU cost to the box). Failed sign-ins are logged to stderr with the address, never a password.
- **Through the proxy:** `Secure` cookie when the proxy says HTTPS; HSTS header then; first-time setup refused (a reset box cannot be claimed from the internet); the signed-out health page no longer shows version or channel; with a public name set, other names get 421. Fixing a wrong public name: open the box by its home address (the check applies only through the proxy).
- **Everywhere:** `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: no-referrer`. (A full script policy is left out on purpose: the page uses inline script and the risk of breaking it is not worth it yet.)
- The page tolerates a health answer without a version (no reload loop).
Next: step 2 passkeys (0.81.1, below), then step 3 recovery.

## 0.81.1: passkey sign-in, step 2 (#245)

`passkeys.py`, standard library only. The owner first chose the `webauthn` package; this workspace cannot reach the package registry, so it could not be installed or tested here, and writing untested security code was the worse option. Own checker instead, which also means **no image rebuild**: it ships as a normal update. The package can still be swapped in behind the same endpoints.
- **Scope:** ES256 (ECDSA P-256, SHA-256) passkeys with no attestation, which is what Apple, Google and Microsoft passkeys are. Anything else is refused with a plain message. `verify_es256` is pure-Python curve maths on public data; the CBOR reader handles only what a passkey carries and is depth- and length-bounded.
- **Checks on both ceremonies:** our own one-time challenge (5 min), exact origin `https://<public name>` (or `http://localhost:<port>` when the public name is `localhost`, for tests), the site-name hash, user present and user verified (Face ID, Touch ID, PIN), a valid signature over authenticatorData + hash(clientData), and a signature counter that never goes backwards (counters that stay 0, as iCloud keychain passkeys do, are allowed). Registration needs a resident key (so "Sign in with a passkey" needs no username) and refuses duplicates.
- **Where it works:** only through the proxy over HTTPS under the public name set in Settings, Sign-in and security. Elsewhere, Settings says why.
- **Endpoints:** signed out `POST /api/passkeys/login/options|finish` (wrong tries count towards the lockout from step 1); signed in `GET /api/security` (lists passkeys), `POST /api/passkeys/register/options|finish`, `/api/passkeys/remove`. A passkey sign-in issues the same 90-day device sign-in as a password (`Auth.issue`).
- **Internet needs a passkey** (`internetNeedsPasskey` in `config/security.json`, a tick box under the list): through the proxy, `/api/login` answers 403, the login screen shows only the passkey button, and the home network keeps the password. It can be switched on only when a passkey exists, and removing the last passkey switches it off.
- **Storage:** `config/passkeys.json` (public keys, counters, names), so backups carry it. Step 3 adds the round-trip test with distinct values and lost-device recovery.
- **Tests:** `tests/test_passkeys.py`: a signature from an independent library, a software authenticator for register/sign-in with forged origin, site, kind, challenge, replay, copied counter, damaged signature, missing Face ID, unsupported key type and garbage input, and a real Chromium with a virtual Face ID that registers, signs in and exercises the internet-only rule.

## 0.81.2: recovery and backups, step 3 (#245)

- **Backups carry it all:** `config/passkeys.json` and `config/security.json` live in `config/`, so config and full backups bring back the passkeys (public keys, counters, names), the proxy address, the public name and the internet-needs-a-passkey choice. A round-trip test gives three passkeys distinct names, ids, keys and counters, restores both kinds of backup, compares every value, and signs in with each restored passkey (and refuses a stranger's).
- **Lost device:** sign in with the password from the home network (always open), remove that device's passkey, then **Sign out every other device** (`POST /api/signout-others`, `Auth.sign_out_others`: every saved sign-in except the asking one). Settings, Sign-in and security says so in those words. Removing the last passkey switches off "internet needs a passkey". For a lost password, the `factory-reset` file in the config folder still starts the box over (and now also removes installed modules; restore a backup after).
- **Count:** the page shows how many devices are signed in (`GET /api/security` `signedIn`).

## 0.81.3: Sign out this device on the Sign-in and security page

The lost-device section only offered "Sign out every other device". It now also has **Sign out this device** beside it. No behaviour change elsewhere.

## 0.81.4: Wi-Fi clients as candidates in "where its traffic goes" (#241)

- `lansampler` now asks the controller for its client list on every 10 s tick (one extra `stat/sta` request) and feeds each Wi-Fi client's `rxBps`/`txBps` into `PortSeries` under a stand-in switch named `wifi`, keyed `name|mac`. Clients that leave are dropped with `PortSeries.forget_ports`.
- `server.wifi_peers` offers them as candidates beside wired devices. The controller's direction names are not trusted: each client is tried both ways round and the better match wins. Only matches with r >= 0.7 (the existing "likely" bar) are shown, and flood-shaped matches are skipped. Same-name clients get the last five characters of the MAC in their label.
- Caveat: AP-reported Wi-Fi rates run well below real traffic (see 0.72.0). Matching is by shape (Pearson, scale-invariant), so this still works, but it is unverified on real hardware.
- Read-only: no new privilege or dependency.

## 0.81.5: Cameras and IoT ticks on the Busiest client card

- Two more ticks beside wired / Wi-Fi / servers, both on by default and stored only when off (`graphs.clean_filter`).
- Cameras: the addresses the connected camera sources (Protect, Scrypted) report. IoT: any client whose UniFi network or Wi-Fi name contains "iot" (`lanmap.is_iot`); the `unifi-network` module now reports each client's `network`. Nothing is guessed from the device itself, so a network not named IoT needs renaming or is not caught.
- Matching is by IP address (the map shows shortened MACs). The lists travel to `busiest.allowed` as private `_cameraIps` / `_iotIps` options built in `Server.busiest_opts`; only the card is affected.
- Hide list (same version): a comma-separated text box plus an on/off tick (`blacklist`, `blacklistOn`, stored only when set / off). A term matches part of the device's name, the last three pairs of its MAC address (all the map keeps; a whole address is read by its last six digits), or its IP address (whole, or a start ending in a dot such as `192.168.7.`), or part of the maker's name (the module now reports each client's `oui`; the map turns it into an address-to-maker table, `makers`). Capitals do not matter. Only the card is affected.

## 0.81.6: publish fix

0.81.5 changed the `unifi-network` module (client network and maker) without bumping its manifest version, so the dev build refused it ("already published with different content"). The module is now 0.2.19. Rule: any change under `modules/<id>/` bumps that module's `manifest.json` version in the same PR.

## 0.81.7: Settings → Graphs keeps its place when a time is tapped

The Main screen and Panel time buttons redraw the Settings page in place. Safari (the iPad) does not hold the scroll position through that, so a tap near the bottom threw the page back to the top. `keepY` put the page back, but on the iPad it still flashed to the top and back, so 0.81.8 stops redrawing: the tapped time is lit in place (`segOn`). The regression test turns scroll anchoring off in Chromium to behave like Safari and checks the page never leaves its place, not even for a moment.

## 0.81.8: Settings opens quickly after a restart

`/api/state` (which Settings waits for) asked each running module to `describe` itself one after another, 5 seconds each. Right after a restart the modules are busy with their first checks, so several busy modules added up to about 20 seconds. Cards never change for a version, so `Modules.describe` now keeps them (`cards`) and asks the ones not yet known all at once, waiting at most 2 seconds. A module that has not answered shows as running with "did not answer yet". Measured on the Pi is still to do; this is the best-supported cause, not a measured one.

## 0.81.9: the backup list no longer takes 14 seconds

The owner's performance report showed `GET /api/backups` averaging 14 s (max 28 s) while every other request took under 0.3 s, which is the 21-second first Settings page; the 0.81.8 module-card change was a guess that did not touch it. Cause: the launcher's `list_backups` finds each archive's manifest with `tarfile.extractfile("manifest.json")`, which reads the whole archive first (full backups hold the module releases), and the in-memory list was empty after every restart, so several Settings requests each read every archive. `backups.listing` now reads the manifest from the start of each file only (it is always the first entry), remembers each archive's row by name, size and time, and lets one reader work while the others wait for its answer. The launcher's own `list_backups` (used for restores) is unchanged: it ships in the container image.

## 0.81.10: a sharp copy still matches when two readings are a reading apart

Owner test of #241: a 30 GB server-to-server copy (Granite out about 9 Gbit/s, Anchor3 in about 7 Gbit/s) showed "not matched to anything" under "Where its traffic goes", with Anchor3 not named. A copy that stalls and bursts loses its correlation if the two ports' readings are one reading apart (simulated: r 1.0 in step, none at one reading apart). `portpeers.likely` now takes the best of the readings in step, one early and one late (`pearson_near`); the cost is negligible (random unrelated pairs still never reach "possible"). This is the best-supported cause; if Anchor3 still does not appear after this, the next step is to show the closest match found with its percentage so it can be read off the box.

## 0.82.0: more than one release repository (#265, part of #264)

The Updates page can follow several public GitHub repositories, not only the built-in one. Plan and decisions are on #264; this is its first step.

- **List.** The default (from `MB_RELEASES_URL`) is always first. Others are stored in `update.repos` (`id` = `owner/name` lowercased, `name`, `url`, `enabled`), the default's switch in `update.default_enabled`, so a settings backup carries them. The add box takes only `owner/name` or a github.com link (no other address, no sign-in, nothing to keep secret). The default cannot be removed in this version; a repo that installed modules still come from cannot be removed either (uninstalling and removing together is #266).
- **Checking.** `App.refresh` asks every switched-on repo for its catalog and the channel's pointer at once. A repo that cannot be reached says "can't reach" on its own line and keeps what was last known; it never fails the others and never marks a module failed (an outage is Unknown). The old `app.info` is now `app.infos`, one answer per repo, which is why `test_auto_update_channels` sets `infos` and gives its fake module the new `running`/`fromDefault` fields.
- **Source.** `update.module_sources` (module id → repo id) says which repo looks after each installed module. It is in the settings, so a config backup restores it; on a fresh box a restored source makes first-run install that module from that repo. `modules.json` now also records the installed build's `sha256`; modules from before that learn it from their repo's catalog at the next check.
- **Taking over.** After a check, a module moves to another repo only when its current repo is reachable but no longer offers the installed build (same `sha256`) and another switched-on repo offers exactly those bytes (this is the forklift: hello-world moves from `_new` to `_test`; settings, pins and history stay, they follow the module id). A different build under the same id is never taken over on its own, because a module's settings can hold passwords. If the old repo still offers the build too, nothing moves, with one exception: when the two repos' catalogs hold exactly the same builds (the same repo under a new name, whose old address GitHub keeps answering after a rename), every module moves by itself. A copy with more or fewer builds is not taken for the same repo, and the module shows "<repo> offers the same build" with an **Update from … instead** button (`/api/repos/adopt`).
- **Nothing installs from a stranger unasked.** A module that is not installed and comes from a non-default repo is shown with an Install button but is skipped by automatic updating and by Update all. Once the owner has installed it, it follows its updates like any other (the add box warns that a repo's modules run on the box and can see the passwords given to them).
- **Screen.** A Repositories box (checkbox per repo, Remove, add box with a confirm). With more than one repo the installed software is grouped under repo headings; with only the default the page looks as before apart from the box. `tests/test_ui_browser` now expects the extra "Repositories" heading.
- **Tests.** `tests/test_repos.py` (list rules, parsing, per-repo failure, taking over and not taking over, nothing unasked, backup round trip with distinct values) and `tests/test_repos_browser.py`.

## Repository names after cutover (#268, part of #264)

The source repo is `monitorbox`, the releases repo `monitorbox-modules` and, for now, the image `ghcr.io/sickicarus-labs/monitorbox_new` (the version 3 repos are `_deprecated`; see the note on the image name below). This changes the launcher's built-in releases address, the publish workflow's target, the image tag and the docs. Two things follow from how it is rolled out:

- The deployed compose file (`deploy/docker-compose.yml`) still names the old image until the image has been built under the new name and the owner re-pulls once; it is changed in a separate PR then.
- The App's default repo id is derived from its address (`owner/name`, lowercased). Once the launcher default points at the clean repo, the default's id becomes the clean repo's; a stored entry for the same id is shown once, as the default, and modules already taken over by it keep working. The `_new` entry is then no longer the default and can be removed (#269).

## 0.82.1: identical repositories no longer hand a module back and forth

Found on the owner's box right after the repo rename: 0.82.0's rule "the same repo under a new name takes its modules over" moved a module to the clean repo and then, at the next check, back to `_new`, because the two catalogs are identical and each looked like the other's successor (the cards kept showing the "offers the same build" button). A module now only moves toward a repository further down the list, never back. Regression tests: `test_the_same_repo_under_a_new_name_takes_everything_over_by_itself` (now checks three more refreshes) and `test_a_module_in_the_later_repo_is_not_pulled_back_to_the_earlier_identical_one`.

Image name: the first run of the Image workflow under the clean name failed to push. the push to `ghcr.io/sickicarus-labs/monitorbox` was refused (the log is not readable from here; the likely cause is that the package is still tied to the old, renamed repository). MonitorBox 3 is retired, so the old package can simply be handed over: in GitHub, Packages, `monitorbox`, Package settings, add this repository under Manage Actions access with write access (or delete the old package). Until then the workflow stays on `monitorbox_new`; then switch the tag here, the compose file and the launcher's note (#268).

## 0.82.2: the clean repository is the locked default (#269, part of #264)

The container image still has the old working name of the releases repository built in as its address, and building a new image is waiting on the image-name decision (#268). So the App itself treats `…/monitorbox-modules_new` as `…/monitorbox-modules` (`updates.LEGACY_URLS`, and `LEGACY_IDS` for sources saved under the old id). Effect: the old repository no longer appears as a separate repo and modules from it are seen as coming from the clean one. The old address keeps answering through GitHub's redirect, which is what the launcher itself still uses until the image is rebuilt.

- The default is locked: always on, cannot be switched off or removed (the API refuses, the tick box is greyed out). A saved "default off" from before is ignored.
- Repositories holding exactly the same builds are one repository under two names: neither offers the other a move button (`App.same_builds`), as before only the module moves once, toward the later one in the list.
- The stored copy of the clean repo (added by hand during the cutover test) is not shown twice.
- Tests in `tests/test_repos.py`: `test_a_repo_can_be_switched_off_and_on_but_the_default_is_locked` (replaces the earlier test that switched the default off, because the lock is what this version is for), the legacy address and id tests, and the no-button test for identical repos.

Image name, settled: the owner gave this repository write access to the `monitorbox` package (the old repository's link was removed), the Dockerfile now carries the `org.opencontainers.image.source` label for this repository, and the Image workflow pushes `ghcr.io/sickicarus-labs/monitorbox:latest` again. The compose file moves to it in a separate step, once the image exists and the owner is ready to re-pull.

## 0.83.0: uninstall a module, and remove a repository with its modules (#266, part of #264)

- **Uninstall** (module card, `POST /api/modules/uninstall`): stops the module and deletes its files, its record, its version choice and its source, and the saved connections that use it with the checks that came from them (the same removal as the connection's own Remove, so a system left with no checks goes too). A backup is offered first: none, settings, or full, made by the existing backup code. If the backup cannot be made nothing is deleted. The module is remembered in `update.uninstalled`, so neither a restart (first-run install), nor automatic updating, nor Update all installs it again; tapping Install on its card clears the mark.
- **Remove repository** (`POST /api/repos/remove`): a repo with no installed modules is removed after a plain confirm. One with modules asks `uninstall: true`; the modules are uninstalled (their connections deleted) after a single backup of the chosen kind, then the repo goes. Without `uninstall` the server refuses, so nothing is deleted by a stray call. The default repo still cannot be removed.
- The Updates view now says per repo which modules are installed from it and how many connections each has (`repos[].installed`, `repos[].uses`), and per module `uses`, `installed` and `declined`.
- Tests: `tests/test_uninstall.py` (distinct secrets per connection, backup holds what is about to go, failed backup deletes nothing, one backup per repo removal, an uninstalled module stays uninstalled) and a browser test in `tests/test_repos_browser.py`.

## 0.83.1: the old-name shim is gone (#282, part of #264)

Both boxes (Bay Harbor and Tidewater) run the image whose built-in releases address is `…/monitorbox-modules`, so the App no longer maps the old `…/monitorbox-modules_new` address and id (`LEGACY_URLS`, `LEGACY_IDS`, `canon_id` and their tests are deleted). A box that somehow still runs an image with the old address would show the old repo as a separate repository. A stored copy of the default repo (made during the cutover) is still shown once.

## 0.83.2: "new things" added from Portainer keep their web address and links (#284)

Adding what a Portainer connection newly found (the follow-up and "new items" paths) copied only six parts of each item. A container's web check lost its type and address and became an empty module check ("Portainer has no environment called 'None'"), and containers lost their `service` (icon, link) and `requires` (the environment they sit under, so they landed in "Other"). Both paths now use `monconfig.watch_item`, which keeps every part that matters (`ITEM_KEYS`). Adding such an item again also replaces an empty web check saved by an earlier version with the real one. Tests: `tests/test_followup_items.py`.

## 0.83.3: "Where its traffic goes" says when the box has only just started reading (#262)

Right after a restart the port history is a minute or two long, and the panel showed a flat "not matched to anything" for traffic it simply had not learned about yet. `PortSeries.history_seconds` gives how long a port has been read; `lan_peers` returns it as `history`, and `lan_flows` adds `history` and `young` (true when the history is under 90% of the window shown). While young, the leftover row is called "not matched yet" (sub-text "still working out where it goes") and a line above the list says how long the box has been reading and that matches appear after a few minutes. Once the window is full the old wording returns. Tests: `tests/test_lan_peers.py` (flows list), `tests/test_portpeers.py` (history length).

## 0.83.4: made-up names and addresses everywhere (launch scrub, #128 follow-up)

Before the repository goes public, the owner's real server names and the example addresses from his network were replaced by made-up ones in the code, the demo mode, the tests and the docs (Bay Harbor and Tidewater for the sites, Granite and Anchor3 for servers, Aurora for a helper box, Cedar hut for a container stack, 192.168.77.x for the example addresses). The new names keep the same alphabetical position as the old ones so sorted lists stay in order. Behaviour is unchanged. Components whose files changed (comments only for the modules and the launcher) carry new versions: app 0.83.4, portainer 0.1.6, unifi-network 0.2.20, wol 0.1.1.

## 0.83.5: a site's Updates page shows that site's own channel

With a far site's tab open, Settings, Updates drew the channel dropdown (and the "Install updates automatically … on the X channel" line) from the main box's own state (`state` is always answered by the main box), so the far site's real channel never showed and a change looked as if it had snapped back. The change itself always reached the far site (`POST /api/channel` is passed through like every other call). The page now reads the channel from the Updates view (`versions`), which is passed through to whichever box is selected. Test: `tests/test_sites.py`, `test_a_sites_updates_page_shows_and_changes_that_sites_channel_not_the_main_boxs`.

## 0.83.6: the built-in repository has no tick box; the page header follows the site tab

- The built-in repository's tick box looked tickable (a lighter blue) although it cannot be switched off. It is now left out of that row entirely; the row says "built in".
- The line under the Settings page titles ("MonitorBox 0.83.5 · channel dev") read the main box's own state, so it showed Broad Leaf's version and channel under every site's tab. It now reads the Updates view, like the channel drop-down (0.83.5). Tests: `tests/test_repos_browser.py` and `tests/test_sites.py`.

## 0.83.7: the box says when its container image needs re-pulling

The App and modules update by themselves, but the image (the launcher, Node, Python) only changes when the owner re-pulls it, and nothing told him a newer one was needed. Now:

- `launcher/monitorbox_launcher/VERSION` is the image's own version. The launcher writes it to `state.json` (`launcher_version`) at start-up.
- The release build writes `launcher: {"version": …}` into the channel pointer: the image version that release was built for. It moves with promotion, so a box on `stable` is only asked for what `stable` was built for. Older boxes ignore the key.
- The App compares the two (`versions.image`, numbers not text). Only when both are known and the box's image is older does `/api/versions` carry `image.outdated`; the bell then lists "The container image needs updating" and the Updates page explains how to re-pull (Portainer: Update the stack, Re-pull image). An image from before the version was recorded, or a release that does not say, gives no notice.
- `tools/check_versions.py` fails a pull request that changes `launcher/` code or the `Dockerfile` without bumping the launcher VERSION, which is what keeps the notice honest.
- Limit: a refresh of only the base image (no launcher change) is not detected. Bump the launcher VERSION when one matters. Watchtower, run by the owner, remains an option for people who prefer automatic pulls; MonitorBox does not ship or control it (read-only rule).
