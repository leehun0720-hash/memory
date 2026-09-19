# MVP용 웹캠 선정 가이드

조사일: 2026-09-19. 가격은 다나와 최저가 기준 참고값이며 구매 직전 다시 확인해야 합니다.

## 이 서비스에서 카메라에 요구되는 것

봉안함 벽면은 **움직이지 않는 피사체**입니다. 화상회의용 웹캠의 장점(자동 초점, 얼굴 추적, 자동 밝기)은 여기서 대부분 단점이 됩니다.

| 요구 조건 | 이유 | 확인 방법 |
|---|---|---|
| **4K(3840×2160)** | 벽 3m를 한 대가 맡으면 30cm 칸이 가로 380픽셀 안팎. 1080p면 190픽셀로 휴대폰에서 흐릿함 | 스펙표 |
| **고정 초점 또는 수동 초점 잠금** | 자동 초점은 조명 변화·유리 반사에 '초점 헌팅'을 일으켜 사진이 주기적으로 흐려짐 | 스펙표에 fixed focus / manual focus, 또는 제조사 앱에서 AF 끄기 가능 여부 |
| **노출·화이트밸런스 수동 고정** | 안치실 조명이 노란색이면 자동 WB가 칸마다 색을 바꿈. 10초마다 찍는 사진의 색이 흔들리면 신뢰감이 떨어짐 | 제조사 앱(Logi Tune, Camera Hub 등) 또는 UVC 컨트롤 |
| **UVC 표준(드라이버 없음)** | 리눅스 소형 컴퓨터에서 OpenCV로 바로 열림 | 대부분의 USB 웹캠은 UVC |
| **시야각 80~90°** | 3m 벽을 1.5m 거리에서 담으려면 약 90° 필요. 더 넓으면 가장자리 왜곡, 더 좁으면 거리를 더 확보해야 함 | 스펙표 FOV |
| 저조도 성능(센서 크기 1/1.8″ 이상) | 안치실은 대개 어둡고, 야간 확인 요청이 있음 | 센서 규격 |
| 삼각대 나사(1/4″) | 벽·천장 거치대에 고정 | 스펙표 |

## 추천 모델

### 1순위 — Elgato Facecam 4K (약 28만~29만 원)

- Sony STARVIS 2 1/1.8″ 센서, **고정 초점 프라임 렌즈**(초점 헌팅 없음), 90° 시야각, 4K60, 최소 초점 거리 30cm(4K)
- Camera Hub 앱에서 노출·ISO·화이트밸런스를 DSLR처럼 수동 고정 가능, 49mm 필터 나사가 있어 **편광 필터 장착 가능**(유리문 반사 대응 — 계획서 4장 '현장 시험 항목')
- 비압축 출력 지원. 이 서비스의 요구 조건(고정 피사체, 수동 제어, 반사 대응)에 가장 잘 맞습니다.
- 주의: 고정 초점이라 벽에서 30cm 이내로 붙이면 흐려짐. 실제 설치 거리(1~2m)에서는 문제 없음.

### 2순위 — Logitech MX Brio (약 31만 원)

- 4K30, 1/2.7″ 센서, 90° 시야각, 국내 정발·AS 편리
- 자동 초점이 헌팅한다는 리뷰가 있으므로 **Logi Tune에서 수동 초점으로 잠가야** 함
- Facecam 4K보다 센서가 작아 저조도에서 불리. 국내 구매·교체 편의성이 중요하면 선택

### 보조 시험용 — Insta360 Link 2 (해외가 $199~233)

- 4K, 짐벌 PTZ. 계획서의 "회전 카메라(PTZ)는 보조로만" 비교 시험용
- 한 대로 방 전체를 훑을 수 있지만 동시 접속에는 부적합하다는 점을 시연으로 확인하는 용도
- 제례 공간 카메라(스님·제단을 따라가는 중계)로는 오히려 적합

### 지금 당장 — 노트북 내장 웹캠 (0원)

- 이 MVP는 내장 1080p 웹캠으로 이미 동작합니다(`USB2.0 FHD UVC WebCam`).
- 칸 6개 시연은 충분하고, 4K 웹캠으로 바꿀 때 코드 변경은 `.env`의 `CAPTURE_WIDTH/HEIGHT`뿐입니다.

### 피할 모델

- 1080p 이하 저가 웹캠(C920 계열 등): 3m 벽을 맡기기엔 해상도 부족. 벽 1.5m당 1대로 늘리면 카메라 수가 두 배.
- 얼굴 추적·자동 프레이밍이 꺼지지 않는 모델(일부 OBSBOT 계열): 고정 화면이 흔들려 칸 좌표가 어긋남.

## 실제 설치(2단계)에서는 웹캠이 아니라 IP 카메라

카메라 55대를 벽·천장에 달 때 USB 웹캠은 맞지 않습니다.

| 문제 | 이유 |
|---|---|
| USB 케이블 길이 | 5m 넘으면 신호 불안. 55대를 컴퓨터 하나에 물릴 수 없음 |
| 전원 | 웹캠마다 USB 전원 필요 |
| 내구성 | 24시간 상시 가동용이 아님 |

대안: **PoE 방식 4K(8MP) 고정 렌즈 IP 카메라**(Hanwha Vision·Hikvision·Dahua 등, RTSP 출력). 랜선 하나로 전원과 영상을 보내고, 현장 소형 컴퓨터가 RTSP를 받아 지금과 같은 방식으로 잘라냅니다. `edge/agent.py`의 `open_camera()`에서 장치 번호 대신 RTSP 주소를 넘기면 되도록 구조를 잡아 두었습니다. 단가는 현장 실측 뒤 견적으로 확정합니다(계획서 6장 2단계 장비비 2,700만~4,100만 원 범위와 비교).

## 구매 뒤 첫 시험 체크리스트

- [ ] 제조사 앱에서 자동 초점·자동 노출·자동 WB 끄고 값 고정
- [ ] `.env`의 `CAPTURE_WIDTH=3840`, `CAPTURE_HEIGHT=2160`으로 바꾸고 `python -m edge.agent` 실행
- [ ] 관리자 콘솔 '칸 좌표 등록'에서 격자 생성 → 유족 앱에서 칸 사진 선명도 확인
- [ ] 유리문 반사: 편광 필터 장착 전후 비교 사진 저장
- [ ] 야간(조명 최소) 상태 사진 저장
- [ ] 사람이 지나갈 때 '참배객 있음' 전환과 복귀 시간(기본 3초) 확인

## 출처

- [Tom's Guide — Best webcams 2026](https://www.tomsguide.com/computing/peripherals/best-webcams)
- [Tom's Hardware — Best Webcams 2026](https://www.tomshardware.com/best-picks/best-webcams)
- [YoloLiv — Best 4K Webcams in 2026](https://www.yololiv.com/blog/best-4k-webcams-in-2026-tested-for-streaming-podcasting-and-calls/)
- [The Gadgeteer — Best Webcams for Working from Home 2026](https://the-gadgeteer.com/2026/06/12/best-webcams-for-working-from-home-2026/)
- [B&H — Facecam Pro vs MX Brio vs Link 2 vs OBSBOT Meet 4K](https://www.bhphotovideo.com/c/compare/Elgato_Facecam+Pro_vs_Logitech_MX+Brio+4K_vs_Insta360_LINK+2_vs_OBSBOT_Meet+4K/BHitems/1792446-REG_1835811-REG_1846367-REG_1698636-REG)
- [Elgato — Facecam 4K 기술 사양](https://www.elgato.com/us/en/explorer/products/camera/facecam-4k-tech-specs/)
- [Elgato — Facecam 4K vs Facecam Pro 차이](https://www.elgato.com/us/en/explorer/products/camera/difference-between-facecam-4k-and-facecam-pro/)
- [Notebookcheck — Elgato Facecam 4K 리뷰](https://www.notebookcheck.net/Streaming-upgrade-Elgato-Facecam-4K-review-with-Sony-Starvis-2-sensor-and-filter-support.1291738.0.html)
- [다나와 — 엘가토 페이스캠 4K 소개](https://dpg.danawa.com/bbs/view?agent=pc&boardSeq=264&headTextSeq=173%2C328%2C15%2C212%2C213%2C392&listSeq=5985359&page=4)
- [마이피씨샵 — Elgato Facecam 4K](https://www.mypcshop.co.kr/shop/item.php?it_id=5749613020)
- [로지텍 — MX Brio](https://www.logitech.com/en-us/shop/p/mx-brio-4k-webcam)
- [다나와 — 로지텍 Brio 4K Pro](https://prod.danawa.com/info/?pcode=5057546)
