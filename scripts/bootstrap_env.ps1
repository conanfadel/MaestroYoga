param(
  [switch]$Recreate,
  [switch]$SkipInstall,
  [string]$PythonSpec = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $root ".venv"
$pythonExe = Join-Path $venvPath "Scripts\\python.exe"
$requirementsFile = Join-Path $root "requirements.txt"
$requirementsStamp = Join-Path $venvPath ".requirements.sha256"

function Resolve-HostPython {
  param([string]$RequestedSpec)

  function Test-PythonCandidate {
    param([string]$Binary, [string]$VersionArg)
    $probe = "import venv, ensurepip, ssl, pyexpat; print('ok')"
    try {
      if ($Binary -eq "py") {
        & py "-$VersionArg" -c $probe *> $null
      } else {
        & $Binary -c $probe *> $null
      }
      return $LASTEXITCODE -eq 0
    } catch {
      return $false
    }
  }

  if ($RequestedSpec) {
    if ($RequestedSpec.StartsWith("py")) {
      $requestedArg = $RequestedSpec.Substring(2).TrimStart("-")
      if (Test-PythonCandidate -Binary "py" -VersionArg $requestedArg) {
        return @("py", $requestedArg)
      }
      throw "Requested Python '$RequestedSpec' is not usable on this machine."
    }
    if (Test-PythonCandidate -Binary $RequestedSpec -VersionArg "") {
      return @($RequestedSpec, "")
    }
    throw "Requested Python binary '$RequestedSpec' is not usable on this machine."
  }

  $preferred = @("3.12", "3.11", "3.10", "3.14", "3")
  foreach ($ver in $preferred) {
    if (Test-PythonCandidate -Binary "py" -VersionArg $ver) {
      return @("py", $ver)
    }
  }

  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd -and (Test-PythonCandidate -Binary "python" -VersionArg "")) {
    return @("python", "")
  }

  throw "Could not find a usable Python launcher. Install Python 3.10+ or make 'py'/'python' available in PATH."
}

function Test-VenvHealthy {
  if (-not (Test-Path $pythonExe)) {
    return $false
  }
  try {
    & $pythonExe -c "import sys; import pip; print(sys.executable)" *> $null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  }
}

function Ensure-CommonAppDataRegistry {
  if ($env:OS -ne "Windows_NT") {
    return
  }
  $keyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
  $valueName = "Common AppData"
  $existing = (Get-ItemProperty -Path $keyPath -Name $valueName -ErrorAction SilentlyContinue).$valueName
  if (-not $existing) {
    New-ItemProperty -Path $keyPath -Name $valueName -Value $env:ProgramData -PropertyType String -Force | Out-Null
    Write-Host "Applied Windows compatibility fix: '$valueName' => '$env:ProgramData'" -ForegroundColor Yellow
  }
}

function New-ProjectVenv {
  param([string]$Launcher, [string]$VersionArg)

  if (Test-Path $venvPath) {
    Remove-Item -Recurse -Force $venvPath
  }

  Write-Host "Creating virtual environment in .venv ..."
  if ($Launcher -eq "py") {
    & py "-$VersionArg" -m venv --without-pip $venvPath
  } else {
    & $Launcher -m venv --without-pip $venvPath
  }
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create virtual environment at '$venvPath'."
  }

  Ensure-CommonAppDataRegistry
  & $pythonExe -m ensurepip --upgrade --default-pip
  if ($LASTEXITCODE -ne 0) {
    throw "ensurepip failed while preparing '$pythonExe'."
  }
}

function Get-RequirementsHash {
  if (-not (Test-Path $requirementsFile)) {
    return ""
  }
  return (Get-FileHash -Algorithm SHA256 $requirementsFile).Hash
}

$resolved = Resolve-HostPython -RequestedSpec $PythonSpec
$launcher = $resolved[0]
$launcherArg = $resolved[1]

if ($Recreate) {
  New-ProjectVenv -Launcher $launcher -VersionArg $launcherArg
} elseif (-not (Test-VenvHealthy)) {
  Write-Host "Detected missing/broken .venv. Rebuilding it for this machine ..." -ForegroundColor Yellow
  New-ProjectVenv -Launcher $launcher -VersionArg $launcherArg
}

if (Test-Path $pythonExe) {
  & $pythonExe -c "import pip" *> $null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "pip is missing in .venv. Repairing with ensurepip ..." -ForegroundColor Yellow
    Ensure-CommonAppDataRegistry
    & $pythonExe -m ensurepip --upgrade --default-pip
    if ($LASTEXITCODE -ne 0) {
      Write-Host "pip repair failed. Recreating .venv ..." -ForegroundColor Yellow
      New-ProjectVenv -Launcher $launcher -VersionArg $launcherArg
    }
  }
}

if (-not $SkipInstall) {
  $targetHash = Get-RequirementsHash
  $currentHash = ""
  if (Test-Path $requirementsStamp) {
    $currentHash = (Get-Content -Raw $requirementsStamp).Trim()
  }

  if ($targetHash -and $targetHash -eq $currentHash) {
    Write-Host "Dependencies already up to date (requirements hash matched)."
  } else {
    Write-Host "Installing dependencies ..."
    & $pythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
      throw "pip upgrade failed for '$pythonExe'."
    }
    if ($targetHash) {
      & $pythonExe -m pip install -r $requirementsFile
      if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed from '$requirementsFile'."
      }
      Set-Content -Path $requirementsStamp -Value $targetHash -NoNewline
    }
  }
}

Write-Host "Done."
Write-Host "Interpreter: $pythonExe"
