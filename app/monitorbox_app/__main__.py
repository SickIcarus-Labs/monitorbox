import os, sys
from .server import App

sys.exit(App(
    root=os.environ.get("MB_CONFIG", "/config"),
    releases_url=os.environ["MB_RELEASES_URL"],
    channel=os.environ.get("MB_CHANNEL", "stable"),
    port=int(os.environ.get("MB_PORT", "8080")),
).serve())
