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
the shared password, and enables both user units. Restart PulseAudio
(`pulseaudio -k`) to pick up the virtual devices.

Then play audio to the **Virtual_Mic_Feed** device and it goes into whatever
conference is live.

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
- Nothing can answer "is *my* injector still in the conference?". The original
  daemon self-healed by noticing its injector had vanished and redialling; with
  one shared account and several injectors, a global present/absent flag cannot
  distinguish yours from someone else's, so that recovery is not implemented
  here. A user whose call drops stays disconnected until the conference changes
  state.

Both are fixed the same way, if it matters: give each user their own SIP
account (a directory XML per user, generated at `conf-audio setup` time rather
than at install). That is worth doing for identity, not for exclusion.

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

`/usr/lib/systemd/user` is the system-wide location for *user* units, which is
what makes this a system package that is nonetheless enabled per user.
`systemctl --global enable` is deliberately not used: that would turn it on for
everybody.

## Audio path

```
player -> [null-sink "vmic_sink"] -> its .monitor
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
