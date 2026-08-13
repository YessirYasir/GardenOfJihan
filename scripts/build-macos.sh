#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The macOS package must be built on a Mac." >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

MACHINE="$(uname -m)"
case "$MACHINE" in
  arm64)
    ARCH_LABEL="Apple-Silicon"
    FFMPEG_ASSET="ffmpeg-darwin-arm64"
    FFPROBE_ASSET="ffprobe-darwin-arm64"
    FFMPEG_LICENSE_ASSET="darwin-arm64.LICENSE"
    FFMPEG_SHA256="a90e3db6a3fd35f6074b013f948b1aa45b31c6375489d39e572bea3f18336584"
    FFPROBE_SHA256="bb2db6f5d8cef919da12fbf592119a987202a8c060a886f3cab091f9cab90b64"
    FFMPEG_LICENSE_SHA256="cb48bf09a11f5fb576cddb0431c8f5ed0a60157a9ec942adffc13907cbe083f2"
    ONNX_VERSION="1.28.0"
    ;;
  x86_64)
    ARCH_LABEL="Intel"
    FFMPEG_ASSET="ffmpeg-darwin-x64"
    FFPROBE_ASSET="ffprobe-darwin-x64"
    FFMPEG_LICENSE_ASSET="darwin-x64.LICENSE"
    FFMPEG_SHA256="ebdddc936f61e14049a2d4b549a412b8a40deeff6540e58a9f2a2da9e6b18894"
    FFPROBE_SHA256="fa3add0ce901f7241abe0dfc0155d958fc834aca3f8ce61f87cc712ae669c1e0"
    FFMPEG_LICENSE_SHA256="2e1d16c72fd74e12063776371da757322f8b77589386532f4fd8634bde7de1af"
    ONNX_VERSION="1.23.2"
    ;;
  *)
    echo "Unsupported Mac architecture: $MACHINE" >&2
    exit 1
    ;;
esac

TOOLS_ROOT="$REPO_ROOT/build-tools/macos-$MACHINE"
MEDIA_ROOT="$TOOLS_ROOT/media"
MODEL_ROOT="$TOOLS_ROOT/models"
PACKAGE_ROOT="$REPO_ROOT/dist/GardenOfJihan-macOS-$ARCH_LABEL"
APP_PATH="$PACKAGE_ROOT/Garden of Jihan.app"
RELEASE_TAG="b6.1.1"
RELEASE_BASE="https://github.com/eugeneware/ffmpeg-static/releases/download/$RELEASE_TAG"
mkdir -p "$MEDIA_ROOT" "$MODEL_ROOT" "$REPO_ROOT/dist"

verify_download() {
  local destination="$1"
  local expected="$2"
  local url="$3"
  if [[ -f "$destination" ]] && [[ "$(shasum -a 256 "$destination" | awk '{print $1}')" == "$expected" ]]; then
    return
  fi
  rm -f "$destination.download"
  curl --fail --location --retry 3 --output "$destination.download" "$url"
  local actual
  actual="$(shasum -a 256 "$destination.download" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    rm -f "$destination.download"
    echo "Downloaded media tool failed its pinned SHA-256 check." >&2
    exit 1
  fi
  mv "$destination.download" "$destination"
}

verify_download "$MEDIA_ROOT/ffmpeg" "$FFMPEG_SHA256" "$RELEASE_BASE/$FFMPEG_ASSET"
verify_download "$MEDIA_ROOT/ffprobe" "$FFPROBE_SHA256" "$RELEASE_BASE/$FFPROBE_ASSET"
verify_download \
  "$MEDIA_ROOT/FFMPEG-LICENSE.txt" \
  "$FFMPEG_LICENSE_SHA256" \
  "$RELEASE_BASE/$FFMPEG_LICENSE_ASSET"
chmod 755 "$MEDIA_ROOT/ffmpeg" "$MEDIA_ROOT/ffprobe"

"$PYTHON_BIN" -m pip install --disable-pip-version-check \
  --only-binary=:all: \
  --constraint requirements-macos-constraints.txt \
  "onnxruntime==$ONNX_VERSION" \
  -e ".[macos,ai,dev]"

"$PYTHON_BIN" scripts/prepare-offline-models.py \
  --destination "$MODEL_ROOT" \
  --cache "$TOOLS_ROOT/model-cache"
"$PYTHON_BIN" scripts/prepare-quran-reference.py \
  --destination "$MODEL_ROOT/quran_reference.json" \
  --cache "$TOOLS_ROOT/quran-reference"

rm -rf "$REPO_ROOT/build/Garden of Jihan" "$REPO_ROOT/dist/Garden of Jihan" "$APP_PATH"

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --noupx \
  --name "Garden of Jihan" \
  --osx-bundle-identifier "com.gardenofjihan.desktop" \
  --osx-entitlements-file "scripts/macos-entitlements.plist" \
  --icon "src/garden_jihan/ui/assets/garden-sanctuary-bg.png" \
  --collect-all garden_jihan \
  --collect-all faster_whisper \
  --collect-all fastembed \
  --collect-all cv2 \
  --collect-all onnxruntime \
  --collect-all ctranslate2 \
  --collect-all tokenizers \
  --collect-all huggingface_hub \
  --collect-all av \
  --add-data "src/garden_jihan/ui:garden_jihan/ui" \
  --add-data "$MODEL_ROOT:models" \
  --add-binary "$MEDIA_ROOT/ffmpeg:bin" \
  --add-binary "$MEDIA_ROOT/ffprobe:bin" \
  src/garden_jihan/launcher.py

rm -rf "$PACKAGE_ROOT"
mkdir -p "$PACKAGE_ROOT"
ditto "$REPO_ROOT/dist/Garden of Jihan.app" "$APP_PATH"
/usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 14.0" "$APP_PATH/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 14.0" "$APP_PATH/Contents/Info.plist"
/usr/bin/codesign --force --deep --sign - "$APP_PATH"
cp "scripts/macos/START-HERE.txt" "$PACKAGE_ROOT/START-HERE.txt"
cp README.md PRIVACY.md THIRD-PARTY-NOTICES.md "$PACKAGE_ROOT/"
cp "$MEDIA_ROOT/FFMPEG-LICENSE.txt" "$PACKAGE_ROOT/FFMPEG-LICENSE.txt"

SOURCE_REVISION="${GITHUB_SHA:-$(git rev-parse HEAD)}"
cat > "$PACKAGE_ROOT/PACKAGE-INFO.json" <<EOF
{
  "product": "Garden of Jihan",
  "arabic_brand": "جيهان",
  "version": "0.1.0",
  "distribution": "private-macos-browser",
  "architecture": "$MACHINE",
  "source_revision": "$SOURCE_REVISION",
  "ffmpeg_release": "$RELEASE_TAG",
  "speech_model_revision": "536b0662742c02347bc0e980a01041f333bce120",
  "meaning_model_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
  "quran_reference_sha256": "d25401b9235ea0c77a2511b1edc5b5d28df1b3bcd0259d6657ec6e303dd8eee9",
  "public_release": false
}
EOF

echo "Built $APP_PATH"
