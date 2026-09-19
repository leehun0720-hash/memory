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
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data")).resolve()
SNAPSHOT_DIR = DATA_DIR / "snapshots"
FRAME_DIR = DATA_DIR / "frames"
MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "memorial.db"

LIVE_SECONDS = _int("LIVE_SECONDS", 30)
CHAT_MAX_MINUTES = _int("CHAT_MAX_MINUTES", 15)
SNAPSHOT_INTERVAL = _int("SNAPSHOT_INTERVAL", 10)
LIVE_FPS = _int("LIVE_FPS", 5)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "auto").strip().lower()

for d in (SNAPSHOT_DIR, FRAME_DIR, MEDIA_DIR):
    d.mkdir(parents=True, exist_ok=True)
