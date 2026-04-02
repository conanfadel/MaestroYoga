param(
  [int]$Port = 8000,
  [switch]$Reload,
  [switch]$RecreateVenv,
  [string]$PythonSpec = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $root ".venv\\Scripts\\python.exe"
$bootstrapScript = Join-Path $PSScriptRoot "bootstrap_env.ps1"

if ($RecreateVenv) {
  & $bootstrapScript -Recreate -PythonSpec $PythonSpec
} else {
  & $bootstrapScript -PythonSpec $PythonSpec
}
if ($LASTEXITCODE -ne 0) {
  throw "Failed to prepare runtime environment."
}

$args = @("-m", "uvicorn", "backend.app.main:app", "--port", "$Port")
if ($Reload) {
  $args += "--reload"
}

Write-Host "Starting API with interpreter: $pythonExe"
$env:PYTHONNOUSERSITE = "1"
& $pythonExe @args
