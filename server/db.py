"""SQLite 접근 계층. 파일럿에서 PostgreSQL로 옮길 때 이 파일만 바꾸면 되도록 SQL은 표준형으로 유지."""
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS facilities (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS rooms (
  id INTEGER PRIMARY KEY, facility_id INTEGER NOT NULL REFERENCES facilities(id), name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cameras (
  id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL REFERENCES rooms(id),
  name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'wall',     -- wall(안치실 벽면) | ritual(제례 공간)
  device_index INTEGER NOT NULL DEFAULT 0, width INTEGER DEFAULT 1920, height INTEGER DEFAULT 1080,
  last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS niches (
  id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL REFERENCES cameras(id),
  code TEXT NOT NULL UNIQUE,                                  -- 봉안함 번호 예: A-3-12
  row INTEGER DEFAULT 0, col INTEGER DEFAULT 0,
  x REAL NOT NULL, y REAL NOT NULL, w REAL NOT NULL, h REAL NOT NULL,   -- 카메라 화면 기준 비율(0~1)
  last_snapshot_at TEXT
);
CREATE TABLE IF NOT EXISTS contracts (
  id INTEGER PRIMARY KEY, niche_id INTEGER REFERENCES niches(id),
  holder_name TEXT NOT NULL, holder_phone TEXT DEFAULT '', plan TEXT NOT NULL DEFAULT 'basic',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS family_members (
  id INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL REFERENCES contracts(id),
  name TEXT NOT NULL, relation TEXT DEFAULT '', role TEXT NOT NULL DEFAULT 'view',   -- view | chat | manage
  invite_token TEXT NOT NULL UNIQUE, is_minor INTEGER DEFAULT 0, created_at TEXT NOT NULL, last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS deceased (
  id INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL REFERENCES contracts(id),
  name TEXT NOT NULL, honorific TEXT DEFAULT '',             -- 가족이 부르던 호칭 예: 어머니
  birth_date TEXT DEFAULT '', death_date TEXT DEFAULT '',
  photo_path TEXT DEFAULT '', memory_card TEXT DEFAULT '',   -- 2,000~5,000자 프로필
  voice_note TEXT DEFAULT '',                                -- 음성 자료 메모(파일은 media)
  ai_enabled INTEGER DEFAULT 0, chat_min_days_after_death INTEGER DEFAULT 49,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consents (
  id INTEGER PRIMARY KEY, deceased_id INTEGER NOT NULL REFERENCES deceased(id),
  signer_name TEXT NOT NULL, relation TEXT DEFAULT '', kind TEXT NOT NULL,   -- ai_chat | likeness | voice | lifetime_record
  signed_at TEXT NOT NULL, revoked_at TEXT, note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS media (
  id INTEGER PRIMARY KEY, deceased_id INTEGER NOT NULL REFERENCES deceased(id),
  kind TEXT NOT NULL,                                        -- photo | video | voice | message_video
  path TEXT NOT NULL, caption TEXT DEFAULT '', ai_generated INTEGER DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guestbook (
  id INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL REFERENCES contracts(id),
  member_id INTEGER REFERENCES family_members(id), author TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rituals (
  id INTEGER PRIMARY KEY, facility_id INTEGER NOT NULL REFERENCES facilities(id),
  contract_id INTEGER REFERENCES contracts(id),              -- NULL이면 시설 공통(명절 합동제사 등)
  title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'memorial',   -- memorial(기일) | holiday(명절) | event(행사)
  scheduled_at TEXT NOT NULL, stream_url TEXT DEFAULT '', camera_id INTEGER REFERENCES cameras(id),
  replay_url TEXT DEFAULT '', note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS offerings (
  id INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL REFERENCES contracts(id),
  member_id INTEGER REFERENCES family_members(id), ritual_id INTEGER REFERENCES rituals(id),
  kind TEXT NOT NULL,                                        -- offering(공양) | flower(헌화) | prayer(기도)
  amount INTEGER DEFAULT 0, note TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'requested',   -- requested | accepted | done | cancelled
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_sessions (
  id TEXT PRIMARY KEY, deceased_id INTEGER NOT NULL REFERENCES deceased(id),
  member_id INTEGER NOT NULL REFERENCES family_members(id),
  started_at TEXT NOT NULL, ended_at TEXT, turns INTEGER DEFAULT 0,
  summary TEXT DEFAULT '', safety_events TEXT DEFAULT '', provider TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS live_sessions (
  id TEXT PRIMARY KEY, niche_id INTEGER NOT NULL REFERENCES niches(id),
  member_id INTEGER NOT NULL REFERENCES family_members(id), started_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT DEFAULT '', detail TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def token(n: int = 16) -> str:
    return secrets.token_urlsafe(n)


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.executescript(SCHEMA)
            _migrate(_conn)
        return _conn


# 기존 DB에 새 컬럼을 더한다(컬럼명, 정의). 파일럿에서 정식 마이그레이션 도구로 교체.
_MIGRATIONS = [
    ("deceased", "voice_id", "TEXT DEFAULT ''"),          # 복제 음성 ID(공급자 측)
    ("deceased", "voice_provider", "TEXT DEFAULT ''"),    # elevenlabs | supertone
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, col, ddl in _MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    conn.commit()


def reset_for_tests(path) -> None:
    """테스트에서 DB 경로를 바꿔 새로 연다."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        config.DB_PATH = path


@contextmanager
def tx():
    conn = connect()
    with _lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rows(sql: str, params=()) -> list[dict]:
    with _lock:
        return [dict(r) for r in connect().execute(sql, params).fetchall()]


def one(sql: str, params=()) -> dict | None:
    with _lock:
        r = connect().execute(sql, params).fetchone()
        return dict(r) if r else None


def execute(sql: str, params=()) -> int:
    with tx() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def audit(actor: str, action: str, target: str = "", detail: str = "") -> None:
    execute(
        "INSERT INTO audit_logs(actor, action, target, detail, created_at) VALUES (?,?,?,?,?)",
        (actor, action, target, detail, now()),
    )


def get_setting(key: str, default: str = "") -> str:
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key: str, value: str) -> None:
    execute("INSERT INTO settings(key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now()))
