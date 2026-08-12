param(
  [Parameter(Mandatory = $true)]
  [string]$PackageRoot,

  [Parameter(Mandatory = $true)]
  [string]$ArchivePath
)

$ErrorActionPreference = "Stop"

$resolvedPackage = (Resolve-Path -LiteralPath $PackageRoot -ErrorAction Stop).Path
$resolvedArchive = (Resolve-Path -LiteralPath $ArchivePath -ErrorAction Stop).Path
$packageExe = Join-Path $resolvedPackage "GardenOfJihan.exe"
if (-not (Test-Path -LiteralPath $packageExe -PathType Leaf)) {
  throw "Public release blocked: GardenOfJihan.exe is missing from the package directory."
}
if ([System.IO.Path]::GetExtension($resolvedArchive) -ne ".zip") {
  throw "Public release blocked: the release archive must be a ZIP file."
}

function Assert-TrustedGardenSignature {
  param([Parameter(Mandatory = $true)][string]$Executable)

  $signature = Get-AuthenticodeSignature -LiteralPath $Executable
  if ($signature.Status -ne "Valid" -or -not $signature.SignerCertificate) {
    throw "Public release blocked: GardenOfJihan.exe is not signed by a valid trusted Authenticode certificate."
  }
  $productName = (Get-Item -LiteralPath $Executable).VersionInfo.ProductName
  if ($productName -ne "Garden of Jihan") {
    throw "Public release blocked: the signed executable has an unexpected product name."
  }
  return $signature
}

$looseSignature = Assert-TrustedGardenSignature -Executable $packageExe
$tempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$inspectionRoot = Join-Path $tempBase "goj-release-inspection-$([guid]::NewGuid())"
$resolvedInspection = [System.IO.Path]::GetFullPath($inspectionRoot)
if (-not $resolvedInspection.StartsWith($tempBase, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to inspect a release archive outside the system temporary directory."
}

New-Item -ItemType Directory -Path $resolvedInspection | Out-Null
try {
  Expand-Archive -LiteralPath $resolvedArchive -DestinationPath $resolvedInspection
  $archiveExecutables = @(
    Get-ChildItem -LiteralPath $resolvedInspection -Filter "GardenOfJihan.exe" -File -Recurse
  )
  if ($archiveExecutables.Count -ne 1) {
    throw "Public release blocked: the ZIP must contain exactly one GardenOfJihan.exe."
  }

  $archivedExe = $archiveExecutables[0].FullName
  $archiveSignature = Assert-TrustedGardenSignature -Executable $archivedExe
  $looseHash = (Get-FileHash -LiteralPath $packageExe -Algorithm SHA256).Hash
  $archiveHash = (Get-FileHash -LiteralPath $archivedExe -Algorithm SHA256).Hash
  if ($looseHash -ne $archiveHash) {
    throw "Public release blocked: the ZIP does not contain the exact signed executable that was verified."
  }
  if ($looseSignature.SignerCertificate.Thumbprint -ne $archiveSignature.SignerCertificate.Thumbprint) {
    throw "Public release blocked: executable signer mismatch between the package directory and ZIP."
  }

  Write-Host "Trusted release publisher: $($archiveSignature.SignerCertificate.Subject)"
  Write-Host "Signed executable SHA256: $($archiveHash.ToLowerInvariant())"
} finally {
  if (Test-Path -LiteralPath $resolvedInspection) {
    Remove-Item -LiteralPath $resolvedInspection -Recurse -Force
  }
}
