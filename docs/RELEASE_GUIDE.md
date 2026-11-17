# Beta publishing and stable-release gates

## Current authorization and scope

The owner approved publishing a versioned testing beta on 2026-11-17, with disclosed
security findings and hardened-browser compatibility limits. The actual source is
https://github.com/chard1988/hi10anime-downloader and the registry namespace is
`ghcr.io/chard1988/hi10anime-downloader`. Stable/latest publishing and CA submission
remain disabled. Historical audit reports describe their dated earlier snapshots.

## Git-flow release procedure

1. Start `git flow release start 0.3.0-beta.2` from develop.
2. Align pyproject/__version__ (`0.3.0b2`), Docker metadata (`0.3.0-beta.2`),
   changelog, release notes, template, Compose and installer. release_metadata.py
   rejects mismatched refs and all stable versions.
3. Push the release branch. release-beta.yml builds and tests it without publishing.
   Repair failures on that branch. No write token is supplied to build/test scripts.
4. After candidate checks pass, finish the git-flow release with an annotated tag,
   merge back into develop, and push master/develop/tag atomically. The tag triggers
   the same build/test pipeline, then publishes the exact tested image and creates
   a GitHub prerelease with allowlisted assets. It refuses an existing version.
5. Set the new GHCR package Public once in Package settings. Anonymous pull and
   actual unRAID install/upgrade remain owner/hardware checks until verified.

The beta workflow only handles matching vMAJOR.MINOR.PATCH-beta.N tags, never
stable/latest tags. Its contents/package write permissions are used only for the
trusted repository's release job; credentials are exposed only to publishing
steps. It does not run on pull requests. Normal validation retains strict security
and sandbox gates for stable-readiness checks. A passing beta job is not a claim
that those stable gates passed.

## Exact-image evidence and explicit beta exceptions

All Python, JavaScript, browser, extension, lifecycle/restart and resource checks
must pass. SBOM/scanner failures, incomplete reports and unexpected browser failures
block publication. The beta audit allows only the explicitly disclosed sandbox
compatibility failure and completed scans with reported high/critical findings.
It records these as failed stable gates in beta-validation.json, without ignores.
Only the explicit testing prerelease path accepts this policy; no stable waiver is
created. Review every match for reachability/remediation before a stable release.

The image pins its Python base and uses a hash-locked dependency resolution. OS
packages and Playwright browser downloads still depend on upstream repositories;
this is not bit-for-bit reproducibility. SBOM and build metadata are attached to
the release. They are not signed publisher attestations. Exact image digests and
checksums support installation/rollback but do not replace signing or license review.

The image is pushed with its immutable-by-policy version tag and the mutable beta
channel. Do not move a published version tag. Partial publication must be inspected;
publish a new beta version rather than silently overwriting a released image.
GitHub's Actions GITHUB_TOKEN handles registry/release authentication. No owner PAT
is committed or needed for public pulls.

## Before stable/public production claims

- Resolve or individually assess every high/critical finding with component,
  reachability, compensating control, owner and expiry; no blanket ignores.
- Resolve embedded-browser support without broad privileges or advertise only the
  verified import path with appropriate UI behavior.
- Validate real unRAID install, upgrade/interrupted upgrade, backup restore and
  rollback against redacted data, plus filesystem lock/fsync and a multi-day soak.
- Verify anonymous published-digest pulls and intended platform behavior. Only
  Linux/amd64 is tested; do not claim ARM or Tailscale-hook support.
- Review dependency notices/licenses, source/history/image-layer secrets, keyboard
  and mobile accessibility, and real account/session flows.
- Enable verified private vulnerability reporting, define support ownership,
  configure registry signing/attestations, and complete CA Validate/Scan externally.

Audit tool versions/hashes are in tools.lock.json. Review upstream changes before
refreshing them. Regenerate Python locks under Python 3.12 and test the resulting
exact image. No credential/session/download folders belong in artifacts or history.
