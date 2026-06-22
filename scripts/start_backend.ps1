$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\26423\.conda\envs\contract_audit_base\python.exe"

if (-not (Test-Path $python)) {
  throw "Conda environment contract_audit_base was not found at $python"
}

Push-Location (Join-Path $root "backend")
try {
  & $python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
} finally {
  Pop-Location
}
