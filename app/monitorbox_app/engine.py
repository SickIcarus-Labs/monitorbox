"""Status engine: nodes + latest check results -> what the screen shows.

Pure functions, no I/O, no clock of their own: everything is passed in, so the whole
rulebook can be tested without a network.

Node (already validated, see monconfig.py):
  {"id","name","group","critical", "checks":[{"id","type",...}], "rule":"primary"|"any",   # a leaf
   "kind":"aggregate", "children":[ids], "rule":"any"|"all",                                # or an aggregate
   "dependsOn":[ids]}

Check result: {"ok": True|False|None, "detail": str, "ms": float|None, "at": iso, "since": iso, "warn": bool (optional: ok, but not properly)}
  ok None means "could not be checked" (unknown), never "failed".

States: healthy, degraded, failed, unknown, pending (no result yet).
Observed state is never rewritten. A node that is down because something it depends on is
down is marked "affectedBy" that root cause; it keeps its own observed state.
Banner precedence: red (a critical thing down: "Everything is fucked."; anything else down: "Something's down") > yellow (something degraded, nothing down) > blue (cannot check) > green.
A check can also carry a notice ("it is fine, but you may want to know", such as a busy CPU): it never changes a state, it only adds a heads-up line under a green headline.
"""
import re

HEALTHY, DEGRADED, FAILED, UNKNOWN, PENDING = "healthy", "degraded", "failed", "unknown", "pending"
LABEL = {FAILED: "Down", DEGRADED: "Degraded", UNKNOWN: "Unknown", HEALTHY: "Healthy", PENDING: "Checking"}
GROUP_ORDER = ["Servers", "Network", "Internet", "Power", "Cameras", "Services"]
_SEVERITY = {FAILED: 3, DEGRADED: 2, UNKNOWN: 1, HEALTHY: 0, PENDING: 0}


def _leaf_state(node, results):
    rs = [results.get(f"{node['id']}/{c['id']}") for c in node["checks"]]
    if not rs or all(r is None for r in rs):
        return PENDING, None
    # a check that has no result yet is ignored; at least one has one
    rs = [r for r in rs if r is not None]
    if node.get("rule", "primary") == "any":
        clean = [r for r in rs if r["ok"] is True and not r.get("warn")]
        warns = [r for r in rs if r["ok"] is True and r.get("warn")]
        bad = [r for r in rs if r["ok"] is False]
        if len(clean) == len(rs):
            return HEALTHY, None
        if clean or warns:
            return (DEGRADED, (bad + warns)[0]) if (bad or warns) else (HEALTHY, None)
        if bad and len(bad) == len(rs):
            return FAILED, bad[0]
        return UNKNOWN, next((r for r in rs if r["ok"] is None), None)
    # primary: first check is "is it there"; the rest are "is it working properly"
    first = results.get(f"{node['id']}/{node['checks'][0]['id']}")
    if first is None:
        return PENDING, None
    if first["ok"] is False:
        return FAILED, first
    if first["ok"] is None:
        return UNKNOWN, first
    problems = [r for r in rs if r["ok"] is False or r.get("warn")]  # "warn" = it answers, but not properly
    if problems:
        return DEGRADED, problems[0]
    return HEALTHY, None


def _camera_key(n):
    """The identity of a camera node (so one camera that two sources both report counts once), or None for anything else."""
    cs = n.get("checks") or []
    if n.get("kind") != "aggregate" and len(cs) == 1 and cs[0].get("type") == "module" and cs[0].get("check") == "camera":
        return "camera:" + re.sub(r"^camera\s+", "", str(n.get("name", "")), flags=re.I).strip().lower()
    return None


def _aggregate_state(node, states):
    kids = [states[c] for c in node["children"] if c in states]
    kids = [k for k in kids if k != PENDING]
    if not kids:
        return PENDING
    healthy = sum(1 for k in kids if k == HEALTHY)
    if healthy == len(kids):
        return HEALTHY
    if node.get("rule", "any") == "any":
        if healthy:
            return DEGRADED
        return FAILED if all(k == FAILED for k in kids) else UNKNOWN
    if FAILED in kids:
        return FAILED
    return DEGRADED if DEGRADED in kids else UNKNOWN


# The words of the NUT module's UPS status that mean the power is going (alerts.py announces these at once; a test keeps them in step with the module)
POWER_URGENT = {"on battery": "is running on battery", "low battery": "has a low battery", "shutting down": "is shutting down"}


_CONFIRMING = re.compile(r"^(?:failed|warning) just now, confirming \([^)]*\): (.*)$", re.S)


def plain_notice(text):
    """One notice in plain words. A check that is still being confirmed says 'warning just now, confirming (2 of 2 in a row, 16 s of 60 s): <what>';
    the line under 'Everything is fine' keeps the <what> and says 'confirming', without the counts."""
    t = str(text).strip()
    m = _CONFIRMING.match(t)
    return f"{m.group(1).strip()}, confirming" if m else t


def heads_up(items):
    """items: [(system name, notice)]. Each thing once, in plain words: a repeat inside one system is dropped, and systems saying the same
    thing share a line ('Aggregation and UniFi: ...')."""
    by_text = {}
    for name, notice in items:
        for part in str(notice).split("; "):
            t = plain_notice(part)
            if t and name not in by_text.setdefault(t, []):
                by_text[t].append(name)
    return [f"{' and '.join(names)}: {t}" for t, names in by_text.items()]


def evaluate(nodes, results, now_iso=""):
    by_id = {n["id"]: n for n in nodes}
    state, why = {}, {}

    def resolve(nid, seen=()):
        if nid in state:
            return state[nid]
        n = by_id[nid]
        if n.get("kind") == "aggregate":
            for c in n["children"]:
                if c in by_id:
                    resolve(c)
            state[nid] = _aggregate_state(n, state)
            why[nid] = None
        else:
            state[nid], why[nid] = _leaf_state(n, results)
        return state[nid]

    for n in nodes:
        resolve(n["id"])

    # --- root cause: the failed ancestors that are not themselves under a failed ancestor
    def ancestors(nid):
        out, stack, seen = [], list(by_id[nid].get("dependsOn", [])), set()
        while stack:
            a = stack.pop()
            if a in seen or a not in by_id:
                continue
            seen.add(a)
            out.append(a)
            stack.extend(by_id[a].get("dependsOn", []))
        return out

    failed_anc = {n["id"]: [a for a in ancestors(n["id"]) if state[a] == FAILED] for n in nodes}
    affected_by = {}
    for n in nodes:
        roots = [a for a in failed_anc[n["id"]] if not failed_anc[a]]
        if roots and state[n["id"]] in (FAILED, DEGRADED, UNKNOWN):
            affected_by[n["id"]] = sorted(roots)

    # Same idea for "cannot be checked": things behind a provider we cannot reach are unknown because of it
    unk_anc = {n["id"]: [a for a in ancestors(n["id"]) if state[a] == UNKNOWN] for n in nodes}
    for n in nodes:
        nid = n["id"]
        if state[nid] == UNKNOWN and nid not in affected_by and unk_anc[nid]:
            roots = [a for a in unk_anc[nid] if not unk_anc[a] and not failed_anc[a]]
            if roots:
                affected_by[nid] = sorted(roots)

    # An aggregate that is down explains its children (Internet down explains both failed pings),
    # unless every child already has its own root cause (all three DNS hosts down explains "DNS down").
    for n in nodes:
        if n.get("kind") == "aggregate" and state[n["id"]] == FAILED and n["id"] not in affected_by:
            kids = [c for c in n["children"] if c in by_id]
            if kids and all(c in affected_by for c in kids):
                affected_by[n["id"]] = sorted({r for c in kids for r in affected_by[c]})
            else:
                for c in kids:
                    if state[c] in (FAILED, DEGRADED, UNKNOWN) and c not in affected_by:
                        affected_by[c] = [n["id"]]

    # --- power: a system "powered by" a UPS that is down, or running on battery, is explained by it when the system goes down too.
    # (A UPS on battery is only degraded, so the ordinary dependency rule above would not cover a server that then shuts down.)
    def power_urgent(pid):
        for c in by_id[pid].get("checks", []):
            r = results.get(f"{pid}/{c['id']}")
            if c.get("module") == "nut" and r and r["ok"] is True and r.get("warn") and any(w in str(r.get("detail") or "").lower() for w in POWER_URGENT):
                return True
        return False

    for n in nodes:
        nid = n["id"]
        if nid in affected_by or state[nid] not in (FAILED, DEGRADED, UNKNOWN):
            continue
        roots = [p for p in n.get("poweredBy") or [] if p in by_id and p != nid and not failed_anc[p] and (state[p] == FAILED or power_urgent(p))]
        if roots:
            affected_by[nid] = sorted(roots)

    # --- what each root takes with it
    affects = {}
    for nid, roots in affected_by.items():
        if by_id[nid].get("kind") == "aggregate":
            continue
        for r in roots:
            affects.setdefault(r, []).append(nid)

    def check_rows(n):
        if n.get("kind") == "aggregate":
            return []
        rows = []
        for c in n["checks"]:
            r = results.get(f"{n['id']}/{c['id']}")
            rows.append({"id": c["id"], "type": c.get("module") or c["type"],
                         "target": c.get("target") or c.get("url") or c.get("check") or "",
                         "label": c.get("label", ""), "web": c["type"] == "http" and not n.get("builtin"),
                         "state": PENDING if r is None else ((DEGRADED if r.get("warn") else HEALTHY) if r["ok"] is True else FAILED if r["ok"] is False else UNKNOWN),
                         "notice": bool(r and r["ok"] is True and r.get("notice")),
                         "detail": "" if r is None else r["detail"], "ms": None if r is None else r.get("ms"),
                         "at": None if r is None else r.get("at")})
        return rows

    # --- expected down: the owner said this is off on purpose. Its observed state is untouched; it just stays out of
    # the banner, the attention list and the card tallies. Whatever only fails because of it is quiet too.
    expected = {n["id"] for n in nodes if n.get("expectedDown")}
    muted = {nid for nid in by_id if state[nid] not in (HEALTHY, PENDING) and
             (nid in expected or (affected_by.get(nid) and all(r in expected for r in affected_by[nid])))}

    out_nodes = {}
    for n in nodes:
        w = why[n["id"]]
        out_nodes[n["id"]] = {
            "id": n["id"], "name": n["name"], "group": n["group"], "critical": bool(n.get("critical")),
            "kind": n.get("kind", "leaf"), "state": state[n["id"]],
            "label": "Down, expected" if n["id"] in muted and state[n["id"]] == FAILED else LABEL[state[n["id"]]],
            "detail": (w or {}).get("detail", ""), "since": (w or {}).get("since"),
            "affectedBy": affected_by.get(n["id"], []),
            "affects": sorted(affects.get(n["id"], [])), "dependsOn": n.get("dependsOn", []), "poweredBy": n.get("poweredBy", []),
            "canWake": bool(n.get("wake")), "expected": n["id"] in expected, "muted": n["id"] in muted,
            "builtin": bool(n.get("builtin")),
            "notice": "; ".join(c["detail"] for c in check_rows(n) if c["notice"]),
            "checks": check_rows(n), "children": list(n.get("children", [])), "service": n.get("service"), "link": n.get("link"),
        }

    # a camera two sources both report (UniFi Protect and Scrypted) is one camera: both say it is down, it is Down; one says down and the other says it is fine,
    # it is only Degraded (the trouble may be with one source, such as Scrypted acting up). Each node keeps what its own source observed; only the banner,
    # the attention list (one entry per camera, so one alert) and the card tallies use this.
    eff = dict(state)
    cam_members = {}
    for n in nodes:
        k = _camera_key(n)
        if k and n["id"] not in muted:
            cam_members.setdefault(k, []).append(n["id"])
    cam_rep = {}
    for ids in cam_members.values():
        if len(ids) < 2:
            continue
        ids.sort()
        seen = [state[i] for i in ids if state[i] != PENDING]
        if FAILED in seen and (HEALTHY in seen or DEGRADED in seen):
            for i in ids:
                if state[i] == FAILED:
                    eff[i] = DEGRADED
        for i in ids:
            cam_rep[i] = ids

    # --- what is worth the person's attention: roots only; aggregates only when they are down
    def counts_for_banner(n):
        return n.get("kind") != "aggregate" or eff[n["id"]] == FAILED

    attention = []
    for n in nodes:
        ids = cam_rep.get(n["id"])
        if ids and n["id"] != ids[0]:
            continue                              # the same camera from another source: the first one speaks for it
        src = by_id[max(ids, key=lambda i: _SEVERITY[eff[i]])] if ids else n          # the source with the most to say
        s = eff[src["id"]]
        if s not in (FAILED, DEGRADED, UNKNOWN) or src["id"] in affected_by or not counts_for_banner(src) or n["id"] in muted:
            continue
        o = out_nodes[src["id"]]
        w = why[src["id"]]
        bad = next((c.get("label") or "" for c in src.get("checks", []) if w is not None and results.get(f"{src['id']}/{c['id']}") is w), "")
        detail = o["detail"]
        if ids and state[src["id"]] == FAILED and s == DEGRADED:
            detail = (detail + " (the other source reports it fine)").strip()
        attention.append({"id": n["id"], "name": n["name"], "group": n["group"], "critical": o["critical"], "state": s, "label": LABEL[s],
                          "detail": detail, "since": o["since"], "check": bad if len(src.get("checks", [])) > 1 else "",
                          "affects": [by_id[a]["name"] for a in o["affects"]]})
    attention.sort(key=lambda a: (-_SEVERITY[a["state"]], not a["critical"], a["name"].lower()))

    visible = [n for n in nodes if counts_for_banner(n) and eff[n["id"]] != PENDING and n["id"] not in muted]
    failed_crit = [n for n in visible if eff[n["id"]] == FAILED and n.get("critical")]
    any_down = [n for n in visible if eff[n["id"]] in (FAILED, DEGRADED)]
    any_unknown = [n for n in visible if eff[n["id"]] == UNKNOWN]
    leaf_total = sum(1 for n in nodes if n.get("kind") != "aggregate")
    pending = any(eff[n["id"]] == PENDING for n in nodes)

    def names(items):
        items = [i["name"] for i in items]
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]

    def plural(k, one, many):
        return one if k == 1 else many

    down = [a for a in attention if a["state"] == FAILED]
    shaky = [a for a in attention if a["state"] == DEGRADED]
    any_failed = [n for n in visible if eff[n["id"]] == FAILED]

    def who(items, one, many, fallback):
        """"A and B are down" for a few things, "5 things are down" for more."""
        if 0 < len(items) <= 3:
            return f"{names(items)} {one if len(items) == 1 else many}"
        k = len(items) or fallback
        return f"{k} {plural(k, 'thing', 'things')} {one if k == 1 else many}"

    if failed_crit:
        status, headline = "red", "Everything is fucked."
        roots = [a for a in attention if a["state"] == FAILED and a["critical"]]
        down = roots or [{"name": n["name"]} for n in failed_crit]
        extra = sum(len(a["affects"]) for a in attention if a["state"] == FAILED)
        sub = f"{names(down)} {plural(len(down), 'is', 'are')} down."
        if extra:
            sub += f" {extra} other {plural(extra, 'item is', 'items are')} affected."
    elif any_failed:                  # an actual down is red, even when nothing critical depends on it
        status, headline = "red", "Something's down"
        sub = who(down, "is down", "are down", len(any_failed)) + ". Nothing critical is affected."
        if shaky:
            sub += " " + who(shaky, "is also having trouble", "are also having trouble", len(shaky)) + "."
    elif any_down:                    # only degraded: it answers, but not properly
        status, headline = "yellow", "Something's not right"
        sub = who(shaky, "is having trouble", "are having trouble", len(any_down)) + ". Nothing is down."
    elif any_unknown:
        k = len(attention) or len(any_unknown)
        status, headline = "blue", "Something needs a look"
        sub = (f"MonitorBox cannot check {k} {plural(k, 'thing', 'things')} right now. Nothing is known to be broken.")
    elif pending and not visible:
        status, headline, sub = "starting", "Checking everything…", "First results are on their way."
    else:
        status, headline = "green", "Everything is fine"
        quiet = sum(1 for n in nodes if n["id"] in muted and n.get("kind") != "aggregate")
        if quiet:
            sub = f"All {leaf_total - quiet} other {plural(leaf_total - quiet, 'item is', 'items are')} reporting normally. {quiet} expected down."
        else:
            sub = f"All {leaf_total} {plural(leaf_total, 'item is', 'items are')} reporting normally."
        heads = heads_up([(out_nodes[n["id"]]["name"], out_nodes[n["id"]]["notice"]) for n in visible if out_nodes[n["id"]]["notice"] and n.get("kind") != "aggregate"])
        if heads:                     # worth knowing, not a problem: a quiet line under the green headline
            sub += " Heads-up: " + "; ".join(heads[:2]) + (f" and {len(heads) - 2} more" if len(heads) > 2 else "") + "."

    # --- cards, one per group
    groups = []
    for n in nodes:
        if n["group"] not in groups:
            groups.append(n["group"])
    seen_order = list(groups)
    groups = sorted(groups, key=lambda g: (GROUP_ORDER.index(g) if g in GROUP_ORDER else len(GROUP_ORDER), seen_order.index(g)))
    cards = []
    for g in groups:
        members = [n for n in nodes if n["group"] == g]
        all_leaves = [n for n in members if n.get("kind") != "aggregate"] or members
        quiet_names = [n["name"] for n in all_leaves if n["id"] in muted]
        leaves = [n for n in all_leaves if n["id"] not in muted]
        if not leaves:      # everything in this group is expected down
            cards.append({"name": g, "state": "expected", "label": "Expected down", "big": "Expected down",
                          "line": ", ".join(quiet_names), "nodes": [n["id"] for n in members]})
            continue
        sts = [eff[n["id"]] for n in leaves if eff[n["id"]] != PENDING]
        worst = max(sts, key=lambda s: _SEVERITY[s]) if sts else PENDING
        # an aggregate that is down outranks its healthy-looking leaves (e.g. all DNS servers failed)
        for n in members:
            if n.get("kind") == "aggregate" and n["id"] not in muted and _SEVERITY[eff[n["id"]]] > _SEVERITY.get(worst, 0):
                worst = eff[n["id"]]
        up = sum(1 for s in sts if s == HEALTHY)
        total = len(leaves)
        # one camera seen by two sources (UniFi Protect and Scrypted both list it) is one camera; a card of cameras counts the cameras, not the integrations
        by_cam = {}
        for n in leaves:
            if _camera_key(n):
                by_cam.setdefault(_camera_key(n), []).append(n)
        if by_cam:
            cam_states = [max((eff[m["id"]] for m in ms if eff[m["id"]] != PENDING), key=lambda s: _SEVERITY[s], default=PENDING) for ms in by_cam.values()]
            up, total = sum(1 for s in cam_states if s == HEALTHY), len(by_cam)

        def distinct(items):
            out_ = []
            for n in items:
                k = _camera_key(n)
                if k and k in seen_cam_for[0]:
                    continue
                if k:
                    seen_cam_for[0].add(k)
                out_.append(n)
            return out_
        if worst == PENDING:
            big, line = "…", "Checking"
        elif total == 1:
            big = {HEALTHY: "Up", DEGRADED: "Degraded", FAILED: "Down", UNKNOWN: "Unknown"}[worst]
            line = leaves[0]["name"]
        else:
            big = f"{up} of {total} up"
            parts = []
            for st, verb_one, verb_many in ((FAILED, "is down", "are down"), (DEGRADED, "is degraded", "are degraded"),
                                            (UNKNOWN, "cannot be checked", "cannot be checked")):
                seen_cam_for = [set()]
                who = [n["name"] for n in distinct([n for n in leaves if eff[n["id"]] == st])]
                if who:
                    shown = who[:3]
                    label = (", ".join(shown[:-1]) + " and " + shown[-1]) if len(shown) > 1 else shown[0]
                    if len(who) > 3:
                        label = ", ".join(shown) + f" and {len(who) - 3} more"
                    parts.append(f"{label} {verb_one if len(who) == 1 else verb_many}")
            line = "; ".join(parts) if parts else (names([{"name": n["name"]} for n in leaves]) if total <= 3 else "All healthy")
        if quiet_names:
            line += ("; " if line and line != "All healthy" else "") + ", ".join(quiet_names) + " expected down"
        cards.append({"name": g, "state": worst, "label": LABEL[worst], "big": big, "line": line,
                      "nodes": [n["id"] for n in members]})

    return {"banner": {"status": status, "headline": headline, "subline": sub},
            "attention": attention, "cards": cards, "nodes": out_nodes, "generatedAt": now_iso}
