import os
from .supervisor import Launcher

Launcher(
    root=os.environ.get("MB_CONFIG", "/config"),
    releases_url=os.environ.get("MB_RELEASES_URL",
        "https://raw.githubusercontent.com/SickIcarus-Labs/monitorbox-modules/main"),
    channel=os.environ.get("MB_CHANNEL", "stable"),
    port=int(os.environ.get("MB_PORT", "8080")),
    health_timeout=int(os.environ.get("MB_HEALTH_TIMEOUT", "30")),
).run()
