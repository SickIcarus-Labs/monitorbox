# Changelog

What changed in each version of the MonitorBox app, in plain words. Every change that reaches a user adds a line under **Not on stable yet**. When a version is promoted to the stable channel, that heading is renamed to the version and a new empty one is started.

Versions move through three channels: **dev** (newest, may be rough), **beta**, then **stable**. A version listed here may not have reached your channel yet; Settings, Updates shows which one you follow.

## Not on stable yet

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
