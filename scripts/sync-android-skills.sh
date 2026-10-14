#!/usr/bin/env bash
# Keep the Android skills in .claude/skills/ in step with the official repo (scripts/android-skills.lock lists them).
#   scripts/sync-android-skills.sh check   report skills that differ from upstream main (exit 1 if any); changes nothing
#   scripts/sync-android-skills.sh sync    copy the listed skills from upstream main and pin the lock to that commit
#   scripts/sync-android-skills.sh sync --pinned   copy at the commit in the lock (reproduce the current state)
set -euo pipefail
cd "$(dirname "$0")/.."
LOCK=scripts/android-skills.lock
mode=${1:-check}; pinned=${2:-}
repo=$(awk '$1=="repo"{print $2}' "$LOCK"); pin=$(awk '$1=="commit"{print $2}' "$LOCK")
paths=$(grep -vE '^(#|repo |commit |$)' "$LOCK")
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
git clone -q --filter=blob:none --no-checkout "$repo" "$tmp/up"
ref=origin/HEAD; [ "$pinned" = "--pinned" ] && ref=$pin
git -C "$tmp/up" sparse-checkout init --no-cone >/dev/null
printf '%s\n' "/LICENSE.txt" $(for p in $paths; do echo "/$p/"; done) | git -C "$tmp/up" sparse-checkout set --no-cone --stdin
git -C "$tmp/up" checkout -q "$ref" 2>/dev/null || git -C "$tmp/up" checkout -q --detach "$ref"
head=$(git -C "$tmp/up" rev-parse HEAD)
changed=0
for p in $paths; do
  name=$(basename "$p"); dest=.claude/skills/$name
  rm -rf "$tmp/want"; cp -R "$tmp/up/$p" "$tmp/want"; cp "$tmp/up/LICENSE.txt" "$tmp/want/LICENSE.txt"
  if [ ! -d "$dest" ] || ! diff -rq "$tmp/want" "$dest" >/dev/null; then
    changed=$((changed+1)); echo "differs: $name  ($p)"
    [ "$mode" = sync ] && { rm -rf "$dest"; cp -R "$tmp/want" "$dest"; echo "  updated"; }
  fi
done
if [ "$mode" = sync ]; then
  sed "s/^commit .*/commit $head/" "$LOCK" > "$tmp/lock" && cp "$tmp/lock" "$LOCK"
  echo "synced $(echo "$paths" | wc -l | tr -d ' ') skills at ${head:0:7} ($changed changed). Review: git diff --stat .claude/skills"
else
  echo "$changed skill(s) differ from upstream ${head:0:7} (pinned ${pin:0:7})"; [ "$changed" = 0 ]
fi
