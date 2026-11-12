#!/bin/sh
# Internal executor: caller must first verify merged PR metadata and origin.
# An explicit SHA lease protects commits added after the metadata snapshot.
set -eu
[ "$#" -eq 3 ] || exit 2
branch=$1
expected=$2
default_branch=$3
case "$branch" in main|dev|develop|master) exit 2 ;; esac
[ "$branch" != "$default_branch" ] || exit 2
[ "${#expected}" -eq 40 ] || exit 2
case "$expected" in *[!a-f0-9]*) exit 2 ;; esac
git check-ref-format "refs/heads/$branch" >/dev/null
log=$(mktemp)
trap 'rm -f "$log"' EXIT HUP INT TERM
if git push \
    --force-with-lease="refs/heads/$branch:$expected" -- origin ":refs/heads/$branch" >"$log" 2>&1; then
    printf '{"status":"deleted"}\n'
else
    printf '{"status":"retained","reason":"delete_rejected"}\n'
    exit 1
fi
