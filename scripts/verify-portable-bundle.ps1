param(
  [Parameter(Mandatory = $true)]
  [string]$PackageRoot
)

$ErrorActionPreference = "Stop"
$resolvedPackage = (Resolve-Path -LiteralPath $PackageRoot -ErrorAction Stop).Path
$python = Join-Path $resolvedPackage "runtime\python.exe"
$pythonw = Join-Path $resolvedPackage "runtime\pythonw.exe"
$launcher = Join-Path $resolvedPackage "START GARDEN OF JIHAN.cmd"
$manifest = Join-Path $resolvedPackage "PACKAGE-FILES.sha256"
$requiredFiles = @(
  $python,
  $pythonw,
  $launcher,
  (Join-Path $resolvedPackage "START-HERE.html"),
  (Join-Path $resolvedPackage "START-HERE.txt"),
  (Join-Path $resolvedPackage "PACKAGE-INFO.json"),
  $manifest,
  (Join-Path $resolvedPackage "app\portable_start.pyw"),
  (Join-Path $resolvedPackage "app\garden_jihan\launcher.py"),
  (Join-Path $resolvedPackage "models\speech\model.bin"),
  (Join-Path $resolvedPackage "models\speech\tokenizer.json"),
  (Join-Path $resolvedPackage "models\meaning\onnx\model_O4.onnx"),
  (Join-Path $resolvedPackage "models\meaning\tokenizer.json"),
  (Join-Path $resolvedPackage "models\quran_reference.json"),
  (Join-Path $resolvedPackage "runtime\bin\ffmpeg.exe"),
  (Join-Path $resolvedPackage "runtime\bin\ffprobe.exe")
)
foreach ($requiredFile in $requiredFiles) {
  if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
    throw "Portable bundle is missing $requiredFile"
  }
}

if (Get-ChildItem -LiteralPath $resolvedPackage -Recurse -File -Filter "GardenOfJihan.exe") {
  throw "Portable browser bundle must not contain an unsigned custom GardenOfJihan.exe"
}
foreach ($pythonBinary in @($python, $pythonw)) {
  $signature = Get-AuthenticodeSignature -LiteralPath $pythonBinary
  if (
    $signature.Status -ne "Valid" -or
    $signature.SignerCertificate.Subject -notlike "*Python Software Foundation*"
  ) {
    throw "Portable runtime does not have the expected trusted Python Software Foundation signature"
  }
}

$packageInfo = Get-Content -LiteralPath (Join-Path $resolvedPackage "PACKAGE-INFO.json") -Raw | ConvertFrom-Json
$expectedArabicBrand = [string]::Concat([char[]](0x062C, 0x064A, 0x0647, 0x0627, 0x0646))
if (
  $packageInfo.product -ne "Garden of Jihan" -or
  $packageInfo.arabic_brand -ne $expectedArabicBrand -or
  $packageInfo.distribution -ne "private-portable-browser" -or
  $packageInfo.public_release -ne $false
) {
  throw "Portable package identity or distribution boundary is invalid"
}

foreach ($line in Get-Content -LiteralPath $manifest) {
  if (-not $line.Trim()) { continue }
  $parts = $line -split "  ", 2
  if ($parts.Count -ne 2 -or $parts[0] -notmatch "^[a-f0-9]{64}$") {
    throw "Portable package file manifest contains an invalid entry"
  }
  $target = Join-Path $resolvedPackage ($parts[1].Replace("/", "\"))
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    throw "Portable package manifest target is missing: $($parts[1])"
  }
  $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $parts[0]) {
    throw "Portable package file failed integrity verification: $($parts[1])"
  }
}

& $python -I -c "import sys; assert sys.flags.isolated == 1; import garden_jihan, fastapi, cv2, faster_whisper, fastembed; print(sys.version.split()[0])"
if ($LASTEXITCODE -ne 0) { throw "Portable Python runtime import check failed" }
& $python -I -c "from pathlib import Path; from garden_jihan.analysis.quran import QuranReference; r=QuranReference(Path(r'$resolvedPackage\models\quran_reference.json')); assert r.available and len(r.records)==6236"
if ($LASTEXITCODE -ne 0) { throw "Portable Qur'an guide integrity check failed" }

$launcherText = Get-Content -LiteralPath $launcher -Raw
if (
  $launcherText -notmatch "runtime\\pythonw\.exe" -or
  $launcherText -notmatch "app\\portable_start\.pyw" -or
  $launcherText -match "https?://|Invoke-WebRequest|curl\.exe|powershell"
) {
  throw "Portable launcher does not satisfy the offline one-click launch contract"
}
