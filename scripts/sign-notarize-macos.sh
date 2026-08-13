#!/bin/bash
set -euo pipefail

required=(
  GOJ_APPLE_CERTIFICATE_BASE64
  GOJ_APPLE_CERTIFICATE_PASSWORD
  GOJ_APPLE_SIGNING_IDENTITY
  GOJ_APPLE_ID
  GOJ_APPLE_TEAM_ID
  GOJ_APPLE_APP_PASSWORD
)
for variable in "${required[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    echo "Missing required Apple signing value: $variable" >&2
    exit 1
  fi
done

PACKAGE_ROOT="$1"
ARCHIVE_PATH="$2"
APP_PATH="$PACKAGE_ROOT/Garden of Jihan.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Garden of Jihan.app was not found in the package." >&2
  exit 1
fi

TEMP_ROOT="$(mktemp -d)"
KEYCHAIN_PATH="$TEMP_ROOT/garden-signing.keychain-db"
CERTIFICATE_PATH="$TEMP_ROOT/developer-id.p12"
KEYCHAIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
cleanup() {
  security delete-keychain "$KEYCHAIN_PATH" >/dev/null 2>&1 || true
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT

CERTIFICATE_PATH="$CERTIFICATE_PATH" python3 -c 'import base64, os, pathlib; pathlib.Path(os.environ["CERTIFICATE_PATH"]).write_bytes(base64.b64decode(os.environ["GOJ_APPLE_CERTIFICATE_BASE64"]))'
security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
security import "$CERTIFICATE_PATH" \
  -k "$KEYCHAIN_PATH" \
  -P "$GOJ_APPLE_CERTIFICATE_PASSWORD" \
  -T /usr/bin/codesign \
  -T /usr/bin/security
security set-key-partition-list \
  -S apple-tool:,apple: \
  -s \
  -k "$KEYCHAIN_PASSWORD" \
  "$KEYCHAIN_PATH"
security list-keychains -d user -s "$KEYCHAIN_PATH"

PACKAGE_INFO="$PACKAGE_ROOT/PACKAGE-INFO.json" python3 -c 'import json, os, pathlib; path = pathlib.Path(os.environ["PACKAGE_INFO"]); value = json.loads(path.read_text()); value["public_release"] = True; path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")'

/usr/bin/codesign \
  --force \
  --deep \
  --options runtime \
  --timestamp \
  --entitlements "scripts/macos-entitlements.plist" \
  --sign "$GOJ_APPLE_SIGNING_IDENTITY" \
  "$APP_PATH"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP_PATH"

python3 scripts/package-macos.py --package-root "$PACKAGE_ROOT" --archive "$ARCHIVE_PATH"
xcrun notarytool submit "$ARCHIVE_PATH" \
  --apple-id "$GOJ_APPLE_ID" \
  --team-id "$GOJ_APPLE_TEAM_ID" \
  --password "$GOJ_APPLE_APP_PASSWORD" \
  --wait
xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"
/usr/sbin/spctl --assess --type execute --verbose=2 "$APP_PATH"

# Stapling changes the app, so regenerate both the integrity manifest and final archive.
python3 scripts/package-macos.py --package-root "$PACKAGE_ROOT" --archive "$ARCHIVE_PATH"
