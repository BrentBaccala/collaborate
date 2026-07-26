# CLAUDE.md — Collaborate

## Overview

This repo contains packages that extend BigBlueButton with remote desktop
capabilities: VNC desktop service, JWT authentication, GNOME desktop
configuration, and supporting Python libraries.

The remote desktop feature itself is now a BBB v3.0 plugin, included as
a git submodule at `bbb-plugin-remote-desktop/`.

## Testing on the BBB VM

### VM details

- **Host**: jammy-300.samsung
- **SSH**: `ubuntu@jammy-300.samsung` (has sudo)
- **BBB version**: 3.0 on Ubuntu 22.04
- **BBB shared secret**: `bbbci`
- **VNC URL**: `wss://jammy-300.samsung/vnc`

### Joining a meeting via login URL (preferred)

bbb-auth-jwt is installed on the VM. Use `bbb-mklogin` to generate
login URLs, then navigate to them in Playwright. Moderator links
create the meeting automatically if it's not already running.

For most tests, use "Moderator" or "Viewer" as the username with the
default meeting (hostname):

```bash
# Generate a moderator login link
ssh ubuntu@jammy-300.samsung "bbb-mklogin -m -e never 'Moderator'"

# Generate a viewer login link
ssh ubuntu@jammy-300.samsung "bbb-mklogin -e never 'Viewer'"
```

In Playwright: navigate to the returned URL with `--ignore-https-errors`.

### Joining a meeting via the BBB API

When you need more control (custom meeting names, multiple users, etc.),
use the BBB API directly. Checksums use **SHA256** (not SHA1).

```python
import hashlib
secret = 'bbbci'
# Create meeting
call = 'create' + 'name=Test&meetingID=test&attendeePW=ap&moderatorPW=mp' + secret
checksum = hashlib.sha256(call.encode()).hexdigest()
# Then GET: https://jammy-300.samsung/bigbluebutton/api/create?name=Test&meetingID=test&attendeePW=ap&moderatorPW=mp&checksum={checksum}
```

### Generating new login tokens

`bbb-mklogin` generates JWT login URLs. It runs on the VM where
bbb-auth-jwt is installed.

```bash
# Moderator login, expires Jan 1 2030
ssh ubuntu@jammy-300.samsung "bbb-mklogin -m -e 'January 1 2030' 'Brent Baccala'"

# Viewer login (no -m flag)
ssh ubuntu@jammy-300.samsung "bbb-mklogin -e 'January 1 2030' 'Student Name'"

# Moderator for a specific meeting (default is the hostname)
ssh ubuntu@jammy-300.samsung "bbb-mklogin -m -M 'Math Class' -e 'June 1 2027' 'Teacher'"

# No expiration
ssh ubuntu@jammy-300.samsung "bbb-mklogin -m -e never 'Admin'"
```

Options:
- `-m` / `--moderator` — moderator role (can start meetings); omit for viewer
- `-e` / `--expiration-time` — expiration date/time, or `never`
- `-M` / `--meeting` — meeting name (default: hostname)
- `-r` / `--rsa` — sign with RSA key instead of BBB shared secret
- `-d` / `--debug` — print the JWT payload being encoded
- The positional argument is the user's display name

### DNS workaround

`bbb-mklogin` generates URLs using the VM's hostname (`jammy-300`), but
the `.samsung` DNS suffix isn't automatically appended on the local
machine (see task 152). The generated URLs won't work as-is. You need to
replace `jammy-300` with `jammy-300.samsung` in the URL before navigating
to it in Playwright or a browser.

### Playwright notes

- Use `--ignore-https-errors` (self-signed cert)
- **Always call `browser_close` as your very last Playwright action**
  before finishing, or Chromium stays alive and the task runner hangs.

## Apt repository

The freesoft.org apt repo at `~/website/jammy-300` contains 6+ packages
(no upstream BBB mirror). To update a package:

```bash
cd ~/collaborate
make status                        # what's built here vs what's published
reprepro -b ~/website/jammy-300 includedeb bigbluebutton-jammy /path/to/new.deb
make status                        # confirm it landed
```

**No `reprepro remove` first.** reprepro compares versions on `includedeb` and
refuses to go backwards (`Skipping inclusion of 'x' '1.0', as it has already
'2.0'`), which is the safety net that catches a stale `.deb`. Removing first
throws it away. The cost is that re-publishing the *same* version with new
content is a no-op — correct, since the rule is to bump the version on every
rebuild. To genuinely replace a version in place, run `reprepro remove`
yourself as a deliberate, separate act.

Then `cd ~/collaborate && make rsync` to push to www.freesoft.org.
(`dists/.htaccess` sets `Cache-Control: no-cache` on the repo metadata and
each new version lands at a fresh `pool/` path, so no CloudFront
invalidation is needed for apt.)

**Do NOT use `make reprepro`** — it republishes every `.deb` in `build/`, not
the one you just built, and `build/` is never cleaned between sessions. It can
no longer *downgrade* anything (the `reprepro remove` is gone, so reprepro's
version check applies), but it will still ship something you never meant to:
on 2026-07-25 `build/` held an unpublished `bbb-wss-proxy 0.3.0-16` against the
repo's `-15`, so publishing two unrelated packages would have shipped it too.
Publish one package at a time, by hand, as above. Same goes for plain `make`
(`all:` depends on `reprepro`). `make rsync` alone is safe — it only mirrors
the repo directory.

## Building packages

Most packages use FPM via `build.sh` or `deb-helper.sh`. Check each
package's directory for its build script.

**Important**: When rebuilding a package with changes, always bump the
version number so `apt upgrade` will install it. For `bbb-plugin-remote-desktop`,
update `debian/changelog`. For FPM packages, the version is derived from the
git timestamp automatically.

**Plugin JS deployment**: The plugin's `manifest.json` (including the
`javascriptEntrypointUrl` with its hash) is fetched by bbb-web at meeting
creation time and stored in the database. The HTML5 client reads it via
GraphQL. After deploying a new plugin JS file, existing meetings will
still reference the old URL. To pick up the new plugin:
- End the meeting and create a new one, **or**
- Run `bbb-conf --restart` to restart bbb-web (which re-reads manifests)

A browser page reload alone is **not** sufficient.
