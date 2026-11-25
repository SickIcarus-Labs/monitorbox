# Portainer module

What the Portainer module brings to MonitorBox, what it talks to, and what it never does. The code is in `modules/portainer/`; the tests are `tests/test_portainer.py`, `tests/test_portainer_e2e.py` and `tests/test_docker_macs.py`. Everything here is read-only: MonitorBox asks Portainer what it sees and changes nothing.

## What it brings

- A view of your Docker containers: which environments (machines) a Portainer server manages, and whether each container on them is running properly.
- One connection to the Portainer **server** covers every environment it manages, including its own machine and any agents.
- A **Docker MAC address watch** per Docker environment: two containers on one Docker bridge with the same MAC address (see below).
- Ready-made suggestions: each container becomes something you can tick to watch, and containers that publish a web page get a web check too.
- Hints for the core app: it reads Portainer's answer to propose other servers and logins ([the core app page](../APP.md) describes how proposals work).

## What it talks to and how

- **Target:** the Portainer server's web address, `https` on port 9443 by default, or plain `http` on port 9000 if you tick the plain-http box. A full address (`base_url`) in the saved connection is used as given.
- **Requests:** only HTTP `GET`, and only to these paths: `/api/endpoints` (the environment list) and `/api/endpoints/<id>/docker/containers/json?all=1` (that environment's containers, stopped ones included). The MAC address watch adds `/api/endpoints/<id>/docker/networks` (the network list), `/api/endpoints/<id>/docker/networks/<network id>` (one network and the endpoints on it) and `/api/endpoints/<id>/docker/containers/<container id>/json` (one container's settings); ids must be plain hex. Any other path is refused inside the module before anything is sent. There is no login call, no POST, PUT or DELETE.
- **What is sent:** your access token in the `X-API-Key` header, to the address in the connection. Nothing else is sent to Portainer.
- **Web probe (suggestions only):** when it lists what to watch, the module also makes one `GET /` (2 s timeout) to each published TCP port of a container (the first three, or a known default port for a few well-known apps on the host network), on that environment's address. It tries `http`, then `https` without checking the certificate. A container that answers with an error of 500 or above is not offered a web check. Edge-agent environments have no address, so they are never probed.
- **Caching:** checks that run together share one Portainer answer for 5 seconds. Proxy settings from the environment are ignored.
- **Why Portainer and not the Docker socket:** the Docker socket is effectively root on the host. MonitorBox has no socket access and does not talk to Portainer agents directly; it asks the Portainer server, which already manages every environment, with a token that can be revoked in Portainer.

## What you need to provide

- A running Portainer server that MonitorBox can reach over the network.
- An **access token**. In Portainer: My account, Access tokens, add one, and copy it (the form's help text names the same place). The token acts with the rights of the Portainer user that made it, so the form recommends a separate non-admin user that can see only what it needs. Whether a given Portainer edition lets such a user read container lists is up to Portainer; MonitorBox only reports what Portainer allows (see "Troubleshooting").
- Optional: the port, if it is not 9443, and the plain-http tick if you use port 9000.
- Guides for creating tokens and users live in Portainer's own documentation, not in MonitorBox.

## Adds to the app

- A **Portainer** service type on the Servers page, with a Test connection button that lists what it found (environments and containers per stack).
- **Three check types:** "environment" (can Portainer reach this environment), "container" (is this container running properly) and "mac" (no two containers share a MAC address on one Docker bridge).
- **Discovery and the pick list:** under "Pick what to watch" the environments are listed first, collapsed, each ticked as a whole, with its containers inside grouped by Compose stack. Running containers start ticked, stopped ones do not.
- **Containers as services:** each container is a system in the Services group with its title, environment, stack, icon and (if found) a web link. The Services screen groups them one fold per environment, with a "Remove all" button per environment.
- **"Runs on" links:** each container depends on its environment's check, and a web check shares the container's system. When an environment is down, its containers show as affected by it.
- **Web checks** for containers with a page that answers (see above).
- **Environment power:** a Portainer environment follows the power of the machine it runs on (matched by address), so it is not offered as a separate item on the Power page. If it cannot be matched, the page says why (edge agent, no address, no watched system at that address, or several).
- **Follow-up proposals:** servers Portainer manages are proposed as servers of their own; Scrypted and UniFi Network containers are proposed as logins for those modules; edge agents get a note that their containers are watched through Portainer. New containers that appear later are offered under "Found more you can add" (the app looks every 30 minutes).
- **First-run setup:** it recognises a Portainer server on ports 9443 or 9000 (it answers a public status page without login). A box that only runs an agent (port 9001) gets a note to use the Portainer server instead.
- **Critical box:** a tick on the connection, "Critical: if Portainer is down here, the whole box goes red", for its environments.
- **Without it:** the app has no container views at all. Nothing else loses function; ping, port, web and other modules still work.

## How it is configured

1. Open **Settings > Servers** and open the server that runs Portainer (or add it with a name and an address).
2. Under "Add", choose **Portainer (containers)**.
3. Fill in the form:
   - **Access token** (shown as dots once saved)
   - **Port** (placeholder: 9443, the usual, or 9000 for plain http)
   - **Portainer uses plain http (port 9000)** (tick)
   - **Check the certificate (leave off for Portainer's own self-signed one)** (tick; off by default)
4. Press **Test connection**. It shows how long Portainer took and what it found.
5. Press **Save, then pick what to watch**, tick environments and containers, then **Apply**.

Later: **Pick what to watch** re-reads Portainer and lets you add or remove items; **Edit** changes the connection. Saving an edited Portainer connection re-reads its environments, and if systems are watched under an environment Portainer no longer has (renamed or deleted), it asks once whether to stop watching them.

The module is installed automatically the first time a Portainer connection is added.

## What it alerts on and how states map

A Portainer that cannot be reached, or a token it refuses, is **Unknown**, never Failed. Only a container's or environment's own reported state can make something Failed. Alerts follow the normal hold-down rules (by default 2 failures in a row over at least 60 seconds); module checks run every 15 s by default, and a failing one every 3 s.

**Environment check**

| State | When |
| --- | --- |
| Healthy | Portainer reports the environment as up ("Docker reachable from Portainer", or "Agent", "Edge agent" and so on) |
| Failed | Portainer reports it as not reachable |
| Unknown | Portainer unreachable or token refused; or Portainer has no environment of that name |

**Container check** (from Docker's own State and Status text)

| Docker says | State |
| --- | --- |
| running | Healthy |
| running, health check "starting" | Healthy ("health check starting") |
| running, "(unhealthy)" | Failed |
| restarting | Failed ("keeps restarting") |
| paused | Degraded |
| exited or created | Failed, unless "allow stopped" is set on the check, then Healthy ("stopped, as expected") |
| anything else (dead, removing, ...) | Failed |
| environment not reachable by Portainer | Unknown (the environment's own check is the one that fails) |
| container name not found on the environment | Unknown |
| Portainer unreachable or token refused | Unknown |

The web check on a container is an ordinary web check of the core app. Because the container check comes first on the system, a failing page makes the system Degraded while the container itself is fine; a failing container check makes it Down.

**Docker MAC address watch** ("Docker MAC addresses (Goliath)", in Services, depends on the environment)

Why it exists: on 2026-11-25 two pairs of containers on Goliath's media bridge shared a MAC address. Packets went to one or the other at random, so Spottarr's NNTP import hung for about 12 hours while Docker still called every container healthy (its health check only talked to itself). The usual cause is a MAC address written into a container's own settings when the container was recreated by a tool: Docker later gives the container a new IP address but keeps the old MAC, and another container gets the old IP and the MAC that goes with it.

It looks every 5 minutes (change it under Edit monitoring), reads every local bridge network and the endpoints Docker lists on it, and each container's own settings. A container's settings are read once per container (they cannot change without the container being recreated, which gives it a new id); a check repeated while a problem is being confirmed reuses what was read in the last 20 seconds.

| What it finds | State |
| --- | --- |
| Two or more endpoints on the **same** network with the same MAC (capitals ignored, empty MACs ignored, stopped endpoints included if Docker lists them) | Failed. The message names the MAC, the network, each container and its address |
| No clash, but a container's own settings ask for a fixed MAC (`Config.MacAddress`, or the MAC a stopped container's network settings ask for) and it is not on the allowed list | Degraded ("No clash now, but ...") |
| Neither | Healthy, with how many networks and MACs were read |
| Portainer, the environment or any one network could not be read | Unknown, never Healthy: a half-read environment is not called clean, so an announced clash is not called over |

- The same MAC on two different networks, or on two different Docker hosts, is not a clash.
- A MAC that Docker gave a running endpoint is not a "fixed MAC"; only one the container's settings ask for is.
- Host-networked containers (and those sharing another container's network) are left out of the fixed-MAC part.
- **Allowed fixed MACs:** under **Edit monitoring** on the item, list containers that have a fixed MAC on purpose, one per line: a name, or `name/network` for one network only. An allowed container never hides a real clash.
- The 02:42-plus-IP pattern (`02:42:ac:1d:00:06` for `172.29.0.6`) is only a hint in the message ("Docker would give it ..."). Newer Docker versions and other drivers choose MACs differently, so a MAC that does not follow it is not a fault.
- Alerts: one message when a clash or an unexpected fixed MAC appears, an update when exactly what is wrong changes (another container joins a clash, a new fixed MAC appears) once the new picture has lasted as long as a new problem must, and an all-clear when it is gone. A restart of MonitorBox does not repeat a message already sent. The item can be ticked Critical like any other.
- Nothing is ever changed: no restart, recreate, reconnect, or edit of a network, container, compose file or stack. Only the few fields named above are kept from Docker's answers; environment variables and labels are never read out, kept or logged.

Existing boxes: open the Portainer connection, **Pick what to watch**, and tick "Docker MAC addresses (...)" under Environments. New connections offer it ticked.

## Known limits

- Only environments of type Docker, Agent and Edge agent (Docker) have their containers listed. Azure and Kubernetes environments get an environment check but no containers.
- Container names are matched exactly (including capitals) on the container's first name. A renamed or recreated container with a new name reads Unknown ("no container called ... any more") until you pick the new one.
- "Allow stopped" (for jobs that are meant to exit) is a setting on the check itself; the pick screen has no tick for it.
- A container on the host network publishes no ports, so a web link is only offered for a short list of well-known apps (Plex, Home Assistant, Homebridge, Jellyfin, Pi-hole, Sonarr, Radarr and others) on their usual port, and only if something answers there.
- The module sees only what the token's Portainer user may see. A container hidden from that user is not listed.
- The certificate is not checked unless you tick the box; Portainer's own certificate is usually self-signed.
- Docker's health check is reported as it is. A container that briefly fails its own health check shows as Failed for that moment (the hold-down rule smooths short blips).
- Suggestions are re-read by the app every 10 minutes (and when you open Pick what to watch); a new container can take that long to be offered.
- The MAC watch covers bridge networks only (not macvlan, ipvlan or overlay). Docker shows the MAC a running container's network settings ask for only while it is stopped, so a per-network fixed MAC on a running container is found through `Config.MacAddress` or the next time it stops; a clash it causes is found either way.

## Troubleshooting

Messages from the module appear as the detail of an Unknown or Failed item, or under Test connection.

| Message | Meaning |
| --- | --- |
| `this connection needs an access token (create one in Portainer under My account > Access tokens)` | The token field is empty. |
| `this connection has no 'host' or 'base_url'` | The connection has no address. |
| `cannot reach Portainer at https://192.0.2.10:9443 (...)` | Network problem: wrong address or port, Portainer down, firewall, or (with the certificate box ticked) a certificate that does not verify. The reason is in brackets. |
| `Portainer refused the access token` | HTTP 401: the token is wrong, deleted or expired. |
| `Portainer refused the access token (it may not be allowed to see that environment)` | HTTP 403: the token's user lacks rights on that environment. |
| `Portainer does not have that (is it a newer or older version?)` | HTTP 404 on one of the paths. |
| `Portainer answered HTTP 500` (or another code) | Portainer replied with an error. |
| `Portainer has no environment called 'X' (it has: A, B)` | The environment was renamed or removed. Re-pick, or accept the offer to stop watching it. |
| `Portainer cannot reach this docker (tcp://192.0.2.20:2375)` | Portainer itself says the environment is down. The word after "this" is the type (docker, agent, edge agent). |
| `Portainer cannot reach A, so its containers cannot be read` | The environment is down; containers are Unknown, not Failed. |
| `A has no container called 'plex' any more` | The container was removed, renamed or recreated. |
| `this check needs a container 'name'. Use Pick what to watch.` | A hand-edited check has no name. |
| `could not read every Docker network on A, so nothing is judged (...)` | The MAC watch could not read one of the networks or containers; it says nothing either way until it can. |
| `A is not a Docker environment` | The MAC watch was pointed at a Kubernetes or Azure environment. |
| `the portainer module is starting` / `is not running` / `did not answer` | The module itself, not Portainer. Starting is brief; "not running" means install it under Settings, Versions. All are Unknown. |

In Test connection, an error line is shown in plain words and the module's own message is under "Technical detail". A refused token may be worded there as "The device refused the connection"; read the technical detail to tell it from a wrong port.

If the certificate box is ticked and Portainer uses its own self-signed one, untick it and test again.

## Where it lives in the code

- `modules/portainer/manifest.json`: module id, version, entry point.
- `modules/portainer/main.py`: request handling (`hello`, `describe`, `check`, `discover`), the web probe.
- `modules/portainer/portainerlib.py`: the read-only Portainer client (allowed paths, token header, errors, 5 s cache).
- `modules/portainer/portainerchecks.py`: state mapping, discovery and suggestion building.
- `modules/portainer/macwatch.py`: the Docker MAC address watch (reading networks and settings, finding clashes and fixed MACs, the wording).
- `app/monitorbox_app/ui.py`: the form (`SVC.portainer`), the pick list, the Services screen.
- `app/monitorbox_app/server.py`: Portainer discovery cache, Test connection, power matching (`power_scan`).
- `app/monitorbox_app/followups.py`: proposals from Portainer (`from_portainer`, `notes_from_portainer`).
- `app/monitorbox_app/thisbox.py`: recognising a Portainer server or agent on this box.
- `app/monitorbox_app/monconfig.py`: `add_watches` (container depends on its environment).
