#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This app must be built on macOS." >&2
  exit 1
fi
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
BUILD_PYTHON="${BUILD_PYTHON:-python3}"
export TG_WS_TARGET_ARCH="${TG_WS_TARGET_ARCH:-$(uname -m)}"
case "$TG_WS_TARGET_ARCH" in
  arm64|x86_64|universal2) ;;
  *) echo "Unsupported architecture: $TG_WS_TARGET_ARCH" >&2; exit 1 ;;
esac

"$BUILD_PYTHON" -m PyInstaller packaging/macos.spec --clean --noconfirm
"$BUILD_PYTHON" scripts/validate_macos_bundle.py "dist/TG WS Proxy Mac.app" "$TG_WS_TARGET_ARCH"
codesign --verify --deep --strict "dist/TG WS Proxy Mac.app"
"dist/TG WS Proxy Mac.app/Contents/MacOS/TgWsProxyMac" --version

DMG_STAGE="$(mktemp -d "$PROJECT_ROOT/dist/dmg.XXXXXX")"
DMG_ERROR_LOG="$(mktemp "$PROJECT_ROOT/dist/dmg-error.XXXXXX")"
trap 'rm -rf "$DMG_STAGE"; rm -f "$DMG_ERROR_LOG"' EXIT
cp -R "dist/TG WS Proxy Mac.app" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
DMG_PATH="dist/TgWsProxyMac_${TG_WS_TARGET_ARCH}.dmg"
for ATTEMPT in 1 2 3; do
  if hdiutil create -volname "TG WS Proxy Mac" -srcfolder "$DMG_STAGE" -ov -format UDZO -fs HFS+ "$DMG_PATH" 2>"$DMG_ERROR_LOG"; then
    break
  fi
  cat "$DMG_ERROR_LOG" >&2
  if [[ "$(cat "$DMG_ERROR_LOG")" != *"Resource busy"* || "$ATTEMPT" -eq 3 ]]; then
    exit 1
  fi
  rm -f "$DMG_PATH"
  sleep 2
done
hdiutil verify "$DMG_PATH"
(cd dist && shasum -a 256 "${DMG_PATH##*/}" > "${DMG_PATH##*/}.sha256")
echo "Built $DMG_PATH"
