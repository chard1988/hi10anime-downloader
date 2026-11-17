# Changelog

## Unreleased

- Check same-quality episode/movie mirror links with bounded video-prefix probes before downloading; skip unavailable links and fail over between validated mirrors without lowering quality.
- Reuse cached alternatives for existing queues, preserve manual URL edits, and recognize completed files downloaded from another known mirror.

- Export the current Hi10 Chrome/Edge session using a site-scoped local extension, including HttpOnly cookies, without another login.

- Desktop login can explicitly use installed Chrome/Edge with sandboxing enabled.
- Browser startup/navigation failures produce safe CLI errors and clean up the browser.

## 0.3.0b1 — unreleased private beta

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
