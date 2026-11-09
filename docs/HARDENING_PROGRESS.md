# Distribution hardening progress

Updated 2026-11-09. The readiness audit records the earlier baseline. This document
tracks the changes since that audit. Version 0.3.0b1 remains an unreleased private
beta. The owner selected MIT; LICENSE contains that license. No repository, image
publication, signing identity, stable release or CA submission has been created.

## Implemented

- Waitress replaces the development HTTP server in production: one application/job
  owner, bounded connections, threads, headers, bodies and idle time. Shared API
  routing is separate from transport. UI scripts are separated into shared core,
  projects, downloads, rendering, detail and browser responsibilities, with ordered
  deferred loading and real-browser validation. Request IDs and minimal authenticated
  diagnostics omit private URLs and credentials.
- Persisted, expiring, revocable interface sessions; fail-closed session recovery;
  bounded login throttling; strict JSON/Origin handling; fixed external origin and
  exact Host options; Secure cookies with HTTPS. Forwarded headers are untrusted.
- Public-address DNS validation and connection pinning preserve TLS hostname
  verification, bound redirects and disallow environment proxy bypass. Streamed
  page/script fetches have size/time limits.
- The login browser has sandbox-on default, a bounded command queue, canceled
  abandoned commands, an authenticated HTTPS-only egress proxy, private-address
  checks and bounded tunnels. Failed starts and shutdown clean up browser resources.
- SIGTERM/SIGINT cancellation and bounded shutdown; exclusive CLI/service locks;
  atomic fsynced state files, private backups, schema/version checks and a durable
  multi-file roll-forward journal. Completion receipts protect the file rename to
  manifest window. Video contents and the containing directory are synced
  before completion is recorded. Credentials and their recovery copies are removed on forgetting.
- Server-side lazy group pagination (50 rows/project, five groups/page), cached
  queue summaries, queue/file/disk limits and download deadlines. Transient-only retries honor
  Retry-After without shortening waits above the bounded retry budget.
- Pinned Python base digest, hash-locked Python dependencies, non-root runtime,
  Docker health check, Compose configuration, SBOM/scanner tooling and CI validation
  with pinned actions and read-only repository permissions. OS/browser repository
  inputs remain mutable; builds are not claimed to be bit-for-bit reproducible.
- MIT, security/contribution policies, changelog, third-party notices, original
  icon, CA profile, candidate metadata generator, admin/release/rollback guides,
  source bundle integrity and private-data exclusion checks.

## Validation evidence

- 103 Python regression tests pass in both the workspace and the final Python
  3.12 image. Source hashes match the checkout and the image exports intact.
  Container health, authenticated APIs, clean stop/restart and persisted access
  cookies pass as UID 99 and with an explicit UID/GID 1000 override. They include HTTP/auth, DNS/redirect rejection, limits,
  corruption/journal/receipt recovery, process locks and shutdown fixtures.
- JavaScript syntax, polling, UI state, progress, exclusion-filter and action
  feedback checks pass. Real Chromium fixture checks cover unlock, grouped server
  pagination, row details, filters, URL editing, settings, exclusion and reload. Keyboard dialog use, unique DOM IDs and a
  390-pixel mobile overflow check pass; a navigation overflow found by that check
  was fixed.
- A 50,000-row synthetic queue produced roughly 9 KB grouped status responses and
  about 4 ms average snapshot time locally. A one-minute fixture soak sampled
  about 61 MB RSS with less than 1 MB growth. These are provisional local readings,
  not throughput guarantees, a multi-day soak or NAS filesystem certification.
- Sandboxed Chromium launches as UID 99 with ordinary engine defaults on this
  Linux/Podman host. The same test FAILS with cap-drop ALL and no-new-privileges.
  The Compose configuration retains these protections and supports session import;
  embedded login under hardened settings remains blocked. No privileged/unconfined
  workaround or automatic sandbox disabling was added. This does not certify
  unRAID's host security configuration.
- Offline distribution metadata and source-bundle checks pass. They do not imply
  Community Applications acceptance or authenticate a future public publisher.

The final image is `547b0b39db2621471bae0e433e6f36d47f9d0e32b12ac0066a5da3c14ec3500f`.
Its exported-image SBOM has 4,185 components. Grype reports **1 critical and 87 high
findings** after available OS updates, down from 89 high initially. No remaining
high/critical match lists an available fix. The critical finding is libxml2
CVE-2026-6653, reported as wont-fix by the scanner's Debian data. Findings require
component/reachability review and remediation or individually justified decisions;
no blanket waiver is configured. The vulnerability gate FAILS.

See VALIDATION_REPORT.md and ignored local artifacts/validation-summary.json,
final-sbom.cdx.json, final-vulnerabilities.json and image-tests.txt. The sandbox
failure at the end of image-tests.txt is a separate host compatibility gate;
its preceding 103 unit tests, UI fixture and benchmark pass.

## Remaining release gates

1. Resolve hardened embedded-browser compatibility without broad privileges.
   Review the exact final-image SBOM and vulnerability report; resolve or explicitly
   assess every high/critical finding. CI deliberately fails on these findings;
   no blanket suppression is configured.
2. Run clean-host unRAID install, update, interrupted update, backup restore and
   rollback against synthetic/redacted existing data. Validate intended filesystem
   lock/fsync behavior, low disk handling and a representative multi-day soak.
3. Review keyboard/mobile accessibility and real website session workflows. The
   tests do not use the owner's account or download media.
4. Create the actual repository and registry namespace, establish support/private
   security reporting, scan repository history and image layers for secrets, then
   configure anonymous pull tests, signing/registry attestations and release policy.
5. Perform live CA Validate/Scan and platform review. Validate optional Tailscale
   integration on unRAID before advertising it. Only amd64 has been exercised.
6. Approve a stable release separately. That work was explicitly deferred.

## Updating existing private installations

Preserve /config and /downloads. Back up the complete appdata and manifest before
upgrading; recovery files contain secrets. Stop the prior service and allow 75
seconds. Rebuild/recreate the container with its existing mappings. Unlock once
after upgrading because interface tokens changed. Do not run old and new services
against the same data or downgrade state in place. See ADMIN_GUIDE.md for rollback.
