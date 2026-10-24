"""Live video across sites when the browser cannot reach the camera box directly (for example over a router port map).

WebRTC media is UDP between the browser and Scrypted. Here the browser talks to a UDP port on the main box, the managed box talks
to Scrypted from a UDP port of its own, and the packets between the two boxes travel inside the existing TLS-PSK site link
(a raw stream after an upgrade, each packet framed with a two-byte length). Nothing in the packets is read or changed: they are
STUN, DTLS and SRTP that belong to the browser and Scrypted, so the video stays encrypted end to end.

What does change is the setup messages: each box replaces the ICE candidates (the addresses each end offers) with its own relay
address, so the browser sends to the main box and Scrypted sends to the managed box. One transport (BUNDLE) is assumed.
"""
import re, select, socket, ssl, struct, threading, time

STUN_COOKIE = b"\x21\x12\xa4\x42"
CAND = re.compile(r"^a=candidate:(\S+) (\d+) (\w+) (\d+) (\S+) (\d+) typ (\w+)", re.I)
MAX_FRAME = 65535
MAX_QUEUE = 1024 * 1024      # bytes waiting for the stream; beyond this new packets are dropped


def is_stun(data):
    return len(data) >= 20 and data[0] < 4 and data[4:8] == STUN_COOKIE


def sdp_lines(sdp):
    return str(sdp or "").replace("\r\n", "\n").split("\n")


def parse_candidates(sdp):
    """[(ip, port, type)] for the UDP candidates in an SDP."""
    out = []
    for line in sdp_lines(sdp):
        m = CAND.match(line.strip())
        if m and m.group(3).lower() == "udp":
            out.append((m.group(5), int(m.group(6)), m.group(7).lower()))
    return out


def parse_candidate_attr(text):
    """The same for one trickled candidate ('candidate:1 1 udp ...')."""
    t = str(text or "").strip()
    return parse_candidates("a=" + t if not t.startswith("a=") else t)


def candidate_line(ip, port):
    return f"a=candidate:mb1 1 udp 2130706431 {ip} {port} typ host"


def strip_candidates(sdp):
    keep = [l for l in sdp_lines(sdp) if not l.strip().lower().startswith(("a=candidate:", "a=end-of-candidates"))]
    return "\r\n".join(keep).rstrip("\r\n") + "\r\n"


def with_candidate(sdp, ip, port):
    """The SDP with exactly one candidate (ours) in every media section."""
    out, in_media = [], False
    for line in sdp_lines(strip_candidates(sdp)):
        if line.startswith("m=") and in_media:
            out += [candidate_line(ip, port), "a=end-of-candidates"]
        if line.startswith("m="):
            in_media = True
        if line != "" or out:
            out.append(line)
    while out and out[-1] == "":
        out.pop()
    if in_media:
        out += [candidate_line(ip, port), "a=end-of-candidates"]
    return "\r\n".join(out) + "\r\n"


def pick_target(cands, prefer_ip=None):
    """Where to send Scrypted's packets: its own address from the candidates it offered (the one at its known host if it offered that)."""
    cands = [c for c in cands if ":" not in c[0]]
    for ip, port, _t in cands:
        if prefer_ip and ip == prefer_ip:
            return (ip, port)
    for ip, port, t in cands:
        if t == "host":
            return (ip, port)
    return (cands[0][0], cands[0][1]) if cands else None


def local_ip_toward(host):
    """The address of this box that the given host reaches it at."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, 9))
        return s.getsockname()[0]
    finally:
        s.close()


class Pipe:
    """A UDP port joined to a raw stream (after the upgrade). Both ends of a relay run one of these."""

    def __init__(self, bind="0.0.0.0"):
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind((bind, 0))
        self.port = self.udp.getsockname()[1]
        self.target = None                 # where UDP goes: known from the candidates, or learned from the first packet that arrives
        self.link = None
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.sent = self.received = 0      # packets that went into / came out of the stream
        self.bytes_in = self.bytes_out = self.dropped = 0      # bytes into / out of the stream; packets that had nowhere to go yet
        self.born = time.time()
        self.on_close = None

    def set_target(self, addr):
        if addr and self.target is None:
            self.target = addr

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        for s in (self.udp, self.link):
            try:
                s and s.close()
            except OSError:
                pass
        cb, self.on_close = self.on_close, None
        if cb:
            cb()

    def stats(self):
        return {"seconds": int(time.time() - self.born), "packetsIn": self.sent, "packetsOut": self.received, "bytesIn": self.bytes_in,
                "bytesOut": self.bytes_out, "dropped": self.dropped, "target": bool(self.target), "linked": self.ready.is_set()}

    def serve(self, sock, speak_first):
        """Run until either side closes. One thread does everything for this view (a TLS connection must not be read and written from two
        threads at once), with both sockets non-blocking: packets from UDP are queued for the stream, frames from the stream go out as UDP.
        If the stream cannot keep up the queue is capped and the newest packets are dropped, as a congested network would drop them, instead
        of delaying everything behind them. speak_first: send the opening empty frame (the side that connected does); the other side waits
        for it, so nothing is written to a stream before its peer has finished the upgrade."""
        self.link = sock
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)      # a packet is sent when it is ready, not held back to be joined with the next
        except OSError:
            pass
        out, held = bytearray(), bytearray()
        try:
            sock.setblocking(False)
            self.udp.setblocking(False)
            if speak_first:
                out += b"\x00\x00"
                self.ready.set()
            while not self.closed.is_set():
                pending = sock.pending() if hasattr(sock, "pending") else 0       # bytes TLS already decrypted: the socket will not announce them
                readable, _w, _x = select.select([self.udp, sock], [sock] if out else [], [], 0 if pending else 0.5)
                if sock in readable or pending:
                    while True:
                        try:
                            chunk = sock.recv(65536)
                        except (BlockingIOError, InterruptedError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
                            break
                        if not chunk:
                            return
                        held += chunk
                    while len(held) >= 2:
                        n = struct.unpack(">H", held[:2])[0]
                        if len(held) < 2 + n:
                            break
                        frame = bytes(held[2:2 + n]); del held[:2 + n]
                        if not frame:
                            self.ready.set()      # the opening frame: the other side is ready to hear from us
                        elif self.target:
                            try:
                                self.udp.sendto(frame, self.target)
                                self.received += 1; self.bytes_out += len(frame)
                            except OSError:
                                pass
                        else:
                            self.dropped += 1
                if self.udp in readable:
                    for _ in range(512):
                        try:
                            data, addr = self.udp.recvfrom(MAX_FRAME)
                        except (BlockingIOError, InterruptedError):
                            break
                        if not self.ready.is_set() or not data or len(out) > MAX_QUEUE:
                            self.dropped += 1
                            continue
                        if self.target is None or (is_stun(data) and addr != self.target):
                            self.target = addr          # a STUN check is how a peer says where it really is (it may sit behind a translation)
                        out += struct.pack(">H", len(data)) + data
                        self.sent += 1; self.bytes_in += len(data)
                while out:
                    try:
                        n = sock.send(out)
                    except (BlockingIOError, InterruptedError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
                        break
                    del out[:n]
        except (OSError, ValueError, EOFError):
            pass
        finally:
            self.close()


class Registry:
    """The main box's relayed live views: view id -> its media pipe and the address the browser reaches this box at."""

    def __init__(self):
        self.cv = threading.Condition()
        self.by_sid = {}
        self.opening = 0               # live/open requests being passed on right now (their view id is not known yet)

    def begin(self):
        with self.cv:
            self.opening += 1

    def end(self):
        with self.cv:
            self.opening -= 1
            self.cv.notify_all()

    def add(self, sid, pipe, ip, client):
        with self.cv:
            self.by_sid[sid] = {"pipe": pipe, "ip": ip, "client": client}
            self.cv.notify_all()
        pipe.on_close = lambda: self.pop(sid)

    def pop(self, sid):
        with self.cv:
            return self.by_sid.pop(sid, None)

    def get(self, sid, wait=0.0):
        """A view's entry. An event can overtake the answer that names its view, so wait briefly while an open is still under way."""
        with self.cv:
            if sid not in self.by_sid and wait and self.opening:
                self.cv.wait_for(lambda: sid in self.by_sid or not self.opening, wait)
            return self.by_sid.get(sid)

    def stats(self):
        with self.cv:
            return [dict(e["pipe"].stats(), view=sid[:4]) for sid, e in self.by_sid.items()]

    def close_client(self, client):
        with self.cv:
            mine = [e for e in self.by_sid.values() if e["client"] == client]
        for e in mine:
            e["pipe"].close()
