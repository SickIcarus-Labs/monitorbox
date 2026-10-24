"""A tiny stand-in mail server for tests: accepts one login, records every message. No TLS (tests use security 'none')."""
import base64, socketserver, threading


class FakeSmtp:
    def __init__(self, user, password):
        self.user, self.password, self.messages, self.logins = user, password, [], []
        outer = self

        class H(socketserver.StreamRequestHandler):
            def say(self, line):
                self.wfile.write((line + "\r\n").encode()); self.wfile.flush()

            def handle(self):
                self.say("220 fake ESMTP")
                authed, frm, rcpt = False, "", []
                while True:
                    raw = self.rfile.readline()
                    if not raw:
                        return
                    line = raw.decode(errors="replace").rstrip("\r\n")
                    cmd = line.split(" ", 1)[0].upper()
                    if cmd == "EHLO":
                        self.say("250-fake"); self.say("250 AUTH PLAIN")
                    elif cmd == "AUTH":
                        parts = line.split()
                        blob = base64.b64decode(parts[2]).split(b"\0") if len(parts) > 2 else []
                        ok = len(blob) == 3 and blob[1].decode() == outer.user and blob[2].decode() == outer.password
                        outer.logins.append(ok)
                        authed = ok
                        self.say("235 ok" if ok else "535 5.7.8 bad credentials")
                    elif cmd == "MAIL":
                        if not authed:
                            self.say("530 authentication required"); continue
                        frm = line.split(":", 1)[1].strip(); rcpt = []; self.say("250 ok")
                    elif cmd == "RCPT":
                        rcpt.append(line.split(":", 1)[1].strip().strip("<>")); self.say("250 ok")
                    elif cmd == "DATA":
                        self.say("354 go")
                        data = []
                        while True:
                            l = self.rfile.readline().decode(errors="replace")
                            if l in (".\r\n", ".\n", ""):
                                break
                            data.append(l.rstrip("\r\n"))
                        outer.messages.append({"from": frm, "to": rcpt, "text": "\n".join(data)})
                        self.say("250 queued")
                    elif cmd == "QUIT":
                        self.say("221 bye"); return
                    else:
                        self.say("250 ok")

        class S(socketserver.ThreadingTCPServer):
            allow_reuse_address = True; daemon_threads = True
        self.srv = S(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()
