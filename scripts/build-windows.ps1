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
Garden of Jihan binds only to 127.0.0.1. Video processing happens on this PC. FFmpeg and ffprobe are bundled. There is no paid AI API key, subscription, credits, token balance, or telemetry requirement. Optional publishing sends only the explicitly chosen export and metadata through an official platform API. YouTube OAuth material is encrypted for the current Windows user; production OAuth credentials are not embedded in this unsigned internal build.

TRUST AND VERIFICATION
Official releases are built by GitHub Actions from the public source repository. Each release includes a SHA256 checksum and GitHub build-provenance attestation. The release pipeline also runs Microsoft Defender Antivirus against the packaged application before publishing.

WINDOWS SIGNING
Never distribute an unsigned GardenOfJihan.exe as a public release. The public release workflows inspect the executable inside the exact ZIP, require a valid trusted Authenticode signature, and block publication when the signature is missing or invalid. Only download releases from the official YessirYasir/GardenOfJihan repository.

Important: Process and republish only media you have permission to use.
"@
Set-Content -Path "dist\GardenOfJihan\START-HERE.txt" -Value $readme -Encoding UTF8
Copy-Item -LiteralPath $archiveLicense -Destination "dist\GardenOfJihan\FFMPEG-LICENSE.txt" -Force
Copy-Item -LiteralPath $archiveReadme -Destination "dist\GardenOfJihan\FFMPEG-BUILD-INFO.txt" -Force
Copy-Item -LiteralPath "THIRD-PARTY-NOTICES.md" -Destination "dist\GardenOfJihan\THIRD-PARTY-NOTICES.md" -Force

Compress-Archive -Path "dist\GardenOfJihan\*" -DestinationPath "dist\GardenOfJihan-Windows-x64.zip" -Force
Write-Host "Build created: dist/GardenOfJihan-Windows-x64.zip"
