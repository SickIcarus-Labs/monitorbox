# Wake on LAN module

What the Wake on LAN module (`wol`) does, what it sends, and what it leaves alone. The code is `modules/wol/main.py`; the part that decides when to send and checks the result is in the App (`app/monitorbox_app/server.py`). For what the App itself does, see [the core app page](../APP.md).

## What it brings

- A **Wake** button on a system that has wake settings. Press it and MonitorBox switches the machine on (if the machine is set up to allow that) and then watches for it to come up.
- That is all. The module has no checks of its own and nothing to log in to.

## What it talks to and how

This is the one module that acts on the network instead of only reading it.

- **What it sends:** a "magic packet" in a single UDP datagram, 102 bytes: six bytes of `ff`, then the machine's MAC address repeated 16 times.
- **Where to:** the broadcast address from the wake settings, which is `255.255.255.255` if none is set. **Port:** UDP `9` unless the settings say otherwise.
- **How many:** one packet for every MAC address listed, so a machine with two network cards can have both listed. The App sends them again every 30 seconds (the `retry` setting) until the machine answers or the time runs out.
- **IPv4 only.** The module opens an IPv4 UDP socket with the broadcast option on.

What it does not do:

- It does not receive anything. It never hears whether the machine woke up; the App finds that out by running the system's own checks (see below).
- It does not log in to, scan or control the machine, and it does not turn anything off.
- It sends only when someone presses **Wake**. It never sends on its own, and a machine going down never triggers a wake.
- Every MAC is checked before anything is sent, so one bad address means nothing at all goes out.

How the App confirms it: it sends the packets, then runs that system's own checks right away, repeating about every 2 seconds. The machine counts as up when the system's state becomes healthy or degraded. The wait is 120 seconds unless the settings say otherwise.

## What you need to provide

- **MAC address of each network card** that can wake the machine. Any common spelling is accepted (`02:00:5e:00:53:01`, `02-00-5e-00-53-01`, `0200.5e00.5301`, `02005e005301`) and it is stored as `02:00:5e:00:53:01`. Two addresses that are the same card are refused.
- **A broadcast address (optional).** For a machine on a /24 network such as 192.0.2.0/24 that would be `192.0.2.255`. Leave it empty to use `255.255.255.255`.
- **Host networking.** MonitorBox must run on the same network as the machine, in the host-networked container ([architecture](../ARCHITECTURE.md) says Wake on LAN needs it).
- **Outside MonitorBox:** Wake on LAN has to be switched on in the machine's BIOS/UEFI and in its network card settings in the operating system, and the machine has to be asleep or off with its network card still powered. MonitorBox cannot change or check any of this. The timeout message below points at it.
- **A check that tells when it is up.** The system needs at least one check (a ping is typical). Without one there is nothing to confirm with.

## Adds to the app

- The **Wake** button in an item's detail view (shown when the system has wake settings; greyed out while a wake is running).
- A status line under the item while a wake runs and for two minutes after: sending, waiting, up, did not answer, or error. It is shown on every open screen.
- A **Wake on LAN** row on each server's page under Settings, Servers, with the MAC addresses and an Edit button, and a button to add it.
- A **Wake on LAN** row in Set up. When the box has seen a machine's MAC address on the network, it offers that address ready to use.

The App loses all of this without the module: no Wake button, and a wake press reports that the module is not running. Monitoring itself is unaffected. It is the one module installed on every new box, because nothing on the network can show that someone wants it. Every other module is installed when a device of its kind is added.

## How it is configured

Everything is on screens. Go to **Settings, Servers**, open the machine, and press **Wake on LAN** (or **Edit** if it is already set up). The same form opens from **Set up**.

| Label on the screen | What it is | Default |
| --- | --- | --- |
| MAC addresses, one per line (a machine with two network cards can list both) | The cards to send to | none; at least one needed |
| Broadcast address (optional) | Where the packet is sent | `255.255.255.255` |
| Give up after, seconds (optional) | How long to wait for the machine to come up | `120`; allowed 5 to 3600 |

The buttons are **Save**, **Cancel** and, once set up, **Remove wake settings** (it asks first).

The form does not show the UDP port (default `9`, allowed 1 to 65535) or how often a packet is sent again (default 30 seconds, allowed 2 to 300). Those two can only be set in the monitoring file under Advanced. Edits there are validated before they are saved, and a bad one is refused with the reasons listed.

If the server has no system yet, saving makes one with a ping check on the server's address, so the wake can be confirmed. A server with no address first needs one ("This server needs an address first."). Wake settings can only go on a system with its own checks, not on a group.

## What it alerts on and how states map

- **Waking does not raise alerts.** The module has no checks and no state. Pressing Wake does not change any state, write to history or send a message.
- The result of a wake is a status line on the item, not an alert. It is kept in memory only: it is gone after two minutes and after a restart of the App.
- The result lines are:
  - Sending, then "Sent N wake packets (try K). Waiting for NAME to answer, up to T s…"
  - Up: "NAME is up (answered after N s)."
  - Did not come up: "NAME did not answer within T s. Check the MAC addresses and that Wake on LAN is on in its BIOS and network card."
  - Could not send: "Could not send the wake packets: …" with the reason.
- A machine that does not come up simply stays in whatever state its own checks give it (Down if it fails them). It is not marked failed because of the wake. If a machine is switched off on purpose, mark it expected down; the normal alert rules for down systems apply, as on [the core app page](../APP.md).
- If the module is not running, the wake reports an error. It is not shown as a failure of the machine. The module's own "check" answers Unknown ("Wake on LAN has no checks; it only wakes machines") and is not used by anything the App shows.

## Known limits

- **Same network segment only.** A magic packet is a broadcast. It does not cross a router unless the router is set up to forward it. MonitorBox does nothing to route it; if the machine is on another VLAN or subnet, set the broadcast address to that subnet's broadcast address and make sure your network passes it, or put MonitorBox on that network.
- **Sent, not delivered.** The module can say how many packets it sent. It cannot know that one arrived. Only the machine coming up shows it worked.
- A press while a wake is already running does nothing new; it shows the running status.
- A machine that is already up is also sent the packets. The App sees it answer at once and reports it as up.
- Wake settings belong to a single system. A wake cannot be set on a group.
- IPv4 only; a broadcast address must be an IP address, not a name.

## Troubleshooting

| Message | What it means |
| --- | --- |
| "NAME did not answer within T s. Check the MAC addresses and that Wake on LAN is on in its BIOS and network card." | Packets were sent but the system's checks never passed. Check the MACs, the BIOS/OS settings, that MonitorBox and the machine are on the same network, and that the system has a check that can pass. Raise "Give up after" if the machine boots slowly. |
| "That system has no wake settings. Add a 'wake' block with its MAC addresses." | The Wake button was used on a system with none. Set it up under Settings, Servers. |
| "Could not send the wake packets: the wol module is not running (install it under Settings, Versions)" | The module is not installed or has stopped. |
| "Could not send the wake packets: wol did not answer wake" | The module took longer than 10 seconds to answer. |
| "Could not send the wake packets: no MAC addresses are set for this system" | The system's wake settings have no MAC addresses. |
| "Could not send the wake packets: 'X' is not a MAC address" | One MAC is not 12 hex digits (separators `:` `-` `.` are allowed). |
| "Could not send the wake packets: …" followed by an operating system error | The packet could not leave the box, for example no route to the broadcast address. |
| "'X' is not a MAC address (like aa:bb:cc:dd:ee:ff)", "MAC X is listed twice", "needs 'macs': a list of one or more MAC addresses" | Refused when saving. |
| "broadcast must be an IP address such as 192.168.77.255", "port must be 1 to 65535", "timeout must be 5 to 3600 seconds", "retry must be 2 to 300 seconds", "has an unknown field 'X'" | Refused when saving. Every message starts with the system's position in the file. |
| "only a system with its own checks can be woken" | Wake settings were put on a group. |
| "The time to give up must be a number of seconds." | The timeout field was not a number. |

## Where it lives in the code

| What | File |
| --- | --- |
| Module: builds and sends the packets (`wake`), `hello`, `describe`, `check` | `modules/wol/main.py`, `modules/wol/manifest.json` |
| Sending, resending, confirming, result lines, the `/api/wake` call | `app/monitorbox_app/server.py` |
| Settings rules and defaults (macs, broadcast, port, timeout, retry) | `app/monitorbox_app/monconfig.py` |
| The "can wake" flag on a system | `app/monitorbox_app/engine.py` |
| Always installed on a new box | `app/monitorbox_app/modules.py` |
| Wake button, status line, Wake on LAN form | `app/monitorbox_app/ui.py` |
| Settings tests | `tests/test_monconfig.py`, `tests/test_install_on_need.py` |
