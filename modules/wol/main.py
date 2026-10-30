"""Wake on LAN module. Sends magic packets; the App confirms the machine came up by checking it.

  wake  {"macs": ["aa:bb:cc:dd:ee:ff", ...], "broadcast": "192.0.2.255", "port": 9}  ->  {"sent": N}

MAC addresses are plain per-system settings (edited in the App; they live in monitorbox.json, so a settings backup carries them).
A packet is sent for every MAC, so a machine with two network cards can be listed with both."""
import json, os, re, socket, sys

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")) as f:
    VERSION = json.load(f)["version"]

MAC_RE = re.compile(r"^[0-9a-f]{12}$")


def normalize(mac):
    """aa:bb:cc:dd:ee:ff, aa-bb-..., aabb.ccdd.eeff or aabbccddeeff -> 'aa:bb:cc:dd:ee:ff', or ValueError."""
    flat = re.sub(r"[:.\-]", "", str(mac)).lower()
    if not MAC_RE.match(flat):
        raise ValueError(f"'{mac}' is not a MAC address")
    return ":".join(flat[i:i + 2] for i in range(0, 12, 2))


def packet(mac):
    return bytes.fromhex("ff" * 6 + normalize(mac).replace(":", "") * 16)


def wake(args):
    macs = args.get("macs") or []
    if not isinstance(macs, list) or not macs:
        raise ValueError("no MAC addresses are set for this system")
    packets = [packet(m) for m in macs]          # validates every MAC before anything is sent
    dest = (args.get("broadcast") or "255.255.255.255", int(args.get("port") or 9))
    sent = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for p in packets:
            sock.sendto(p, dest)
            sent += 1
    finally:
        sock.close()
    return {"sent": sent}


def check(args):
    return {"state": "unknown", "detail": "Wake on LAN has no checks; it only wakes machines"}


METHODS = {
    "hello": lambda a: {"module": "wol", "version": VERSION},
    "describe": lambda a: {"title": "Wake on LAN", "text": "Wakes machines with a magic packet", "status": "healthy"},
    "wake": wake,
    "check": check,
}

if __name__ == "__main__":
    for line in sys.stdin:
        req = json.loads(line)
        try:
            fn = METHODS.get(req.get("method"))
            if not fn:
                raise ValueError(f"unknown method {req.get('method')}")
            out = {"id": req["id"], "result": fn(req.get("params", {}))}
        except Exception as e:
            out = {"id": req["id"], "error": str(e)}
        print(json.dumps(out), flush=True)
