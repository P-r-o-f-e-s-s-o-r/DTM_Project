# ============================================================================
# GridSense - Launch Full Simulated Pipeline (PowerShell)
# Starts: Mosquitto -> Bridge -> Fake ESP32 -> Risk API -> Backend API -> Frontend
# ============================================================================

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Starting GridSense Autonomous Feeder Monitoring Stack  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Resolve-Path "$ScriptDir\.."
Set-Location $RootDir

# Locate Python
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe -or (Test-Path "C:\Users\Mukeshwar Raudra\AppData\Local\Programs\Python\Python313\python.exe")) {
    $pythonExe = "C:\Users\Mukeshwar Raudra\AppData\Local\Programs\Python\Python313\python.exe"
}
Write-Host "[1/6] Python Runtime: $pythonExe" -ForegroundColor Yellow

# 1. Start Mosquitto MQTT Broker
$mosquittoExe = "$env:USERPROFILE\tools\mosquitto\mosquitto.exe"
if (-not (Test-Path $mosquittoExe)) {
    $mosquittoExe = "C:\Program Files\mosquitto\mosquitto.exe"
}
$mosqProc = Get-Process mosquitto -ErrorAction SilentlyContinue
if (-not $mosqProc) {
    Write-Host "[2/6] Starting Mosquitto MQTT Broker (port 1883)..." -ForegroundColor Yellow
    Start-Process -FilePath $mosquittoExe -ArgumentList "-c `"$RootDir\mosquitto.conf`" -v" -WindowStyle Hidden
} else {
    Write-Host "[2/6] Mosquitto MQTT Broker is already running (PID: $($mosqProc[0].Id))." -ForegroundColor Green
}
Start-Sleep -Seconds 2

# 2. Start MQTT-to-MySQL Bridge
Write-Host "[3/6] Starting MQTT -> MySQL Telemetry Bridge..." -ForegroundColor Yellow
$bridgeProc = Start-Process -FilePath $pythonExe -ArgumentList "ingestion\mqtt_to_mysql.py" -WorkingDirectory $RootDir -PassThru
Start-Sleep -Seconds 2

# 3. Start Risk Prediction Microservice (OpenRouter LLM + Local RF)
Write-Host "[4/6] Starting AI Risk Prediction Microservice (Port 8001)..." -ForegroundColor Yellow
$riskProc = Start-Process -FilePath $pythonExe -ArgumentList "-m uvicorn services.risk_api.main:app --host 127.0.0.1 --port 8001" -WorkingDirectory $RootDir -PassThru
Start-Sleep -Seconds 3

# 4. Start Backend Orchestration API (REST + WebSocket)
Write-Host "[5/6] Starting Backend Orchestration API (Port 8000)..." -ForegroundColor Yellow
$backendProc = Start-Process -FilePath $pythonExe -ArgumentList "-m uvicorn services.backend_api.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $RootDir -PassThru
Start-Sleep -Seconds 3

# 5. Start Simulated ESP32 Publisher
Write-Host "[6/6] Starting Simulated ESP32 Feeder Publisher..." -ForegroundColor Yellow
$simProc = Start-Process -FilePath $pythonExe -ArgumentList "ingestion\fake_esp32.py" -WorkingDirectory $RootDir -PassThru
Start-Sleep -Seconds 2

# 6. Start React Frontend Dashboard
Write-Host "`nAll backend services online! Launching Frontend Dashboard..." -ForegroundColor Green
Write-Host "Opening Dashboard at: http://localhost:5173" -ForegroundColor Cyan
Write-Host "Press Ctrl+C in this terminal when finished to stop all services.`n" -ForegroundColor DarkGray

try {
    npm --prefix frontend run dev
} finally {
    Write-Host "`nShutting down background services..." -ForegroundColor Yellow
    Stop-Process -Id $simProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $riskProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $bridgeProc.Id -Force -ErrorAction SilentlyContinue
    Write-Host "All GridSense services stopped." -ForegroundColor Green
}
