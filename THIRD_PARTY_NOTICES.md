# Third-party software notices

The MIT license in this repository applies to this project's original code. It
does not replace the licenses of bundled third-party components or grant rights to
website content, artwork, trademarks, or downloaded media.

The image includes the Python base distribution, Debian packages, Playwright and
its downloaded Chromium/FFmpeg components, and the Python packages in
requirements.lock. Preserve their installed license files and notices when
redistributing the image. Chromium carries multiple third-party notices, not one
project-wide license. Debian package copyright files are retained under
/usr/share/doc; Python package licenses are retained in installed distributions.

The generated CycloneDX SBOM inventories the exact built image, including detected
licenses. Review it, the upstream dependency notices and vulnerability report before
publication; automated license detection can be incomplete. No copyrighted media,
account/session data, or upstream website artwork should be added to release
artifacts. The repository's icon.svg is an original simple vector icon.

Pinned audit tools Syft and Grype are developer/CI tools downloaded separately from
their official Anchore releases and are not copied into the runtime image. Their
upstream license files are available in their release archives/repositories.


## React frontend migration

The frontend uses React/React DOM (MIT), Vite (MIT), Tailwind CSS (MIT),
shadcn/ui source components and dashboard-01/login-01 blocks (MIT), Base UI (MIT),
TanStack Table (MIT), Lucide icons (ISC), and the Inter font (SIL OFL 1.1).
Exact versions and transitive dependencies/integrities are recorded in
frontend/pnpm-lock.yaml. Upstream license files are available in their packages.
The Velocity theme was applied from the owner-provided tweakcn registry URL;
its public registry payload and provenance are recorded in frontend/theme-registry.json
and docs/FRONTEND.md. Runtime assets are served locally; no font CDN is contacted.
