$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$envPath = Join-Path $projectRoot ".env"
if (Test-Path $envPath) {
  Get-Content $envPath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
      return
    }

    $key, $value = $line.Split("=", 2)
    $key = $key.Trim()
    $value = $value.Trim().Trim("'").Trim('"')
    if ($key -and -not (Test-Path "Env:$key")) {
      Set-Item -Path "Env:$key" -Value $value
    }
  }
}

$masterProfileDir = if ($env:MASTER_PROFILE_DIR) { $env:MASTER_PROFILE_DIR } elseif ($env:WEB_LLM_MASTER_PROFILE_DIR) { $env:WEB_LLM_MASTER_PROFILE_DIR } else { ".profiles/masters/doubao-edge" }
$cdpUrl = if ($env:CDP_URL) { $env:CDP_URL } elseif ($env:WEB_LLM_CDP_URL) { $env:WEB_LLM_CDP_URL } else { "http://127.0.0.1:9222" }

$profilePath = $masterProfileDir
if (-not [System.IO.Path]::IsPathRooted($profilePath)) {
  $profilePath = Join-Path $projectRoot $profilePath
}
$profilePath = [System.IO.Path]::GetFullPath($profilePath)

$cdpUri = [System.Uri]$cdpUrl
$port = $cdpUri.Port
$browserCandidates = @(
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)

$browserPath = $browserCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browserPath) {
  throw "Microsoft Edge not found in the default install locations."
}

New-Item -ItemType Directory -Force -Path $profilePath | Out-Null

Write-Host "Browser path: $browserPath"
Write-Host "Profile path: $profilePath"
Write-Host "CDP URL: $cdpUrl"

Start-Process -FilePath $browserPath -ArgumentList "--remote-debugging-port=$port", "--user-data-dir=$profilePath", "https://www.doubao.com/chat/"
