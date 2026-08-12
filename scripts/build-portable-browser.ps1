param(
  [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$distRoot = Join-Path $repoRoot "dist"
$packageRoot = Join-Path $distRoot "GardenOfJihan-Portable"
$runtimeRoot = Join-Path $packageRoot "runtime"
$appRoot = Join-Path $packageRoot "app"
$vendorRoot = Join-Path $appRoot "vendor"
$toolsRoot = Join-Path $repoRoot "build-tools"

$pythonVersion = "3.12.10"
$pythonArchiveName = "python-$pythonVersion-embed-amd64.zip"
$pythonArchiveSha256 = "4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3"
$pythonArchiveUrl = "https://www.python.org/ftp/python/$pythonVersion/$pythonArchiveName"
$pythonToolsRoot = Join-Path $toolsRoot "python"
$pythonArchivePath = Join-Path $pythonToolsRoot $pythonArchiveName
$pythonDownloadPath = "$pythonArchivePath.download"

$ffmpegVersion = "8.1"
$ffmpegArchiveSha256 = "587B1C37DE29C5003D01CF65DA10001BAC43A58B88E61AF0FC77C61DAFF04761"
$ffmpegArchiveUrl = "https://github.com/GyanD/codexffmpeg/releases/download/$ffmpegVersion/ffmpeg-$ffmpegVersion-full_build.zip"
$ffmpegToolsRoot = Join-Path $toolsRoot "ffmpeg-portable"
$ffmpegArchivePath = Join-Path $toolsRoot "ffmpeg-$ffmpegVersion-full_build.zip"
$ffmpegDownloadPath = "$ffmpegArchivePath.download"
$ffmpegExtractRoot = Join-Path $toolsRoot "ffmpeg-$ffmpegVersion-portable"
$ffmpegArchiveRoot = Join-Path $ffmpegExtractRoot "ffmpeg-$ffmpegVersion-full_build"

function Get-VerifiedArchive {
  param(
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [Parameter(Mandatory = $true)][string]$DownloadPath,
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][string]$Label
  )

  $valid = (Test-Path -LiteralPath $ArchivePath -PathType Leaf) -and (
    (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash -eq $ExpectedSha256
  )
  if ($valid) { return }

  & curl.exe --fail --location --retry 3 --output $DownloadPath $Url
  if ($LASTEXITCODE -ne 0) { throw "$Label download failed" }
  $downloadHash = (Get-FileHash -LiteralPath $DownloadPath -Algorithm SHA256).Hash
  if ($downloadHash -ne $ExpectedSha256) {
    Remove-Item -LiteralPath $DownloadPath -Force
    throw "$Label download failed the pinned SHA256 check"
  }
  Move-Item -LiteralPath $DownloadPath -Destination $ArchivePath -Force
}

New-Item -ItemType Directory -Force -Path $distRoot, $pythonToolsRoot, $ffmpegToolsRoot | Out-Null
if (Test-Path -LiteralPath $packageRoot) {
  $resolvedPackage = [System.IO.Path]::GetFullPath($packageRoot)
  if (-not $resolvedPackage.StartsWith($distRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to replace a portable package outside the repository dist directory"
  }
  Remove-Item -LiteralPath $resolvedPackage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $runtimeRoot, $appRoot, $vendorRoot | Out-Null

Write-Host "Acquiring checksum-pinned official Python $pythonVersion embedded runtime..."
Get-VerifiedArchive `
  -ArchivePath $pythonArchivePath `
  -DownloadPath $pythonDownloadPath `
  -Url $pythonArchiveUrl `
  -ExpectedSha256 $pythonArchiveSha256 `
  -Label "Official Python embedded runtime"
Expand-Archive -LiteralPath $pythonArchivePath -DestinationPath $runtimeRoot -Force

foreach ($pythonBinaryName in @("python.exe", "pythonw.exe")) {
  $pythonBinary = Join-Path $runtimeRoot $pythonBinaryName
  $signature = Get-AuthenticodeSignature -LiteralPath $pythonBinary
  if (
    $signature.Status -ne "Valid" -or
    $signature.SignerCertificate.Subject -notlike "*Python Software Foundation*"
  ) {
    throw "$pythonBinaryName does not have the expected trusted Python Software Foundation signature"
  }
}

@(
  "python312.zip"
  "."
  "..\app"
  "..\app\vendor"
) | Set-Content -LiteralPath (Join-Path $runtimeRoot "python312._pth") -Encoding ascii

Write-Host "Installing hash-locked local AI dependencies into the portable folder..."
& $PythonExecutable -m pip install `
  --disable-pip-version-check `
  --only-binary=:all: `
  --require-hashes `
  --no-compile `
  --target $vendorRoot `
  -r (Join-Path $repoRoot "requirements-portable-windows.txt")
if ($LASTEXITCODE -ne 0) { throw "Portable dependency installation failed" }

Copy-Item -LiteralPath (Join-Path $repoRoot "src\garden_jihan") -Destination $appRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "scripts\portable\portable_start.pyw") -Destination $appRoot -Force
Get-ChildItem -LiteralPath $appRoot -Recurse -Directory -Force |
  Where-Object Name -eq "__pycache__" |
  Sort-Object FullName -Descending |
  Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $appRoot -Recurse -File -Filter "*.pyc" | Remove-Item -Force

Write-Host "Acquiring checksum-pinned FFmpeg $ffmpegVersion..."
Get-VerifiedArchive `
  -ArchivePath $ffmpegArchivePath `
  -DownloadPath $ffmpegDownloadPath `
  -Url $ffmpegArchiveUrl `
  -ExpectedSha256 $ffmpegArchiveSha256 `
  -Label "FFmpeg archive"
Expand-Archive -LiteralPath $ffmpegArchivePath -DestinationPath $ffmpegExtractRoot -Force
$ffmpeg = Join-Path $ffmpegArchiveRoot "bin\ffmpeg.exe"
$ffprobe = Join-Path $ffmpegArchiveRoot "bin\ffprobe.exe"
$ffmpegLicense = Join-Path $ffmpegArchiveRoot "LICENSE"
$ffmpegReadme = Join-Path $ffmpegArchiveRoot "README.txt"
if (
  -not (Test-Path -LiteralPath $ffmpeg -PathType Leaf) -or
  -not (Test-Path -LiteralPath $ffprobe -PathType Leaf) -or
  -not (Test-Path -LiteralPath $ffmpegLicense -PathType Leaf) -or
  -not (Test-Path -LiteralPath $ffmpegReadme -PathType Leaf)
) {
  throw "Checksum-verified FFmpeg archive did not contain the expected files"
}
$mediaBinRoot = Join-Path $runtimeRoot "bin"
New-Item -ItemType Directory -Force -Path $mediaBinRoot | Out-Null
Copy-Item -LiteralPath $ffmpeg -Destination (Join-Path $mediaBinRoot "ffmpeg.exe") -Force
Copy-Item -LiteralPath $ffprobe -Destination (Join-Path $mediaBinRoot "ffprobe.exe") -Force

Copy-Item -LiteralPath (Join-Path $repoRoot "scripts\portable\START GARDEN OF JIHAN.cmd") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "scripts\portable\START-HERE.txt") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "scripts\portable\START-HERE.html") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "README.md") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "PRIVACY.md") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "CODE_SIGNING.md") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE") -Destination (Join-Path $packageRoot "GARDEN-OF-JIHAN-LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "THIRD-PARTY-NOTICES.md") -Destination $packageRoot -Force
Copy-Item -LiteralPath $ffmpegLicense -Destination (Join-Path $packageRoot "FFMPEG-LICENSE.txt") -Force
Copy-Item -LiteralPath $ffmpegReadme -Destination (Join-Path $packageRoot "FFMPEG-BUILD-INFO.txt") -Force

$sourceRevision = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (& git rev-parse HEAD).Trim() }
$requirementsHash = (Get-FileHash -LiteralPath (Join-Path $repoRoot "requirements-portable-windows.txt") -Algorithm SHA256).Hash.ToLowerInvariant()
# Windows PowerShell 5.1 reads BOM-less scripts using the active ANSI code page.
# Construct the approved Arabic brand from Unicode code points so package metadata
# remains exact on every Windows locale: جيهان.
$arabicBrand = [string]::Concat([char[]](0x062C, 0x064A, 0x0647, 0x0627, 0x0646))
[ordered]@{
  product = "Garden of Jihan"
  arabic_brand = $arabicBrand
  version = "0.1.0"
  distribution = "private-portable-browser"
  source_revision = $sourceRevision
  python_version = $pythonVersion
  python_archive_sha256 = $pythonArchiveSha256.ToLowerInvariant()
  ffmpeg_version = $ffmpegVersion
  ffmpeg_archive_sha256 = $ffmpegArchiveSha256.ToLowerInvariant()
  requirements_sha256 = $requirementsHash
  public_release = $false
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $packageRoot "PACKAGE-INFO.json") -Encoding utf8

$fileManifest = Get-ChildItem -LiteralPath $packageRoot -Recurse -File |
  Where-Object Name -ne "PACKAGE-FILES.sha256" |
  Sort-Object FullName |
  ForEach-Object {
    $relative = $_.FullName.Substring($packageRoot.Length).TrimStart("\").Replace("\", "/")
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $relative"
  }
$fileManifest | Set-Content -LiteralPath (Join-Path $packageRoot "PACKAGE-FILES.sha256") -Encoding ascii

$archivePath = Join-Path $distRoot "GardenOfJihan-Portable-Browser-Windows-x64.zip"
$checksumPath = Join-Path $distRoot "GardenOfJihan-Portable-Browser-Windows-x64.sha256"
Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $archivePath -CompressionLevel Optimal -Force
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
"$archiveHash  GardenOfJihan-Portable-Browser-Windows-x64.zip" |
  Set-Content -LiteralPath $checksumPath -Encoding ascii

Write-Host "Portable browser bundle created: $archivePath"
Write-Host "SHA256: $archiveHash"
