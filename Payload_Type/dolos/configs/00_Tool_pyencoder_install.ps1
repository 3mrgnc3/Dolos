# Dolos PyEncoder Install Script for Windows
# Installs Python via winget and deploys the encoder script.
# Run once on each target Windows machine.

Write-Host "[DOLOS-INSTALL] Starting PyEncoder setup..." -ForegroundColor Cyan

# Update winget
Write-Host "[DOLOS-INSTALL] Updating winget source..." -ForegroundColor Gray
winget source update

# Install Python 3.12
Write-Host "[DOLOS-INSTALL] Installing Python 3.12..." -ForegroundColor Gray
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements

# Create target directory
Write-Host "[DOLOS-INSTALL] Creating C:\tools\dolos\" -ForegroundColor Gray
New-Item -ItemType Directory -Force -Path "C:\tools\dolos" | Out-Null

# Copy encoder script from workdir (uploaded by Dolos SFTP)
$workdir = $PSScriptRoot
$encoderSrc = Join-Path $workdir "encoder.py"
$dest = "C:\tools\dolos\encoder.py"

if (Test-Path $encoderSrc) {
    Copy-Item $encoderSrc $dest -Force
    Write-Host "[DOLOS-INSTALL] Copied encoder.py to $dest" -ForegroundColor Green
} else {
    Write-Host "[DOLOS-INSTALL] encoder.py not found in workdir - you may need to copy it manually" -ForegroundColor Yellow
}

Write-Host "[DOLOS-INSTALL] Setup complete. Test with: py.exe C:\tools\dolos\encoder.py" -ForegroundColor Cyan