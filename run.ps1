# 봉안당 시연 시작: 서버 + 현장 카메라 프로그램을 띄우고 브라우저에서 시작 화면을 엽니다.
# (더블클릭: 시작.bat  /  PowerShell: .\run.ps1)
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$health = "http://127.0.0.1:8765/health"
function Up { try { (Invoke-WebRequest $health -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $false } }

if (Up) { Write-Host "서버가 이미 켜져 있습니다." }
else {
  Write-Host "서버를 켜는 중…"
  Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit", "-Command", "`$env:PYTHONIOENCODING='utf-8'; Set-Location '$root'; python -m uvicorn server.main:app --host 127.0.0.1 --port 8765 --reload --reload-dir server"
  $i = 0; while (-not (Up) -and $i -lt 60) { Start-Sleep -Milliseconds 500; $i++ }
  if (-not (Up)) { Write-Host "서버가 30초 안에 뜨지 않았습니다. 최소화된 '서버' 창의 오류를 확인하세요."; Read-Host "Enter를 누르면 닫힙니다"; exit 1 }
}

$edge = Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*edge.agent*' }
if ($edge) { Write-Host "현장 카메라 프로그램이 이미 켜져 있습니다." }
else {
  Write-Host "현장 카메라 프로그램(웹캠)을 켜는 중…"
  Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit", "-Command", "`$env:PYTHONIOENCODING='utf-8'; Set-Location '$root'; python -m edge.agent"
}

Write-Host "시작 화면을 엽니다: http://127.0.0.1:8765/"
Start-Process "http://127.0.0.1:8765/"
