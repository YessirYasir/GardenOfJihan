$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -e ".[windows,ai]"

$toolsDir = Join-Path $PWD "build-tools\ffmpeg"
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

Write-Host "Installing FFmpeg for the distributable..."
choco install ffmpeg -y --no-progress

$ffmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe.exe -ErrorAction Stop).Source
Copy-Item $ffmpeg (Join-Path $toolsDir "ffmpeg.exe") -Force
Copy-Item $ffprobe (Join-Path $toolsDir "ffprobe.exe") -Force

Write-Host "Building Garden of Jihan..."
pyinstaller `
  --noconfirm `
  --clean `
  --onedir `
  --noconsole `
  --noupx `
  --version-file "scripts\version-info.txt" `
  --name GardenOfJihan `
  --collect-all garden_jihan `
  --collect-all faster_whisper `
  --collect-all fastembed `
  --collect-all cv2 `
  --collect-all onnxruntime `
  --collect-all ctranslate2 `
  --collect-all tokenizers `
  --collect-all huggingface_hub `
  --collect-all av `
  --add-data "src/garden_jihan/ui;garden_jihan/ui" `
  --add-binary "$toolsDir\ffmpeg.exe;bin" `
  --add-binary "$toolsDir\ffprobe.exe;bin" `
  src/garden_jihan/launcher.py

$readme = @"
Garden of Jihan — Windows Release Package

GET STARTED
1. Extract this ZIP to a normal folder such as Documents\GardenOfJihan.
2. Open GardenOfJihan.exe.
3. Your default browser opens the private local Garden of Jihan interface.
4. Paste a supported video URL or choose a local video.
5. Choose the analysis mode and clip settings, then click Find the best moments.
6. Preview, adjust, keep, and export your clips.

FIRST AI ANALYSIS
The first analysis downloads the local Whisper speech model and multilingual meaning model once and caches them on this PC. This can take a few minutes depending on the internet connection. Later analyses reuse the cached models. If the meaning model is unavailable, Garden of Jihan reports that it used base ranking and never sends transcript text to a paid or cloud fallback.

PRIVACY
Garden of Jihan binds only to 127.0.0.1. Video processing happens on this PC. FFmpeg and ffprobe are bundled. There is no paid AI API key, subscription, credits, token balance, or telemetry requirement.

TRUST AND VERIFICATION
Official releases are built by GitHub Actions from the public source repository. Each release includes a SHA256 checksum and GitHub build-provenance attestation. The release pipeline also runs Microsoft Defender Antivirus against the packaged application before publishing.

WINDOWS SIGNING
Never distribute an unsigned GardenOfJihan.exe as a public release. The public release workflows inspect the executable inside the exact ZIP, require a valid trusted Authenticode signature, and block publication when the signature is missing or invalid. Only download releases from the official YessirYasir/GardenOfJihan repository.

Important: Process and republish only media you have permission to use.
"@
Set-Content -Path "dist\GardenOfJihan\START-HERE.txt" -Value $readme -Encoding UTF8

Compress-Archive -Path "dist\GardenOfJihan\*" -DestinationPath "dist\GardenOfJihan-Windows-x64.zip" -Force
Write-Host "Build created: dist/GardenOfJihan-Windows-x64.zip"
