# Distribution readiness audit

Date: 2026-11-09. Scope: current workspace source, Dockerfile, unRAID template/installer, release packaging, tests, and current upstream distribution guidance. No application code changed or images published during this audit.

## Verdict

Suitable for continued private beta on a trusted network. Not yet ready to advertise as production-ready, expose directly to the internet, or submit as a supported stable public release. Publishing a container and obtaining an app-store listing are separate from operational/security readiness; neither is a certification of the application.

The application does not need a complete rewrite. Preserve the parser, downloader, UI, and regression tests. Harden the service boundary, persistence/lifecycle, resource limits, and release pipeline first.

## Evidence and limits

- All 75 Python regression tests pass in this workspace. JavaScript syntax, polling, UI state, start-button progress, and project-filter checks pass.
- Local test interpreter reports Python 3.15.2; the image specifies Python 3.12. Tests therefore do not establish release-image compatibility. CI must test the actual supported container runtime.
- No fresh container build/pull, image vulnerability scan, SBOM generation, penetration test, ARM hardware test, load/soak test, or clean unRAID installation/upgrade was performed in this audit. Previous development smoke tests and user reports are useful, but do not replace release validation.
- Existing protections: non-root UID/GID 99:100, nonprivileged template, restricted build context, owner-only state writes, scoped Hi10 cookies, signed expiring app cookies, origin/JSON checks, CSP and no-store headers, path/symlink checks, temporary downloads, checksum manifests, queue cancellation, and private-URL redaction in status responses.

## Release blockers

### P1 — Production HTTP service and authentication boundary

Evidence: `src/hi10_downloader/web.py:778` and `:818`, `src/hi10_downloader/runtime.py:68`.

The service uses ThreadingHTTPServer. Python explicitly advises against using http.server in production. A one-second sleep on incorrect passwords is not an attempt limiter; parallel requests bypass its intended slowdown. Request bodies get a timeout after headers are parsed, but there is no service-level connection/thread cap. Cookies have HttpOnly/SameSite but no configurable Secure flag, and the service has no explicit trusted-proxy/TLS configuration. Lock clears the browser cookie but does not revoke a copied token server-side.

Required: move request handling to a maintained production WSGI/ASGI stack, keeping a single background-job owner; add connection/body/time limits, login throttling, clear reverse-proxy trust settings, HTTPS-aware cookies, and revocable sessions. Do not start one independent scheduler/download manager per web worker. Retain LAN/Tailnet deployment as the documented default.

Acceptance: concurrency/rate-limit tests; logout/revocation tests; HTTPS proxy tests; single scheduler under the supported deployment; malformed-request tests without uncaught handlers or secret logging.

### P1 — Outbound URL and browser isolation

Evidence: `src/hi10_downloader/cli.py:28`, `:120`; `src/hi10_downloader/sources.py:13`; `src/hi10_downloader/web.py` edit-url handler; `src/hi10_downloader/browser.py:57`.

Download URLs may be supplied by the website or edited by authenticated users. HTTP(S) validation permits localhost, LAN, link-local, and metadata endpoints; redirects are followed automatically. Source hostname checks do not validate each redirect destination. This creates a server-side request risk if an authorized user or upstream page supplies an unsafe target. The login browser checks its current hostname before actions, which is not an outbound network policy for navigation/subresources.

Required: define an explicit egress policy; block nonpublic targets by default with narrowly configured exceptions if needed, validate DNS results and every redirect, and test IPv4/IPv6/rebinding behavior. Verify Chromium sandboxing and document the actual container capabilities/seccomp requirements. Limit browser command queues and expire abandoned commands rather than executing them after callers time out.

Acceptance: private-address/redirect tests, cookie-leakage tests across redirect hosts, browser isolation smoke test in the final image. URL edits must retain useful functionality for supported public mirrors.

### P1 — Graceful stop and recoverable persistence

Evidence: `src/hi10_downloader/web.py:818`, `src/hi10_downloader/cli.py:16`, `src/hi10_downloader/runtime.py:19`.

There is no explicit SIGTERM handler for Docker stop. Workers are daemon threads; setting cancellation flags does not join and drain them. JSON files are replaced atomically individually, but writes do not fsync, there is no cross-file transaction or exclusive process lock, and several startup reads are unguarded json.loads. Corrupt queue/library/schedule state can prevent startup. Two app/CLI processes sharing output can collide on temporary files and manifests.

Required: SIGTERM/SIGINT lifecycle, bounded worker/browser shutdown, process locking, validated/versioned state migrations, last-known-good backups and recovery. Introduce durable transactions, using SQLite if beneficial; a database is an option, not automatically a requirement. Address queue/index/manifest consistency and interrupted rename/manifest writes.

Acceptance: stop/restart during scan/download/save/migration; forced-kill recovery; corrupt/truncated state; concurrent-process rejection; upgrade and restore tests. Preserve videos and explain ambiguous recovery cases.

### P1 — Bounded resources

Evidence: `src/hi10_downloader/web.py:288`, `src/hi10_downloader/cli.py:47`, `:120`; `src/hi10_downloader/sources.py:26`.

Grouped status responses include all file metadata for five projects. Inner 50-file pagination limits DOM rendering, but not server payload size. Every poll regroups filtered queue entries under the application lock. Source response size limits run after responses are already buffered. Downloads have no configured maximum size/free-space guard, and a 60-second HTTP timeout is not a total-operation deadline against a continuously streaming peer.

Required: server-side item pagination/lazy group detail, cached aggregate counts/deltas, streamed bounded HTML fetches, disk/free-space and queue limits, explicit cancellation/deadline behavior, and realistic resource budgets.

Acceptance: measured CPU/RSS/status latency/payload size for a large queue, a single very large project, multiple tabs, slow mirrors, and low disk space. Start with measurable provisional targets and publish minimum hardware guidance after measurement.

### P1 — Reproducible, traceable public releases

Evidence: `Dockerfile:1`, `pyproject.toml:1`, `unraid/install.sh:26`, `unraid/package.py:1`.

Current installation rebuilds a local image on the user's server. The base tag is mutable; dependencies use ranges without a locked resolution. There is no visible CI publishing workflow, image health check, release signing/attestation, SBOM or vulnerability gate. Version remains 0.2.0 while the HTTP user agent says 0.1. SHA256SUMS detects accidental source corruption; it does not independently authenticate the publisher.

Required: public source repository, automated tests/builds, pinned dependency resolution and base digest with an update process, version/changelog discipline, OCI metadata, release tags/digests, public registry publishing, image scan/SBOM/provenance and verification instructions. Add /healthz and a lightweight health check separate from remote Hi10/session availability. Start with tested linux/amd64; advertise ARM only after Chromium and downloader validation on that platform.

Acceptance: fresh anonymous pull on a clean host; test the exact published digest as UID 99:100; known-good rollback instructions; no credentials/downloads/runtime state in any image layer or release artifact.

### P1 — Licensing and unRAID submission package

Evidence: no LICENSE, ca_profile.xml, CI workflow or support-policy files found in the inspected project tree. `unraid/hi10-downloader.xml:3` points to hi10-downloader:local and lacks public support/project/icon metadata.

Required: choose a license deliberately and verify ownership/dependency redistribution notices; public source and support destination; maintained unRAID template using a pullable registry image; repository profile, icon and appropriate project/support metadata. Run the current CA Validate/Scan flow. Do not include this workspace's live appdata, sessions, sample download URLs or videos. Review historical commits/artifacts as well as the current build context before publication.

The current CA submission help explicitly lists a public active repository, OSI-approved root LICENSE, ca_profile.xml with a nonempty Profile, valid template/plugin XML, and validation/scanning. These are platform requirements; acceptance remains subject to platform review. Do not assume CA listing approves third-party content or trademarks. Document intended authorized use and affiliation accurately.

## Important improvements before stable release

- **Operational diagnostics:** stop printing the generated password on every startup (`web.py:97`); use a documented first-run/retrieval flow. Add structured redacted logs, stable error codes, request/job IDs, runtime/version/build information, readiness and a private diagnostics export. Preserve useful errors without URL/header/cookie secrets. Avoid silent generic catches that make field failures difficult to investigate.
- **Container portability:** UID/GID 99:100 is an unRAID assumption. Support documented configurable identity/permissions or explicit --user usage, fail clearly on unwritable mounts, and test NAS/NFS/SMB behavior. Document --init/shared-memory requirements, restart policy and Compose installation. Prefer a lean browser-optional image variant later if measurement shows worthwhile savings.
- **Tailscale:** optional compatibility work, not a prerequisite for distribution. Current USER 99:100 cannot be assumed compatible with unRAID's dependency-installing hook. Test hook startup, controlled privilege drop, persistent /config state, and both Tailscale-enabled and normal launches before claiming support. Do not silently switch the whole app to root.
- **External service resilience:** document source/mirror limitations, detect changed markup and session expiry distinctly, respect Retry-After where applicable, classify retryable errors, and keep a bounded retry policy. Add fixtures for changed upstream data and expired links; do not add CAPTCHA bypass behavior.
- **Download integrity/recovery:** test truncated/chunked responses, full disk, failed cleanup, checksum mismatch, large files, Unicode/path collisions and changed mirror URLs for an existing file. Byte-range resume is a useful later feature, not a stable-release prerequisite if restart behavior is explicit.
- **UI maintenance/testing:** split growing inline/minified HTML/CSS and monolithic JS into maintained modules/components without requiring a redesign. Add real browser end-to-end tests for grouped queues, nested pagination, bulk selection, URL edits, exclusions, scheduling, restart progress and dialogs. The current JS tests evaluate extracted snippets rather than the full rendered application. Add keyboard/accessibility checks.
- **Documentation/support:** replace accumulated update notes with a clean install/admin guide, upgrade/rollback matrix, changelog, SECURITY.md, issue templates and contribution guidance. Remove user-specific IPs and reconcile stale claims about what has/has not been validated on unRAID. Make supported versions/platforms and maintenance ownership explicit.

## Recommended release sequence and gates

1. **Private beta hardening:** resolve service/auth, egress, shutdown/state recovery and bounded-resource blockers. Keep feature scope stable.
2. **Public beta image:** license/source hygiene; reproducible CI; tested amd64 image; Compose guide; GHCR public package; health check, SBOM/scan/provenance; versioned releases and rollback. Label beta and document deployment boundaries.
3. **unRAID candidate:** complete XML/profile/support/icon metadata; clean-server install, upgrade from existing appdata, failed-upgrade recovery, restart and permissions tests. Test Tailscale separately if advertised. Submit through CA Validate/Scan only after these pass.
4. **Stable 1.0:** close blocker findings with evidence, complete a multi-day representative soak, verify backup restoration, and establish a dependency/security update and support process. A listing or passing unit suite alone does not meet this gate.

Suggested effort: plan several focused hardening milestones rather than a Dockerfile-only change. Exact calendar time depends on scope, deployment/security decisions and access to test hardware; this audit does not establish an engineering estimate.

## Current primary references

- [Python http.server production warning](https://docs.python.org/3.12/library/http.server.html)
- [Docker image-building best practices](https://docs.docker.com/build/building/best-practices/)
- [GitHub Container registry: anonymous access and repository linking](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub Packages billing: public packages and current container-registry pricing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
- [unRAID Community Apps submission requirements](https://ca.unraid.net/submit/help)
- [unRAID Tailscale integration](https://docs.unraid.net/unraid-os/system-administration/secure-your-server/tailscale/)

Recommended registry: public GHCR. Public images support anonymous pulls and current GitHub documentation makes public packages free; container storage/bandwidth is currently free. This does not promise unlimited free CI minutes, artifacts, private packages or an unchanged future pricing policy. Use ghcr.io/<owner>/hi10-downloader:<version>, plus an explicitly managed stable channel, after owner/repository naming is decided.
