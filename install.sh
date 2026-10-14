#!/bin/sh
# AppScreenMap installer for macOS: puts the `appscreenmap` binary in ~/.local/bin, then runs `appscreenmap setup`
# (which installs uv if you agree, the engine and the dashboard).
#
#   curl -fsSL https://github.com/MKS-01/appscreenmap/releases/latest/download/install.sh | sh
#
# APPSCREENMAP_RELEASE_URL  where the release files are (default: the latest GitHub release; file:// works for testing)
# APPSCREENMAP_BIN_DIR      where the binary goes (default: ~/.local/bin)
set -eu

RELEASE="${APPSCREENMAP_RELEASE_URL:-https://github.com/MKS-01/appscreenmap/releases/latest/download/}"
case "$RELEASE" in */) ;; *) RELEASE="$RELEASE/" ;; esac
BIN_DIR="${APPSCREENMAP_BIN_DIR:-$HOME/.local/bin}"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "AppScreenMap is built and tested on macOS for now." >&2
  exit 1
fi
case "$(uname -m)" in
  arm64) ASSET=appscreenmap-darwin-arm64 ;;
  x86_64) ASSET=appscreenmap-darwin-x64 ;;
  *) echo "Unsupported Mac: $(uname -m)" >&2; exit 1 ;;
esac

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "▸ downloading $ASSET"
curl -fsSL "${RELEASE}SHA256SUMS" -o "$TMP/SHA256SUMS"
curl -fsSL "${RELEASE}${ASSET}" -o "$TMP/$ASSET"
if ! (cd "$TMP" && grep "  ${ASSET}\$" SHA256SUMS | shasum -a 256 -c - >/dev/null 2>&1); then
  echo "✘ checksum mismatch for $ASSET: not installing it" >&2
  exit 1
fi
mkdir -p "$BIN_DIR"
install -m 755 "$TMP/$ASSET" "$BIN_DIR/appscreenmap"
echo "✓ installed $BIN_DIR/appscreenmap"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "  $BIN_DIR isn't on your PATH yet; add it with:"
     echo "    echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc && exec zsh" ;;
esac

# setup asks before installing uv; read the answer from the terminal even when this script is piped from curl.
if [ -r /dev/tty ] && [ -t 1 ]; then
  APPSCREENMAP_RELEASE_URL="$RELEASE" "$BIN_DIR/appscreenmap" setup </dev/tty
else
  APPSCREENMAP_RELEASE_URL="$RELEASE" "$BIN_DIR/appscreenmap" setup
fi
