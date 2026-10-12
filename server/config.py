"""환경 설정. .env → 환경변수 → 기본값 순."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


ADMIN_KEY = os.getenv("ADMIN_KEY", "admin1234")
EDGE_KEY = os.getenv("EDGE_KEY", "edge1234")

# 인터넷에 올린 서버(Railway 등)에서는 기본값·짧은 키로 켜지지 않게 막는다.
# Railway 는 RAILWAY_ENVIRONMENT 를 스스로 넣어 준다. 다른 곳은 REQUIRE_STRONG_KEYS=1 로 켠다.
REQUIRE_STRONG_KEYS = bool(os.getenv("RAILWAY_ENVIRONMENT")) or os.getenv("REQUIRE_STRONG_KEYS", "0") == "1"
if REQUIRE_STRONG_KEYS:
    _weak = [name for name, value, default in (("ADMIN_KEY", ADMIN_KEY, "admin1234"), ("EDGE_KEY", EDGE_KEY, "edge1234"))
             if value == default or len(value) < 24]
    if _weak:
        raise RuntimeError(
            f"온라인 서버에는 강한 키가 필요합니다(24자 이상, 기본값 금지): {', '.join(_weak)}. "
            "scripts/railway-keys.ps1 로 설정하세요."
        )


def _writable_data_dir() -> tuple[Path, bool]:
    """(데이터 폴더, 임시 폴더로 내려갔는지). 서버리스(Vercel 등)는 프로젝트 폴더가 읽기 전용이라 /tmp 로 내려가고,
    그 경우 데이터는 인스턴스가 바뀌면 사라진다. Railway 볼륨(/data)처럼 프로젝트 밖이어도 쓸 수 있으면 영구 저장이다."""
    want = Path(os.getenv("DATA_DIR", ROOT / "data")).resolve()
    try:
        want.mkdir(parents=True, exist_ok=True)
        (want / ".w").write_text("ok")
        (want / ".w").unlink()
        return want, False
    except OSError:
        tmp = Path(os.getenv("TMPDIR", "/tmp")) / "memorial-data"
        tmp.mkdir(parents=True, exist_ok=True)
        return tmp, True


DATA_DIR, EPHEMERAL = _writable_data_dir()   # EPHEMERAL: /tmp 로 내려간 상태(서버리스)
AUTO_SEED = os.getenv("AUTO_SEED", "0") == "1"           # 서버 시작 시 비어 있으면 시연 데이터 생성
SEED_SALT = os.getenv("SEED_SALT", "")
LAUNCHER_DISABLED = os.getenv("LAUNCHER", "1") != "1"   # LAUNCHER=0 이면 로컬 시작 화면(바로가기)도 끔                   # 있으면 시연 초대 토큰이 고정됨(서버리스 재시작에도 링크 유지)
SNAPSHOT_DIR = DATA_DIR / "snapshots"
FRAME_DIR = DATA_DIR / "frames"
MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "memorial.db"

LIVE_SECONDS = _int("LIVE_SECONDS", 30)
CHAT_MAX_MINUTES = _int("CHAT_MAX_MINUTES", 15)
SNAPSHOT_INTERVAL = _int("SNAPSHOT_INTERVAL", 10)
LIVE_FPS = _int("LIVE_FPS", 12)          # 실시간 보기 초당 프레임(현장 프로그램이 이 값으로 보냄)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "auto").strip().lower()

for d in (SNAPSHOT_DIR, FRAME_DIR, MEDIA_DIR):
    d.mkdir(parents=True, exist_ok=True)
