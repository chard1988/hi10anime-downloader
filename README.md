# Hi10 Download Manager

A self-hosted project scanner and MKV download queue, with a web interface and CLI.
**0.3.0-beta.3 is a testing prerelease**, with disclosed security and embedded-browser
compatibility limits. It is not a stable release or Community Applications listing.
See the [beta release](https://github.com/chard1988/hi10anime-downloader/releases/tag/v0.3.0-beta.3)
for the image, installation files and exact-image validation reports.

## Features

- Opt-in project monitoring checks periodically and automatically downloads existing
  missing files and new additions using your quality and section selections.

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
- Before downloading a file with multiple same-quality links, check the alternatives
  and choose a working mirror. Keep the selected quality if every mirror fails.
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

Already signed in in your normal Chrome/Edge browser? Use the
[Hi10 session exporter](browser-extension/hi10-session-export/README.md) to save
that profile’s existing Hi10 cookies, then import its `session.json` in Account &
session. You do not need another login or a Docker rebuild.

## Container / unRAID

Published beta image:

```sh
docker pull ghcr.io/chard1988/hi10anime-downloader:0.3.0-beta.3
```

See [unRAID install/upgrade instructions](docs/UNRAID_INSTALL.md). Existing users
can edit Repository and keep their appdata/download mappings; uninstalling is not
required. Back up the complete appdata and download manifest before upgrading.
The package owner must make the new GHCR package Public once before anonymous
pulls work. Only the beta/versioned tags are published; no latest/stable tag exists.

The image runs as UID 99/GID 100, uses `/config` and `/downloads`, exposes port
8080, and supports a documented `--user` override with writable mounts/HOME.
Use `--init --shm-size=1g --stop-timeout=75 --cap-drop=ALL --security-opt=no-new-privileges`.
No existing host folder is recursively chowned. Use the browser-session exporter
and import JSON; hardened embedded login remains a beta compatibility limitation.

For Compose, create writable appdata/downloads, copy `.env.example` to a private
`.env`, set a unique app password and run `docker compose up -d`. The provided
Compose file binds to localhost. To build locally instead, use
`docker compose -f compose.yaml -f compose.build.yaml up -d --build`.
A local build can differ from the published digest.

The verified source bundle's `install.sh` pulls the published image and installs
an unRAID template, while preserving existing templates and data. Its explicit
`--build-local` option is for source testing. See the guide for upgrades, backup,
rollback and choosing an unused host port. A prior state format may require one
unlock after upgrade; website sessions are retained and can be verified/imported.

Integrated unRAID Tailscale hooks and ARM are not advertised as validated. Use a
private LAN/Tailnet; do not enable Privileged or disable sandboxing to make login work.

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
restart; unscheduled manual queues do not auto-start. The container must be available at
the chosen time. Closing the browser does not cancel background work.

## Development and distribution

```sh
.venv/bin/python -m unittest discover -s tests -q
for script in src/hi10_downloader/static/*.js; do node --check "$script"; done
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

The beta release workflow tests and publishes only explicit beta refs to GHCR and
GitHub prereleases. Strict stable-readiness checks remain separate; beta publication
does not waive their findings. CA submission and stable/latest publishing remain
disabled. See [the release procedure](docs/RELEASE_GUIDE.md).

## Project monitoring

In the project library, click **Monitor** on a project or select checkboxes and
**Monitor selected**. This enables automatic checks and downloads of existing
missing files and future additions. Use **Monitoring** in the page header to set
an interval (15 minutes–7 days, default 60 minutes), pause/resume, or check now.
The **Monitored** filter shows watched, included projects.

The container must stay running and have a working saved Hi10 session. Browser
closure does not stop monitoring. Checks run sequentially in small batches, can
run alongside downloads, and use the project's quality and section selections.
A saved download schedule takes priority over automatic starts. Existing manual
queue entries are preserved and remain manual; only files added by monitoring
auto-start. Failed/interrupted attempts need manual Retry. **Stop batch** on an
automatic batch pauses monitoring until resumed in its settings.

Already handled files are tracked across restarts and queue clearing, so they
are not repeatedly downloaded or upgraded. Unmonitoring prevents further
automatic starts for the project; a transfer already in progress may finish.
Exclusions suspend its checks/starts. Unmonitor then monitor again to deliberately
reset its tracked history; verified files and existing queue entries are retained.
Monitoring is limited to 200 projects and 100,000 tracked file identities.

Monitoring is included in beta.3. Follow [the installation guide](docs/UNRAID_INSTALL.md)
to update an existing installation while retaining appdata and downloaded files.
