param(
  [string]$PythonExecutable = "python",
  [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

if (-not $SkipDependencyInstall) {
  & $PythonExecutable -m pip install --upgrade pip
  & $PythonExecutable -m pip install -e ".[windows,ai]"
}

$ffmpegVersion = "8.1"
$ffmpegArchiveSha256 = "587B1C37DE29C5003D01CF65DA10001BAC43A58B88E61AF0FC77C61DAFF04761"
$ffmpegArchiveUrl = "https://github.com/GyanD/codexffmpeg/releases/download/$ffmpegVersion/ffmpeg-$ffmpegVersion-full_build.zip"
$toolsRoot = Join-Path $PWD "build-tools"
$toolsDir = Join-Path $toolsRoot "ffmpeg"
$archivePath = Join-Path $toolsRoot "ffmpeg-$ffmpegVersion-full_build.zip"
$downloadPath = "$archivePath.download"
$extractRoot = Join-Path $toolsRoot "ffmpeg-$ffmpegVersion"
$archiveBin = Join-Path $extractRoot "ffmpeg-$ffmpegVersion-full_build\bin"
$archiveLicense = Join-Path $extractRoot "ffmpeg-$ffmpegVersion-full_build\LICENSE"
$archiveReadme = Join-Path $extractRoot "ffmpeg-$ffmpegVersion-full_build\README.txt"
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

Write-Host "Acquiring checksum-pinned FFmpeg $ffmpegVersion for the distributable..."
$archiveValid = (Test-Path -LiteralPath $archivePath) -and ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -eq $ffmpegArchiveSha256)
if (-not $archiveValid) {
  & curl.exe --fail --location --retry 3 --output $downloadPath $ffmpegArchiveUrl
  if ($LASTEXITCODE -ne 0) { throw "FFmpeg archive download failed" }
  $downloadHash = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256).Hash
  if ($downloadHash -ne $ffmpegArchiveSha256) {
    Remove-Item -LiteralPath $downloadPath -Force
    throw "Downloaded FFmpeg archive failed the pinned SHA256 check"
  }
  Move-Item -LiteralPath $downloadPath -Destination $archivePath -Force
}
Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
$ffmpeg = Join-Path $archiveBin "ffmpeg.exe"
$ffprobe = Join-Path $archiveBin "ffprobe.exe"
if (
  -not (Test-Path -LiteralPath $ffmpeg) -or
  -not (Test-Path -LiteralPath $ffprobe) -or
  -not (Test-Path -LiteralPath $archiveLicense) -or
  -not (Test-Path -LiteralPath $archiveReadme)
) {
  throw "Checksum-verified FFmpeg archive did not contain the expected files"
}
Copy-Item -LiteralPath $ffmpeg -Destination (Join-Path $toolsDir "ffmpeg.exe") -Force
Copy-Item -LiteralPath $ffprobe -Destination (Join-Path $toolsDir "ffprobe.exe") -Force

Write-Host "Building Garden of Jihan..."
& $PythonExecutable -m PyInstaller `
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

Write-Host "Including checksum-verified speech and meaning resources for a fast first analysis..."
& $PythonExecutable "scripts\prepare-offline-models.py" `
  --destination "dist\GardenOfJihan\models" `
  --cache (Join-Path $toolsRoot "model-cache")
if ($LASTEXITCODE -ne 0) { throw "Verified offline resource preparation failed" }

& $PythonExecutable "scripts\prepare-quran-reference.py" `
  --destination "dist\GardenOfJihan\models\quran_reference.json" `
  --cache (Join-Path $toolsRoot "quran-reference")
if ($LASTEXITCODE -ne 0) { throw "Verified Qur'an reference preparation failed" }

$readme = @"
Garden of Jihan — Windows Release Package

GET STARTED
1. Extract this ZIP to a normal folder such as Documents\GardenOfJihan.
2. Open GardenOfJihan.exe.
3. Your default browser opens the private local Garden of Jihan interface.
4. Paste a supported video URL or choose a local video.
5. Choose the analysis mode and clip settings, then click Find the best moments.
6. Preview, adjust, keep, and export your clips.

FIRST USE
Everything needed to find moments is already included. A visible clock shows how long the current video has been processing and the estimated time remaining.

PRIVACY
Video processing stays on this PC. No account, subscription, credits, or payment is required. Only a finished video that you explicitly choose to publish can leave the private garden.

TRUST AND VERIFICATION
Official releases include a matching authenticity fingerprint and trusted Windows signature, and are scanned by Microsoft Defender before publication.

WINDOWS SIGNING
Never distribute GardenOfJihan.exe publicly unless Windows identifies its trusted publisher. Only download releases from the official Garden of Jihan release page.

Important: Process and republish only media you have permission to use.
"@
Set-Content -Path "dist\GardenOfJihan\START-HERE.txt" -Value $readme -Encoding UTF8
Copy-Item -LiteralPath $archiveLicense -Destination "dist\GardenOfJihan\FFMPEG-LICENSE.txt" -Force
Copy-Item -LiteralPath $archiveReadme -Destination "dist\GardenOfJihan\FFMPEG-BUILD-INFO.txt" -Force
Copy-Item -LiteralPath "THIRD-PARTY-NOTICES.md" -Destination "dist\GardenOfJihan\THIRD-PARTY-NOTICES.md" -Force

Compress-Archive -Path "dist\GardenOfJihan\*" -DestinationPath "dist\GardenOfJihan-Windows-x64.zip" -Force
Write-Host "Build created: dist/GardenOfJihan-Windows-x64.zip"
