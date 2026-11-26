#!/bin/sh
# Pull the versioned beta image and register its unRAID template. Does not start downloads.
set -eu
hi10_build_local=false
case "${1:-}" in
    --build-local) hi10_build_local=true ;;
    --help) printf '%s\n' 'Usage: sh install.sh [--build-local]' 'Default: pull the versioned beta from GHCR. --build-local builds this source bundle instead.'; exit 0 ;;
    '') ;;
    *) printf '%s\n' 'Unknown option. Use --help.' >&2; exit 1 ;;
esac
hi10_image=ghcr.io/chard1988/hi10anime-downloader:0.3.0-beta.3

if [ ! -f /etc/unraid-version ]; then
    printf '%s\n' 'Run this script in the unRAID Terminal, not on your desktop.' >&2
    exit 1
fi
if [ "$(id -u)" != '0' ]; then
    printf '%s\n' 'Run this script as root in the unRAID Terminal.' >&2
    exit 1
fi
if [ "$(uname -m)" != 'x86_64' ]; then
    printf '%s\n' 'This test bundle targets an x86-64 unRAID server.' >&2
    exit 1
fi
command -v docker >/dev/null
cd "$(dirname "$0")"
printf '%s\n' 'Verifying bundle checksums...'
sha256sum -c SHA256SUMS
if [ ! -f Dockerfile ]; then
    printf '%s\n' 'Bundle is incomplete. Run the installer from the extracted hi10-unraid bundle.' >&2
    exit 1
fi
if [ "$hi10_build_local" = true ]; then
    printf '%s\n' 'Building from source. The result may differ from the published image digest.'
    docker build --pull -t "$hi10_image" .
else
    printf '%s\n' "Pulling $hi10_image..."
    if ! docker pull "$hi10_image"; then
        printf '%s\n' 'Image pull failed. Verify network access and that the GitHub package visibility is Public.' 'See docs/UNRAID_INSTALL.md. You may explicitly build this source with --build-local.' >&2
        exit 1
    fi
fi

hi10_template_dir=/boot/config/plugins/dockerMan/templates-user
hi10_template_path="$hi10_template_dir/my-hi10-downloader.xml"
mkdir -p "$hi10_template_dir"
if [ -e "$hi10_template_path" ]; then
    printf '%s\n' "Kept your existing template: $hi10_template_path"
else
    cp hi10-downloader.xml "$hi10_template_path"
    printf '%s\n' "Installed template: $hi10_template_path"
fi

for hi10_folder in /mnt/user/appdata/hi10-downloader /mnt/user/downloads/hi10anime; do
    if [ ! -d "$hi10_folder" ]; then
        mkdir -p "$hi10_folder"
        chown 99:100 "$hi10_folder"
        chmod 750 "$hi10_folder"
    fi
done

printf '%s\n' \
    'Image and template installed. No app container or downloads have been started.' \
    'Open Docker -> Add Container and select hi10-downloader.' \
    'Set an app password, download location, appdata location, and an unused web port.' \
    'Both mapped folders must be writable by UID 99 / GID 100.' \
    'Click Apply, then use the container WebUI action.' \
    "For an existing installation, keep its mappings and change Repository to $hi10_image." \
    'Import a session from the browser exporter; hardened embedded login remains a beta limitation.'
