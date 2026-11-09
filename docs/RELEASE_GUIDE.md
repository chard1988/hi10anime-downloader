# Candidate validation (no stable release)

## Scope and owner gates

All preparation in this checkout is local. No repository has been created, no
image pushed, no signing identity provisioned, no CA submission finalized, and no
stable release approved. MIT was selected by the owner. Choose the real repository,
registry namespace and support/reporting URLs before public distribution.

## Rebuild and verify

The Dockerfile pins the Python base digest and installs requirements.lock using
--require-hashes. OS packages/Chromium downloads still depend on upstream build
repositories; this is traceable input pinning, not a claim of bit-for-bit builds.
Update base/lock regularly rather than preserving vulnerable dependencies.

Build the candidate, save its immutable image ID/digest, and run the unit suite,
benchmark, browser fixture and lifecycle smoke against that exact image. The
prepared `.github/workflows/validate.yml` does this without publishing. It has
read-only repository permission and hash-pinned actions. Do not use pull_request_target
or pass release credentials to untrusted pull requests.

```
docker build -t hi10-downloader:beta .
docker run --rm --entrypoint python -v "$PWD/tests:/tests:ro" -v "$PWD/unraid:/unraid:ro" hi10-downloader:beta -m unittest discover -s /tests -q
docker run --rm --shm-size=1g --entrypoint python -v "$PWD/tests:/tests:ro" hi10-downloader:beta /tests/e2e.py
python3 scripts/container_smoke.py --image hi10-downloader:beta
python3 scripts/install_audit_tools.py
docker save -o artifacts/image.tar hi10-downloader:beta
.tools/syft docker-archive:artifacts/image.tar -o cyclonedx-json=artifacts/sbom.cdx.json
.tools/grype sbom:artifacts/sbom.cdx.json --fail-on high -o json > artifacts/vulnerabilities.json
```

Create artifacts/ first. Review all scanner findings, including unfixed issues;
CI blocks all high/critical findings. A waiver must name the CVE, affected
component, compensating control, owner and expiry. Do not add blanket ignores.
Scanner outputs, SBOM and build metadata are stored as CI artifacts. Local metadata
is not a signed public attestation. BuildKit provenance is collected in metadata;
registry attestations/signatures will be configured with the actual repository and
publishing identity when authorized. Only advertised/tested architecture is amd64.

Audit tools are official version/hash-locked Syft and Grype downloads. To update,
review upstream releases, run scripts/tool_metadata.py, then
scripts/install_audit_tools.py --refresh-hashes, and review the resulting lock file.
Dependency updates should run pip-compile under Python 3.12 with --allow-unsafe,
--generate-hashes, and --strip-extras, followed by exact-image tests.

## Prepare unRAID metadata

The existing unraid/hi10-downloader.xml remains a local-source template. An original
SVG icon and root ca_profile.xml are ready. To generate public candidate XML files
without publishing:

```
python3 scripts/prepare_distribution.py --repository OWNER/REPO --support https://github.com/OWNER/REPO/issues
```

Generated files go under ignored artifacts/distribution. Replace them only after
the actual destinations exist, image tags pull anonymously, ownership/support text
is reviewed and private vulnerability reporting is enabled. Run Community
Applications Validate/Scan externally before submission. An offline XML check is
not equivalent to CA acceptance. Tailscale hook support is optional and remains
unadvertised until exercised on a real unRAID installation.

## Release-candidate gates before public beta

- Clean-host install and anonymous image pull after the registry exists.
- Upgrade from a redacted/synthetic old appdata snapshot, interrupted upgrade,
  backup restore and rollback to the prior exact image.
- Stop/restart, forced kill, disk full, corrupt state, receipt recovery and auth tests.
- Real-browser workflows and manual keyboard/mobile accessibility review.
- Image scan, SBOM/license notice review, secret scan of source/history/image layers.
- Representative multi-day soak and NAS filesystem tests on the intended hardware.
- No public credentials/media/site artwork in source or artifacts.

Hardware tests, a multi-day soak, a published-image pull, repository history scan,
CA platform review and real Tailscale integration cannot be certified by local
source/unit checks. Record evidence and retain unresolved gates explicitly.
