# 봉안당 종료: 서버와 현장 카메라 프로그램을 끕니다(바탕화면 '봉안당 종료' 아이콘).
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
  Where-Object { $_.CommandLine -like '*uvicorn server.main*' -or $_.CommandLine -like '*edge.agent*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
