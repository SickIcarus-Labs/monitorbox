"""Alert email over plain SMTP (standard library only). Used beside the Home Assistant sender, not instead of the rule that alerts are
read-only notices: this only ever sends mail to the addresses the owner saved. The password is never logged or put in an error message."""
import smtplib, socket, ssl, time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

SECURITY = ("starttls", "ssl", "none")
GMAIL = {"host": "smtp.gmail.com", "port": 587, "security": "starttls"}


def addresses(raw):
    """'a@x.com, b@y.com' (or a list) -> a clean list. An address is just checked for one @ and no spaces: the server is the real judge."""
    items = raw if isinstance(raw, list) else str(raw or "").replace(";", ",").split(",")
    out = []
    for a in items:
        a = str(a).strip()
        if a and a not in out:
            out.append(a)
    return out


def valid_address(a):
    return a.count("@") == 1 and " " not in a and not a.startswith("@") and not a.endswith("@") and len(a) <= 254


def ready(e):
    return bool(e.get("host") and e.get("from") and e.get("to"))


def _why(e, cfg):
    host = cfg["host"]
    gmail = host.lower().endswith("gmail.com")
    if isinstance(e, smtplib.SMTPAuthenticationError):
        if gmail:
            return ("Gmail refused the login. Use an app password (Google account → Security → 2-Step Verification → App passwords), "
                    "not your normal password, and your full Gmail address as the user.")
        return "The mail server refused the user name or password."
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "The mail server refused the to-address: " + "; ".join(f"{a} ({m[1].decode(errors='replace') if isinstance(m[1], bytes) else m[1]})" for a, m in e.recipients.items())
    if isinstance(e, smtplib.SMTPSenderRefused):
        return "The mail server refused the from-address (" + cfg["from"] + ")."
    if isinstance(e, ssl.SSLCertVerificationError):
        return f"{host} has a certificate this box does not trust."
    if isinstance(e, (ssl.SSLError,)):
        return f"Could not set up a secure connection to {host}:{cfg['port']}. Check the security setting (587 normally uses STARTTLS, 465 uses SSL)."
    if isinstance(e, smtplib.SMTPNotSupportedError):
        return f"{host} does not support that: {e}"
    if isinstance(e, (socket.timeout, TimeoutError)):
        return f"{host}:{cfg['port']} did not answer in time."
    if isinstance(e, socket.gaierror):
        return f"Could not find {host}. Check the server name."
    if isinstance(e, ConnectionRefusedError):
        return f"Nothing is listening on {host}:{cfg['port']}."
    if isinstance(e, (smtplib.SMTPException, OSError)):
        return f"{host}: {type(e).__name__}"
    return f"{type(e).__name__}"


def send(cfg, subject, body, timeout=15.0):
    """Returns None when the server took the message, else one plain sentence. cfg: host, port, security, user, password, from, to (list)."""
    msg = EmailMessage()
    msg["Subject"] = str(subject)[:200].replace("\r", " ").replace("\n", " ")
    msg["From"], msg["To"] = cfg["from"], ", ".join(cfg["to"])
    msg["Date"], msg["Message-ID"] = formatdate(time.time(), localtime=False), make_msgid(domain="monitorbox.local")
    msg["X-Mailer"] = "MonitorBox"
    msg.set_content(body)
    srv = None
    try:
        if cfg["security"] == "ssl":
            srv = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=timeout, context=ssl.create_default_context())
        else:
            srv = smtplib.SMTP(cfg["host"], cfg["port"], timeout=timeout)
        srv.ehlo()
        if cfg["security"] == "starttls":
            srv.starttls(context=ssl.create_default_context())
            srv.ehlo()
        if cfg.get("user"):
            srv.login(cfg["user"], cfg.get("password", ""))
        srv.send_message(msg)
        return None
    except Exception as e:
        return _why(e, cfg)
    finally:
        try:
            if srv:
                srv.quit()
        except Exception:
            pass
