#!/usr/bin/env bash
# Copy the Apple skills listed in scripts/xcode-skills.list from the installed Xcode into .claude/skills/ (git-ignored).
#   scripts/sync-xcode-skills.sh [check]   list skills that are missing or differ from this Xcode; changes nothing
#   scripts/sync-xcode-skills.sh sync      export and copy them
set -euo pipefail
cd "$(dirname "$0")/.."
mode=${1:-check}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
xcrun agent skills export "$tmp" >/dev/null 2>&1 || { echo "needs Xcode 27+ (xcrun agent skills export failed)"; exit 2; }
changed=0
# Xcode's export writes the SKILL.md frontmatter keys in a different order each run, so compare SKILL.md ignoring line order.
same() { diff -rq -x SKILL.md "$1" "$2" >/dev/null && [ "$(sort "$1/SKILL.md")" = "$(sort "$2/SKILL.md")" ]; }
for name in $(grep -vE '^(#|$)' scripts/xcode-skills.list); do
  [ -d "$tmp/$name" ] || { echo "not in this Xcode: $name"; continue; }
  if [ ! -d ".claude/skills/$name" ] || ! same "$tmp/$name" ".claude/skills/$name"; then
    changed=$((changed+1)); echo "differs: $name"
    [ "$mode" = sync ] && { rm -rf ".claude/skills/$name"; cp -R "$tmp/$name" ".claude/skills/$name"; echo "  updated"; }
  fi
done
echo "$changed skill(s) differ from $(xcodebuild -version | head -1)"
[ "$mode" = sync ] || [ "$changed" = 0 ]
