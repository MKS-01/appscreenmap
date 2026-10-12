#!/usr/bin/env bash
# Rebuild the Playground's v1 and v2 release APKs into apk/.
set -euo pipefail
cd "$(dirname "$0")"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
[ -f local.properties ] || echo "sdk.dir=$SDK" > local.properties
./gradlew -q :app:assembleV1Release :app:assembleV2Release
mkdir -p apk
cp app/build/outputs/apk/v1/release/app-v1-release.apk apk/playground-v1.apk
cp app/build/outputs/apk/v2/release/app-v2-release.apk apk/playground-v2.apk
ls -la apk/
