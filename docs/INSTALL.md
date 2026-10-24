# Install MonitorBox

You need a machine that runs Docker (a Raspberry Pi 5 is what MonitorBox is built and tested on). You install it once. After that MonitorBox updates itself and tells you when its container image needs pulling.

**Portainer is the preferred way.** MonitorBox needs Portainer anyway to see your containers. But Portainer is not required to install MonitorBox: if you prefer plain Docker Compose, use Option B.

## Before you start

None of this is required, but a few minutes of preparation makes the first run much smoother. MonitorBox walks you through connecting each thing and finds what it can on its own.

- **SNMP:** turn it on, in advance, on the systems you want to watch (servers, switches, NAS). MonitorBox then finds their disks, interfaces and temperatures by itself.
- **Portainer:** install it even if you do not use it to manage your containers. It is how MonitorBox sees your container stack. MonitorBox only reads from it (give it its own non-admin user and an access token: Portainer, My account, Access tokens).
- **UniFi Network:** create a **local** user that can only **view**. Name your devices cleanly in UniFi, because those names are what MonitorBox shows.
- **UniFi Protect:** create a local user that can only view Protect. It cannot record, move or change anything.
- **Scrypted:** create a user that is **not an admin**, and give it only the **Camera** and **VideoCamera** interfaces of the cameras. For live view it also needs the **RTCSignalingChannel** interface on those cameras (view only).
- **Alerts by email:** an SMTP server. For Gmail, use your full address and an **app password** (Google account, Security, 2-Step Verification, App passwords).
- **Alerts through Home Assistant:** make a user just for MonitorBox (Settings, People, Users, Add user), leave Administrator off, and turn on "Can only log in from the local network". The phones and tablets that have the Home Assistant app are offered as places to send alerts.

## Option A: Portainer

### 1. Install Portainer (skip if you already have it)

```
docker volume create portainer_data
docker run -d -p 9443:9443 --name portainer --restart=always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data portainer/portainer-ce:lts
```

Browse to `https://<your-machine>:9443` (your browser will warn about the certificate; that is normal) and create the admin account. Do this within a few minutes of starting it, or Portainer locks itself and needs a restart (`docker restart portainer`).

### 2. Create the MonitorBox stack

In Portainer: **Stacks, Add stack**, name it `monitorbox`, paste the compose file below into the web editor, then **Deploy the stack**.

## Option B: Docker Compose

```
sudo mkdir -p /Containers/monitorbox
cd /Containers/monitorbox
sudo nano docker-compose.yml
```

Paste the compose file below, save (Ctrl+O, Enter, Ctrl+X), then:

```
sudo docker compose up -d
```

(Older installs use `docker-compose` with a hyphen instead.)

## The compose file

```yaml
services:
  monitorbox:
    image: ghcr.io/sickicarus-labs/monitorbox:latest
    container_name: monitorbox
    restart: unless-stopped
    network_mode: host
    # Only if port 8080 is already used on this machine, uncomment both lines:
    # environment:
    #   MB_PORT: "8090"
    volumes:
      - /Containers/monitorbox:/config
    read_only: true
    tmpfs:
      - /tmp
    cap_drop: [ALL]
    cap_add: [NET_RAW]
    security_opt:
      - no-new-privileges:true
```

The one line to check is `/Containers/monitorbox:/config`. Change the part before the colon to a folder on your machine. **That folder holds everything MonitorBox keeps (settings, history, backups), so back it up.**

## First start

Open `http://<your-machine>:8080` (or the port you chose). The first start downloads the app, which takes a few seconds. MonitorBox asks you to choose a password and which updates to follow (Stable is the default), then walks you through adding what to watch.

## Updating

The app and its modules update from the Updates page (Settings, Updates): **Latest** follows what your channel offers, and picking a specific version holds you there (this is also how you go back). Stable shows only stable releases, beta shows beta and stable, dev shows everything.

The container image itself changes rarely. When it does, MonitorBox says so in the bell and on the Updates page. Pull the new image and restart the container: in Portainer, update the stack with "Re-pull image"; with Compose, `sudo docker compose pull && sudo docker compose up -d`. Your settings and data are kept.
