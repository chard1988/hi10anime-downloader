# Beta administration guide

## Supported deployment

This is an MIT-licensed Linux/amd64 private beta with Python 3.12 and a bundled
Chromium login browser. No stable/public registry image or CA listing is published.
Use a private LAN/Tailnet or an HTTPS reverse proxy. Default unRAID UID/GID is
99:100. Other Linux users may specify --user UID:GID with writable config/download
mounts and a writable HOME. The process never recursively chowns existing mounts.
Use one service OR CLI process per appdata/download directory.

## Install and update

Build locally with `docker build -t hi10-downloader:beta .`. For Compose, copy
.env.example to a private .env, set a unique password, create appdata/downloads
writable by 99:100, and run `docker compose up -d --build`. Compose binds to
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
python -m unittest discover -s tests -q
for script in src/hi10_downloader/static/*.js; do node --check "$script"; done
node tests/test_polling.cjs
node tests/test_ui_state.cjs
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
