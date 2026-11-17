# Install Hi10 Download Manager on unRAID

Version: **0.3.0-beta.2**, Linux/amd64, testing prerelease.
Image: `ghcr.io/chard1988/hi10anime-downloader:0.3.0-beta.2`.
Release: https://github.com/chard1988/hi10anime-downloader/releases/tag/v0.3.0-beta.2

This beta has disclosed security findings and embedded-browser compatibility
limitations. Use a private LAN/Tailnet for testing. It is not a stable release,
Community Applications listing, or validated Tailscale-hook integration. The
release includes exact-image test, SBOM and vulnerability reports. Use session
import rather than weakening container protections to make embedded login work.

## One-time publisher step

GitHub initially creates a container package as Private, even with a public source
repository. After the workflow publishes it, the repository owner must open the
`hi10anime-downloader` package's **Package settings → Change visibility → Public**.
Do this for the package, not the source repository (which is already public).
Then unRAID can pull without a GitHub token. A `denied` error at `docker pull` can
mean this step has not been completed. Do not paste tokens into chat or templates.

Package page: https://github.com/chard1988/hi10anime-downloader/pkgs/container/hi10anime-downloader
GitHub reference: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#pushing-container-images

## Updating an existing installation (recommended for current users)

1. Stop download and scan jobs in Hi10, then stop its container in unRAID.
2. Back up the entire existing appdata directory and the download folder's
   `hi10-manifest.json` plus any `.receipt.json` recovery files. These contain
   private state. Record the current image ID with
   `docker inspect --format '{{.Image}}' hi10-downloader` if that is its name.
3. Open **Docker → hi10-downloader → Edit**. Change **Repository** to:

   ```text
   ghcr.io/chard1988/hi10anime-downloader:0.3.0-beta.2
   ```

4. Keep the existing `/config`, `/downloads`, host web port and app password.
   **Do not delete appdata, the manifest or downloaded videos.**
5. In Advanced View, use Extra Parameters:

   ```text
   --init --shm-size=1g --stop-timeout=75 --cap-drop=ALL --security-opt=no-new-privileges
   ```

6. Click **Apply** to pull/recreate. A changed Repository makes Apply available.
   Open WebUI and hard-refresh it. Unlock if requested. Existing session files are
   retained; verify access and re-import if the website session expired.
7. Confirm project/queue state and destination, then test a small selected batch.
   Schedules persist; review any saved scheduled start before restarting.

Do not run old and new containers against the same appdata/download mappings.
For rollback, stop the beta, restore the complete pre-upgrade appdata/manifest
backup, and recreate with the prior exact image. Do not downgrade state in place.

## Fresh install with the template

Open the unRAID Terminal and run as root:

```sh
(
set -eu
mkdir -p /mnt/user/appdata/hi10-install
cd /mnt/user/appdata/hi10-install
curl -fL --retry 3 -o hi10-unraid.tar.gz https://github.com/chard1988/hi10anime-downloader/releases/download/v0.3.0-beta.2/hi10-unraid.tar.gz
curl -fL --retry 3 -o SHA256SUMS https://github.com/chard1988/hi10anime-downloader/releases/download/v0.3.0-beta.2/SHA256SUMS
awk '$2 == "hi10-unraid.tar.gz" {print}' SHA256SUMS | sha256sum -c -
tar -xzf hi10-unraid.tar.gz
cd hi10-unraid
sh install.sh
)
```

The installer verifies source checksums, pulls the image and installs the unRAID
user template. It does not start a container or download media. Existing templates
and existing folder ownership are preserved. It creates only missing default
appdata/download folders with UID 99/GID 100 ownership. Checksums detect corruption;
this beta does not yet provide signed publisher attestations.

Then open **Docker → Add Container**, select **hi10-downloader** from templates,
and configure:

| Field | Value |
| --- | --- |
| Repository | `ghcr.io/chard1988/hi10anime-downloader:0.3.0-beta.2` |
| Network Type | Bridge |
| Privileged | Off |
| Container Web Port | `8080` |
| Host Web Port | `8080`, or another unused port |
| `/config` host path | `/mnt/user/appdata/hi10-downloader` |
| `/downloads` host path | `/mnt/user/downloads/hi10anime`, or your chosen folder |
| `HI10_WEB_PASSWORD` | A unique app password; this is not your Hi10 website password |

Both host folders must be writable by UID 99/GID 100. If using different existing
folders, verify their ownership before Apply; the app does not recursively change
permissions. Leave the optional website credentials empty when using session import.

Click Apply, enable Autostart if desired, and use WebUI. Use `http://YOUR_UNRAID_SERVER:HOST_PORT`, with your server address and chosen
host port. Container state should become Healthy; inspect
Logs if it exits or stays unhealthy. The health check does not verify website access.

UnRAID reference: https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/

## Import your working browser session

Download `hi10-session-export.zip` from the release on your desktop and extract it.
In the browser profile already signed in to Hi10, open `chrome://extensions`,
enable Developer mode and Load unpacked → the extracted `hi10-session-export`
folder. This helper requests cookie access only to Hi10. Click its Save session.json
button, then import that file through the app's **Account & session → Choose session
JSON**. The file contains login credentials; do not share or commit it. You can
remove the helper after exporting. Docker does not need rebuilding for session import.

After connection, refresh projects, scan a small selection, add files to the queue
and click Start selected. Same-quality alternative links are checked at download
time; all-dead alternatives fail without reducing quality. Queueing alone does not
start unscheduled downloads. Closing the browser does not stop server-side downloads.

## Manual fallback and troubleshooting

If the template is not installed, Add Container manually using the table above,
plus WebUI `http://[IP]:[PORT:8080]/` and the Extra Parameters above. This app is not
yet searchable as an accepted Community Applications listing.

- Pull denied: check package Public visibility and the exact image/version.
- Port allocated: choose a free host port; keep container port 8080.
- Permission error: verify both host mappings are writable by 99:100.
- Sandbox login failure: use session import; do not enable Privileged or disable
  sandboxing globally. The beta release records this host-compatibility gate.
- Restoring data: allow startup to finish and inspect Logs before restarting again.
- Source build for explicit local testing: inside the verified source bundle use
  `sh install.sh --build-local`. It requires internet access and may not reproduce
  the published digest; it is not the normal registry installation path.

Use the fixed version for repeatable installs. `:beta` follows future betas;
`:latest` and `:stable` are deliberately not published. To pin a tested build more
strictly, use the `ghcr.io/...@sha256:...` reference in the release's image-digest.txt.
