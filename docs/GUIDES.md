# Setup guides

Short guides for the parts that need something done outside MonitorBox first. MonitorBox walks you through the rest. Where it asks for a setting, the guide names the field.

## Alerts

MonitorBox sends a message when something has been **down** or **degraded** for about a minute, and another when it recovers. It stays quiet about anything you marked expected down, about things that are down only because something they depend on is down (you get one message for the cause), and about things it cannot check. Set it up in **Settings, Alerts**. You can use email, Home Assistant, or both.

### Email

1. Settings, Alerts, choose email.
2. Enter your mail server, port, user and password, and where to send.
3. **Gmail:** press the **Gmail** button, use your full Gmail address as the user, and an **app password**, not your normal password. To make one: Google account, Security, 2-Step Verification, App passwords.
4. Press the test button. You should get a message within a moment.

### Home Assistant (phone notifications)

1. In Home Assistant, make a user just for MonitorBox: **Settings, People, Users, Add user**. Leave **Administrator** off and turn on **Can only log in from the local network**.
2. In MonitorBox, Settings, Alerts, choose Home Assistant and enter your Home Assistant's address.
3. Home Assistant opens its own sign-in page. Sign in as the MonitorBox user and approve. MonitorBox never sees the password. You can remove the sign-in from that user's profile at any time.
4. Tick the phones and tablets (the ones with the Home Assistant app) that should get alerts, and press the test button.

MonitorBox only ever sends notifications to your phones and tablets.

## SNMP

SNMP lets MonitorBox read a system's health, disks and network ports. It only reads.

1. Turn SNMP on, ahead of time, on each system you want to watch. How depends on the device: NAS boxes and network gear have a setting in their admin page; on Linux you run an SNMP service (snmpd).
2. **Use SNMP v3** where you can: it has a user and passwords instead of a shared community word. Make the user read-only.
3. In MonitorBox, when you add the server, choose SNMP and fill the fields: version, user, login method (SHA is the usual), password, privacy (AES is the usual), privacy password, and the port (161 unless you changed it). For v2c, enter the community word instead.

## Battery backup (NUT)

MonitorBox reads a UPS from a NUT server. It never shuts anything down.

1. On the machine the UPS is plugged into, run the NUT server (`upsd`) and make sure it listens on your network address, not only on the machine itself.
2. In MonitorBox, choose Battery backup, and enter that machine's address. The port is 3493 unless you changed it. Enter a user and password only if your NUT server asks for one.

## Several sites

Each site runs its own MonitorBox, so each keeps watching and sending alerts even if the others go offline. One MonitorBox, the **main** one, is paired with the others to show them and manage their settings. The main one can change the others. The others cannot change the main one.

**On the site to be managed:**

1. Settings, Sites. Switch on the **site port** (8443 unless you change it).
2. Press **Let a main MonitorBox manage this one.** It shows a one-time code, good for ten minutes.

**On the main MonitorBox:**

1. Settings, Sites, add a site. Enter the other site's address and the code.
2. The address is either its internet address with the site port, or its address on your own network if the two sites are joined by a VPN.

If you connect over the internet instead of a VPN, you forward **one port** (the site port) on that site's router. The connection is encrypted and needs the key made during pairing; a visitor without it gets nothing. Do not forward the normal web port for this.

To undo it, remove the site on the main side, or cut the manager off from the managed site's own Sites page.
