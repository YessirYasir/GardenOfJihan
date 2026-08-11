param(
  [Parameter(Mandatory = $true)]
  [string]$FfmpegPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $FfmpegPath -PathType Leaf)) {
  throw "Caption smoke test could not find FFmpeg at: $FfmpegPath"
}

$filters = (& $FfmpegPath -hide_banner -filters 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $filters -notmatch "(?m)^\s*\.\.\.\s+subtitles\s") {
  throw "Bundled FFmpeg does not provide the libass subtitles filter required for captions."
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) "goj-caption-smoke-$([guid]::NewGuid())"
$resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$resolvedSmoke = [System.IO.Path]::GetFullPath($smokeRoot)
if (-not $resolvedSmoke.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to use a caption smoke directory outside the system temporary directory."
}

New-Item -ItemType Directory -Path $resolvedSmoke | Out-Null
try {
  $captionFile = Join-Path $resolvedSmoke "unicode.ass"
  $outputFile = Join-Path $resolvedSmoke "caption-smoke.mp4"
  @"
[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Segoe UI,28,&H00FFFFFF,&H000000FF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,3,1,2,30,30,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Caption,,0,0,0,,Garden of Jihan · جيهان · Soomaali
"@ | Set-Content -LiteralPath $captionFile -Encoding utf8

  $filterPath = ([System.IO.Path]::GetFullPath($captionFile)).Replace("\", "/").Replace(":", "\:")
  & $FfmpegPath `
    -hide_banner `
    -loglevel error `
    -f lavfi `
    -i "color=c=0x244A35:s=640x360:d=1" `
    -vf "subtitles=filename='$filterPath'" `
    -c:v libx264 `
    -pix_fmt yuv420p `
    -y `
    $outputFile
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputFile -PathType Leaf)) {
    throw "Bundled FFmpeg failed the styled Unicode caption render smoke test."
  }
} finally {
  if (Test-Path -LiteralPath $resolvedSmoke) {
    Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force
  }
}
