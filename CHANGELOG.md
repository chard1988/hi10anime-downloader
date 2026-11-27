# Changelog

## Unreleased

- Report incoming bytes without 1 MiB buffering so ongoing transfers can show
  speed promptly; scale throttled chunks for responsive reporting at low limits.

- Show live overall download speed in the Downloads bulk action toolbar, combining
  all active transfers with a bounded five-second rolling rate.

- Remove selected project groups from the Downloads queue across all item pages,
  preserving downloaded files and library records. Replaces the queue re-scan action.

- Saved total download speed limit in kbps and 1–8 parallel file transfers in the
  download settings Sheet, with shared throttling, batch limits and cancellation.

- Migrate the web interface to React and TypeScript with official shadcn Base UI
  dashboard/login blocks, Lucide icons, Velocity theme, and Light/Dark/System modes.
- Searchable comboboxes, Sheets for forms, Toast feedback, and paginated project
  and queue data tables with bounded server-side queue search/page sizes.
- Preserve scanning, monitoring, quality/section selections, grouped queue actions,
  URL repair, scheduling, session import and embedded-browser interaction.
- Multi-stage frontend build with a pinned Node builder, frozen pnpm lockfile, and
  self-hosted assets served by Python without a separate Node frontend server.

## 0.3.0b3 — 2026-11-26 testing prerelease

- Include explicit download tables outside the first WordPress content block,
  retaining deduplication and highest-quality selection.

- Detect explicit MKV destinations in fc.lc and Spaste download wrappers alongside
  ouo links; deduplicate wrappers for the same file and ignore ZIP patches.

- Opt-in persistent project monitoring with bulk controls, a monitored filter,
  interval settings, pause/resume and check-now controls.
- Automatically queue/download existing missing files and future additions using
  current quality/section selections, without adopting manual queues or retrying
  failed attempts indefinitely. Preserve schedules, exclusions and restart history.

## 0.3.0b2 — 2026-11-17 testing prerelease

- Check same-quality episode/movie mirror links with bounded video-prefix probes before downloading; skip unavailable links and fail over between validated mirrors without lowering quality.
- Reuse cached alternatives for existing queues, preserve manual URL edits, and recognize completed files downloaded from another known mirror.

- Export the current Hi10 Chrome/Edge session using a site-scoped local extension, including HttpOnly cookies, without another login.

- Desktop login can explicitly use installed Chrome/Edge with sandboxing enabled.
- Browser startup/navigation failures produce safe CLI errors and clean up the browser.

- Versioned GHCR beta publication, GitHub prerelease assets/reports and pull-based unRAID installation.
- Explicitly disclosed beta security/browser compatibility limits; no stable/latest image tag.

## 0.3.0b1 — bootstrap private-beta snapshot

- Production Waitress WSGI boundary with bounded HTTP resources and request IDs.
- Login throttling, persisted revocable sessions, fixed-origin HTTPS cookie policy.
- Pinned public-address HTTP connections, redirect checks, bounded page bodies.
- Authenticated HTTPS-only login browser egress proxy and sandbox-on default.
- Recoverable multi-file state journal, schema validation, and CLI/service locks.
- Server-side lazy queue pagination, bounded downloads, and disk/time limits.
- MIT license, pinned release inputs, local/CI validation and distribution guides.

No stable image has been published; no Community Applications submission made.

## 0.2.0 — private development snapshots

Initial web interface, session import/login, project/season parsing, queueing,
scheduling, quality selection, exclusions, URL editing, and grouped queue controls.
