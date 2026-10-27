# Changelog

What changed in each version of the MonitorBox app, in plain words. Every change that reaches a user adds a line under **Not on stable yet**. When a version is promoted to the stable channel, that heading is renamed to the version and a new empty one is started.

Versions move through three channels: **dev** (newest, may be rough), **beta**, then **stable**. A version listed here may not have reached your channel yet; Settings, Updates shows which one you follow.

## Not on stable yet

- **1.4.0** Faster, calmer start. After a restart the modules start all at once instead of one after another, and a check whose module is still coming up shows "checking" instead of "Unknown, the snmp module is not running", then runs again the moment its module answers. The page also opens with the readings from before the restart, marked "(last reading before the restart)", until each check's own fresh answer replaces its reading (two minutes at most; readings older than ten minutes are not used, and alerts never act on them). A module that really cannot start is still reported after 90 seconds.
- **1.3.0** Port watch also watches the network cards of SNMP servers (errors and drops per card, read every 30 seconds while the watch is on). A server card is matched by its hardware address to the switch port it is plugged into, so that port's line shows what the server's side of the cable sees ("other end (apollo, eth0): ..."). Marking a switch port as a known issue silences the server card at the other end of that link too. A card that is not matched to a switch port still raises the heads-up in History and alerts, but cannot be marked from the map.
- **1.2.0** Port watch can read errors and drops over SNMP. A switch that is also an SNMP connection gives its receive and transmit errors and drops straight from the interface, which is exact and works for switches that are not UniFi. UniFi's own counters are used for everything else, and one device never mixes the two. Link drops still come from UniFi. (SNMP module 0.2.8.)
- **1.1.3** Port watch shows the other end of a link: a port with rising errors also says what the port at the far end is seeing ("other end (Aggregation, Port 3): 0 receive, 0 transmit an hour"), so a one-direction problem is plain at a glance.
- **1.1.2** Port watch says what kind of errors: receive and transmit counted apart ("29,000 receive, 68 transmit"), and how busy the port was while they happened ("carrying about 4.1 Gbit/s, peak 9.2"). Receive errors point at the cable, optic or the far end; transmit errors and drops point at a port backing up.
- **1.1.1** Port watch: link drops are only reported for uplinks, links between switches and servers, not for ports with a laptop or TV on them (they drop whenever the device sleeps). A port is also compared with the worst 15 minutes it has had in the last day, so errors that only come under a big transfer are not flagged each time.
- **1.1.0** Watch for rising port errors (off until you tick it, on the Network map page). MonitorBox learns what is normal for each switch port and shows a yellow heads-up, never red, when a port's errors, drops or link drops climb well above that. A port you mark "known issue" keeps its numbers but never raises anything. It needs about half an hour of readings before it says anything, and starts over after a restart of the box or of a switch.
- **1.0.1** The busiest-client card says "The network is quiet" when nothing is busy, not "The wired LAN is quiet": it watches wifi devices too.

## 1.0.0 and 0.83.18 to 0.83.22 (stable, October 25)

- **1.0.0** Version number only, nothing else changed: MonitorBox is in use, so it is 1.0. From here the middle number moves for new abilities and the last for fixes.
- **0.83.22** The Sites card counts the sites it watches even when there is only one ("1 of 1 up"), like the other cards. A row with a long name and a middling detail (a camera called "Camera Garage") now gets two lines instead of a cut-off one.
- **0.83.21** A camera that UniFi Protect and Scrypted both watch is one camera: both say it is down, it is Down; they disagree (one says down, the other says fine), it is only Degraded, since one source may be the one acting up. One attention line and one alert per camera, and the detail says the other source reports it fine.
- **0.83.20** Cards fold their many alike items: cameras, switches and access points, and VPN tunnels each sit under one heading per source (for example "UniFi Protect cameras"). A problem inside opens its heading by itself. A camera that two sources both report counts once, so the Cameras summary counts cameras instead of 19 of 19.
- **0.83.19** Choose what counts as critical: a Critical tick on each item's detail and on each server's settings page (and for Portainer as a whole). When a critical thing is Down, the whole banner goes red.
- **0.83.18** Every camera, UniFi device and VPN tunnel is its own item, so one that is offline shows as Down by name instead of making a shared item ("Cameras", "UniFi", "Scrypted") only Degraded. Existing boxes are split automatically; the recorder and storage stay together as "UniFi Protect", and the old all-cameras summary checks are dropped because each camera now says its own state.

## 0.83.11 to 0.83.17 (stable, October 25)

- **0.83.17** Busiest client: the gateway, switches and access points are never crowned (the gateway could show up as the "busiest client" because it appears in its own flow log).
- **0.83.16** Tapping a traffic graph: a big download the gateway has not named yet (a game download, for example) is now listed as internet traffic instead of "not matched yet".
- **0.83.15** Alerts: choose what sends an alert. Tick Down, Degraded, Unknown and Restored. Unknown is off unless you turn it on. A UPS running on battery always alerts.
- **0.83.14** Site name: the welcome page asks "What do you call this site?". When a managed site has no name of its own, the main box offers to set one (never over a name you chose). Phone (Home Assistant) alerts end with the time at the site, for example "(1:36 PM CDT at Riverside)".
- **0.83.13** Alert emails show the time in the box's own time zone instead of UTC.
- **0.83.12** Alerts use the site name set under Settings, Sites, not the computer's name.
- **0.83.11** Busiest client: cameras are recognised by hardware address and name, so the Cameras tick works; links between switches are never crowned.

## 0.83.10

- Traffic graphs no longer show spikes and gaps for devices that only refresh their counters every few seconds.

## Earlier

- **0.83.9** New boxes follow the stable channel.
- **0.83.8** The image version shows on the Settings line, with "(update available)".
- **0.83.7** Tells you when the container image needs re-pulling.
- **0.83.6** The built-in repository has no tick box; the Settings header follows the site tab.
- **0.83.5** The Updates page shows the selected site's own channel.
