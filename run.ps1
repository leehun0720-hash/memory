# 봉안당 접속: 서버와 현장 카메라 프로그램을 창 없이 켜고(이미 켜져 있으면 건너뜀) 브라우저에서 시작 화면을 엽니다.
# 바탕화면 '봉안당 접속' 아이콘이 이 파일을 실행합니다. 로그: data\server.log · data\edge.log (UTF-8)
param([switch]$Admin)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
New-Item -ItemType Directory -Force "$root\data" | Out-Null
$health = "http://127.0.0.1:8765/health"
function Up { try { (Invoke-WebRequest $health -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $false } }
function Running($needle) { Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like "*$needle*" } }

if (-not (Up)) {
  Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", "8765" `
    -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$root\data\server.out.log" -RedirectStandardError "$root\data\server.log"
  $i = 0; while (-not (Up) -and $i -lt 60) { Start-Sleep -Milliseconds 500; $i++ }
}
if (-not (Running "edge.agent")) {
  Start-Process -FilePath "python" -ArgumentList "-m", "edge.agent" `
    -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$root\data\edge.out.log" -RedirectStandardError "$root\data\edge.log"
}
if (Up) {
  if ($Admin) {
    # Read the current local configuration; never store the admin key in shortcuts.
    $adminKey = & python -c "from server.config import ADMIN_KEY; print(ADMIN_KEY)"
    if ($LASTEXITCODE -eq 0 -and $adminKey) {
      Start-Process ("http://127.0.0.1:8765/admin?key=" + [Uri]::EscapeDataString(($adminKey -join "").Trim()))
    } else {
      Add-Type -AssemblyName System.Windows.Forms
      [System.Windows.Forms.MessageBox]::Show("관리자 설정을 읽지 못했습니다. 시작 화면에서 관리자 콘솔을 열어 주세요.", "봉안당 관리자") | Out-Null
      Start-Process "http://127.0.0.1:8765/"
    }
  } else { Start-Process "http://127.0.0.1:8765/" }
}
else {
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.MessageBox]::Show("서버가 켜지지 않았습니다. data\server.log 를 확인해 주세요.", "봉안당 접속") | Out-Null
  Start-Process notepad "$root\data\server.log"
}
