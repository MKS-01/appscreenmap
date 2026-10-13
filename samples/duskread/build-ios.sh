#!/usr/bin/env bash
# Build the DuskRead sample for the iOS Simulator (https://github.com/MKS-01/duskread, iosApp/).
# Uses ../../../duskread if it exists next to this repo, else clones it into a temp dir.
# A simulator runs a .app from an iphonesimulator build (an .ipa is device-signed and won't run), so the
# build is unsigned. The first build compiles the Kotlin Multiplatform core with Gradle and takes minutes.
#   samples/duskread/build-ios.sh ["iPhone 17"]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SIM="${1:-iPhone 17}"
SRC="${DUSKREAD_SRC:-$HERE/../../../duskread}"
if [ ! -d "$SRC/iosApp" ]; then
  SRC="$(mktemp -d)/duskread"
  git clone --depth 1 https://github.com/MKS-01/duskread.git "$SRC"
fi
OUT="$HERE/build/ios"   # build/ is git-ignored
xcodebuild -quiet -project "$SRC/iosApp/iosApp.xcodeproj" -scheme iosApp -sdk iphonesimulator -configuration Debug \
  -destination "platform=iOS Simulator,name=$SIM" -derivedDataPath "$OUT/dd" CODE_SIGNING_ALLOWED=NO build
APP="$(ls -d "$OUT"/dd/Build/Products/Debug-iphonesimulator/*.app | head -1)"
rm -rf "$OUT/DuskRead.app"
cp -R "$APP" "$OUT/DuskRead.app"
echo "→ $OUT/DuskRead.app"
