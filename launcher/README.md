# launcher

Tiny first-run program in the container image (standard library only). On every start it reads the channel pointer, downloads the App (sha256 verified), switches `current` atomically, starts the App, rolls back if it is not healthy, and serves a recovery page while the App is down. A version it rolled back from is not retried until a newer one is published.

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
