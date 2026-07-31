# bbb-conf-audio — desktop audio into a BigBlueButton conference

Plays a Linux desktop's audio into a BigBlueButton conference with no browser
participant, by joining the FreeSWITCH conference as a SIP "injector"
(baresip). It shows up in the user list as **Remote Desktop Injector**.

Any user on the box can use it. The package installs system-wide and enables
nothing; each user turns it on for themselves with `conf-audio setup`.

Originally developed on itpietraining.com by the Claude running there, and
mailed over as a set of hand-installed files. This package is that work
restructured around one constraint that the hand-installed version could not
meet — see *Why it is split in two* below.

## Why it is split in two

The original design ran a single per-user daemon that spoke to FreeSWITCH's
Event Socket directly. That cannot be packaged for general use, because the
per-user side would need the **ESL password**, and ESL is not a read-only
feed: it is full control of FreeSWITCH — `originate`, `uuid_kill`, `conference
kick`, eavesdrop on any conference. Handing that to every desktop user on the
box to enable a convenience feature is a much larger grant than "may inject
audio". (The original also invoked `fs_cli -p <password>`, which puts the
credential in a command line where any user can read it out of `/proc`.)

So the ESL work moved to a system service, and the per-user side kept only what
it actually needs:

| | holds | runs as | does |
|---|---|---|---|
| `bbb-conf-audio-watcher` | ESL password | root, system unit | watches conference events, publishes state |
| `conf-audio` | injector SIP password | the desktop user | starts/stops baresip to match that state |

The SIP password *is* world-readable, deliberately — it is the credential that
makes "any user may inject audio" true, which is the point of the feature. It
lives in `/etc/bigbluebutton/conf-audio.conf`, generated once at install and
never regenerated on upgrade.

> Worth verifying on your box: the original notes say a SIP call from localhost
> is in FreeSWITCH's trusted `domains` ACL and **skips digest auth entirely**,
> which is why the `aaa_vlcinject.xml` dialplan hack exists at all. If that is
> right, the SIP password is not really the gate for local calls — the
> dialplan's `sip_from_user=vlcinject` test is, and any local process can
> present that. It does not change this design, but it does mean the SIP
> password is not load-bearing the way it looks.

## The event path (no polling anywhere)

```
FreeSWITCH --ESL event--> watcher --writes--> /run/bbb-conf-audio/state.stamp
                                                       |
                                              inotify (systemd .path)
                                                       |
                              per-user conf-audio-autojoin.service (oneshot)
                                                       |
                                              baresip joins/leaves
```

The Event Socket is publish/subscribe, so the watcher blocks until FreeSWITCH
pushes a `conference::maintenance` event; an idle box does no work. systemd has
no way for a system unit to signal user units, so the state file *is* the
event bus: each user's `.path` unit watches it with inotify and runs a oneshot.
No per-user daemon, no timer, no credentials on the user side.

**Two files, on purpose.** `state.json` is replaced atomically (temp + rename)
so a reader never sees it half-written. But `PathChanged=` triggers on
`IN_CLOSE_WRITE` — *"activated if the file which was open for writing gets
closed"* (systemd.path(5)) — and a rename is `IN_MOVED_TO`. Rather than bet on
systemd's parent-directory watch catching the rename, the `.path` unit watches a
separate `state.stamp` that is written in place. Readers get atomicity; the path
unit gets the documented trigger. If the rename is ever confirmed to trigger
reliably, the stamp can go away.

`state.json` is world-readable and looks like:

```json
{"conference": "78123", "real": 2, "injector": false, "updated_ms": 1750000000000}
```

`conference` is the voice bridge to inject into (or `null`), `real` counts
actual participants (excluding BBB's `GLOBAL_AUDIO` pseudo-member and the
injector itself), and `injector` says whether one is already in there.

## Install

```
sudo apt-get install bbb-conf-audio
```

The postinst generates the SIP credential, writes the FreeSWITCH directory user
and dialplan extension, reloads FreeSWITCH, and starts the watcher. It enables
nothing for any user.

Then, per user:

```
conf-audio setup                      # as the user: audio devices, baresip, units
sudo loginctl enable-linger <user>    # once, as admin: run without a login
```

`conf-audio setup` writes `~/.config/pulse/default.pa` (only if absent — it
will not edit a config you wrote), renders `~/.baresip/{config,accounts}` from
the shared password, and enables both user units.

The `default.pa` it writes is a two-line stub:

```
.include /etc/pulse/default.pa
.include /usr/share/bbb-conf-audio/conf-audio-modules.pa
```

A user's `default.pa` **replaces** the system one rather than merging with it
(`default.pa(5)`), so the first include is what keeps the session's real sound
devices. The second keeps the device definitions in a package-owned file
instead of inlining them, so changing the device set in a later release reaches
users who have already run setup — inline copies would freeze into each home
directory at the version its owner first ran. Nothing in the modules file is
user-specific, which is what makes one shared copy correct for everybody.

If the package is later removed, the dangling include is not fatal (tested):
PulseAudio still starts, just without the virtual devices.

**No PulseAudio restart is needed.** `default.pa` only takes effect when
PulseAudio *starts*, so on a long-lived desktop the config would be in place
with none of the devices actually loaded — and the failure is quiet: baresip
dies with `start_source failed (pulse.virtmic): No such device` while
`conf-audio status` still says `RUNNING`, because baresip stays alive and idle
after a failed call. So setup asks the *daemon* whether `virtmic` exists and,
if not, replays the module lines from
`/usr/share/bbb-conf-audio/conf-audio-modules.pa` into it with `pactl`. Those
lines are read from the same file the stub includes, rather than duplicated in
the script, so the live and persistent paths cannot drift.

Setup used to tell you to run `pulseaudio -k` by hand. **Don't** — on these
boxes PulseAudio is a systemd *user* service (`pulseaudio.service` +
`pulseaudio.socket`, both enabled, every daemon parented by systemd), and
`pulseaudio -k` does not fit that lifecycle. Observed on Ubuntu 22.04: it exits
with `Failed to kill daemon: No such process`, the daemon does not come back,
`pactl` gives `Connection refused`, and retrying trips the socket unit's
start-limit so it stays down until you run

```
systemctl --user restart pulseaudio.socket pulseaudio.service
```

`systemctl --user restart pulseaudio.service` is the correct way to reload the
config. It is still disruptive — it tears down every stream on the desktop,
including any injector already in a conference — which is why setup loads the
modules live instead of restarting anything.

Then play audio to the **Remote Desktop Injector** device and it goes into
whatever conference is live. The playback device carries the same name the
injector shows under in the BBB user list, so "play to Remote Desktop Injector"
and "Remote Desktop Injector is in the meeting" refer to the same thing.

## Use

```
conf-audio status      # what's running, and what the watcher sees
conf-audio start [vb]  # join now (uses the live conference if not given)
conf-audio stop        # leave
```

With the auto-join units enabled, none of that is normally needed: the injector
joins when a conference gets its first real participant and leaves when the
last one goes.

## Multiple users

Several users can inject at once, and nothing stops them. A FreeSWITCH
conference takes any number of SIP legs, BBB sets no `max-members`, and since
the account never REGISTERs (`regint=0`) there is no shared registration state
to contend over — each injector is an independent authenticated INVITE. Two
desktops injecting is two people unmuting.

What the shared account does cost is **identity**:

- Every injector shows up as "Remote Desktop Injector", so the user list cannot
  tell you which desktop a given one is.
- Asking FreeSWITCH "is *my* injector still in the conference?" has no answer,
  since a global present/absent flag cannot distinguish yours from someone
  else's. Per-user SIP accounts would fix that — but see below, because there
  is a better place to ask the question.

Per-user accounts (a directory XML per user, generated at `conf-audio setup`
time rather than at install) are therefore worth doing for the *name*, not for
exclusion and not for recovery.

## "Is my injector still connected?"

Nothing detects a dropped call today, and process liveness does not tell you.
baresip is a persistent user agent: when FreeSWITCH sends BYE the call ends and
baresip returns to idle **without exiting**, so the `pgrep` that `conf-audio`
uses proves the process is alive, not that a call is up. The failure is silent
— the audio simply stops.

Two local fixes, neither needing FreeSWITCH or per-user identity:

- **`redial_attempts` / `redial_delay`** (menu module, both in baresip's own
  example config, default `0` = off). baresip redials itself. Two config lines
  and no code. Needs checking on a live box: whether redial fires on a normal
  remote BYE or only on a failed outgoing attempt.
- **`ctrl_tcp`** — a JSON control interface that reports call state, so the
  reconcile could ask baresip directly. If used, it MUST be given an explicit
  `ctrl_tcp_listen 127.0.0.1:<per-user port>`: the default is `0.0.0.0:4444`,
  which exposes control of that user's baresip to the network and cannot be
  bound by two users at once. That is why the shipped `baresip.config` no
  longer loads the module at all.

The remaining wrinkle is policy, not mechanism: with auto-join enabled, *every*
user who ran `conf-audio setup` joins *every* meeting on the box. That is fine
when the injecting desktops are deliberate, and a footgun for someone who
enabled it once and later plays music. Enabling is the opt-in;
`systemctl --user disable --now conf-audio-autojoin.path` is the opt-out.

## Files

| File | Installed to |
|---|---|
| `bin/bbb-conf-audio-watcher` | `/usr/bin/` — system daemon, holds the ESL password |
| `bin/conf-audio` | `/usr/bin/` — per-user CLI and reconcile |
| `systemd/bbb-conf-audio-watcher.service` | `/usr/lib/systemd/system/` |
| `systemd/conf-audio-autojoin.{path,service}` | `/usr/lib/systemd/user/` — shipped, not enabled |
| `freeswitch/vlcinject.xml.in` | template → `/opt/freeswitch/etc/freeswitch/directory/default/vlcinject.xml` (0640, holds the password) |
| `freeswitch/aaa_vlcinject.xml` | `/opt/freeswitch/etc/freeswitch/dialplan/public/` |
| `share/baresip.config`, `share/conf-audio.pa` | `/usr/share/bbb-conf-audio/` — templates for `conf-audio setup` |
| `share/conf-audio-modules.pa` | `/usr/share/bbb-conf-audio/` — the virtual devices; `.include`d by each user's stub, and replayed via `pactl` at setup |

`/usr/lib/systemd/user` is the system-wide location for *user* units, which is
what makes this a system package that is nonetheless enabled per user.
`systemctl --global enable` is deliberately not used: that would turn it on for
everybody.

## Audio path

```
player -> [null-sink "vmic_sink" = "Remote Desktop Injector"] -> its .monitor
       -> [remap-source "virtmic"]  (the virtual microphone)
       -> baresip captures virtmic -> SIP/RTP (opus) -> FreeSWITCH conference
```

A second null sink, `desktop_out`, is the default sink and a dead end, so
conference audio coming back (and ordinary desktop sounds) never loop into the
microphone.

## Tests

- `tests/test-reconcile.sh` — the per-user state machine against a stub baresip
  and hand-written state: joins when a conference goes live, follows it when it
  moves, disconnects when it ends, does **not** pile in when an injector is
  already present, and leaves a running injector alone when the state file is
  missing or corrupt (the case that would otherwise disconnect people whenever
  the watcher restarted). No root, FreeSWITCH or PulseAudio needed.

The watcher was exercised against a scripted fake Event Socket covering the
same transitions, including `GLOBAL_AUDIO` and injector exclusion from the
participant count.

## Known gaps

- **Not yet run against a live BBB.** Everything here was verified against
  stubs and fakes; the FreeSWITCH-facing half (directory user, dialplan
  transfer, actual RTP into a conference) is inherited unchanged from the
  itpietraining deployment but has not been re-tested end to end from this
  packaging.
- **`.path` trigger not verified on a real user manager.** This machine has no
  lingering user session to test against. The design deliberately uses only the
  documented `IN_CLOSE_WRITE` behaviour, but it should be confirmed on a real
  box.
- **baresip is launched detached** (`nohup ... &`) and survives the oneshot via
  `KillMode=process`. Cleaner would be a `conf-audio-injector@.service` user
  unit so systemd tracks it properly.
- The conference plays enter/exit chimes, so a rejoin beeps.
