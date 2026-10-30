# The App: what it checks and how it is configured

This page describes the core App: the part of MonitorBox that runs the checks, decides what is healthy, sends alerts and holds your settings. It is written for someone who has never seen MonitorBox. Where a feature only exists because a module feeds it (Port errors, the network map, Busiest client, cameras, power views), this page says so and does not describe it as part of the core. The page that maps features to modules is [the capabilities map](CAPABILITIES.md); each module page says what that module adds.

Everything here is read-only. MonitorBox looks at things and tells you; it does not restart, repair or control anything. The one exception is Wake-on-LAN, which is a module.

The code for each rule is named in the last section.

## What the App checks by itself

Four kinds of check need no module. Each one answers "worked", "did not work" or "could not be checked here".

| Check | What it does | Looked at every |
| --- | --- | --- |
| **Ping** | Sends one ICMP echo and waits (2 s by default). Needs the container's raw-network permission; without it the answer is "could not be checked", never "down". | 5 s |
| **Port (TCP)** | Opens a TCP connection to a host and port (3 s by default). Says whether the port is open, refused or timed out. | 5 s |
| **Web (HTTP)** | Fetches a web address (5 s by default). Healthy means a status code you accept (200 to 399 unless you change it). Optional: a piece of text the page must contain, so a login page or a different app on the same port does not read as healthy. A private-network address with HTTPS skips certificate checking, because a device's own certificate is almost always self-signed and can never match a bare address; names on the internet are checked fully. | 30 s |
| **DNS** | Asks one named DNS server to resolve a name (google.com unless you change it) and says whether that server answers. | 5 s |

A check that is failing is looked at again every 3 seconds, so recovery shows quickly. Every check can have its own interval and timeout.

A ping that answers slower than 200 ms three times in a row adds a heads-up line ("slow") to the item. It does not change the item's state.

**Built-in Internet checks.** A new box starts with a small Internet group: ping to 1.1.1.1 and 8.8.8.8 (the item "Internet" is healthy if either answers), DNS through each, and a web check of google.com. They let MonitorBox tell "no route to the internet" from "my local DNS is broken" from "public DNS is broken". You can switch them off in the monitoring settings; they cannot be edited one by one.

**Other sites.** A paired MonitorBox at another site appears as a "<name> link" item. That is part of the multi-site feature, described under [Several sites](#several-sites).

### What only looks built in

These need modules and are not described as core:

- Port errors, the network map, link awareness: UniFi Network and/or SNMP.
- Busiest client: UniFi Network.
- Cameras: UniFi Protect and/or Scrypted.
- Power and UPS views: NUT.
- Container views: Portainer.
- Waking a machine: Wake on LAN.

## How modules plug in

A module is a small separate program the App starts and talks to over its standard input and output, one JSON message per line. A module crashing takes down only that module. Modules are downloaded into the config folder and update in place; only the launcher is in the container image.

- **Connections.** A login or address for a device or service is entered once, under Servers, and checks refer to it. A module check is a check of type "module" that names the module, the kind of check and the connection.
- **Check types a module adds.** The module says what it can check for a connection (for example a disk, a CPU, a camera, a UPS). The App asks for one answer per check and turns it into healthy, degraded, failed or unknown.
- **Discovery and suggestions.** Once a connection works, the module can list what it found (disks, interfaces, cameras, containers). Nothing is watched until you say so; only your decisions are stored. The App also proposes additions from what is already connected (a UniFi Network login whose address also answers on the Protect port, a server answering on Scrypted's usual port). It makes one plain TCP connect (or, for SNMP, one small UDP message) to one well-known port per address you already declared; it never scans your network.
- **Start-up.** A module starts when something needs it. A new box installs only Wake on LAN at once, because nothing can detect that someone wants it; every other module is installed when a connection to a device of its kind first appears. While a module is still starting, its checks wait and ask again about a second later instead of saying "not running".
- **When a module is missing, slow or broken.** The check is **Unknown**, never Failed. The wording says why ("the snmp module is not running", "did not answer"). Only the module that actually talked to the device can say it is down.
- **Sample module.** "hello" is a template for module authors. Only the dev channel offers it; a box on beta or stable never installs it.

## States and how they combine

A thing on the screen is a **system** (one or more checks) or an **aggregate** (a group of systems). Each has one state:

| State | Shown as | Means |
| --- | --- | --- |
| Healthy | green | everything checked is fine |
| Degraded | yellow | it answers, but not properly |
| Down (failed) | red | it is not there, or answered wrongly |
| Unknown | blue | it could not be checked right now |
| Checking (pending) | | no result yet |

**One system, several checks.** By default the first check is "is it there" and the rest are "is it working properly": if the first fails the system is Down, if the first cannot be checked it is Unknown, and a later problem makes it Degraded. A system can instead use the "any" rule, where it is healthy if all pass, Degraded if some pass, and Down only if all fail.

**Aggregates.** An aggregate over children with the "any" rule is healthy when all children are, Degraded when some are, and Down only when every child is down (Unknown if the rest cannot be checked). With the "all" rule any Down child makes it Down. The built-in Internet item is an "any" aggregate of the two pings.

**The main screen.** The headline follows the worst state, in this order: red, yellow, blue, green.

- Green, "Everything is fine".
- Yellow, "Something's not right": something is degraded and nothing is down.
- Red, "Something's down": something is down. A separate, stronger headline is used when something marked critical is down.
- Blue, "Something needs a look": something cannot be checked. The wording says nothing is known to be broken.

Every state is also written as text, never colour alone. A status change reaches the screen within about two seconds without refreshing.

### Confirmation (hold-down)

A blip should not reach the screen or a phone. When a check first fails, the App looks again about 2 seconds later before believing it. Then a failure (or a warning) must also last: by default **2 failures in a row over at least 60 seconds** before the thing turns Down or Degraded. Until then it stays healthy, with a heads-up line under the green headline such as "failed just now, confirming (1 of 2 in a row, 12 s of 60 s)". You can change the site-wide setting (1 to 20 failures, 0 to 3600 seconds) and override it per system. A success shows at once. Unknown shows at once and is never turned into Failed.

History is not held back. It records what each check actually answered, and the bars hide stretches shorter than the grace period when drawn.

### Dependencies, "affected by", expected down

- **Depends on.** A system can depend on others (a container on its host, anything behind the Internet item). When something is down because something it depends on is down, it is marked **affected by** the root cause. It keeps showing what was actually observed, and it does not raise its own alert. One root cause, one alert.
- **Unknown propagates the same way.** Things behind a provider that cannot be reached are Unknown because of it.
- **An aggregate that is down** explains its children (Internet down explains both failed pings), unless every child already has its own root cause.
- **Powered by.** A system can say which UPS powers it. If that UPS is down, or running on battery, low, or shutting down, a system that then goes down is explained by it.
- **Expected down.** You can mark a system as expected down (for example a machine you switch off at night). It shows grey, its observed state is unchanged, and it raises no alert.
- **Critical.** Core things (servers, core network gear, the Internet item) can be marked critical. Onboarding proposes it and you can change it. It affects the headline, the order of the attention list, and the order and flag in alert messages; it never changes a state.

Observed state is never rewritten. Dependencies and "expected down" only affect what is explained and what alerts.

The App has no maintenance windows or silences yet. The tools for "I am restarting this on purpose" are expected down and the alert delay.

## Alerts

What counts is exactly what the main screen's "Needs attention" list shows: one alert per root cause, nothing for what is marked expected down, nothing for heads-up notices, and nothing for Unknown unless you tick it.

- **When.** A problem is announced after it has lasted the alert delay (60 seconds by default). A "back" message follows after the thing has stayed healthy for 30 seconds.
- **Updates.** Going from degraded to down, or back, while a problem is open sends an update.
- **Storms.** Three or more new problems within a minute are sent as one message ("6 things went down at once"), and one message when they are all back.
- **Flapping.** A thing that goes down three times in ten minutes is one message, then one more when it has been steady for ten minutes.
- **Power.** A UPS running on battery, low, or shutting down is announced at once and never held back by the storm or flap rules. While that alert is open, and for 10 minutes after it clears, the systems it powers do not alert for being down.
- **Delivery.** Alerts go by **email** (any SMTP server, STARTTLS, SSL or none) and/or **Home Assistant**. For Home Assistant you can connect as a Home Assistant user and tick which phones and tablets with the app should get alerts, or use a webhook address. Home Assistant answers 200 to any webhook address, so a typo shows no error; that is why the page shows the address. A message that cannot be delivered is tried again (5 s, 15 s, 45 s, up to 5 minutes apart) for 30 minutes. Open alerts and undelivered messages survive a restart or update.
- **Triggers you can tick:** down, degraded, unknown (off until you ask for it) and restored.
- Secrets (SMTP password, Home Assistant tokens, webhook address) live only in the alerts file, are never shown after saving except where a typo must be found, and are never written to a log or an error message.

## How it is configured

Everything is a screen first. The JSON editors are under Advanced and are for repair, not setup.

The Settings page has these sections:

| Section | What it holds |
| --- | --- |
| **Display** | Summarized or Detailed main screen, and how far back the history bar reaches. Both are per device. |
| **History** | What was not healthy and when; which states the bars show. 30 days are kept. |
| **Servers** | The machines MonitorBox watches and how it reaches them (connections). |
| **Power** | Which UPS keeps what running. |
| **Graphs** | Which traffic graphs to show and how much time they cover. |
| **Alerts** | Who is told, which triggers, and how long to wait first. |
| **Sites** | Other MonitorBoxes, managed from here or managing this one. Only on the main site's own page. |
| **Sign-in and security** | How the box is reached from outside, trusted proxies and lock-outs. |
| **Backups** | Automatic backups, download, restore. |
| **Updates and versions** | Channel, installed versions, module updates. |
| **This box** | Time zone, memory use, restart, factory reset, sign out. |
| **Advanced** | Network map, performance report, switch report, flows, JSON editors. |

**Monitoring items.** Each system has a name, a group (Servers, Network, Internet, Power, Cameras, Services), its checks, a rule, what it depends on, what powers it, whether it is critical or expected down, an optional opened link, and optionally its own confirmation settings. Onboarding and suggestions create most of these for you.

**Safe edits.** Every change to the monitoring settings is validated before it is saved. A bad edit is refused with every problem listed, and nothing changes. The last 20 saved versions are kept so a change can be undone. A bad file on disk never takes the app down: it keeps running on the last good setup and shows the exact error.

**Sign-in.** There is one admin password (stored only as a salted hash), with passkeys as another way in. A sign-in lasts 90 days after its last use and each device has its own. Wrong passwords are slowed from one address after five tries, and a burst of guesses from many addresses pauses outside sign-ins. For outside visits behind a reverse proxy (such as Caddy), the proxy's address must be listed as trusted before its forwarded headers are believed.

**Updates and channels.** Three channels: dev (newest, may be rough), beta and stable. A beta box sees beta and stable versions; a stable box sees stable only. The App checks automatically; installing is a button unless auto-update is switched on (off by default). An update is downloaded, its checksum verified (a mismatch is refused), the data snapshotted, and the new version activated and watched; it is rolled back automatically if it does not stay healthy. Modules can be updated and pinned one by one. If a release needs a newer container image than the one running, the bell and the Updates page say so and you pull the new image yourself. Extra releases repositories can be added on the Updates page.

**Backups.** A settings backup is made nightly and a full backup (settings plus data) weekly, once there is something worth keeping. You can also make, download and restore one by hand. Restoring validates the file, stages it, migrates it, swaps it in and checks health, and puts the original back if anything fails. The password the box had is kept through a restore. Backups never include the backups folder or live sign-ins.

## Several sites

One MonitorBox per site; one (the main one) is paired with the others and can manage them. Control goes one way only. They talk over a separate site port (8443 by default, off until switched on) with a pre-shared key created at one-time pairing. If the link drops, each site keeps watching and alerting on its own. A silent link alone proves nothing, so the sites tell each other their public addresses and judge a silent link by pinging that address from outside the tunnel: the address answers, Degraded; it does not and this box's own internet is fine, Down; this box's own internet is down too, Unknown. Trouble at another site is listed under Needs attention and can alert, but never changes this site's own headline.

## Where the data lives

Everything is under the config folder (`/config` in the container). Backups are never inside a backup.

| Folder | Holds |
| --- | --- |
| `config/` | `monitorbox.json` (systems, connections, intent only), its `revisions/`, `history.jsonl`, alert settings and state, display and graph settings, sites and security settings, passkeys. These are the files a settings backup carries. |
| `data/app/` | The password record, module install state, the last readings, the last map, the port-error history. |
| `data/local/` | Live sign-ins; never carried by a backup to another box. |
| `releases/` | Downloaded App and module versions. Switching version is changing a link. |
| `backups/`, `logs/` | Backup archives and logs. |

**What survives a restart.** Settings, alert state, history, and the port-error history do. The latest readings are saved every 20 seconds, and for the first two minutes after a start the App may show readings up to 10 minutes old (marked as saved) while fresh ones come in; a long outage is not treated as "just a restart". History keeps 30 days as state changes only. While the App was off, every item reads Unknown for that gap, never Healthy and never Failed. Availability figures leave Unknown time out.

Secrets (device logins, SMTP password, tokens) are stored in plain text in these files, readable only by the app (mode 0600), shown as dots in the editor and never logged. Protect the config folder.

## Where each rule lives in the code

| Rule | File |
| --- | --- |
| States, aggregates, dependencies, "affected by", headline, attention list | `app/monitorbox_app/engine.py` |
| Scheduling, intervals, hold-down, grace period, saved readings | `app/monitorbox_app/monitor.py` |
| Ping, TCP, HTTP and DNS checks | `app/monitorbox_app/probes.py` |
| Module start-up, protocol, "Unknown not Failed" | `app/monitorbox_app/modules.py` |
| Settings validation, built-in Internet checks, revisions | `app/monitorbox_app/monconfig.py` |
| Alert rules, delivery, retries | `app/monitorbox_app/alerts.py`, `mailer.py`, `ha.py` |
| History | `app/monitorbox_app/history.py` |
| Suggestions | `app/monitorbox_app/followups.py` |
| Sign-in and lock-outs | `app/monitorbox_app/auth.py`, `security.py`, `passkeys.py` |
| Updates and channels | `app/monitorbox_app/updates.py`, `versions.py` |
| Backups | `app/monitorbox_app/backups.py`, and the launcher's backup code |
| Sites | `app/monitorbox_app/peer.py`, `wanaddr.py` |
| Screens | `app/monitorbox_app/ui.py` |
