$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

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

Push-Location (Join-Path $root "backend")
try {
  & $python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
} finally {
  Pop-Location
}
