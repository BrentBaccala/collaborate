# bbb-aws-hibernate

Hibernates a BigBlueButton server when it's idle and brings it back on demand —
saving cost on an AWS instance that's only used during classes. Two independent
halves:

- a **stop side** — a service that hibernates *this* instance when nobody's
  using it (and, optionally, stops companion instances), and
- a **start side** — an AWS Lambda that wakes the instance from a signed login
  link.

## Stopping the system (self-hibernate)

### Install

Build from the top-level collaborate repo and install from the apt repo:

```bash
cd ~/collaborate && make bbb-aws-hibernate     # -> build/bbb-aws-hibernate_3.0.0+<ts>-1_amd64.deb (root:root)
# publish to the repo (reprepro into ~/website/jammy-300, then the rsync), then on the host:
sudo apt install bbb-aws-hibernate
```

The service (`bbb-aws-hibernate.service`, runs as `nobody`) polls every 60 s and
hibernates the instance when idle.

> **Conffile gotcha:** `/etc/default/bbb-aws-hibernate` is a dpkg conffile. If
> you place your credentials there *before* installing, the install hits a
> conffile prompt (and fails under a non-interactive apt). Either install with
> `sudo apt-get -o Dpkg::Options::=--force-confold install bbb-aws-hibernate`
> to keep your file, or add the credentials after installing.

### Giving it permission to hibernate

The service needs AWS credentials allowing `ec2:StopInstances` on this instance.
Credentials come from the normal boto3 chain (environment first, then an
instance profile via IMDS). Two ways to provide them:

**Recommended — scoped static key (`create-hibernate-controller`).** A dedicated
IAM user whose key lives only in the service's environment file, so nothing else
on the box can use it:

```bash
# run with admin creds; pins the user to this instance via an InstanceId principal tag
./create-hibernate-controller i-0123456789abcdef0 --name collaborate-hibernate --profile <admin>
```

Put the printed `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` lines into
`/etc/default/bbb-aws-hibernate` (mode 600). The policy is generic —
`ec2:StopInstances` on `arn:aws:ec2:*:*:instance/${aws:PrincipalTag/InstanceId}` —
and the instance is pinned by the user's `InstanceId` tag (the same
`aws:PrincipalTag` trick `create-DNS-updater` uses). The service runs as
`nobody` reading the key from the 600 env file, so a participant in a desktop
session can't read it.

**Alternative — `StopSelf` instance profile.** The `policy` file in this
directory is the instance-profile policy: `ec2:StopInstances` on
`${ec2:SourceInstanceARN}` (self-only — note `ec2:SourceInstanceARN` is *only*
populated for instance-profile credentials, which is why a static key cannot use
this exact policy). Create an IAM role `StopSelf` with it and attach the
instance profile to the instance.

> ⚠️ An attached instance profile serves its credentials from IMDS
> (`169.254.169.254`) to **every local user** — on a collaborate host, any
> participant with a desktop terminal could fetch them and hibernate the box.
> Prefer the static key; use the instance profile only on trusted, single-user
> hosts.

### When it hibernates

`is_server_idle()` is true — and the instance hibernates — only when **all** of:

- **no SSH sessions** — it counts `psutil.users()` whose `host` is set;
  VNC/`machinectl` desktops have `host=''` and are *not* counted, so idle remote
  desktops don't keep it awake;
- **no `swapoff` running** — AWS advises against hibernating while the previous
  resume's `swapoff` is still finishing;
- **no running BigBlueButton meetings** — `bigbluebutton.getMeetings()` is empty.

It checks every 60 s, but **won't hibernate within `HIBERNATE_GRACE_SECONDS`
(default 300) of a boot or a resume** — so a freshly-woken server gives users
time to (re)connect before it can put itself back to sleep, rather than
hibernating on its first idle check. The grace resets on resume too (the
service detects it via `CLOCK_BOOTTIME`/`CLOCK_MONOTONIC` divergence, since the
process is *restored*, not restarted, on resume). Set it in
`/etc/default/bbb-aws-hibernate`. (Normal collaborate desktop use happens inside
a meeting, so the meeting check keeps it awake during class.)

To also stop **companion instances** when this one hibernates, set
`ADDITIONAL_STOP_INSTANCES` / `ADDITIONAL_STOP_TAGS` / `ADDITIONAL_STOP_FILTERS`
in `/etc/default/bbb-aws-hibernate` (the tag/filter forms need
`ec2:DescribeInstances`, so widen the policy accordingly).

### Guest / OS prerequisites

Hibernation also needs the instance prepared (done at launch and by
`ec2-hibinit-agent`): launched with `HibernationOptions` enabled and an
**encrypted root** large enough for RAM, a swapfile with a consistent
`resume=` / `resume_offset=`, and **`nokaslr`** on the kernel cmdline for a clean
resume. See the `bbb-install` skill's hibernation section for those steps.

## Starting the system (wake Lambda)

Once hibernated, the instance can't start itself, so an AWS Lambda starts it from
a JWT login link signed with an SSH RSA key.

1. Edit **`configuration.py`** — a `CONFIG` dict keyed by server name (see the
   docs at the top of that file). Per server:
   - `fqdn` — the BBB host's DNS name,
   - `keys` — the OpenSSH **RSA public keys** allowed to sign wake links,
   - instance selection — any of `primary_instance`, `instances` (explicit IDs),
     `tags` (e.g. `{"AutoStart": "x"}`), or `filters` (boto3 filter spec); the
     primary is always included.
2. Run **`make`** in this directory. (This is *not* the package build — it
   deploys the Lambda + API Gateway and records its URL in
   `../bbb-auth.sqlite`.) Run it from a secure machine with admin AWS creds,
   **not** on the server. If it errors with *"An update is in progress,"* just
   run it again.
3. Put the signing RSA **public** key in **`/etc/bigbluebutton/authorized_keys`**
   on the server. (`bbb-auth-jwt` reloads this file when it changes — no service
   restart needed.)
4. Generate a wake link: `bbb-mklogin -n <nickname> -m '<Name>'` (moderator; `-n`
   is the server nickname from `configuration.py`). Opening it invokes the
   Lambda, which starts the instance and redirects once it's up and DNS (e.g.
   ddclient / `nsupdate-aws`) has caught up to the new public IP.

## Notes

- The stop side and start side are independent; either works alone.
- Validated on collaborate.freesoft.org (2026-05-21): the service hibernated the
  instance (`Client.UserInitiatedHibernate`) using the `collaborate-hibernate`
  static key, and the wake-Lambda start path was verified separately.
