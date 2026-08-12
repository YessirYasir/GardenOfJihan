param(
  [Parameter(Mandatory = $true)]
  [string]$PackageRoot,

  [int]$Port = 8876,

  [string]$AppDataRoot = ""
)

$ErrorActionPreference = "Stop"
$resolvedPackage = (Resolve-Path -LiteralPath $PackageRoot -ErrorAction Stop).Path
$launcher = Join-Path $resolvedPackage "START GARDEN OF JIHAN.cmd"
if ($Port -lt 1024 -or $Port -gt 65535) {
  throw "Portable smoke-test port must be between 1024 and 65535"
}

& (Join-Path $PSScriptRoot "verify-portable-bundle.ps1") -PackageRoot $resolvedPackage

$previousPort = $env:GOJ_PORT
$previousNoBrowser = $env:GOJ_NO_BROWSER
$previousLocalAppData = $env:LOCALAPPDATA
try {
  $env:GOJ_PORT = [string]$Port
  $env:GOJ_NO_BROWSER = "1"
  if ($AppDataRoot) {
    $resolvedAppData = [System.IO.Path]::GetFullPath($AppDataRoot)
  } else {
    $resolvedAppData = Join-Path ([System.IO.Path]::GetTempPath()) "goj-portable-smoke-$([Guid]::NewGuid().ToString('N'))"
  }
  New-Item -ItemType Directory -Force -Path $resolvedAppData | Out-Null
  $env:LOCALAPPDATA = $resolvedAppData

  $arguments = @("/d", "/c", "`"$launcher`"")
  # Start-Process -Wait waits for the entire descendant process tree on Windows.
  # The launcher intentionally detaches pythonw.exe, so wait for cmd.exe itself
  # instead of accidentally waiting for the application to exit.
  $starter = Start-Process -FilePath $env:ComSpec -ArgumentList $arguments -WorkingDirectory $resolvedPackage -WindowStyle Hidden -PassThru
  if (-not $starter.WaitForExit(10000)) {
    throw "Portable one-click launcher did not return control within 10 seconds"
  }
  if ($starter.ExitCode -ne 0) { throw "Portable one-click launcher exited with code $($starter.ExitCode)" }

  $origin = "http://127.0.0.1:$Port"
  $health = $null
  for ($attempt = 0; $attempt -lt 90; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
      $health = Invoke-RestMethod -Uri "$origin/api/health" -TimeoutSec 3
      if ($health.ok -eq $true) { break }
    } catch {}
  }
  if (
    $health.ok -ne $true -or
    $health.local -ne $true -or
    $health.product -ne "garden-of-jihan" -or
    $health.distribution -ne "portable-browser" -or
    $health.first_run -ne $true -or
    $health.auto_framing_available -ne $true -or
    $health.credential_protection_available -ne $true
  ) {
    throw "Portable browser application did not become fully healthy"
  }

  $homeMarkup = & curl.exe --fail --silent --show-error "$origin/"
  if ($LASTEXITCODE -ne 0 -or ($homeMarkup -join "`n") -notmatch "Garden of Jihan") {
    throw "Portable browser UI did not load"
  }
  $tokenMatch = [regex]::Match(($homeMarkup -join "`n"), '<meta name="goj-token" content="([^"]+)">')
  if (-not $tokenMatch.Success) { throw "Portable browser UI did not provide its local request token" }
  $headers = @{ "X-GOJ-Token" = $tokenMatch.Groups[1].Value; "Origin" = $origin }

  $welcome = Invoke-RestMethod -Method Post -Uri "$origin/api/onboarding/complete" -Headers $headers -TimeoutSec 5
  if ($welcome.complete -ne $true) { throw "Portable first-run welcome could not be completed" }
  $afterWelcome = Invoke-RestMethod -Uri "$origin/api/health" -TimeoutSec 3
  if ($afterWelcome.first_run -ne $false) { throw "Portable first-run preference was not persisted" }

  $quit = Invoke-RestMethod -Method Post -Uri "$origin/api/app/quit" -Headers $headers -TimeoutSec 5
  if ($quit.closing -ne $true) { throw "Portable browser application did not accept clean shutdown" }
  $closed = $false
  for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-RestMethod -Uri "$origin/api/health" -TimeoutSec 1 | Out-Null } catch { $closed = $true; break }
  }
  if (-not $closed) { throw "Portable browser application did not close cleanly" }
} finally {
  $env:GOJ_PORT = $previousPort
  $env:GOJ_NO_BROWSER = $previousNoBrowser
  $env:LOCALAPPDATA = $previousLocalAppData
}
