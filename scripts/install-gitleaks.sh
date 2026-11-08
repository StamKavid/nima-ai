#!/bin/sh
set -eu

if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]; then
    echo 'Install gitleaks 8.30.1 for your platform and set GITLEAKS to its executable.' >&2
    exit 1
fi

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
download_dir=$(mktemp -d)
trap 'rm -rf "$download_dir"' EXIT HUP INT TERM
archive=gitleaks_8.30.1_linux_x64.tar.gz
url=https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/$archive

curl --fail --location --silent --show-error --max-time 60 \
    "$url" --output "$download_dir/$archive"
expected=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
(
    cd "$download_dir"
    printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status
)
mkdir -p "$project_root/.tools/bin"
tar -xzf "$download_dir/$archive" -C "$project_root/.tools/bin" gitleaks
"$project_root/.tools/bin/gitleaks" version
