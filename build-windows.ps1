$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $projectRoot
try {
  npm.cmd run check
  if ($LASTEXITCODE -ne 0) { throw "Svelte validation failed." }

  npm.cmd run tauri -- build
  if ($LASTEXITCODE -ne 0) { throw "Tauri build failed." }

  $releaseRoot = Join-Path $projectRoot "src-tauri\target\release"
  $tauriConfig = Get-Content (Join-Path $projectRoot "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json
  $releaseVersion = $tauriConfig.version
  $portableRoot = Join-Path $releaseRoot "portable"
  $portableCompiler = Join-Path $portableRoot "compiler"
  New-Item -ItemType Directory -Force -Path $portableCompiler | Out-Null
  Copy-Item -LiteralPath (Join-Path $releaseRoot "handfont.exe") -Destination (Join-Path $portableRoot "ky.handwriter.exe") -Force
  Copy-Item -LiteralPath (Join-Path $projectRoot "compiler\dist\handfont-compiler.exe") -Destination (Join-Path $portableCompiler "handfont-compiler.exe") -Force

  $portableZip = Join-Path $releaseRoot "ky.handwriter_${releaseVersion}_x64-portable.zip"
  Compress-Archive -Path (Join-Path $portableRoot "*") -DestinationPath $portableZip -Force
  Write-Host "Portable build: $portableZip"
  Write-Host "Installers: $(Join-Path $releaseRoot 'bundle')"
} finally {
  Pop-Location
}
