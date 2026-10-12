#!/usr/bin/env bash
# Rebuild the DuskRead sample APK from source (https://github.com/MKS-01/duskread).
# Uses ../../../duskread if it exists next to this repo, else clones it into a temp dir.
# Without DuskRead's release keystore the build is unsigned, so it's signed with the local debug key.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
SRC="${DUSKREAD_SRC:-$HERE/../../../duskread}"
if [ ! -d "$SRC" ]; then
  SRC="$(mktemp -d)/duskread"
  git clone --depth 1 https://github.com/MKS-01/duskread.git "$SRC"
fi
(cd "$SRC" && [ -f local.properties ] || echo "sdk.dir=$SDK" > "$SRC/local.properties")
(cd "$SRC" && ./gradlew -q :androidApp:assembleRelease)
OUT="$(ls "$SRC"/androidApp/build/outputs/apk/release/*.apk | head -1)"
VERSION="$("$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)/aapt2" dump badging "$OUT" | sed -n "s/.*versionName='\([^']*\)'.*/\1/p")"
DEST="$HERE/duskread-$VERSION.apk"
cp "$OUT" "$DEST"
APKSIGNER="$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)/apksigner"
if ! "$APKSIGNER" verify "$DEST" >/dev/null 2>&1; then
  "$APKSIGNER" sign --ks "$HOME/.android/debug.keystore" --ks-pass pass:android --key-pass pass:android "$DEST"
fi
echo "→ $DEST"
