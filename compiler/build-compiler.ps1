$ErrorActionPreference = "Stop"

$compilerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $compilerRoot ".venv\Scripts\python.exe"
$output = Join-Path $compilerRoot "dist\handfont-compiler.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw "Compiler virtual environment not found at $python. Create it and install compiler/requirements.txt first."
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is not installed. Run: compiler\.venv\Scripts\python.exe -m pip install -r compiler\requirements-build.txt"
}

Push-Location $compilerRoot
try {
  & $python -m PyInstaller --noconfirm --clean --onefile --name handfont-compiler --distpath dist --workpath build\pyinstaller --specpath build pyinstaller_entry.py
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

  $health = '{"command":"health-check"}' | & $output | ConvertFrom-Json
  if (-not $health.success) { throw "The packaged compiler failed its health check." }
  Write-Host "Packaged compiler: $output"
} finally {
  Pop-Location
}
