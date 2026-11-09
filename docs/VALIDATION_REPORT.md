# Local beta validation — 2026-11-09

Status: **engineering candidate; not cleared for public distribution**.
MIT is selected. No GitHub repository, registry publication, CA submission or
stable release was created.

## Tested image

- Linux/amd64, Python 3.12, non-root UID 99/GID 100.
- Image ID: `547b0b39db2621471bae0e433e6f36d47f9d0e32b12ac0066a5da3c14ec3500f`.
- Built from the Dockerfile with pinned base/hash-locked Python inputs and available
  OS updates. Image source hashes match the checkout; Docker archive export passed.
- Local evidence: ignored `artifacts/validation-summary.json`, image-metadata.json,
  image-source-hashes.json and image.tar. These are local records, not signed
  publisher attestations or a public registry digest.

## Passing checks

- 103 Python regression tests in the exact image and workspace.
- JavaScript syntax, polling, UI state, exclusion filter, progress and action feedback.
- Real Chromium UI fixture: unlock, grouped lazy pagination, details, filters, URL
  repair, settings, project exclusion, persisted unlock, keyboard dialog operation,
  unique DOM IDs and 390-pixel mobile overflow. A navigation overflow was corrected.
- Container health declaration/endpoint, authenticated API, clean SIGTERM stop,
  restart and access-cookie persistence as both UID 99 and UID/GID 1000.
- 50,000-entry fixture: 50 visible rows, 9,091-byte response, 3.087 ms mean snapshot,
  53,640 KiB sampled RSS inside this image. A one-minute workspace soak showed
  884 KiB sampled growth. These are local synthetic measurements, not hardware
  requirements, network throughput promises or a multi-day NAS soak.
- Offline source metadata and source bundle path/checksum/private-state exclusions.

The initial five-second async test wait timed out during simultaneous large image
I/O. The harness now allows 30 seconds; the exact-image rerun passes all 103 tests.
No application timeout was relaxed for this test.

## Failed gates

1. **Vulnerability scan:** 1 critical, 87 high, 147 medium, 25 low and 138 negligible
   matches in the final exported-image SBOM (4,185 components). Available zlib
   updates removed two high findings. No remaining high/critical match lists an
   available fix. libxml2 CVE-2026-6653 is reported critical/wont-fix. Matches are
   scanner findings, not a claim that every path is exploitable. They need reviewed
   component/reachability assessment and remediation or individual documented
   decisions. CI continues to fail at high severity; there are no blanket ignores.
2. **Hardened embedded browser:** sandboxed Chromium launches with ordinary Podman
   defaults but fails with cap-drop ALL/no-new-privileges on this host. A versioned
   upstream seccomp profile experiment did not resolve it and was not retained.
   Security defaults remain intact; session import is the supported tested path in
   this hardened configuration. UnRAID/Docker host compatibility needs resolution.

The scanner rejected a temporary database checksum. A fresh database was downloaded
and verified on persistent disk before the final successful scan execution; that
execution failed the vulnerability threshold, rather than failing database loading.
Full reports are local under artifacts/. CI validation has been prepared but has
not run on GitHub because the repository does not yet exist.

## External work before distribution

Clean unRAID install/update/interrupted upgrade/restore/rollback, actual NAS lock
and fsync behavior, a representative multi-day soak, real account session flows,
manual accessibility review, third-party notices/license review, repository/history
and image-layer secret review, real support/private reporting URLs, anonymous
registry pull/signing/attestations and CA Validate/Scan remain release gates.
Tailscale and ARM support are not advertised as validated. See RELEASE_GUIDE.md.
