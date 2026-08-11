param(
  [Parameter(Mandatory = $true)]
  [string]$PackageRoot,

  [int]$Port = 8765,

  [string]$AppDataRoot = ""
)

$ErrorActionPreference = "Stop"

$resolvedPackage = (Resolve-Path -LiteralPath $PackageRoot -ErrorAction Stop).Path
$executable = Join-Path $resolvedPackage "GardenOfJihan.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
  throw "Packaged executable smoke test could not find GardenOfJihan.exe."
}
if ($Port -lt 1024 -or $Port -gt 65535) {
  throw "Packaged executable smoke-test port must be between 1024 and 65535."
}

$previousPort = $env:GOJ_PORT
$previousNoBrowser = $env:GOJ_NO_BROWSER
$previousLocalAppData = $env:LOCALAPPDATA
$process = $null
try {
  $env:GOJ_PORT = [string]$Port
  $env:GOJ_NO_BROWSER = "1"
  if ($AppDataRoot) {
    $resolvedAppData = [System.IO.Path]::GetFullPath($AppDataRoot)
    New-Item -ItemType Directory -Force -Path $resolvedAppData | Out-Null
    $env:LOCALAPPDATA = $resolvedAppData
  }

  $process = Start-Process -FilePath $executable -WindowStyle Hidden -PassThru
  $origin = "http://127.0.0.1:$Port"
  $healthy = $false
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Seconds 1
    if ($process.HasExited) {
      throw "GardenOfJihan.exe exited before becoming healthy."
    }
    try {
      $health = Invoke-RestMethod -Uri "$origin/api/health" -TimeoutSec 3
      if (
        $health.ok -eq $true -and
        $health.local -eq $true -and
        $health.auto_framing_available -eq $true -and
        $health.credential_protection_available -eq $true
      ) {
        $healthy = $true
        break
      }
    } catch {}
  }
  if (-not $healthy) {
    throw "Packaged application did not become healthy in time."
  }

  $homeMarkup = & curl.exe --fail --silent --show-error "$origin/"
  if ($LASTEXITCODE -ne 0 -or ($homeMarkup -join "`n") -notmatch "Garden of Jihan") {
    throw "Packaged UI did not load."
  }
  $tokenMatch = [regex]::Match(
    ($homeMarkup -join "`n"),
    '<meta name="goj-token" content="([^"]+)">'
  )
  if (-not $tokenMatch.Success) {
    throw "Packaged UI did not provide its local request token."
  }

  $token = $tokenMatch.Groups[1].Value
  $quit = Invoke-RestMethod `
    -Method Post `
    -Uri "$origin/api/app/quit" `
    -Headers @{ "X-GOJ-Token" = $token; "Origin" = $origin } `
    -TimeoutSec 5
  if ($quit.closing -ne $true) {
    throw "Packaged application did not accept a clean shutdown request."
  }
  if (-not $process.WaitForExit(15000)) {
    throw "Packaged application did not exit cleanly after the shutdown request."
  }
  if ($process.ExitCode -ne 0) {
    throw "Packaged application exited with code $($process.ExitCode)."
  }
} finally {
  if ($process -and -not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
  }
  $env:GOJ_PORT = $previousPort
  $env:GOJ_NO_BROWSER = $previousNoBrowser
  $env:LOCALAPPDATA = $previousLocalAppData
}
