# 서버와 현장 프로그램을 창 두 개로 실행합니다.
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PYTHONIOENCODING='utf-8'; Set-Location '$root'; python -m uvicorn server.main:app --host 127.0.0.1 --port 8765 --reload --reload-dir server"
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PYTHONIOENCODING='utf-8'; Set-Location '$root'; python -m edge.agent"
Write-Host "서버: http://127.0.0.1:8765   관리자: http://127.0.0.1:8765/admin?key=admin1234"
Write-Host "초대 링크는  python -m server.seed  로 확인합니다."
