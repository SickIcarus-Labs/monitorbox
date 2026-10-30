# UniFi Protect module

What the UniFi Protect module reads, how it decides, and what it never does. The code is `modules/unifi-protect/`; the tests are `tests/test_unifi_protect.py`. Everything here is read-only: the module logs in and reads. It cannot record, move a camera, restart anything or change a setting. For what the core app does with a module's answers (states, hold-down, alerts), see [the core app page](../APP.md).

## What it brings

- The health of every UniFi Protect camera: connected, offline, starting, updating, or not recording when it should be.
- The Protect recorder (the NVR) by name and version, and its recording space.
- Each recording drive's temperature and its own health verdict.
- A still picture of each camera, for the Cameras panel.

## What it talks to and how

It talks to a UniFi OS console that runs Protect (a Cloud Key, Dream Machine or UNVR), over HTTPS. The address is the connection's `host` or `base_url`. With no scheme it uses `https://`; without a port it uses 443. A port written into the address is kept (`192.0.2.10:8443`). Any path in the address is dropped. Environment proxy settings are ignored.

It sends only these requests:

| Request | Used for |
| --- | --- |
| `POST /api/auth/login` with the user name and password (`remember` false) | Logging in. The only POST it ever sends. |
| `GET /proxy/protect/api/bootstrap` | The recorder and every camera and their state. |
| `GET /proxy/protect/api/nvr` | The recorder's drives (only for drive checks and for finding drives). |
| `GET /proxy/protect/api/cameras/<id>/snapshot` | One camera's still picture. The id must be 6 to 40 letters or digits. |

- The login session cookie is kept in memory and reused. If a request is answered 401 or 403 it logs in again once.
- Answers are shared for 5 seconds, so checks that run together cause one request.
- Each request waits 8 seconds by default (the connection's `timeout` setting changes that).
- Certificates are not checked unless "Check the console's certificate" is ticked, because consoles use self-signed ones. The password only goes to the address in the connection.
- After a refused login it does not try again for 60 seconds, so a wrong password cannot lock the account.
- A picture larger than 3,000,000 bytes, or one that is not a JPEG or PNG, is refused.

## What you need to provide

- The console's address (the server's address on Settings > Servers).
- A user name and password for a **local** UniFi OS account that can only view Protect. In UniFi OS, create the local user and give it view access to Protect only. The module logs in on the console itself.
- Nothing else. If a UniFi Network connection already exists on the same address, the app can copy its address and login for you (see below). The login is copied on the box and the password never reaches the browser.

## Adds to the app

- **Check types** (see "What it alerts on"): `camera`, `cameras`, `nvr`, `storage` and `drive`.
- **Discovery.** Once the connection works, the module offers: "Protect recorder" and "Protect storage" (batch Overview), one "Camera <name>" per camera (batch Cameras), and one "Protect drive <model> (slot N)" per drive that reports a temperature or a health value (batch Drives). All go in the Cameras group. Each camera and each drive becomes its own item, so an offline camera shows as Down by name.
- **The Cameras card.** Tapping it opens a panel with a picture of every camera from every camera source, with its state and detail line. The module answers the app's source-neutral "cameras" and "snapshot" requests. Pictures show as snapshots (the panel says "A new snapshot about every second"); a camera that is offline has no picture requested.
- **Folded lists.** Camera items fold under "UniFi Protect cameras" and drive items under "UniFi Protect drives".
- **Suggestions.** A UniFi Network connection with no Protect connection on the same address gets a suggestion, "UniFi Protect on <address>" ("Found more you can add", and "Add with the same login" on the Set up page). One tap copies the address, login and certificate choice, saves the connection and starts watching everything the module offers by default.
- **One camera, two sources.** A camera that both Protect and Scrypted report (same name) shows once, from Protect. If one source says it is down and the other says it is fine, the app shows it as Degraded, not Down. Live video is not from Protect: it needs Scrypted, and Protect cameras show snapshots only.
- **Camera addresses.** The module passes each camera's hardware address and IP address to the app. The app uses them to find the switch ports cameras are on and for the Busiest client "Cameras" tick (unticking it hides cameras from that list).

Without this module the app has no Protect camera health, no recorder or drive checks, no Protect pictures, and no camera addresses from Protect (Scrypted can still supply cameras).

## How it is configured

1. Open Settings > Servers. Open the server (or choose Add a server, give it a name and the console's address, and press Next).
2. Under Add, press "UniFi Protect (cameras)".
3. Fill in User and Password. Leave "Check the console's certificate (leave off for a self-signed one)" unticked unless the console has a real certificate.
4. Press "Test connection". It reports "It answered in N s" with what it found, for example "Found: Overview 2 · Cameras 4 · Drives 2", or an error in plain words.
5. Press "Save, then pick what to watch" and tick what to watch. Each item can be changed later with "Pick what to watch" or "Edit" on the server's page.

Drive checks have a temperature limit of 55 °C. It is stored with the check (`max_c`) and has no field in the connection form.

## What it alerts on and how states map

A console that cannot be reached, a refused login, or a console with no Protect is **Unknown**, never Failed. Only a camera or disk that the console itself says is bad can make a check Failed. The core app applies its normal hold-down and alert delay on top.

| Check | Healthy | Degraded | Failed | Unknown |
| --- | --- | --- | --- | --- |
| `camera` (one, by name) | Connected. The detail says recording, "records on motion", "records on a schedule", "recording is off" or "motion now". | Being adopted, updating its firmware, connecting, or connected but not recording although set to record all the time. | Offline or disconnected ("offline, last seen N min ago"). | The camera name is missing or no longer exists, or the console cannot be asked. |
| `cameras` (all, or those named) | All fine ("N of M cameras fine"). | Some are Degraded ("needs a look"). | Any is offline ("offline: ..."). | No cameras, or the console cannot be asked. Not offered by Re-detect any more. |
| `nvr` | The console described its recorder (name, Protect version, uptime in days). | Never. | Never. | The recorder was not described, or the console cannot be asked. |
| `storage` | Space and disks fine. Shows "X of Y used" and "N disks healthy". A nearly full recorder is normal (it overwrites the oldest video), so fullness is shown, never judged. | Never. | A disk reports itself unhealthy ("disk not healthy: <model>"). | No storage figures at all, or the console cannot be asked. |
| `drive` (by slot) | Cool and healthy; the detail shows the temperature. | Temperature at or above the limit (55 °C by default), bad sectors up from the first count seen, drive health not "good", drive state not "normal", or the drive reports a reason. | Never. | Drive not listed, no slot given, the drive reports nothing, or the console cannot be asked. |

- Recording "off", "on motion" or "on a schedule" is the owner's choice and reads Healthy.
- Bad sectors: the first count the module sees is the baseline. Only growth is reported. The baseline is kept in memory only.
- A drive that Protect shows as not compatible (`hddNotCompatible`) is not read as a problem.
- Module checks run every 15 seconds by default.

## Known limits

- Cameras and the recorder only. No motion history, no recordings, no video. Motion is only "motion now" on a camera line.
- Live video is not provided; it comes from Scrypted.
- Pictures are fetched, shown and forgotten; nothing is stored.
- Bad-sector growth is lost when the module restarts.
- Field names follow the UniFi OS Protect API and are read defensively. A field a console does not send reads as "not reported", never as a failure. Drives only appear in discovery if the console reports them on its `nvr` answer.

## Troubleshooting

These are the messages the module produces. The Test connection box shows a plain-words version, with the exact text under "Technical detail".

| Message | Meaning |
| --- | --- |
| `this connection has no 'host' or 'base_url'` | The server has no address. |
| `this connection needs a 'username' and 'password' (a local account that can only view Protect)` | One of them is empty. |
| `cannot reach UniFi Protect at <address> (<reason>)` | Nothing answered, the name did not resolve, or the connection timed out. Check the address, the port and that the box can reach it. |
| `cannot log in to UniFi Protect: the username or password was refused` | HTTP 401 on login. |
| `cannot log in to UniFi Protect: the login was refused` | HTTP 400 or 403 on login. |
| `cannot log in to UniFi Protect: this is not a UniFi OS console` | HTTP 404 on login. The address is not a UniFi OS console. |
| `cannot log in to UniFi Protect: the console says too many login attempts` | HTTP 429. |
| `cannot log in to UniFi Protect: the console answered HTTP N` | Any other login status. |
| `... (not retrying for a minute, so the account is not locked out)` | A login was just refused. Fix the login and wait a minute. |
| `the console accepted the login but sent no session` | Login worked but no cookie came back. |
| `UniFi Protect refused this account's access (give it view access to Protect)` | The account logs in but cannot read Protect. |
| `this console has no UniFi Protect (or it is not running)` | HTTP 404 on Protect's address. |
| `UniFi Protect answered HTTP N` | Any other unexpected status. |
| `UniFi Protect sent an answer this module cannot read` | The answer was not the expected JSON. |
| `UniFi Protect reports no cameras` | The console lists none (or all named ones are missing). |
| `UniFi Protect has no camera called '<name>' any more (it has: ...)` | A watched camera was renamed or removed. The message lists the names that exist. Change what is watched. |
| `this check needs a camera 'name'` / `this check needs a drive 'slot'` | The check has no camera name or drive slot. |
| `UniFi Protect does not list that drive (it may be out, or the console did not report its drives)` | The slot is missing from the recorder's drive list. |
| `UniFi Protect reports nothing about this drive` | The drive has no temperature or health value. |
| `UniFi Protect did not report its storage` / `did not describe its recorder` | The console left those parts out. |
| `the snapshot is larger than expected` / `the camera did not return a picture` / `that is not a camera id` | A picture request was refused. |
| `unknown UniFi Protect check '<name>' (known: ...)` | A check type the module does not have. |
| `the unifi-protect module is not running` / `did not answer` | Raised by the app, not the module. The check is Unknown. |

A certificate message in the Test box means the "Check the console's certificate" box is ticked and the console's certificate is not trusted: untick it for a self-signed console.

## Where it lives in the code

| What | File |
| --- | --- |
| Module id, version, request handling, one client per login | `modules/unifi-protect/main.py`, `manifest.json` |
| The read-only console client (login, back-off, snapshot) | `modules/unifi-protect/protectlib.py` |
| States, camera list, discovery, drive rules | `modules/unifi-protect/protectchecks.py` |
| Cameras panel, picture merging with Scrypted | `app/monitorbox_app/server.py` (`CAMERA_SOURCES`, `cameras`, `camera_snapshot`) |
| Suggestion from UniFi Network, copied login | `app/monitorbox_app/followups.py` |
| Settings > Servers form and help text | `app/monitorbox_app/ui.py` (`SVC`) |
| Same camera from two sources | `app/monitorbox_app/engine.py` |
| Tests | `tests/test_unifi_protect.py`, `tests/protect_fake.py` |
