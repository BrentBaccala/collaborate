# bbb-plugin-rtt-monitor

A **moderator-only** BigBlueButton v3.0 plugin that shows a live graph of
every participant's network round-trip time (RTT) to the server, over a
rolling window (default 10 minutes). It is the in-meeting, glance-able
counterpart to the after-the-fact `rtt-report` / `rtt-plot` tools in
`~/collaborate/scripts/`.

## Why

A moderator currently has no easy way to see, live, that a specific
participant's connection is degrading. BBB's built-in "Connection status"
modal lists users who went *unstable* but shows no RTT trend. This panel
plots per-user RTT over time so the moderator can immediately see
"Bruce's line is spiking, everyone else is flat — it's his connection."

The RTT probe (`/bigbluebutton/rtt-check`, every ~10 s) runs regardless of
audio/video/screenshare, so the monitor works even in a remote-desktop-only
session.

## How it works

- **Launcher**: an entry in the options ("...") menu, top-right. It is
  registered *only* when the current user's role is `MODERATOR`.
- **Data**: a custom GraphQL subscription on the `user_connectionStatusHistory`
  view, joined with the `user` relationship for name/role:

  ```graphql
  subscription ModeratorRttHistory {
    user_connectionStatusHistory(order_by: { statusUpdatedAt: asc }) {
      userId
      networkRttInMs
      status
      statusUpdatedAt
      user { name role }
    }
  }
  ```

  The view's Hasura `select_permission` (role `bbb_client`) returns **all**
  meeting users' rows to a moderator (`meetingId == X-Hasura-ModeratorInMeeting`)
  but only own-rows to a viewer. So moderator-only visibility is enforced
  **server-side**, not just in the UI — a non-moderator who runs the same
  subscription by hand sees only their own RTT.

- **Chart**: a movable floating window with a per-user scatter (dots, not
  connected lines — isolated spikes read better as points). Log y-axis
  (`10 ms … 15 s`), one color per user, legend with name + median + peak,
  and the BBB `public.stats.rtt` thresholds drawn as reference lines:
  warning 500 ms, danger 1 s, critical 2 s. These conventions match
  `rtt-plot` so the live view and the report look consistent.

- **Charting approach**: a **hand-rolled SVG scatter** (no chart library).
  The plot is a log-scaled scatter with a handful of reference lines — too
  simple to justify a dependency. This keeps the bundle small (React + the
  SDK only) and avoids pulling in D3/recharts/uPlot.

- **Rolling buffer**: the server retains only the last `public.stats.lastEntriesCap`
  samples per user-session (default **20** ≈ 3.3 min at 10 s cadence). The
  panel keeps its **own** client-side rolling buffer, merging each
  subscription push and deduping by `(userId, statusUpdatedAt)`, so the
  window grows toward the full 10 min while the panel stays open — and
  degrades gracefully (shows however much history exists) on deployments
  where the cap was left at its default.

## Server configuration

### 10-minute window: bump `lastEntriesCap`

For the default 10-minute window to be populated *immediately* on open
(rather than filling in over the first ~10 min the panel is open), raise the
history cap. In `/usr/share/meteor/bundle/programs/server/assets/app/config/settings.yml`
(or the `/etc/bigbluebutton/bbb-html5.yml` override), set:

```yaml
public:
  stats:
    lastEntriesCap: 64   # ≈ 10.5 min at 10 s cadence (default 20 ≈ 3.3 min)
```

The SQL trigger in `bbb_schema.sql` reads this from client settings and caps
the UNLOGGED history table accordingly. Apply with a restart that re-reads
client settings and the trigger:

```bash
sudo bbb-conf --restart        # or: systemctl restart bbb-apps-akka bbb-graphql-server
```

The plugin works with **whatever cap is set** — the bump only changes how
much backfill is visible the instant the panel opens. The client-side buffer
extends the window past the cap regardless.

### Registering the plugin

The Debian package's `postinst` adds the plugin's manifest URL to
`pluginManifests=` in `/etc/bigbluebutton/bbb-web.properties` automatically.
Plugin manifests are read by **bbb-web** at meeting-creation time, so an
existing meeting won't pick up a newly installed plugin — end the meeting and
start a new one, or run `bbb-conf --restart`.

## Settings

Optional plugin settings (set in `/etc/bigbluebutton/bbb-html5.yml` under the
plugin's entry; read by bbb-apps-akka at startup, so an akka restart is needed
to change them):

| Setting           | Type   | Default | Meaning                                      |
|-------------------|--------|---------|----------------------------------------------|
| `windowMinutes`   | number | `10`    | Rolling plot window, in minutes.             |
| `sampleIntervalMs`| number | `10000` | Probe cadence hint (informational).          |

## Build

```bash
git commit ...        # commit FIRST — webpack names the JS bundle from
                      # `git rev-parse --short HEAD` (cache-busting)
npm install
npm run build         # → dist/RttMonitor-<hash>.js, dist/manifest.json, dist/locales/
```

## Package

```bash
dpkg-buildpackage -us -uc -b      # builds bbb-plugin-rtt-monitor_<ver>_all.deb
```

Bump `debian/changelog` on every rebuild so `apt upgrade` installs it.

## Install / publish

Install on a test box (jammy-300):

```bash
scp ../bbb-plugin-rtt-monitor_*_all.deb ubuntu@jammy-300.samsung:
ssh ubuntu@jammy-300.samsung 'sudo apt install -y ./bbb-plugin-rtt-monitor_*_all.deb && sudo bbb-conf --restart'
```

Publish to the collaborate apt repo (do **not** publish to production from a
task without confirmation):

```bash
cd ~/website/jammy-300
reprepro includedeb bigbluebutton-jammy /path/to/bbb-plugin-rtt-monitor_*_all.deb
cd ~/collaborate && make rsync
```
