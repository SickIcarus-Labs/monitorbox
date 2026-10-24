"""Hello module: proves the install/update path and the JSON-lines protocol, and is the reference
implementation of the "check" call that real modules (wol, snmp, nut, unifi) follow.

  App -> module : {"id", "method": "check", "params": {"check": name, "params": {...}, "connection": {...settings...}}}
  module -> App : {"id", "result": {"state": "healthy"|"degraded"|"failed"|"unknown", "detail": text}}  or  {"id", "error": text}

An error or silence from the module makes the check "unknown" (could not be checked), never "failed":
only a module that really talked to the device may say "failed"."""
import json, os, sys

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")) as f:
    VERSION = json.load(f)["version"]


def check(args):
    want, conn = args.get("params", {}), args.get("connection") or {}
    if want.get("crash"):
        sys.exit(3)
    if want.get("raise"):
        raise RuntimeError("simulated device library error")
    res = {"state": want.get("state", "healthy"), "detail": want.get("detail", "hello check")}
    if want.get("echo"):  # lets a test see exactly what reached the module
        res["detail"] = json.dumps({"fields": sorted(conn), "value": conn.get(want["echo"])})
    return res


METHODS = {
    "hello": lambda a: {"module": "hello", "version": VERSION},
    "describe": lambda a: {"title": "Hello", "text": f"Hello from module version {VERSION}", "status": "healthy"},
    "check": check,
}

for line in sys.stdin:
    req = json.loads(line)
    fn = METHODS.get(req.get("method"))
    try:
        if not fn:
            raise ValueError(f"unknown method {req.get('method')}")
        out = {"id": req["id"], "result": fn(req.get("params", {}))}
    except Exception as e:
        out = {"id": req["id"], "error": str(e)}
    print(json.dumps(out), flush=True)
