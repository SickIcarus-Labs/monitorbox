"""Turning what Portainer reports into check results and ready-made suggestions. No I/O here except the optional
web probe, which is passed in so tests can replace it."""
import re
from urllib.parse import urlsplit

EDGE_TYPES = (4, 7)
DOCKER_TYPES = (1, 2, 4)        # Docker, Agent on Docker, Edge Agent on Docker: the ones that have containers to list
TYPE_NAMES = {1: "Docker", 2: "Agent", 3: "Azure", 4: "Edge agent", 5: "Kubernetes", 6: "Kubernetes agent", 7: "Edge agent (Kubernetes)"}


def find_env(endpoints, params):
    want_id, want = params.get("env_id"), str(params.get("env") or params.get("name") or "").strip().lower()
    for e in endpoints:
        if want_id is not None and e.get("Id") == want_id:
            return e
        if want and str(e.get("Name", "")).lower() == want:
            return e
    return None


def env_host(env):
    """The address Portainer uses for an environment, or None when it is Portainer's own machine (a unix socket)."""
    url = env.get("URL") or ""
    if url.startswith("unix:") or url.startswith("npipe:") or not url:
        return None
    return urlsplit(url if "://" in url else "tcp://" + url).hostname


def check_environment(params, endpoints):
    env = find_env(endpoints, params)
    names = ", ".join(sorted(str(e.get("Name")) for e in endpoints)) or "none"
    if not env:
        return {"state": "unknown", "detail": f"Portainer has no environment called '{params.get('name') or params.get('env')}' (it has: {names})"}
    kind = TYPE_NAMES.get(env.get("Type"), "environment")
    if env.get("Status") == 1:
        return {"state": "healthy", "detail": f"{kind} reachable from Portainer"}
    return {"state": "failed", "detail": f"Portainer cannot reach this {kind.lower()} ({env.get('URL') or 'no address'})"}


def container_name(c):
    n = (c.get("Names") or [""])[0]
    return n.lstrip("/")


def judge(c, allow_stopped=False):
    """(state, detail) for one container from Docker's own State and Status text."""
    st, status = str(c.get("State", "")).lower(), str(c.get("Status", ""))
    low = status.lower()
    if st == "running":
        if "(unhealthy)" in low:
            return "failed", f"running, but Docker's health check says unhealthy ({status})"
        if "health: starting" in low:
            return "healthy", f"running · health check starting ({status})"
        return "healthy", f"running · healthy" if "(healthy)" in low else f"running ({status})"
    if st == "restarting":
        return "failed", f"keeps restarting ({status})"
    if st == "paused":
        return "degraded", f"paused ({status})"
    if allow_stopped and st in ("exited", "created"):
        return "healthy", f"stopped, as expected ({status})"
    return "failed", f"{st or 'not running'} ({status})"


def check_container(params, endpoints, fetch):
    env = find_env(endpoints, params)
    if not env:
        return {"state": "unknown", "detail": f"Portainer has no environment called '{params.get('env')}'"}
    if env.get("Status") != 1:
        return {"state": "unknown", "detail": f"Portainer cannot reach {env.get('Name')}, so its containers cannot be read"}
    name = str(params.get("name") or "")
    if not name:
        return {"state": "unknown", "detail": "this check needs a container 'name'. Use Pick what to watch."}
    for c in fetch(env["Id"]):
        if container_name(c) == name:
            return dict(zip(("state", "detail"), judge(c, bool(params.get("allow_stopped")))))
    return {"state": "unknown", "detail": f"{env.get('Name')} has no container called '{name}' any more"}


# ---- suggestions -----------------------------------------------------------
def pretty(name):
    s = re.sub(r"[-_.]+", " ", name).strip()
    return s[:1].upper() + s[1:] if s else name


def icon_guess(c):
    """A slug to look the app's icon up by: the image's last path part, else the container name."""
    img = str(c.get("Image", "")).split("@")[0].rsplit("/", 1)[-1].split(":")[0].lower()
    return img or container_name(c).lower()


def stack_of(c):
    labels = c.get("Labels") or {}
    return labels.get("com.docker.compose.project") or labels.get("com.docker.stack.namespace") or ""


def web_ports(c):
    seen, out = set(), []
    for p in c.get("Ports") or []:
        pp = p.get("PublicPort")
        if pp and p.get("Type", "tcp") == "tcp" and pp not in seen:
            seen.add(pp)
            out.append(pp)
    return out


# Containers on the host network publish no ports, so Portainer lists none and there is nothing to link to. For a few well-known apps
# we try their usual web port instead, and only offer the link when something answers there.
DEFAULT_WEB_PORTS = {"plex": 32400, "pms-docker": 32400, "homeassistant": 8123, "home-assistant": 8123, "homebridge": 8581,
                     "jellyfin": 8096, "emby": 8096, "pihole": 80, "pi-hole": 80, "adguard": 3000, "scrypted": 10443,
                     "uptime-kuma": 3001, "grafana": 3000, "tautulli": 8181, "sonarr": 8989, "radarr": 7878, "lidarr": 8686,
                     "prowlarr": 9696, "bazarr": 6767, "ombi": 3579, "overseerr": 5055, "seerr": 5055, "jellyseerr": 5055}


# Where the app's own front page lives, for the link on its row (the web check keeps testing the plain address).
LINK_PATHS = {"plex": "web", "pms-docker": "web", "pihole": "admin/", "pi-hole": "admin/", "jellyfin": "web/", "emby": "web/",
              "adguard": "", "homebridge": "", "unifi": "manage/"}


# Apps whose bare address stops being a page after an update (Pi-hole 6 answers 404 on "/"): the web check tests the front page instead.
CHECK_PATHS = {"pihole": "admin/", "pi-hole": "admin/"}


def check_path(c):
    for key in (container_name(c).lower(), icon_guess(c)):
        for name, path in CHECK_PATHS.items():
            if key == name or key.startswith(name + "-") or key.endswith("-" + name):
                return path
    return ""


def link_path(c):
    for key in (container_name(c).lower(), icon_guess(c)):
        for name, path in LINK_PATHS.items():
            if key == name or key.startswith(name + "-") or key.endswith("-" + name):
                return path
    return ""


def host_networked(c):
    return str(((c.get("HostConfig") or {}).get("NetworkMode")) or "").lower() == "host"


def web_candidates(c):
    """Ports worth probing for a web page: the published ones, else (host network only) the app's usual port."""
    ports = web_ports(c)[:3]
    if ports or not host_networked(c):
        return ports
    for key in (container_name(c).lower(), icon_guess(c)):
        for name, port in DEFAULT_WEB_PORTS.items():
            if key == name or key.startswith(name + "-") or key.endswith("-" + name):
                return [port]
    return []


def discover(endpoints, fetch, host_of_portainer, probe_web):
    """endpoints: Portainer's list. fetch(env_id) -> containers. probe_web(host, port) -> {"url","expect"?,"insecure"?} or None."""
    suggest, envs = [], []
    for env in sorted(endpoints, key=lambda e: str(e.get("Name", "")).lower()):
        name, up = str(env.get("Name")), env.get("Status") == 1
        edge = env.get("Type") in EDGE_TYPES            # an edge agent calls Portainer; it has no address of its own to look at
        host = None if edge else (env_host(env) or host_of_portainer)
        envs.append({"name": name, "type": TYPE_NAMES.get(env.get("Type"), "environment"), "up": up, "address": host or "", "edge": edge})
        env_item = {"label": f"Environment {name}", "check": "environment", "params": {"name": name},
                    "node": f"{name} Portainer", "group": "Services", "batch": "Environments", "env": name}
        suggest.append(env_item)
        if not up or env.get("Type") not in DOCKER_TYPES:
            continue
        try:
            containers = fetch(env["Id"])
        except Exception:
            continue
        probes = {}
        for c in containers:
            for port in web_candidates(c):
                probes[(container_name(c), port)] = (host, port)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            hits = dict(zip(probes, pool.map(lambda hp: probe_web(*hp) if hp[0] else None, probes.values())))
        for c in sorted(containers, key=container_name):
            cname = container_name(c)
            stack = stack_of(c)
            title = pretty(cname)
            node = f"{title} ({name})"
            running = str(c.get("State")).lower() == "running"
            service = {"title": title, "env": name, "container": cname, "icon": icon_guess(c)}
            if stack:
                service["stack"] = stack
            web = next((hits[(cname, p)] for p in web_candidates(c) if hits.get((cname, p))), None)
            if web:
                service["url"] = web["url"] + link_path(c)
            batch = f"{name} · {stack}" if stack else f"{name} · other containers"
            item = {"label": f"Container {cname} on {name}", "check": "container", "params": {"env": name, "name": cname},
                    "node": node, "group": "Services", "batch": batch, "service": service, "requires": env_item, "default": running,
                    "env": name}
            suggest.append(item)
            if web:
                w = {"label": f"Web {cname} on {name}", "type": "http", "url": web["url"] + check_path(c), "node": node, "group": "Services",
                     "batch": batch, "service": service, "requires": env_item, "default": running, "env": name}
                for k in ("expect", "insecure"):
                    if web.get(k):
                        w[k] = web[k]
                suggest.append(w)
    return {"environments": envs, "suggest": suggest}
