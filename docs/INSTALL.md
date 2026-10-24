# Trying MonitorBox 4 (preview)

This runs alongside MonitorBox 3 and does not touch it. It uses its own volume and container name, and web port 8090 by default.

1. Copy `deploy/docker-compose.yml` to the Pi (or paste it into a Portainer stack).
2. Start it. First start downloads the App from the `dev` channel (a few seconds).
3. Open `http://<pi>:8090`, choose an admin password, and you should see the Hello module.

What the first test proves: blank volume to running App with nothing but the compose file; update from the page (Check for updates, Apply); roll back; the App and module move without the compose file ever changing.

Until the first dev release is published, the page says it is waiting for a release. That is expected.

If the container will not start with a permissions message about `/config`, tell me the exact text: this is the one thing I could not test without Docker.

## Updating

The page lists the App and each module with a version dropdown. **Latest** follows whatever the channel currently offers; picking a specific version holds you there (this is also how you go back). The channel setting limits what is offered: stable shows only stable releases, beta shows beta and stable, dev shows everything. "Check for updates automatically" is on by default; "Install updates automatically" is off by default and only affects items set to Latest. A new version that will not start is dropped and the previous one keeps running.

The launcher lives in the container image. If the page says the image is out of date, redeploy the stack once with "Re-pull image".
