#!/usr/bin/env bash
# Build the iOS Playground for the simulator into build/Playground.app (needs Xcode and xcodegen).
set -euo pipefail
cd "$(dirname "$0")"
xcodegen generate --quiet
xcodebuild -project Playground.xcodeproj -scheme Playground -sdk iphonesimulator -configuration Debug \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath build/dd CODE_SIGNING_ALLOWED=NO -quiet build
rm -rf build/Playground.app
cp -R build/dd/Build/Products/Debug-iphonesimulator/Playground.app build/Playground.app
echo "built $(pwd)/build/Playground.app"
