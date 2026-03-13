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

if (-not $env:PYTHONPATH) {
  $env:PYTHONPATH = "src"
}

$hostValue = if ($env:HOST) { $env:HOST } elseif ($env:WEB_LLM_HOST) { $env:WEB_LLM_HOST } else { "127.0.0.1" }
$portValue = if ($env:PORT) { $env:PORT } elseif ($env:WEB_LLM_PORT) { $env:WEB_LLM_PORT } else { "8000" }
$masterProfileDir = if ($env:MASTER_PROFILE_DIR) { $env:MASTER_PROFILE_DIR } elseif ($env:WEB_LLM_MASTER_PROFILE_DIR) { $env:WEB_LLM_MASTER_PROFILE_DIR } else { ".profiles/masters/doubao-edge" }
$runtimeProfileDir = if ($env:RUNTIME_PROFILE_DIR) { $env:RUNTIME_PROFILE_DIR } elseif ($env:WEB_LLM_RUNTIME_PROFILE_ROOT) { $env:WEB_LLM_RUNTIME_PROFILE_ROOT } else { ".profiles/runtime/doubao-edge" }
$cdpUrl = if ($env:CDP_URL) { $env:CDP_URL } elseif ($env:WEB_LLM_CDP_URL) { $env:WEB_LLM_CDP_URL } else { "http://127.0.0.1:9222" }
$browserMode = if ($env:BROWSER_MODE) { $env:BROWSER_MODE } elseif ($env:WEB_LLM_BROWSER_MODE) { $env:WEB_LLM_BROWSER_MODE } else { "cdp" }

Write-Host "Project root: $projectRoot"
Write-Host "HOST: $hostValue"
Write-Host "PORT: $portValue"
Write-Host "MASTER_PROFILE_DIR: $masterProfileDir"
Write-Host "RUNTIME_PROFILE_DIR: $runtimeProfileDir"
Write-Host "CDP_URL: $cdpUrl"
Write-Host "BROWSER_MODE: $browserMode"

py -m uvicorn web_adapter.main:app --host $hostValue --port $portValue
