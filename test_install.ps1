# Test installation script for PowerShell (Windows)

Write-Host "=== Testing agent-setting package ===" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "Python version:" -ForegroundColor Yellow
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Python not found. Please install Python 3.10+." -ForegroundColor Red
    exit 1
}
Write-Host ""

# Test imports
Write-Host "1. Testing imports..." -ForegroundColor Yellow
try {
    python -c "from agent_setting import __version__, main, detect_system; print(f'Version: {__version__}')"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Import test failed!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

# Test module execution
Write-Host ""
Write-Host "2. Testing module execution..." -ForegroundColor Yellow
try {
    python -c "from agent_setting.detector import detect_system; s, u = detect_system(); print(f'System: {s}, User: {u}')"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Module test failed!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== All tests passed! ===" -ForegroundColor Green
Write-Host ""

Write-Host "To install with uv:" -ForegroundColor Cyan
Write-Host "  uv pip install ."
Write-Host ""
Write-Host "To install with pip:" -ForegroundColor Cyan
Write-Host "  pip install ."
Write-Host ""
Write-Host "To run:" -ForegroundColor Cyan
Write-Host "  agent-setting"
Write-Host "  python -m agent_setting"
