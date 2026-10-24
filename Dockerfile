# The image holds the launcher, a Python runtime and a Node runtime. Everything else
# (the App and modules) is downloaded into /config and updates itself.
# Node is here for one reason: Scrypted's official client library is JavaScript, and it is the only supported way
# to read Scrypted's cameras and start live video. Only the node binary is copied (no npm, no build tools); a module
# that needs it ships its own packages. The same Debian release as the Python image, so it runs without extra libraries.
FROM node:22-bookworm-slim AS node
FROM python:3.13-slim-bookworm
# Ties the package to this repository on GitHub (the Package settings page shows it as the repository source).
LABEL org.opencontainers.image.source="https://github.com/SickIcarus-Labs/monitorbox"
COPY --from=node /usr/local/bin/node /usr/local/bin/node
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY launcher/monitorbox_launcher /opt/monitorbox/monitorbox_launcher
ENV PYTHONPATH=/opt/monitorbox
WORKDIR /opt/monitorbox
ENTRYPOINT ["python", "-m", "monitorbox_launcher"]
