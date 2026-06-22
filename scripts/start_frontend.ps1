$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $root "frontend")
try {
  npm run dev -- --host 0.0.0.0 --port 5173
} finally {
  Pop-Location
}
