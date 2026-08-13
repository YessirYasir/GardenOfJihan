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
    FFMPEG_ASSET="ffmpeg-osx-arm64"
    FFPROBE_ASSET="ffprobe-osx-arm64"
    FFMPEG_SHA256="e7b9fcd97f95f333512d6e8b8ac24d9dbc08f189f36047695499bd7b57214b22"
    FFPROBE_SHA256="ded4c698b8ff38d0bc1fd30fcc5e768dc46f58bc15a8dfd61f98615ba49cde5c"
    ONNX_VERSION="1.28.0"
    ;;
  x86_64)
    ARCH_LABEL="Intel"
    FFMPEG_ASSET="ffmpeg-osx-x64"
    FFPROBE_ASSET="ffprobe-osx-x64"
    FFMPEG_SHA256="62c87854d851f202fc4a29bdda0fe7b6ebcddd37b863482ce1bdc81151b03fe4"
    FFPROBE_SHA256="d530823f480a3c7eb6334f18a00197d1e9f1070e86172b9aa89c4bf4022bd879"
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
RELEASE_TAG="n8.1.2-1"
RELEASE_BASE="https://github.com/shaka-project/static-ffmpeg-binaries/releases/download/$RELEASE_TAG"
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
