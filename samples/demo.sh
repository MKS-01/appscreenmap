#!/usr/bin/env bash
# Run every AppScreenMap demo scenario on the sample apps (see samples/README.md).
#   samples/demo.sh [all|playground|duskread]
# Needs a running emulator. Installs the sample APKs, wipes their data, and leaves device settings as found.
set -euo pipefail
cd "$(dirname "$0")/.."
ASM=(uv run appscreenmap)
WHAT="${1:-all}"
PG_CFG=samples/playground-app/appscreenmap.toml
# The Playground's password comes from the environment (scenario 16: secrets never land in run files).
export APP_PASSWORD="${APP_PASSWORD:-playground-demo}"
DR_CFG=samples/duskread/appscreenmap.toml

step() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
latest() { ls -td "runs/$1/$2"-2* 2>/dev/null | head -1; }

# A sample APK signed with a different key than what's installed can't update it in place.
install_fresh() {
  local apk="$1" pkg="$2"
  if ! adb install -r -t -g "$apk" >/dev/null 2>&1; then
    echo "  installed $pkg has a different signature or a newer version; reinstalling (its data is wiped anyway)"
    adb uninstall "$pkg" >/dev/null 2>&1 || true
    adb install -t -g "$apk" >/dev/null
  fi
}

analyse() {
  local run="$1"
  "${ASM[@]}" report "$run"
  "${ASM[@]}" perf "$run"
  "${ASM[@]}" a11y "$run" --report | tail -3
}

step "Preflight"
"${ASM[@]}" doctor || true

if [[ "$WHAT" == all || "$WHAT" == playground ]]; then
  PG=dev.appscreenmap.playground

  step "1–9: Playground v1, clean install (map, forms, lists, variants, nav inference, stay-in-app, crash, perf)"
  install_fresh samples/playground-app/apk/playground-v1.apk "$PG"
  "${ASM[@]}" crawl --package "$PG" --config "$PG_CFG" --clear-data --project playground --name playground-v1
  V1="$(latest playground playground-v1)"
  analyse "$V1"

  step "11: Playground v1 at 200% font size (WCAG 1.4.4 Resize Text)"
  "${ASM[@]}" crawl --package "$PG" --config "$PG_CFG" --clear-data --font-scale 2.0 --project playground --name playground-font200
  analyse "$(latest playground playground-font200)"

  step "12–13: Playground v2 (the next release)"
  install_fresh samples/playground-app/apk/playground-v2.apk "$PG"
  "${ASM[@]}" crawl --package "$PG" --config "$PG_CFG" --clear-data --project playground --name playground-v2
  V2="$(latest playground playground-v2)"
  analyse "$V2"

  step "12: Visual diff v1 → v2 (pixels + text changes)"
  "${ASM[@]}" diff "$V1" "$V2"

  step "17: verify: replay every v1 path on the v2 build (exit 1 if v2 broke a path)"
  "${ASM[@]}" verify "$V1" --apk samples/playground-app/apk/playground-v2.apk || echo "  (verify reported broken paths: expected, v2 removed 'Rate us')"

  step "16: secrets: the password never reaches the run files"
  if grep -rq "$APP_PASSWORD" "$V1" "$V2"; then echo "  ✘ password found in run files"; exit 1; else echo "  ✔ only \${APP_PASSWORD} is stored"; fi
fi

if [[ "$WHAT" == all || "$WHAT" == duskread ]]; then
  step "1, 2, 4, 9, 10: DuskRead, a real app, from a clean install"
  install_fresh samples/duskread/duskread-1.3.0.apk dev.mks.duskread
  "${ASM[@]}" crawl --package dev.mks.duskread --config "$DR_CFG" --clear-data --project duskread --name duskread
  analyse "$(latest duskread duskread)"
fi

step "Done. Open the viewer:"
echo "  uv run appscreenmap serve"
