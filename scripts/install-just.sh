#!/bin/sh
set -eu

if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]; then
    echo 'Install just 1.59.0 for your platform from https://just.systems/.' >&2
    exit 1
fi
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
download_dir=$(mktemp -d)
trap 'rm -rf "$download_dir"' EXIT HUP INT TERM
archive=just-1.59.0-x86_64-unknown-linux-musl.tar.gz
url=https://github.com/casey/just/releases/download/1.59.0/$archive
curl --fail --location --silent --show-error --max-time 60 \
    "$url" --output "$download_dir/$archive"
expected=409044617b6f06517c1035e55ca38c8c856ff8b650e41bc2aa1ef82d5903a23e
(
    cd "$download_dir"
    printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status
)
mkdir -p "$project_root/.tools/bin"
tar -xzf "$download_dir/$archive" -C "$project_root/.tools/bin" just
"$project_root/.tools/bin/just" --version
