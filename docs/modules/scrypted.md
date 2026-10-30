# Scrypted module: cameras and live video

What the Scrypted module reads, what it adds to MonitorBox, and what it never does. The code is `modules/scrypted/main.mjs`; the tests are `tests/test_scrypted_module.py`. Everything here is read-only: MonitorBox logs in to Scrypted, looks at its cameras and asks for pictures. It does not change a setting, move a camera or record anything. For what the core app does with these answers, see [the core app page](../APP.md).

## What it brings

[Scrypted](https://www.scrypted.app) is a camera hub that many people run in front of their cameras (and HomeKit or other systems). This module lets MonitorBox:

- tell whether Scrypted itself is answering,
- list the cameras and doorbells Scrypted shows to the account you give it, and whether each one is online,
- take a still picture from each camera,
- show **live video** from cameras that support it.

## What it talks to and how

- **Where:** Scrypted's web address, `https://<address>:10443` by default. The address comes from the server's **Address** on the Servers page and the **Port** field (10443 if left empty). The module also accepts a full web address (`base_url`) in the saved connection, but the screens only ask for an address and a port.
- **What it does there:** it logs in with the user name and password you give it, using Scrypted's own client library (`@scrypted/client`, version pinned in `package.json`). Then it lists Scrypted's devices and reads each device's name, type, interfaces and online flag. Only devices of type Camera or Doorbell are used.
- **Pictures:** it asks one camera for one picture and converts it to JPEG. It gives up after 15 seconds for the picture and 15 more for the conversion. A picture larger than 3,000,000 bytes, or an empty one, is refused.
- **Live video (WebRTC):** MonitorBox only carries the setup messages. When you ask for live video, the module starts a signalling session with that one camera (`startRTCSignalingSession`) and Scrypted asks your browser, through MonitorBox, to build the WebRTC offer and answer. The video itself goes between Scrypted and your browser, never through MonitorBox. A live view ends after 10 minutes, and the screen simply starts it again. Setup must finish in 30 seconds. At most 10 live views are open at once.
- **Across sites:** if the browser cannot reach Scrypted directly because the camera is at a managed site, the video can be relayed between the two MonitorBoxes inside the existing site link. The packets are not read or changed, so the video stays encrypted end to end between Scrypted and the browser. See `app/monitorbox_app/liverelay.py`.
- **One login per Scrypted account:** the module keeps the connection open and shares it between checks. If Scrypted refuses the login, the module does not try again for 60 seconds, so a wrong password cannot lock the account.
- **Certificate:** Scrypted normally uses a self-signed certificate. With **Check the certificate** off (the default), certificate checking is switched off for this module's own process only.

## What you need to provide

- **A Scrypted user that is not an admin**, with only the **Camera** and **VideoCamera** interfaces of the cameras. For live video it also needs the **RTCSignalingChannel** interface on those cameras (view only). Do this in Scrypted, under the user's settings. This is also described in [the install page](../INSTALL.md).
- **The address and port** of Scrypted (default 10443).
- **The MonitorBox image that includes Node.** The module is a Node program. The Settings screen says it needs the newer MonitorBox image.
- Nothing is needed on the cameras themselves. Scrypted must be able to reach them; MonitorBox never talks to the cameras directly.

## Adds to the app

- **A Cameras group and card** on the main screen, with one item "Camera <name>" per camera and one "Scrypted" item for the server.
- **Snapshots:** the camera drawer asks for a new picture about every second per camera.
- **Live video:** the Live switch in the camera drawer, a "Go live" button on each camera, and a Light / Balanced / Sharp quality choice. This is the only source of live video. The app's live view code refuses any connection that is not Scrypted ("Live video comes from Scrypted only.").
- **Camera discovery:** after the connection works, the module lists the cameras and offers ready-made items to tick.
- **Suggestions:** the app proposes "Scrypted on <address>" when a server you already added answers on port 10443, and when Portainer reports a container named or imaged "scrypted". It makes one plain connection to that port per declared address and never scans the network.
- **The same camera from two sources:** if UniFi Protect and Scrypted both list a camera with the same name (ignoring capitals), the camera list shows it once. The picture comes from Protect, and live video still comes from Scrypted. Alerting treats the two as one camera.

Without this module the app has no live video, and cameras come from UniFi Protect only (pictures and status, no live view).

## How it is configured

1. Open **Settings > Servers** and choose **Add a server** (or open the server that runs Scrypted). Give it a **Name** and an **Address**.
2. Under **Add**, choose **Scrypted (camera hub)**.
3. Fill in **User** and **Password**. Leave **Port** empty for 10443. Optionally fill **Leave out these cameras** with names separated by commas (not case sensitive). Tick **Check the certificate** only if Scrypted has a certificate your browser trusts.
4. Choose **Test connection**. It logs in, lists cameras and takes one picture from the first one. It tells you in plain words if that fails.
5. Choose **Save, then pick what to watch**. The list is grouped as **Overview** (the Scrypted item) and **Cameras** (one entry per camera). Nothing is watched until you tick it.

The connection also accepts a `timeout` (seconds, default 10) for logging in; it has no field on the screen.

## What it alerts on and how states map

A provider outage is **Unknown**, never Failed: if Scrypted cannot be reached, the login is refused, or the module cannot answer, every Scrypted item reads Unknown.

| Check | Healthy | Degraded | Failed | Unknown |
| --- | --- | --- | --- | --- |
| **Scrypted** (server) | Answers and shows at least one camera ("Scrypted <version> · N cameras") | Answers but the account sees no cameras | never | cannot reach it, login refused, any other error |
| **Camera <name>** | Scrypted does not say it is offline | never | Scrypted says the camera is offline ("offline in Scrypted") | the camera is gone from the list ("... no camera called ... any more"), plus every outage case above |
| **All cameras** (older setups only, no longer offered) | all online | never | any listed camera offline | no cameras shown |

- Only an explicit "offline" from Scrypted counts as Offline. A camera whose online flag is missing is treated as online.
- A camera that is Failed on one source (Scrypted) and healthy on the other (Protect) is shown as Degraded in the banner and counts once in alerts. If both say it is down, it is Down.
- The Scrypted item is a module check, looked at every 15 seconds by default with a 10 second timeout, and the usual hold-down applies ([the core app page](../APP.md)).

## Known limits

- The module reports no recording status, last-seen time or motion: those are always empty for Scrypted cameras.
- A camera is found by its **name**. Two cameras with the same name in Scrypted cannot be told apart by the camera check.
- A camera with no picture (offline) shows "No picture" and has no Go live button.
- Live video needs the browser to reach Scrypted over UDP (or the site relay). Browsers without WebRTC or EventSource cannot play it ("this browser cannot play live video").
- A camera that does not offer RTCSignalingChannel gets snapshots only.
- Setting **Check the certificate** off turns off certificate checking for the whole module process, including a second Scrypted connection that has it on.

## Troubleshooting

| Message | What it means |
| --- | --- |
| this connection has no 'host' or 'base_url' | The server has no address. |
| this connection needs a 'username' and 'password' (a Scrypted user that can only see the cameras) | Fill in both fields. |
| Scrypted refused the user name or password (...) | Login rejected. The module will not retry for a minute: "(not retrying for a minute, so the account is not locked out)". Fix the password, wait, test again. |
| cannot reach Scrypted at https://<address>:10443 (...) | Wrong address or port, Scrypted is down, or something blocks MonitorBox. |
| connecting to Scrypted timed out | No answer in 10 seconds. |
| Scrypted <version> answers, but this account can see no cameras (...) | The account lacks the Camera and VideoCamera interfaces. Server item is Degraded. |
| connected, but this account can see no cameras. In Scrypted, open the user and give it the Camera and VideoCamera interfaces of each camera | Same cause, shown by Test connection. |
| connected and can see N cameras, but taking a picture from <name> failed (...) | The account can list cameras but not photograph them. Check its access in Scrypted. |
| this account cannot take pictures from that camera (give it the Camera interface in Scrypted) | A single camera lacks the Camera interface for this user. |
| the picture was empty or larger than expected | Scrypted returned nothing or more than 3 MB. |
| taking a picture timed out / reading the picture timed out | Scrypted or the camera is slow (15 seconds each). |
| Scrypted shows this account no camera called '<name>' any more ... | The camera was renamed, removed or excluded. Rescan the server and pick it again. |
| this account cannot start live video from that camera. In Scrypted, give the user the RTCSignalingChannel interface ... | Add RTCSignalingChannel for that camera; if already done, that camera has no live video. |
| live video setup timed out / Live video did not start in time (is the camera reachable from Scrypted?) | Setup took over 30 s (module) or 35 s (screen). |
| The connection is up but no picture has arrived | WebRTC connected but no video frame in 20 seconds. Often UDP is blocked between the browser and Scrypted. |
| Too many live views are open (10) | Close some. |
| the scrypted module is not running / did not answer | App-level: module not installed or crashed. Shown as Unknown. |

The **Live details** button in live mode shows what the relays have carried.

## Where it lives in the code

| What | File |
| --- | --- |
| Checks, discovery, snapshots, live session | `modules/scrypted/main.mjs` |
| Module id and version | `modules/scrypted/manifest.json` |
| Camera list, de-duplication by name, snapshots, live sessions | `app/monitorbox_app/server.py` (`CAMERA_SOURCES`, `cameras`, `live_open`) |
| Camera counted once for states and alerts | `app/monitorbox_app/engine.py`, `app/monitorbox_app/alerts.py` (`_one_per_camera`) |
| Cross-site live relay | `app/monitorbox_app/liverelay.py` |
| "Scrypted on <address>" suggestions | `app/monitorbox_app/followups.py`, `thisbox.py` |
| Server form and camera screens | `app/monitorbox_app/ui.py` |
| Tests | `tests/test_scrypted_module.py`, `tests/fake_scrypted_client.mjs`, `tests/test_cameras_e2e.py`, `tests/test_liverelay.py` |
