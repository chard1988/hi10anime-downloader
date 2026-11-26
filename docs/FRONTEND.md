# React / TypeScript frontend

Development branch: `feature/react-typescript-ui`, based on released beta.3.
This does not publish or retag the existing release.

## Stack and generated sources

React 19, strict TypeScript, Vite, Tailwind 4, TanStack Table 8, Lucide React,
and shadcn Base UI (`base-nova`). All application controls use the generated
shadcn components under frontend/src/components/ui; semantic layout and the
interactive login-browser image use ordinary HTML. Forms use Sheets (the initial
unlock page follows the login-01 Card/Field block). Feedback uses the official
Base UI Toast manager, not browser alerts. Combobox inputs filter their options.

The official dashboard-01 and login-01 blocks were installed with the shadcn CLI
and adapted to Hi10 navigation, live metrics, library and queue data. Demo charts,
demo users, sample data, and unused chart/drag-and-drop dependencies were removed.

References:

- https://ui.shadcn.com/blocks#dashboard-01
- https://ui.shadcn.com/blocks/login
- https://ui.shadcn.com/docs/components/base/data-table
- https://ui.shadcn.com/docs/components/base/combobox
- https://ui.shadcn.com/docs/components/base/sheet
- https://ui.shadcn.com/docs/components/base/toast
- https://lucide.dev/icons/

## Velocity theme

Installed using the owner-specified command:

```sh
pnpm dlx shadcn@latest add https://tweakcn.com/r/themes/cmo1jei81000004l734a5ekys
```

Registry source: https://tweakcn.com/r/themes/cmo1jei81000004l734a5ekys
Preview: https://tweakcn.com/themes/cmo1jei81000004l734a5ekys
The retrieved payload is frontend/theme-registry.json. Light/dark tokens are in
frontend/src/index.css. Inter is self-hosted (its package uses the family name
Inter Variable). The theme selector offers Light, Dark and System; selection is
stored in hi10-theme in localStorage, with System as the default. System changes
are observed live. An external theme bootstrap runs before the React module to
avoid a wrong-theme flash without weakening the script CSP.

## Local development and build

Node 24 and pnpm 11.25.0 (packageManager pin) are used for the build.

```sh
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
```

Run the Python web service separately on 127.0.0.1:8080 with disposable appdata
when testing. Vite proxies /api and /healthz to that service. Do not run a second
service against a directory already owned by another app instance.

```sh
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python tests/e2e.py
.venv/bin/python tests/benchmark.py
```

Vite generates src/hi10_downloader/static/index.html, theme.js and hashed assets.
These are build outputs, not hand-edited source. Build before making a Python
wheel or running the Python server from a clean checkout. Docker's separate,
digest-pinned Node stage installs the frozen lockfile, runs frontend tests, builds
assets and copies only the results into the existing non-root Python runtime.
No Node server is needed on unRAID. The source bundle includes frontend build
inputs while excluding node_modules and test artifacts.

## Compatibility and resource bounds

The same authenticated API, cookie protections, sessions and appdata formats are
retained. Existing callers of /api/state retain the previous defaults. Optional
query parameters add download_page_size and group_page_size (5/10/25/50/100), and
download_search (up to 200 characters, filename/project matching). Queue status
filters compose with search. At most five expanded groups return file rows; page
sizes cap each group at 100 files. Search caches are capped at eight variants.

Project tables use the incremental library snapshot and client pagination.
Queue grouping/search/pagination remain server-side. View state survives navigation;
page modules load on first visit. Polls deduplicate in-flight work, abort stale
queries and unmount requests, slow down when idle, and pause while the page is
hidden. Authentication expiry clears protected state and returns to unlock.

All existing operations remain: selected/all scans, independent scan/download
jobs, quality and collection selection, monitoring, exclusions, manual/scheduled
starts, per-item/bulk controls, expandable destinations/errors, URL edits, session
import and embedded login interaction. Queue URLs are fetched only when requested.
Private cookies/URLs are not included in generic state snapshots.

## Testing this branch on unRAID

The published beta.3 image still uses the prior UI. Build this source with a
separate local tag rather than replacing a published version:

```sh
docker build -t hi10-downloader:react-ui-test .
```

For NAS transfer, generate the source bundle with `python3 unraid/package.py`, copy
`dist/hi10-unraid.tar.gz` to unRAID and extract it before building. Stop the current
container and back up appdata and hi10-manifest.json. Edit its Repository to
`hi10-downloader:react-ui-test`, retaining existing mappings, password and web port,
then Apply and hard-refresh the browser. Do not run both services on the same data.
The default installer still pulls the published beta.3 image and will not select
this development UI. No new public release is created by this migration branch.
