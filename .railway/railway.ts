// Railway 인프라 설정 (2026-10-12). 예전 railway.json(Config as Code, 2026-12-01 지원 종료)을 대신한다.
// - `railway config pull` 로 지금 Railway 에 있는 볼륨·변수를 가져오고, railway.json 의 빌드·시작·상태 확인·재시작 정책을 옮겼다.
// - 변수 값은 preserve(): Railway 에 이미 넣은 값을 그대로 두고 이 파일에는 적지 않는다(관리자 키 등 비밀 보호).
// - 바꾸기 전에는 반드시 `railway config plan` 으로 확인하고, 삭제가 들어간 계획은 적용하지 않는다.
// - 이 폴더(.railway/)의 package.json·node_modules 는 이 파일을 쓰기 위한 것이며 앱 배포(.railwayignore 로 제외)와는 무관하다.
import { defineRailway, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  // SQLite 와 사진·음성 자료가 들어 있는 볼륨. 지우면 기록이 사라지므로 절대 빼지 않는다.
  const memorialVolume = volume("memorial-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const memorial = service("memorial", {
    build: { builder: "RAILPACK" },
    deploy: {
      startCommand: "python -m uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips=*",
      healthcheckPath: "/health",
      healthcheckTimeout: 120,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
    },
    // SQLite 한 파일을 쓰므로 인스턴스는 1개(늘리면 기록이 갈라진다)
    replicas: { "sfo": 1 },
    volumeMounts: { "/data": memorialVolume },
    env: { ADMIN_KEY: preserve(), AUTO_SEED: preserve(), DATA_DIR: preserve(), EDGE_KEY: preserve(), KAKAO_SEND_ENABLED: preserve(), LAUNCHER: preserve(), SEED_SALT: preserve() },
  });

  return project("yunhoedang-memorial", {
    resources: [memorial, memorialVolume],
  });
});
