$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root ".run-logs\sessions"

function Resolve-PythonCommand {
  if ($env:PYTHON_EXECUTABLE) {
    return $env:PYTHON_EXECUTABLE
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return $python.Source
  }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return $py.Source
  }
  throw "Python was not found. Set PYTHON_EXECUTABLE or add python to PATH."
}

$python = Resolve-PythonCommand

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$backendOut = Join-Path $logsDir "$stamp-backend.stdout.log"
$backendErr = Join-Path $logsDir "$stamp-backend.stderr.log"
$frontendOut = Join-Path $logsDir "$stamp-frontend.stdout.log"
$frontendErr = Join-Path $logsDir "$stamp-frontend.stderr.log"

Start-Process -FilePath $python `
  -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8010" `
  -WorkingDirectory (Join-Path $root "backend") `
  -RedirectStandardOutput $backendOut `
  -RedirectStandardError $backendErr `
  -WindowStyle Hidden

Start-Process -FilePath "npm.cmd" `
  -ArgumentList "run","dev","--","--host","0.0.0.0","--port","5173" `
  -WorkingDirectory (Join-Path $root "frontend") `
  -RedirectStandardOutput $frontendOut `
  -RedirectStandardError $frontendErr `
  -WindowStyle Hidden

Write-Host "Backend  : http://127.0.0.1:8010  or http://<LAN-IP>:8010"
Write-Host "Frontend : http://127.0.0.1:5173  or http://<LAN-IP>:5173"
Write-Host "Session logs:"
Write-Host "  $backendOut"
Write-Host "  $backendErr"
Write-Host "  $frontendOut"
Write-Host "  $frontendErr"
