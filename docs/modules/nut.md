# Battery backup (NUT)

What the `nut` module (shown in the app as **Battery backup**, version 0.1.2) does, what it talks to, and what it never does. The code is in `modules/nut/`; the tests are `tests/test_nut.py` and `tests/test_nut_e2e.py`. For what the core app does with a module's answers, see [the core app page](../APP.md).

## What it brings

It reads the state of a UPS (a battery backup) from a **NUT server** (the `upsd` program that runs on the machine the UPS is plugged into). For each UPS it gives one check, "ups": is the mains power on, is it running on battery, how full is the battery, how loaded is the UPS, and how many minutes of runtime are left.

It can also ask the NUT server which machines are attached to a UPS, so MonitorBox can guess which servers a UPS keeps running.

## What it talks to and how

Everything is read-only.

- **Where:** plain TCP to the NUT server, port **3493** unless you change it. The module does not use TLS.
- **What is sent:** only `LIST UPS`, `LIST VAR <ups>` and `LIST CLIENT <ups>`. Each request opens a new connection, sends one command and reads the answer.
- **Login:** only if you enter a user name. Then `USERNAME` and `PASSWORD` go first on the same connection, ahead of the read, and nothing else. It never sends `LOGIN` (which would attach MonitorBox to the UPS as a client), `SET`, `INSTCMD` or `FSD`. The test suite fails if anything else is ever sent.
- **Timeout:** 3 seconds to connect and to wait for each answer. This is not on a screen.
- **No shutdowns:** the network UPS never triggers a shutdown, and MonitorBox cannot make a UPS or a server do anything.

## What you need to provide

- **The address of the NUT server** (the machine the UPS is plugged into). NUT must listen on the network address, not only on that machine itself. See "Battery backup (NUT)" in [GUIDES.md](../GUIDES.md).
- **A user name and password, only if the server asks.** Some NUT servers (a NAS's built-in one, for example) refuse a read without one. A read-only NUT user is enough.
- **Permission on the NUT server for this box.** If the server only answers certain addresses, allow the MonitorBox machine there. A login does not help in that case.
- The NUT server's own setup (drivers, `upsd.conf`, `upsd.users`) is outside MonitorBox. Use NUT's own documentation.

## Adds to the app

- **A "ups" check type.** Each UPS becomes a system called "UPS <name>" in the **Power** group on the main screen.
- **Discovery.** Re-reading a connection lists every UPS the server knows, as ready-made items. The set-up scan also notices a server with port 3493 open and offers "Battery backup (NUT)". A UPS that appears later is proposed under "Found more you can add".
- **Power settings.** Settings > Power lists each UPS and the systems it keeps running. It is empty ("No battery backup is being watched yet...") until a UPS is watched.
- **Power guesses.** Every 10 minutes the app asks each watched UPS who is attached (`LIST CLIENT`) and pre-ticks a system on the Power page, marked "best guess", when the client address is exactly one watched system.
- **"Powered by" explanations.** A system that goes down while its UPS is on battery, low, shutting down or failed is shown as affected by the UPS, and does not alert on its own. This is how one alert replaces one per server.
- **Urgent power alerts.** A UPS on battery, low or shutting down alerts at once, outside the storm and flap rules.

Without the module the app has no UPS check, no Power group, no Power page entries and no power guesses. Alerts still work, but a power cut shows as every server going down separately.

## How it is configured

1. **Settings > Servers > Add a server.** Enter a **Name** and an **Address** (the machine the UPS is on, for example `192.0.2.10`), then **Next**. If the server is already listed, open it instead.
2. Under **Add:** choose **Battery backup (NUT)**. The fields are:
   - **Port** (shows "3493 (the usual)" when empty)
   - **User (only if the server asks for one)**
   - **Password**
3. **Test connection** asks the server for its UPS list and shows "It answered in N s" and "Found: UPS 1" (the count of UPSes), or the reason it could not.
4. **Save, then pick what to watch.** Tick each UPS, then **Apply**. When nothing is watched yet, every UPS is ticked. Each one goes into its own item under the **Power** group, not under the server that hosts NUT.
5. Later, open the server and use **Pick what to watch** to change the choice, **Edit** to change the login, or **Rescan this server** to look again.
6. **Settings > Power:** under each UPS heading, tick the systems it keeps running. A system is on one UPS at a time. Systems with no UPS are under "Not on a backup yet", each with a menu (choose **none** to say "no UPS, and do not guess"). Your answer always wins over a guess.

The warning limits (below) have no screen. They are check parameters, changed only in the JSON editors under Settings > Advanced.

## What it alerts on and how states map

A NUT server that cannot be reached means **Unknown**, never Failed. So do an unknown UPS name, a driver that has lost the UPS, and a UPS that reports no status.

| State | When |
| --- | --- |
| **Failed** | status contains `LB` (low battery), `FSD` (shutting down) or `OFF` |
| **Degraded** | status contains `OB` (on battery), `RB` (replace battery), `OVER` (overloaded), `BYPASS`, `ALARM`, `DISCHRG` (discharging) or `CAL` (calibrating); **or** battery charge below `charge_warn` (default **50** %) and not charging (`CHRG` absent); **or** load at or above `load_warn` (default **80** %); **or** runtime below `runtime_warn_s` (default **300** s) |
| **Healthy** | none of the above |
| **Unknown** | server unreachable, login refused, unknown UPS name, driver data stale, no status reported |

The detail line reads like `online · battery 100% · load 23% · 41 min runtime`. Status codes are shown as words: online, on battery, low battery, high battery, replace battery, charging, discharging, on bypass, calibrating, off, overloaded, trimming voltage, boosting voltage, shutting down, alarm. A code not in that list is shown as sent. Runtime under 2 minutes is shown in seconds.

**The three power words.** `on battery`, `low battery` and `shutting down` (see `POWER_URGENT` in `engine.py`) are the words the app looks for in a UPS check's detail:

- `alerts.py` announces a UPS whose detail has one of these words immediately, with no alert delay, as time-sensitive, and outside the storm and flap rules. The messages read "<name> is running on battery.", "<name> has a low battery." and "<name> is shutting down." This works even when the Degraded trigger is unticked. The first matching word wins, in that order.
- While that alert is open, and for **10 minutes** after it clears (`POWER_GRACE`), systems the UPS powers do not alert for being down. This holds even if the UPS itself turns Unknown, for example because its host lost power too.
- `engine.py` marks a system that is Failed, Degraded or Unknown as affected by its UPS when that UPS is Failed, or Degraded with one of these words. Observed states are never rewritten.

A confirmation wait still applies to the state itself: by default a Degraded reading must last 2 checks over 60 seconds before the screen shows it (see [the core app page](../APP.md)). `OFF` is Failed but is not one of the three words, so it alerts as an ordinary "is down" after the alert delay.

Checks run every 15 seconds by default, and every 3 seconds while failing.

## Known limits

- One check type only, `ups`. Any other name gives Unknown ("unknown NUT check ... (known: ups)").
- The password goes over the network in clear text, as NUT's own protocol does without TLS. Use a user that can only read.
- The power guess needs the NUT server to list the machines (the ones running `upsmon`). Client addresses are matched as text with the address you gave each watched system. `127.0.0.1` means the NUT server's own machine. An address shared by two watched systems, or claimed by two UPSes, is not guessed.
- A system can only be on one UPS.
- The warning limits and the 3-second timeout are not on any screen.
- Planned maintenance (a commanded shutdown) is not detected.

## Troubleshooting

These are the messages the module produces, as shown in an item's detail or in the Test connection box.

- **"cannot reach the NUT server at 192.0.2.10:3493 (...)"**: nothing answered, the port was refused, or the server did not finish answering in 3 seconds. Check the address and port, that `upsd` is running and listening on the network address, and any firewall.
- **"the NUT server said ACCESS-DENIED (the server may only allow certain addresses, or want a user name and password...)"**: no login was entered. Add a user and password, or allow this box on the NUT server.
- **"the NUT server said ACCESS-DENIED (check the user name and password)"**: a login was sent and refused. Check it, for example user `example-reader`.
- **"the UPS driver has lost contact with the UPS (data stale)"**: `upsd` is fine but its driver cannot reach the UPS (cable, USB, power). Fix it on the NUT machine. The item is Unknown.
- **"the NUT server has no UPS called 'x' (it has: ...)"**: the name saved in the check no longer matches. Pick what to watch again.
- **"this check needs a 'ups' name (the server has: ...). Use Re-detect."**: the check has no UPS name. Use **Pick what to watch** on the server's Battery backup service.
- **"the UPS did not report a status"**: the server answered but gave no `ups.status`.
- **"the NUT server closed the connection without answering"** and **"the NUT server said <code>"**: the server sent nothing, or an error this module does not translate. Read the code against NUT's documentation.
- **"this connection has no 'host'"**: the connection has no address. Edit it.
- **"the nut module is starting"**, **"is not running"** or **"did not answer"**: the module itself, not the UPS. The item is Unknown; see Settings > Updates and versions.
- **Test connection shows "Found:" with nothing, or the item list says "Nothing found."**: the server answered but lists no UPS.
- **Settings > Power shows a line like "<name>: <error>"**: the power guess could not ask that server. Guesses stay as they were; your own ticks are unaffected.

## Where it lives in the code

| Part | File |
| --- | --- |
| Manifest (id `nut`, name "UPS (NUT)", version, entry) | `modules/nut/manifest.json` |
| Check, discovery, status words and thresholds, protocol with the app | `modules/nut/main.py` |
| The read-only NUT client | `modules/nut/nutlib.py` |
| Power words, "powered by" explanation | `app/monitorbox_app/engine.py` |
| Urgent alerts, 10-minute hold | `app/monitorbox_app/alerts.py` |
| Power guessing (`power_scan`, `power_page`, every 10 minutes) | `app/monitorbox_app/server.py` |
| Applying guesses; owner's `poweredBy` wins | `app/monitorbox_app/monitor.py`, `monconfig.py` (`set_powered_by`) |
| Battery backup form and Settings > Power screen | `app/monitorbox_app/ui.py` |
| Set-up scan for port 3493 | `app/monitorbox_app/thisbox.py` |
| Test fake NUT server | `tests/nut_fake.py` |
