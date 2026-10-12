# Railway 관리자·현장 장치 키 설정 (2026-10-12)
# 사용: 저장소 폴더에서  powershell -NoProfile -File scripts\railway-keys.ps1
#   - 이 컴퓨터에서 강한 무작위 키(40자)를 만들어 Railway 서비스 변수로 넣고, 넣은 값이 맞는지 다시 읽어 확인합니다.
#   - 관리자 키는 내 문서 폴더의 텍스트 파일에 한 번 저장합니다. 저장소 안에는 저장하지 않습니다.
#   - 이미 키가 있으면 덮어쓸지 묻습니다(덮어쓰면 기존 관리자 주소·현장 프로그램 키가 바뀝니다).
# Railway 명령은 경고를 오류 출력으로 내보내므로, 성공 여부는 종료 코드로만 판단합니다.
param([string]$Service = 'memorial')
$ErrorActionPreference = 'Continue'

function Invoke-Railway {
  # 경고(오류 출력)는 버리고 표준 출력만 돌려준다. 실패하면 종료 코드로 알 수 있다.
  $out = & railway @args 2>$null
  return ,$out
}
function New-Secret([int]$bytes = 30) {
  $buf = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
  return ([Convert]::ToBase64String($buf)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
function Get-Vars {
  $json = (Invoke-Railway variable list --service $Service --json) -join "`n"
  if ($LASTEXITCODE -ne 0 -or -not $json) { throw 'Railway 변수 목록을 읽지 못했습니다. railway login 상태와 연결된 프로젝트를 확인해 주세요.' }
  return $json | ConvertFrom-Json
}
function Set-Secret([string]$key, [string]$value) {
  Invoke-Railway variable set "$key=$value" --service $Service --skip-deploys | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "$key 를 넣지 못했습니다." }
}

try {
  $vars = Get-Vars
  if ($vars.ADMIN_KEY -or $vars.EDGE_KEY) {
    $answer = Read-Host '이미 관리자·현장 키가 있습니다. 새 키로 바꿀까요? (예/아니오)'
    if ($answer -ne '예') { Write-Host '바꾸지 않았습니다.'; return }
  }

  $admin = New-Secret; $edge = New-Secret; $salt = New-Secret 18
  Set-Secret 'ADMIN_KEY' $admin
  Set-Secret 'EDGE_KEY' $edge
  Set-Secret 'SEED_SALT' $salt

  # 넣은 값이 정확히 들어갔는지 확인(값은 화면에 보이지 않음)
  $check = Get-Vars
  if ($check.ADMIN_KEY -ne $admin -or $check.EDGE_KEY -ne $edge -or $check.SEED_SALT -ne $salt) {
    throw 'Railway 에 들어간 값이 만든 값과 다릅니다. 다시 실행해 주세요.'
  }

  $note = Join-Path ([Environment]::GetFolderPath('MyDocuments')) '윤회당-railway-관리자키.txt'
  @(
    "윤회당 원격 추도식 (Railway) 관리자 정보 - $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    "관리자 키: $admin",
    "현장 장치 키(EDGE_KEY): $edge",
    '관리자 화면: https://<서비스 주소>/admin?key=<관리자 키>',
    '이 파일은 다른 사람과 공유하지 마세요.'
  ) | Set-Content -LiteralPath $note -Encoding UTF8

  Write-Host ''
  Write-Host '키 3개(ADMIN_KEY, EDGE_KEY, SEED_SALT)를 Railway 에 넣고, 들어간 값이 맞는지 확인했습니다.'
  Write-Host "관리자 키는 여기에 저장했습니다: $note"
  Write-Host '이제 Claude 에게 "키 넣었어"라고 알려 주세요.'
} catch {
  Write-Host ''
  Write-Host ('키를 넣지 못했습니다: ' + $_.Exception.Message)
  exit 1
}