# Beta administration guide

## Supported deployment

This is an MIT-licensed Linux/amd64 testing beta with Python 3.12 and a bundled
Chromium login browser. Versioned beta images use GHCR; no stable image or CA listing
is published. See UNRAID_INSTALL.md for registry installation and upgrades.
Use a private LAN/Tailnet or an HTTPS reverse proxy. Default unRAID UID/GID is
99:100. Other Linux users may specify --user UID:GID with writable config/download
mounts and a writable HOME. The process never recursively chowns existing mounts.
Use one service OR CLI process per appdata/download directory.

## Install and update

Build locally with `docker build -t hi10-downloader:beta .`. For Compose, copy
.env.example to a private .env, set a unique password, create appdata/downloads
writable by 99:100, and run `docker compose up -d`. Compose binds to
127.0.0.1 by default; deliberately choose a LAN binding if needed. For unRAID,
use the source installer and existing template, keeping /config and /downloads.
Allow 75 seconds for stop. `--init --shm-size=1g` is recommended for Chromium.

Back up ALL appdata and hi10-manifest.json before upgrading; backup files contain
credentials. Back up videos separately. Stop the old service, save its exact image
ID/digest, build the beta, and recreate it with the SAME mappings. Do not run old
and new versions against the same data. An existing installation must unlock once
because authentication tokens changed to revocable sessions. Hi10 session import
is retained. The generated web password is only in private web-password.json.

To roll back, stop the beta and restore the entire pre-upgrade appdata and manifest
backup before starting the prior image. Do not downgrade state in place. Videos
are preserved. New receipt files identify completed downloads awaiting manifest
recording; recovery verifies checksums before trusting them. Do not delete receipts
until recovery has finished. `.bak`, `.corrupt`, and the pending state journal are
private recovery records, not disposable public diagnostics.

## Security settings

- HI10_WEB_ORIGIN: exact external HTTP(S) origin, e.g. https://downloads.example.test.
  With HTTPS, cookies gain Secure. Set this behind a reverse proxy.
- HI10_ALLOWED_HOSTS: comma-separated exact Host headers, including port when used.
  Include the external host AND 127.0.0.1:8080 (or the configured port) for
  the container health check.
- Forwarded headers are not trusted. The proxy must preserve Host; do not rely on
  a user-supplied X-Forwarded-Proto to enable security behavior.
- HI10_ALLOWED_NETWORKS: optional narrow outbound CIDR exceptions. Default is none.
  The downloader and login proxy block nonpublic addresses, including localhost,
  link-local, LAN and metadata endpoints. Avoid broad exceptions.
- HTTP(S) download redirects are bounded to five and each fresh connection validates
  and pins resolved addresses while retaining original TLS hostname verification.
  Environment HTTP proxy settings are intentionally ignored to prevent bypasses.
- The login browser uses an authenticated loopback HTTPS tunnel proxy, 8 tunnels,
  32 MiB/tunnel and 90-second tunnel deadline. Plain HTTP login sites are unsupported.
  Chromium sandbox is enabled by default. If a host cannot run sandboxed Chromium,
  use desktop session import; do not grant the container broad privileges.
  On this development host the exact-image sandbox test passes with ordinary
  engine defaults but fails with the Compose cap-drop/no-new-privileges settings.
  The hardened deployment supports session import; embedded login compatibility
  remains an unresolved gate. See https://playwright.dev/docs/docker for the
  upstream namespace/seccomp guidance; no unconfined profile is recommended here.
  HI10_BROWSER_SANDBOX=0 exists only for explicitly accepted private troubleshooting,
  not the recommended public distribution configuration.
- Login limits: 10 attempts per client per five minutes, with a bounded global
  budget. Behind an untrusted proxy, clients may share its peer limit. Logout
  revokes that cookie on the server; password changes invalidate existing tokens.

No incoming external network is opened by these settings. Tailscale hook support
is not advertised as validated; use host Tailscale or import a desktop session.
Tailscale state can live under /config/.tailscale_state if integration is configured,
but the current non-root image must not simply be changed to run the app as root.

## Resource and operational settings

Waitress runs 4 request threads, 64 connections, a 32 KiB header limit, a 2 MiB body
limit and a 20-second idle channel timeout. One owner runs one scan and one download
batch; do not launch multiple WSGI workers with independent schedulers.

- HI10_MAX_QUEUE_ITEMS: 50000.
- HI10_MAX_FILE_BYTES: 107374182400 (100 GiB).
- HI10_MIN_FREE_BYTES: 268435456 (256 MiB) reserved beyond the expected file size.
- HI10_DOWNLOAD_DEADLINE: 21600 seconds (6 hours) per file.

HTML/script/data fetches are streamed with bounded decoded size and a 45-second
elapsed check; individual HTTP reads are bounded to 30 seconds (connect: 15).
Automatic retries apply only to transient network/HTTP failures (up to three web
attempts). HTTP 403/404, invalid files and filesystem errors stop immediately.
Retry-After seconds/HTTP dates are honored up to a five-minute wait; longer
requests stop for a later manual retry instead of retrying early.

Queue group summaries are cached. Only open groups fetch rows, at most 50 per
project and five projects per outer page. The page selection checkbox selects
loaded rows; project-level exclusion still affects the entire project.

/healthz checks this service only, not external Hi10 access. Docker health status
does not automatically restart a container; configure monitoring separately.
Request/job IDs and error categories are safe diagnostics. Logs deliberately omit
URLs, passwords, request bodies and headers. Never publish appdata or full URLs.

State-format version 3 guards unsupported upgrades. Selected top-level schemas are
validated; versioned per-file backups and a private roll-forward journal recover
committed state changes. A failed journal commit marks the app stopping: restart
it to replay the journal before accepting further writes. Advisory locks are local
filesystem locks; verify network filesystem lock/fsync semantics before use. No
claim is made that every NAS/NFS/SMB setup is supported.

## Validation commands

```
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend test
pnpm --dir frontend build
python -m unittest discover -s tests -q
python tests/benchmark.py
python tests/e2e.py
python scripts/container_smoke.py --engine podman --image localhost/hi10-downloader:beta
python scripts/check_distribution.py
```

Run Python/browser tests inside the built image to test the actual Python 3.12 and
Chromium versions. E2E fixtures are local and require no Hi10 account or video data.
The unit loopback tests need local socket permissions. The synthetic benchmark is
not a throughput promise or multi-day soak substitute.

The deprecated one-shot container runner no longer submits credentials automatically.
Use web login or desktop session import. CLI scan/download/login now also acquire
resource locks; do not run them while the service owns the same directory.

## Desktop session capture on Ubuntu

If `hi10 login` reports `No usable sandbox` or `Chromium sandboxing failed`,
Ubuntu's AppArmor policy may be blocking the downloaded Chromium executable.
The CLI supports an explicitly selected, separately installed Google Chrome or
Microsoft Edge while keeping Chromium sandboxing enabled:

```sh
.venv/bin/hi10 --state "$HOME/Downloads/hi10-session/session.json" login --browser chrome
```

Complete login/CAPTCHA in the new browser window, return to the terminal and press
Enter. Then import `Downloads/hi10-session/session.json` through Account & session
in the server WebUI. This is a new temporary browser context; it does not access
an existing personal Chrome profile or copy its saved passwords. A graphical
desktop is required. Use `--browser msedge` for an installed Edge, or omit the
option to use the downloaded Chromium. The command does not install branded
browsers automatically and never retries with sandboxing disabled.

Chromium documents Ubuntu's executable-path AppArmor restrictions in its
[AppArmor guide](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md).
Playwright documents the supported installed-browser channels in its
[browser guide](https://playwright.dev/python/docs/browsers#google-chrome--microsoft-edge).
This desktop option does not change the container's embedded login browser or
resolve its separately recorded hardened-runtime compatibility gate.

## Import an existing normal-browser session

If a new automated browser login fails while your regular browser is already
signed in, use the local [Hi10 session exporter](../browser-extension/hi10-session-export/README.md).
Load it in that same Chrome/Edge profile and explicitly export the existing
Hi10 cookies to `session.json`; then use Account & session → Choose session JSON
in the downloader. This includes HttpOnly login cookies and avoids another
login attempt. The local helper requests cookie access only to Hi10 and sends
no data over the network. You grant that access when loading the extension.
No Docker update is needed to import the standard Playwright storage-state file.

The chat’s in-app browser is a separate browser context; its connection does not
provide access to your personal Chrome session. Do not use `document.cookie` or
Save page as to capture an authenticated session: protected HttpOnly cookies are
not available to page JavaScript. The app still verifies the imported session;
expiration and site/browser/IP binding can affect reuse.

## Alternative download links

Link checking runs automatically at download time for files with multiple known
links at the selected resolution. Episodes, movies and other single-file projects
use the same behavior. Alternatives are grouped by the existing file identity,
section/season and quality; different episodes, editions and encodes stay separate.
The selected filename and destination remain stable.

Each alternative receives a streamed GET requesting `Range: bytes=0-3`. An active
response must serve a Matroska/EBML prefix, rather than merely an HTTP 200 login,
HTML error or challenge page. Both valid partial responses and servers ignoring
Range with HTTP 200 are supported; the stream closes after reading the prefix.
Probes use the same authenticated client, redirect limits, public-address policy
and cookie-domain restrictions as downloads. No HEAD support is required.

All alternatives are checked sequentially, then the first working one is used.
If that mirror fails during transfer, another validated same-quality alternative
can be tried. Full download integrity and disk/size/time limits still apply.
A prefix probe proves current availability only, not that the entire transfer will
succeed. If no alternative works, the item fails with counts/error categories;
**the link checker never falls back to a lower resolution**. Failed links are retained for
future retries rather than permanently blacklisted.

Files with one link have no extra request. Explicitly edited queue URLs stay
authoritative and bypass alternative selection. Existing queues reuse alternatives
from cached scan data when available. Rescan a project to refresh changed upstream
links; adding it to the queue again refreshes pending records without duplicates.
Older CLI plans can reuse their recorded variants, without changing queued quality.

Link-check progress and the final count are shown in expanded queue-row details.
View download link uses the chosen mirror after selection. Already downloaded files
can be verified against their manifest if its source is any known same-quality
mirror, without probing or downloading again.

Resource limits: at most 32 alternative links per file, a 60-second elapsed checking
budget (checked between probes and prefix chunks), and 5-second connect/read
inactivity timeouts. Redirects retain the client's existing five-hop limit.
Cancellation is checked between probes and prefix chunks. Timeouts and HTTP errors
mean unavailable during this check, not proof that a URL is permanently dead.

## Project monitoring

Opt in through Monitor/Monitor selected in the project library. Monitoring checks
existing missing files as well as future additions, using saved quality/section
choices. Header Monitoring settings control interval, pause/resume and Check now.
Only monitoring-owned new queue entries auto-start. Existing manual entries remain
manual, and explicit download schedules take priority. Stop batch pauses automatic
monitoring; resume in settings. Failures require manual Retry after an attempt.

The private `monitoring.json` in appdata stores settings, project check times and
hashed file identities; include it in full appdata backups. It uses the same schema
validation, last-known-good backups and transaction recovery as the queue. Keep the
container running with a valid session. Expired sessions suspend checks until
verification/import succeeds. Checks are sequential, up to five projects per
scheduler pass, with a 15-minute minimum interval. Limits: 200 monitored projects,
100,000 tracked identities. Excluded projects are skipped; unmonitoring retains
queue/files but prevents future automatic starts. A currently transferring file
may finish. Re-enabling an unmonitored project resets its tracked history; verified
files and existing queue entries still prevent duplicates.

## Download transfer settings

In Downloads, Settings contains a saved download speed limit in kbps and a maximum
parallel file count. The speed is a total budget shared by all transfers in the
batch, measured in decimal kilobits per second (1,000 bits per kilobit). For example,
8,000 kbps is approximately 1 MB/s; it is not 8,000 KB/s. Zero means unlimited.
Allowed speed values are integers from 0 to 10,000,000; parallel count is 1 to 8.
Defaults retain the prior behavior: unlimited bandwidth and one file at a time.

Settings are kept privately in appdata/transfer-settings.json with schema checks,
backup recovery and the existing durable transaction mechanism. Save transfer
settings does not start downloads or alter a schedule. A batch captures its limits
when started; edits apply to the next batch, including manual, selected, retry,
scheduled and monitoring starts. Stop and restart the batch to change its limits.
Stop cancels active transfers and retains pending files. Parallel workers preserve
per-file failures and serialize queue/manifest writes. More workers consume more
network connections, memory and disk bandwidth.

Limiting uses a shared cancellable byte budget with read chunks up to 64 KiB.
At low limits, chunks shrink so a reservation from every worker fits within
roughly 250 ms. Unlimited downloads report incoming chunks without buffering
1 MiB before updating their progress. Socket and
HTTP buffering can create short bursts; this is an application throughput target,
not a packet shaper. Metadata/mirror probes are outside the video byte budget.
The existing six-hour per-file deadline still applies at low speed limits. Failed
or interrupted files retain the existing manual retry/restart behavior.


The Downloads action toolbar shows Overall speed in B/s, KB/s or MB/s. This is a
combined video transfer rate across every worker, independent of queue filters
and pagination, averaged over the last five seconds. It updates with active job
polling (about 1.5 seconds), decays to zero after a stall and shows zero immediately
when a batch stops. Retries count newly transferred bytes; verified existing files
are not counted as network transfers. Measurements stay in memory in fixed 250 ms
buckets, reset on each batch, and are not saved in appdata.
