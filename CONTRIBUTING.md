# Contributing

Use synthetic HTML/download fixtures. Never commit appdata, session JSON, signed
URLs, credentials, videos, or real account identifiers. Keep the restricted Docker
build context and test the exact container image before proposing a release.

Run Python unit tests, the JavaScript checks, the browser fixture, and the queue
benchmark as documented in docs/ADMIN_GUIDE.md. Changes to HTTPX/httpcore require
network-policy tests because the pinned backend adapter controls DNS pinning.

Update CHANGELOG.md and migration/recovery notes for state changes. Regenerate
requirements.lock under Python 3.12 using pip-tools, review its diff, and scan the
resulting image. Verify any action/scanner/base-image hash changes against the
upstream source. Keep publishing manual and disabled until repository ownership
and distribution gates are configured. Use small, reviewable pull requests.

Branch and release conventions are documented in [Git-flow and versioning](docs/VERSIONING.md).
