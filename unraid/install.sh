#!/bin/sh
# Build the source bundle and register its unRAID template. Does not start downloads.
set -eu

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
printf '%s\n' 'Building a fresh image (requires internet access for Python, Chromium, and OS packages)...'
docker build --pull -t hi10-downloader:local .

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
    'For an existing installation, keep its mappings and recreate it with this local image.'
