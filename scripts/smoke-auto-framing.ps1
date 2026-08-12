param(
  [Parameter(Mandatory = $true)]
  [string]$FfmpegPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $FfmpegPath -PathType Leaf)) {
  throw "Auto-framing smoke test could not find FFmpeg at: $FfmpegPath"
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) "goj-framing-smoke-$([guid]::NewGuid())"
$resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$resolvedSmoke = [System.IO.Path]::GetFullPath($smokeRoot)
if (-not $resolvedSmoke.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to use an auto-framing smoke directory outside the system temporary directory."
}

New-Item -ItemType Directory -Path $resolvedSmoke | Out-Null
try {
  $outputFile = Join-Path $resolvedSmoke "auto-framing-smoke.mp4"
  $dynamicCenter = "if(lt(t\,1.000)\,0.20000+(0.60000)*(t-0.000)/1.000\,0.80000)"
  $cropX = "max(0\,min(iw-ow\,($dynamicCenter)*iw-ow/2))"
  & $FfmpegPath `
    -hide_banner `
    -loglevel error `
    -f lavfi `
    -i "testsrc2=s=1280x720:d=2:r=12" `
    -vf "scale=540:960:force_original_aspect_ratio=increase,crop=540:960:${cropX}:0" `
    -c:v libx264 `
    -pix_fmt yuv420p `
    -y `
    $outputFile
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputFile -PathType Leaf)) {
    throw "Bundled FFmpeg failed the dynamic vertical crop smoke test."
  }
} finally {
  if (Test-Path -LiteralPath $resolvedSmoke) {
    Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force
  }
}
