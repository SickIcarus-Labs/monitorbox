# Troubleshooting

## Getting the logs

```
sudo docker logs monitorbox
```

More detailed logs are in the `logs` folder inside your config folder (the left side of the `:/config` line in your compose file). When you ask for help, include the last lines of both.

## Restarting

Use the **Restart** button in Settings, or:

```
sudo docker restart monitorbox
```

## The container will not start

- **A permissions message about `/config`:** the config folder must exist and be writable by the container. Create it first (`sudo mkdir -p /Containers/monitorbox`, or whatever path you chose) and start again.
- **Port already in use:** another program uses port 8080. In the compose file, uncomment the `environment:` and `MB_PORT` lines and pick a free port, then start the container again.
- **It cannot see devices on your network:** MonitorBox needs host networking (`network_mode: host`), which only works on Docker running directly on Linux, not Docker Desktop on Windows or macOS.

## "The container image needs updating"

MonitorBox updates itself, but its container image is separate and changes rarely. When the bell or the Updates page says the image needs updating, pull the new image and restart the container. In Portainer, update the stack and tick "Re-pull image". With Compose:

```
sudo docker compose pull && sudo docker compose up -d
```

Your settings and data are kept.

## Forgot the password

There is no password recovery, by design. You start over, and then restore a backup or set things up again.

If you can reach the box itself, create an empty file named `factory-reset` in your config folder. The next time MonitorBox starts, it clears the settings, history, password and installed modules, and starts again at the setup screen. **Your backups are kept**, so you can restore one after setting a new password. (A restore brings back your settings and history, and keeps the password you set on the fresh box.)

```
sudo touch /Containers/monitorbox/factory-reset
sudo docker restart monitorbox
```

Use your own config folder in place of `/Containers/monitorbox`.

## Starting over on purpose

Settings, This box, **Factory reset**. It does the same as the file above. Make a backup first if there is anything you want to keep.

## The app will not start, or something looks wrong after an update

If the app cannot start, the launcher serves a recovery page on the same address. From there you can see stored backups, upload one and restore it. It asks for your admin password if you have one.

You can also go back to an earlier version: Settings, Updates, pick the earlier version in the dropdown for that item.

## Something shows "Unknown" (blue)

That means MonitorBox could not check it right now, for example because the provider (UniFi, Portainer, a server) did not answer. It does not mean the thing is down. Check that the provider is reachable from the MonitorBox machine, and that the account or token MonitorBox uses still works.
