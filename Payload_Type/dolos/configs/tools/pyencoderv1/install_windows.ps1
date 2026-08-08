# PyEncoder Windows Tool Installation
# Idempotent: safe to run multiple times.
# Checks for py.exe (Python Launcher) and installs via winget if missing.

$ErrorActionPreference = "Stop"

# Check if py.exe is already available
try {
    $pyResult = & py.exe --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Output "TOOLS_OK: py.exe already available ($pyResult)"
        exit 0
    }
} catch {
    # py.exe not found, continue to install
}

# Try winget first
try {
    $wingetResult = & winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Output "TOOLS_OK: Python installed via winget"
        exit 0
    }
} catch {
    # winget not available or failed
}

Write-Output "TOOLS_INSTALL_FAILED: Could not install Python. Install py.exe manually or ensure winget is available."
exit 1
