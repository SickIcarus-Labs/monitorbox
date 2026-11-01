"""#337: names from devices and other boxes must never run as code in the page.

esc() makes a value safe as HTML text or in a quoted attribute, but not inside a JS string in an onclick="..." handler: the browser turns
&#39; back into ' before it runs the handler, so a Docker label or camera id like  x')(alert(1))('  ran in the owner's signed-in session.
Every value inside a handler now goes through jsq(), which leaves nothing the browser could decode back into a quote."""
import os, re, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from monitorbox_app import ui, peer  # noqa: E402
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

EVIL = "x')(window.hit=1)('\"&#39;</b><img src=x onerror=window.hit=2>\\"


def handler_values(page):
    """The text of every inline on...="..." handler that builds in a value, with ${...} kept whole (they hold quotes of their own)."""
    out, pos = [], 0
    pat = re.compile(r'\bon[a-z]+="')
    while True:
        m = pat.search(page, pos)
        if not m:
            return out
        j, depth = m.end(), 0
        while depth or page[j] != '"':
            if page.startswith("${", j):
                depth += 1; j += 2; continue
            if depth and page[j] == "}":
                depth -= 1
            j += 1
        v = page[m.end():j]
        if "${" in v:
            out.append(v)
        pos = j


class NoRawValuesInHandlers(unittest.TestCase):
    def test_every_quoted_value_in_a_handler_goes_through_jsq(self):
        bad = []
        for v in handler_values(ui.PAGE):
            for m in re.finditer(r"'\$\{", v):
                if not v.startswith("jsq(", m.end()):
                    bad.append(v[:120])
            if "decodeURIComponent('" in v or re.search(r"esc\([^)]*\)\.replace\(/'/g", v):
                bad.append(v[:120])
        self.assertEqual(bad, [], "a value in a quoted JS string inside an onclick must use jsq(), not esc() or encodeURIComponent()")


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class InTheBrowser(unittest.TestCase):
    def test_a_hostile_name_in_a_handler_is_only_data(self):
        js = re.search(r"function jsq\(s\)\{.*?\}\s", ui.PAGE).group(0) + re.search(r"function esc\(s\)\{.*?\}\s", ui.PAGE).group(0)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page()
            pg.set_content("<div id=out></div>")
            pg.add_script_tag(content=js + "window.hit=0;window.got=null;function toggleN(v){window.got=v}")
            pg.evaluate("evil => { document.querySelector('#out').innerHTML = `<button id=b onclick=\"toggleN('${jsq(evil)}')\">${esc(evil)}</button>` }", EVIL)
            pg.click("#b")
            self.assertEqual(pg.evaluate("window.hit"), 0, "the name ran as code")
            self.assertEqual(pg.evaluate("window.got"), EVIL, "the handler got the name back exactly")
            pg.evaluate("evil => { document.querySelector('#out').innerHTML = `<button id=c onclick=\"toggleN('${esc(evil)}')\">x</button>` }", "x')(window.hit=1)('")
            pg.click("#c")
            self.assertEqual(pg.evaluate("window.hit"), 1, "the old esc()-only handler really was open (so this test proves something)")
            b.close()


class SiteTabAnswers(unittest.TestCase):
    """A managed site that has gone bad must not get a page of its own onto the main box's address through a site tab."""
    def test_only_api_types_pass_and_everything_is_marked_inert(self):
        self.assertEqual(peer.safe_type("application/json"), "application/json")
        self.assertEqual(peer.safe_type("text/plain; charset=utf-8"), "text/plain; charset=utf-8")
        for t in ("text/html", "TEXT/HTML; charset=utf-8", "image/svg+xml", "application/javascript", "text/xml", ""):
            self.assertEqual(peer.safe_type(t), "application/octet-stream", t)

        class Resp:
            status, chunked = 200, False
            def __init__(s): s.h = {"Content-Type": "text/html", "Content-Disposition": "inline", "Content-Length": "4"}; s.done = False
            def getheader(s, k): return s.h.get(k)
            def read(s, n=-1):
                if s.done: return b""
                s.done = True; return b"<b>"

        class H:
            def __init__(s): s.sent = []; s.close_connection = False
            def send_response(s, c): s.sent.append(("status", c))
            def send_header(s, k, v): s.sent.append((k, v))
            def end_headers(s): pass
            class wfile:
                @staticmethod
                def write(b): pass
                @staticmethod
                def flush(): pass
        h = H()
        peer.relay(Resp(), h)
        got = dict(h.sent)
        self.assertEqual(got["Content-Type"], "application/octet-stream")
        self.assertNotIn("Content-Disposition", got, "an inline disposition is dropped")
        self.assertEqual(got["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", got["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
