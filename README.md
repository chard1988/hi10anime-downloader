# Hi10 Download Manager

A self-hosted project scanner and MKV download queue, with a web interface and CLI.
**0.3.0b1 is an unreleased private beta**, undergoing distribution hardening. No
stable image, public registry repository, or Community Applications listing exists.

## Features

- Import a desktop Playwright session, or sign in using the embedded Chromium view.
  Fill login fields does not submit; complete challenges yourself. CAPTCHA is not
  bypassed, and successful login cannot be guaranteed.
- Load the Hi10 project list, scan selected/all projects, exclude unwanted projects,
  and choose global/project/section/file quality preferences.
- Group collection series and seasons under their parent download folders. Prefer
  the highest detected resolution, with configured-quality fallback.
- Queue now and start later, schedule a start in your browser timezone, run one scan
  alongside one sequential download batch, and stop them independently.
- Group queue files under expandable projects. Expand files for destination/errors,
  edit expired links, retry individual files, filter status and apply bulk actions.
- Files use private manifests, checksums, temporary downloads and completion receipts.
  Existing untracked files are preserved. Interrupted transfers currently restart
  from the beginning; byte-range resume is not implemented.

Only supported direct HTTP(S) MKV targets and recognized wrappers are resolved.
Landing pages/archives/changed upstream markup can need a new resolver. This is an
independent tool: no affiliation or reliability promise from the upstream website.
Use it only for content you are authorized to access/download.

## Install locally

Linux and Python 3.12 are the tested release target. Other Python/platform versions
are development conveniences until separately validated.

```sh
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.lock
.venv/bin/pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m playwright install chromium
.venv/bin/hi10-web --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080. Set HI10_WEB_PASSWORD or retrieve the generated password
from private `.hi10/web-password.json`. It is not printed in logs. This password is
separate from your website credentials. Keep the entire appdata directory private.

## Container / unRAID

```sh
docker build -t hi10-downloader:beta .
```

The image runs as UID 99/GID 100, uses `/config` and `/downloads`, and exposes port
8080. Use `--init --shm-size=1g --stop-timeout=75`. Both mounted folders must be
writable by the process identity. Other UID/GID values can be supplied through
Docker's `--user` option with appropriate directory ownership and writable HOME.
No existing host folder is recursively chowned.

For Compose, create writable `appdata`/`downloads`, copy `.env.example` to a private
`.env`, set a unique password and run `docker compose up -d --build`. The provided
Compose file binds to localhost by default. See [administration](docs/ADMIN_GUIDE.md)
for reverse-proxy settings and LAN access.

For unRAID source installations, use `unraid/package.py` to produce the installer
bundle, transfer it to the server and run its `install.sh`. It builds the local
`hi10-downloader:local` image and preserves existing templates. Stop/recreate the
existing container with the same `/config` and `/downloads` mappings. Set the stop
timeout to 75 seconds. If Apply is disabled, increment an innocuous update-marker
variable to make the template change concrete. Hard-refresh the WebUI afterward.

**Before upgrading:** stop jobs and back up all appdata plus hi10-manifest.json.
Do not downgrade state in place: restore the complete pre-upgrade backup before
running an older image. The new revocable app-cookie format requires one unlock;
website session imports remain available. A pending transaction is replayed before
state is loaded after a crash. See the full recovery/rollback guide below.

The embedded browser requires working Chromium sandbox support. If the host blocks
sandboxed Chromium, import a session captured on a desktop. Do not run the entire
container privileged to make login work. Integrated unRAID Tailscale hook support
is not yet advertised as validated; host Tailscale is a separate deployment option.

## Operation

Project exclusion is persistent. It skips scans and queueing and removes pending
queue records for the selected projects, while preserving completed files. Undo
through Project library → Excluded → Include selected. Change exclusions while idle.
Ready to download excludes these projects.

Queue groups show filtered item/completed/failed counts, five projects per outer
page. Open groups fetch 50 items at a time from the server. File selections persist
across pages; the page checkbox selects loaded files only. Group checkboxes select
projects for exclusion, separately from file bulk actions.

Start downloads / Start selected shows a spinner and processed/total count. The
count includes failed attempts processed in the batch, not only successful files.
Failed rows retain the specific saved failure cause and retry count. Older generic
failure records gain new details after retrying.

View download link opens an editable dialog for pending/failed/interrupted files.
Stop jobs first. Save URL keeps filename/destination, marks the item queued and does
not start it. Manually edited links persist across restart/requeue. Viewing/opening
a link is authenticated; private URLs are not included in ordinary status polls.

Settings shows the container destination and scheduling picker. Change the host
folder through container mappings. Schedules persist and can run after an overdue
restart; unscheduled queues do not auto-start. The container must be available at
the chosen time. Closing the browser does not cancel background work.

## Development and distribution

```sh
.venv/bin/python -m unittest discover -s tests -q
node --check src/hi10_downloader/static/app.js
node tests/test_polling.cjs
node tests/test_ui_state.cjs
.venv/bin/python tests/benchmark.py
.venv/bin/python tests/e2e.py
```

Tests use disposable fixtures; live website credentials are not required. Container
validation must run the same suite in the exact built image. HTTPX/httpcore are
hash-locked because the outbound transport pins validated DNS addresses. Regenerate
locks under Python 3.12, including `--allow-unsafe` for pinned build dependencies.

- [Administration, security configuration, limits and recovery](docs/ADMIN_GUIDE.md)
- [Distribution audit and initial findings](docs/DISTRIBUTION_READINESS_AUDIT.md)
- [Hardening progress and remaining external gates](docs/HARDENING_PROGRESS.md)
- [Local candidate validation and release gates](docs/RELEASE_GUIDE.md)
- [Security reporting](SECURITY.md), [contributing](CONTRIBUTING.md), [changelog](CHANGELOG.md)
- [MIT license](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md)

CI is prepared locally and deliberately does not publish images or submit CA apps.
Repository ownership, actual public URLs, a reporting channel and stable release
approval remain owner-controlled distribution steps.
