# UniFi Network module

What the UniFi Network module reads, what it feeds into MonitorBox, and what it never does. The code is `modules/unifi-network/`; the tests are `tests/test_unifi.py`, `tests/test_unifi_e2e.py` and `tests/test_rename_unifi.py`. It is version 0.2.22 (the manifest says so). Everything here is read-only: the module logs in to your UniFi controller and reads lists. It changes nothing on the controller or on any device.

For what the core app does with these answers (states, hold-down, alerts), see [the core app page](../APP.md). For the Port errors rules, see [Port errors](../PORT-WATCH.md).

## What it brings

- Checks on the controller's own view of your gear: every adopted device, each device on its own, the controller's health lines (WAN, LAN, Wi-Fi, Internet, VPN), each VPN tunnel and each device's temperature.
- The controller's picture of your network: which device hangs off which, each port's speed and counters, and which client is on which port or access point. The network map, Port errors and the Busiest client card are built from this.
- The gateway's own view of traffic: who is using the internet, and the flow log behind UniFi's Insights, Flows page.
- The gateway's WAN interfaces and their addresses.

## What it talks to and how

It talks to the controller over HTTPS, using the address of the server it is added to. A bare address gets `https://` put in front. It logs in once and keeps the session; the login is the only request that sends your password.

- **Login:** `POST /api/auth/login` (UniFi OS gateways such as a Dream Machine or Cloud Gateway). If the controller answers 404, it tries `POST /api/login` (a classic controller). The password goes only to the address in the connection.
- **Reads (GET):** under `/proxy/network/api/s/<site>/` on UniFi OS (no prefix on a classic controller): `stat/device` (devices), `stat/health` (health lines), `rest/networkconf` (to list VPN tunnels), `stat/sta` (clients). On UniFi OS only: the VPN connection status at `/proxy/network/v2/api/site/<site>/vpn/connections`, and the traffic usage at `v2/api/site/<site>/traffic` (bytes per client over a window of 60 to 3600 seconds; 300 by default).
- **The one extra POST:** the flow log. `POST v2/api/site/<site>/traffic-flows` is a search of the flow list (a time window and a page number, nothing else). It creates and changes nothing, but it is the only request besides the login that is not a GET. UniFi OS wants the login's CSRF token on it, so the module sends the token it was given at login. It reads up to 10 pages of 200 flows (2000 flows) per question, and falls back to pages of 50 if the controller refuses 200.
- **Flows look:** a tool under Settings > Advanced that asks the gateway a fixed list of read questions (the traffic, flow, applications and categories endpoints) and reports each answer's status and shape, not its content. Public addresses are hidden, MAC addresses are shortened to their last three bytes, and long text is replaced by its length.
- **Guard rail:** the module refuses to fetch anything that is not on its fixed list of paths (`READ_ONLY_PATHS`, and `LOOK_ALLOWED` for the flows look).
- **Certificates:** a controller usually has a self-signed certificate, so the certificate is not checked unless you tick the box (see below). System proxy settings are ignored.
- **Timing:** each request waits 8 seconds by default. Checks that run together share one fetch for 5 seconds. After a refused login the module does not try again for 60 seconds, so a wrong password does not lock the account out.
- **Shortened data:** the network report copies a fixed list of port fields only and shortens MAC addresses to `..:dd:ee:ff`. No secret can ride along.

## What you need to provide

- A **local user on the controller that can only view**. The login form says "Create a local user that can only view." A cloud (Ubiquiti account) login is not what the module uses: it posts the user name and password to the controller itself.
- That user's name and password. The password is stored in plain text in the config folder, readable only by the app (see [the core app page](../APP.md)), and shown as dots afterwards.
- The controller's address (the server's address in MonitorBox) and the **site** name if it is not `default`.
- Network access from the MonitorBox machine to the controller on the HTTPS port it listens on (443 on a UniFi OS console). Another port can be given in the address.
- Permission for the user to read the network data. A user that can log in but not read it gets "the UniFi controller refused this account's access to the network data".
- The flows list, per-client internet usage and VPN tunnel status need **UniFi OS** (a Dream Machine, Cloud Gateway or similar). A classic controller still gives devices, health and the network picture.
- No guide outside MonitorBox is needed. Create the user in the UniFi console's own user settings.

## Adds to the app

Without the module, MonitorBox still pings and watches your gateway and other things by address, but loses everything below.

- **Check types** (a "UniFi Network" module check): `devices`, `device`, `health`, `tunnel`, `temperature`. Details in the states section.
- **Discovery:** Test connection and Re-detect list what the controller has. The suggestions are grouped as *Overview* ("UniFi devices", and one line each for UniFi WAN, LAN, Wi-Fi and Internet health), *Devices* (one per adopted device), *Temperatures* (one per device that reports a temperature) and *VPN tunnels* (one per client or site-to-site tunnel). Nothing is watched until you pick it. Each device and tunnel becomes its own item in the Network group, so an offline one shows as Down by name.
- **Setup and suggestions:** when a UniFi console answers on the gateway, the setup page offers a "UniFi gateway" row. Once a UniFi Network login exists, MonitorBox offers "UniFi Protect on <address>", which reuses the same login (the password is copied on the box and never sent to the browser). It also uses the UniFi device list to offer your saved SNMP login on UniFi switches that are not SNMP connections yet.
- **Network map:** the map of devices and links is built from the module's network report (every 5 minutes in the background, and when the map page is older than a minute). Without a UniFi login the background map is not built.
- **Port errors:** error and drop counters, link-down counts and port state for UniFi switches, gateways and access points, read every 10 seconds. SNMP can read the same ports on its own; see [Port errors](../PORT-WATCH.md).
- **Busiest client:** wired clients come from port readings; Wi-Fi clients (and anything else not on a port) come from the gateway's flow log, read every 20 seconds. The card says it needs a UniFi network connection.
- **Graph panel and flows:** tapping a traffic graph on the gateway shows the flow log for that time. If the flow log has nothing, it lists who is using the internet instead. A Wi-Fi client's traffic is stood in for by the controller's own per-client rate.
- **WAN address:** the gateway's public WAN address is taken from the module and shared with paired sites. Without it, MonitorBox asks a public address page.
- **Settings > Advanced tools:** "Ask the switches" (Switch report) and "Ask the gateway" (Flows look).
- **Old name:** a connection saved under the old module name `unifi` is read as `unifi-network` automatically.

## How it is configured

Everything is done on screens.

1. Open **Settings > Servers**, then the server that is your UniFi console (or add it). Choose to add the service **UniFi Network** ("UniFi Network controller"). On the setup page the same form opens from the "UniFi gateway" row, with **Set up** or **Edit**.
2. Fill in **User**, **Password** and **Site** (the placeholder says `default`).
3. Tick **Check the controller's certificate (leave off for a self-signed one)** only if the controller has a certificate your MonitorBox machine trusts. Off is the default.
4. Press **Test connection**. It runs the same discovery as Re-detect and tells you how many items it found in each group, or a plain error.
5. Press **Save, then pick what to watch**, and tick what to watch. To change the list later, use **Pick what to watch** on the connection. **Edit** changes the login and **Remove this service** deletes it.

Not on the form: the request timeout (8 seconds by default) and a temperature limit. The limit is set per temperature check (`max_c`, 80 °C by default), and a device check can have a `min_uplink_mbps` floor. Both are on the check, not the login. New module checks run every 15 seconds unless the check sets another interval, and every check can have its own timeout (10 seconds by default).

## What it alerts on and how states map

The module only reports a state for each check; the app decides when to alert (see [the core app page](../APP.md)). A controller that cannot be reached, a refused login or a missing module is **Unknown, never Failed**. A device that is down is Failed only when the controller says it is.

| Check | Healthy | Degraded | Failed | Unknown |
| --- | --- | --- | --- | --- |
| **device** | Connected, uplink up and not under the floor | Any state other than connected that is not listed as Failed (pending adoption, upgrading, provisioning, heartbeat missed, isolated and so on); or connected with its uplink down; or uplink slower than `min_uplink_mbps` | Controller state disconnected, inform error or adoption failed | No device name; no device by that name (the message lists the names it has) |
| **devices** (all adopted, or those named) | All connected | Some not settled (upgrading, adopting and so on) and none disconnected | Any disconnected, inform error or adoption failed; the message names them | The controller reports no adopted devices |
| **health** (wan, lan, wlan, www, vpn) | Controller says `ok` | `warning` | `error` | Any other word; no subsystem named; the controller has no such line; see the Internet note below |
| **tunnel** | Connected | none | Disconnected, down, error or failed; also **paused** (turned off in UniFi) | Any other status; or the controller does not report tunnel status |
| **temperature** | Hottest sensor under the limit | Hottest sensor at or over the limit (80 °C by default), or the device says it is overheating | never | Device not connected; no temperature reported |

- An available firmware update adds "update available" to a device's line. It is information and does not change the state.
- A connected gateway's uplink is usually a modem the controller does not manage; the line then says "via a device outside UniFi".
- **Internet (www) health:** if UniFi's old Internet summary says `warning` but has no latency and no uptime behind it, the module does not count it as a problem. It looks at the gateway's own WAN blocks instead: Healthy if any WAN is up, Failed if every WAN is down. If the gateway reports none, the result is Unknown with "UniFi's Internet summary has no measurements right now".
- **VPN health:** the controller's summary is coarse and can say `error` while every tunnel is up, so the line also shows the numbers behind it. The suggestions skip it and offer one check per tunnel instead.
- **Port errors** is part of the app and turns Degraded, never Failed; see [Port errors](../PORT-WATCH.md).

## Known limits

- Read-only by design: no restart, adopt, block or configuration change.
- The flows list, per-client usage and VPN tunnel status need UniFi OS. A classic controller answers "this controller does not report VPN tunnel status", "...per-client internet usage" or "...does not keep a flow log (the Flows page needs UniFi OS)".
- Per-client usage counts what passes through the gateway (the internet and traffic between networks). Traffic that stays on one switch is not in it. It shows at most the biggest 30 clients. The flow summary keeps the biggest 300 rows.
- The flow log is an interface UniFi does not publish. The module adapts when a controller wants smaller pages, but a change in the controller can break it. The Flows look tool exists to see what a gateway answers.
- A device is known by its name, else its host name, else its model, else its MAC address (case ignored when matching). Two devices with the same name give the first match.
- Only adopted devices are listed in discovery and the network report.
- The request timeout is not on the login form.
- One shared cache of 5 seconds means a state can be up to about 5 seconds behind the controller, on top of the check's own interval.
- The module runs at most 4 requests at once, and one controller login is handled one request at a time.
- Certificates are not checked by default. Tick the box if you want the controller's certificate verified.
- The Busiest client's wired part works from port readings; its Wi-Fi part needs UniFi.

## Troubleshooting

Messages appear in the check's line, in Test connection, or on the Port errors page. The app also turns many of them into a plainer sentence in Test connection.

| Message | What it means |
| --- | --- |
| `cannot reach the UniFi controller at https://192.0.2.10 (...)` | Nothing answered: wrong address or port, the controller is off, or a firewall. The reason from the network follows in brackets. |
| `cannot log in to UniFi: the username or password was refused (not retrying for a minute, so the account is not locked out)` | Wrong user or password. Fix it, then wait a minute or press Test connection after the minute. |
| `cannot log in to UniFi: the login was refused` | The controller answered 400 or 403 to the login and gave no reason. |
| `cannot log in to UniFi: the controller says too many login attempts` | The controller is blocking logins for a while. Wait. |
| `cannot log in to UniFi: the controller answered HTTP N` | Some other answer from something at that address. Check it is the UniFi console. |
| `the UniFi controller accepted the login but sent no session` | The login went through but no session cookie came back. |
| `the UniFi controller refused this account's access to the network data` | The login works but this user may not read the network data. Give it view access to Network. |
| `the controller has no site called 'X' (or this is not a UniFi controller)` | Wrong **Site** name, or the address is not a UniFi controller. |
| `the UniFi controller answered HTTP N` | The controller gave an unexpected answer to a read. |
| `the UniFi controller sent an answer this module cannot read` | The answer was not what the module expects. |
| `the UniFi controller said: ...` | The controller itself reported an error. |
| `this connection has no 'host' or 'base_url'` / `this connection needs a 'username' and 'password' (a read-only local account is best)` | The connection is incomplete. Edit it. |
| `the controller has no device called 'X' (it has: ...)` | The device was renamed or removed in UniFi. Use Pick what to watch to re-select it. |
| `the controller has no VPN tunnel called 'X' (it has: ...)` | Same, for a tunnel. |
| `this check needs a device 'name' (or 'mac'). Use Re-detect.` (also for tunnel name and health subsystem) | The saved check is missing its target. Re-pick it. |
| `the controller has no 'X' health (it has: ...)` | That health line does not exist on this controller. |
| `the controller reports no adopted devices` | Nothing adopted, or the filter names matched none. |
| `device is not connected, so its temperature is not known` / `the controller reports no temperature for this device` | The temperature check cannot read it. Not a fault. |
| `this controller does not report VPN tunnel status` | A classic controller, or an older UniFi OS. Tunnels then read Unknown unless paused. |
| `this controller does not report per-client internet usage (HTTP N)` / `this controller does not report flows (HTTP N)` | The traffic endpoints are not available on this controller. |
| `the UniFi controller refused this account's access to the traffic data` / `...to the flow log` | The user may not read the traffic or flows. |
| `the unifi-network module is not running` / `... did not answer: ...` | The module did not start or was too slow. The check is Unknown. The app's own message suggests installing it under Settings, Versions. |
| `unknown UniFi check 'X' (known: device, devices, temperature, health, tunnel)` | A check type that does not exist. |
| `This UniFi login cannot read the client list, so devices on ports are not named.` (on the map) | The account can read devices but not clients. The map shows ports without names. |

If the Internet health line is Unknown with "so this is not counted", UniFi's old summary has no data and the gateway reported no WAN blocks either. If it differs from what UniFi's screen shows, the line lists the numbers behind it.

## Where it lives in the code

| What | File |
| --- | --- |
| Module entry, request handling, one session per login | `modules/unifi-network/main.py` |
| Manifest (id, name, version, start command) | `modules/unifi-network/manifest.json` |
| Controller client (login, back-off, the fixed read paths, usage, flows, flows look) | `modules/unifi-network/unifilib.py` |
| Checks, discovery, WAN ports, network report, usage and flow summaries | `modules/unifi-network/unifichecks.py` |
| Test connection, Re-detect, flows, usage, WAN address calls | `app/monitorbox_app/server.py` |
| Network report reading, Port errors feed | `app/monitorbox_app/lansampler.py`, `portwatch.py` |
| Network map | `app/monitorbox_app/lanmap.py` |
| Busiest client | `app/monitorbox_app/busiest.py` |
| Protect and SNMP suggestions | `app/monitorbox_app/followups.py` |
| WAN address | `app/monitorbox_app/wanaddr.py` |
| Old name `unifi` | `app/monitorbox_app/monconfig.py` |
| The login form and tools | `app/monitorbox_app/ui.py` |
