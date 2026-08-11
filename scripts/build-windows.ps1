$ErrorActionPreference = "Stop"

python -m pip install -e ".[windows,ai]"

$toolsDir = Join-Path $PWD "build-tools\ffmpeg"
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

Write-Host "Installing FFmpeg for the distributable..."
choco install ffmpeg -y --no-progress

$ffmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe.exe -ErrorAction Stop).Source
Copy-Item $ffmpeg (Join-Path $toolsDir "ffmpeg.exe") -Force
Copy-Item $ffprobe (Join-Path $toolsDir "ffprobe.exe") -Force

pyinstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name GardenOfJihan `
  --collect-all garden_jihan `
  --collect-all faster_whisper `
  --add-data "src/garden_jihan/ui;garden_jihan/ui" `
  --add-binary "$toolsDir\ffmpeg.exe;bin" `
  --add-binary "$toolsDir\ffprobe.exe;bin" `
  src/garden_jihan/launcher.py

$readme = @"
Garden of Jihan — Windows Public Beta

1. Open GardenOfJihan.exe.
2. Your browser opens the local Garden of Jihan interface.
3. Paste a supported video URL or choose a local video.
4. The first AI analysis downloads the selected local Whisper model once.

The local interface binds only to 127.0.0.1. FFmpeg and ffprobe are bundled.
No paid AI API key is required.
"@
Set-Content -Path "dist\GardenOfJihan\START-HERE.txt" -Value $readme -Encoding UTF8

Compress-Archive -Path "dist\GardenOfJihan\*" -DestinationPath "dist\GardenOfJihan-Windows-x64.zip" -Force
Write-Host "Build created: dist/GardenOfJihan-Windows-x64.zip"
