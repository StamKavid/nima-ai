#!/bin/sh
# Read-only by default; set NIMA_CLEANUP_APPLY=1 to apply the reviewed plan.
set -eu
repository=${GITHUB_REPOSITORY:?Set GITHUB_REPOSITORY to owner/repo}
origin=$(git remote get-url origin)
case "$origin" in
    "https://github.com/$repository"|"https://github.com/$repository.git") ;;
    *) echo 'Origin does not match the requested GitHub repository.' >&2; exit 2 ;;
esac
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
metadata=$(mktemp -d)
trap 'rm -rf "$metadata"' EXIT HUP INT TERM
gh api --hostname github.com "repos/$repository" \
    --jq '{full_name,default_branch}' > "$metadata/repository.json"
gh api --hostname github.com --paginate "repos/$repository/branches?per_page=100" \
    --jq '[.[]|{name,protected,commit:{sha:.commit.sha}}]' > "$metadata/branches.json"
for state in closed open; do
    gh api --hostname github.com --paginate "repos/$repository/pulls?state=$state&per_page=100" \
        --jq '[.[]|{number,merged_at,head:{ref:.head.ref,sha:.head.sha,repo:{full_name:.head.repo.full_name}},base:{ref:.base.ref,repo:{full_name:.base.repo.full_name}}}]' \
        > "$metadata/$state.json"
done
python3 "$root/scripts/branch_cleanup.py" --repository "$metadata/repository.json" \
    --branches "$metadata/branches.json" --closed "$metadata/closed.json" --open "$metadata/open.json" \
    > "$metadata/plan.json"
cat "$metadata/plan.json"
[ "${NIMA_CLEANUP_APPLY:-0}" = 1 ] || exit 0
default_branch=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["default_branch"])' "$metadata/repository.json")
python3 -c 'import json,sys; [print(p["branch"]+" "+p["sha"]) for p in json.load(open(sys.argv[1]))["delete"]]' \
    "$metadata/plan.json" > "$metadata/refs"
while IFS=' ' read -r branch expected; do
    sh "$root/scripts/delete-merged-ref.sh" "$branch" "$expected" "$default_branch"
done < "$metadata/refs"
