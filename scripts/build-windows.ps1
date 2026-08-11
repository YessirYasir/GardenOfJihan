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
  --name GardenOfJihan `
  --collect-all garden_jihan `
  --collect-all faster_whisper `
  --collect-all ctranslate2 `
  --collect-all tokenizers `
  --collect-all huggingface_hub `
  --collect-all av `
  --add-data "src/garden_jihan/ui;garden_jihan/ui" `
  --add-binary "$toolsDir\ffmpeg.exe;bin" `
  --add-binary "$toolsDir\ffprobe.exe;bin" `
  src/garden_jihan/launcher.py

$readme = @"
Garden of Jihan — Windows Release Candidate

1. Extract this ZIP to a normal folder.
2. Open GardenOfJihan.exe.
3. Your browser opens the local Garden of Jihan interface.
4. Paste a supported video URL or choose a local video.
5. The first AI analysis downloads the local Whisper model once and caches it on this PC.

Garden of Jihan binds only to 127.0.0.1. FFmpeg and ffprobe are bundled.
No paid AI API key, subscription, credits, or token balance is required.

Important: Process and republish only media you have permission to use.
"@
Set-Content -Path "dist\GardenOfJihan\START-HERE.txt" -Value $readme -Encoding UTF8

Compress-Archive -Path "dist\GardenOfJihan\*" -DestinationPath "dist\GardenOfJihan-Windows-x64.zip" -Force
Write-Host "Build created: dist/GardenOfJihan-Windows-x64.zip"
