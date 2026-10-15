"""아이디·비밀번호 로그인 (2026-10-14).

- 가족: 초대 링크로 들어온 가족이 설정에서 본인 아이디·비밀번호를 정한다(family_members.login_id/pw_hash).
  로그인하면 그 가족의 초대 토큰을 돌려주므로, 가족 화면은 지금처럼 토큰으로 동작한다.
- 직원: 시설 운영자(관리자 키)가 관리자 콘솔에서 직원 계정을 만든다(staff_accounts).
  로그인하면 12시간짜리 세션 토큰(stf_…)을 주고, 관리자 콘솔은 이 토큰을 관리자 키 자리에 쓴다.
  직원 계정 관리 자체는 관리자 키로만 할 수 있다(직원이 다른 직원을 만들지 못하게).
비밀번호는 scrypt(솔트 16바이트) 해시만 저장하고, 세션 토큰도 SHA-256 해시만 저장한다.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from . import config, db

LOGIN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{3,29}$")
LOGIN_ID_RULE = "아이디는 영문 소문자·숫자와 점(.)·밑줄(_)·붙임표(-)로 4~30자입니다(첫 글자는 영문 소문자나 숫자)."
PASSWORD_RULE = "비밀번호는 8자 이상 128자 이하로 정해 주세요."
STAFF_PREFIX = "stf_"
STAFF_HOURS = 12
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}

# 공개 시연·내 컴퓨터 시연에서만 만드는 가상 가족 로그인(시드 시연 가족 이미영 님). 실제 가족과 무관.
DEMO_LOGIN = {"login_id": "yeohae-demo", "password": "yeohae-2026", "member": "이미영"}


class AccountError(ValueError):
    """입력이 규칙에 맞지 않거나 이미 쓰이는 아이디일 때."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    try:
        kind, salt, digest = (stored or "").split("$")
        if kind != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), **_SCRYPT)
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, TypeError):
        return False


_DUMMY = hash_password("timing-equaliser")   # 없는 아이디도 같은 시간이 걸리게(아이디 존재 여부를 흘리지 않음)


def clean_login_id(value: str) -> str:
    v = (value or "").strip().lower()
    if not LOGIN_ID.match(v):
        raise AccountError(LOGIN_ID_RULE)
    return v


def check_new_password(password: str) -> str:
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise AccountError(PASSWORD_RULE)
    return password


# ---------- 가족 ----------

def family_login_of(member_id: int) -> str | None:
    r = db.one("SELECT login_id FROM family_members WHERE id=?", (member_id,))
    return r["login_id"] if r else None


def set_family_login(member_id: int, login_id: str, password: str) -> str:
    lid = clean_login_id(login_id)
    check_new_password(password)
    taken = db.one("SELECT id FROM family_members WHERE login_id=? AND id<>?", (lid, member_id))
    if taken:
        raise AccountError("이미 쓰이는 아이디입니다. 다른 아이디를 정해 주세요.")
    db.execute("UPDATE family_members SET login_id=?, pw_hash=? WHERE id=?", (lid, hash_password(password), member_id))
    return lid


def family_login(login_id: str, password: str) -> dict | None:
    """맞으면 가족 행(초대 토큰 포함), 아니면 None. 철회·만료된 가족은 들어올 수 없다."""
    lid = (login_id or "").strip().lower()
    m = db.one("SELECT id, name, invite_token, pw_hash, revoked_at, invite_expires_at FROM family_members WHERE login_id=?", (lid,))
    if not m:
        check_password(password or "", _DUMMY)
        return None
    if not check_password(password or "", m["pw_hash"]) or m["revoked_at"]:
        return None
    if m["invite_expires_at"]:
        try:
            if datetime.fromisoformat(m["invite_expires_at"]) <= datetime.now().astimezone():
                return None
        except (ValueError, TypeError):
            return None
    return m


def ensure_demo_login() -> bool:
    """시드 시연 가족(이미영 님)에게 시연용 로그인을 만든다. 공개 시연이거나 내 컴퓨터 시연(강한 키 강제 아님)일 때만."""
    if not (config.PUBLIC_DEMO or not config.REQUIRE_STRONG_KEYS):
        return False
    m = db.one("""SELECT f.id, f.login_id FROM family_members f
                  WHERE f.name=? AND f.contract_id IN (SELECT contract_id FROM deceased WHERE photo_path LIKE 'photos/seed_%')""",
               (DEMO_LOGIN["member"],))
    if not m or m["login_id"]:
        return False
    if db.one("SELECT id FROM family_members WHERE login_id=?", (DEMO_LOGIN["login_id"],)):
        return False
    db.execute("UPDATE family_members SET login_id=?, pw_hash=? WHERE id=?",
               (DEMO_LOGIN["login_id"], hash_password(DEMO_LOGIN["password"]), m["id"]))
    return True


# ---------- 직원 ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


ROLES = ("staff", "master")   # master = 시설 운영자 마스터(관리자 키처럼 직원 계정까지 관리, 2026-10-15)


def staff_list() -> list[dict]:
    return db.rows("SELECT id, login_id, name, COALESCE(role, 'staff') AS role, created_at, disabled_at FROM staff_accounts ORDER BY id")


def staff_create(login_id: str, name: str, password: str, role: str = "staff") -> int:
    lid = clean_login_id(login_id)
    check_new_password(password)
    if role not in ROLES:
        raise AccountError("계정 종류는 직원 또는 시설 운영자(마스터)입니다.")
    if role == "master" and len(password) < 12:
        raise AccountError("시설 운영자(마스터) 비밀번호는 12자 이상으로 정해 주세요.")
    name = (name or "").strip()
    if not 1 <= len(name) <= 40:
        raise AccountError("이름을 1~40자로 적어 주세요.")
    if db.one("SELECT id FROM staff_accounts WHERE login_id=?", (lid,)):
        raise AccountError("이미 쓰이는 아이디입니다. 다른 아이디를 정해 주세요.")
    return db.execute("INSERT INTO staff_accounts(login_id, name, pw_hash, created_at, role) VALUES (?,?,?,?,?)",
                      (lid, name, hash_password(password), db.now(), role))


def staff_set_password(staff_id: int, password: str) -> None:
    check_new_password(password)
    db.execute("UPDATE staff_accounts SET pw_hash=? WHERE id=?", (hash_password(password), staff_id))
    db.execute("DELETE FROM staff_sessions WHERE staff_id=?", (staff_id,))   # 비밀번호를 바꾸면 기존 로그인은 끝


def staff_set_disabled(staff_id: int, disabled: bool) -> None:
    db.execute("UPDATE staff_accounts SET disabled_at=? WHERE id=?", (db.now() if disabled else None, staff_id))
    if disabled:
        db.execute("DELETE FROM staff_sessions WHERE staff_id=?", (staff_id,))


def staff_login(login_id: str, password: str) -> tuple[str, dict] | None:
    lid = (login_id or "").strip().lower()
    s = db.one("SELECT id, name, login_id, pw_hash, disabled_at, COALESCE(role, 'staff') AS role FROM staff_accounts WHERE login_id=?", (lid,))
    if not s:
        check_password(password or "", _DUMMY)
        return None
    if not check_password(password or "", s["pw_hash"]) or s["disabled_at"]:
        return None
    token = STAFF_PREFIX + secrets.token_urlsafe(32)
    now = datetime.now().astimezone()
    db.execute("DELETE FROM staff_sessions WHERE expires_at <= ?", (now.isoformat(timespec="seconds"),))
    db.execute("INSERT INTO staff_sessions(token_hash, staff_id, created_at, expires_at) VALUES (?,?,?,?)",
               (_token_hash(token), s["id"], now.isoformat(timespec="seconds"),
                (now + timedelta(hours=STAFF_HOURS)).isoformat(timespec="seconds")))
    return token, {"id": s["id"], "name": s["name"], "login_id": s["login_id"], "role": s["role"]}


def staff_session(token: str | None) -> dict | None:
    """유효한 직원 세션이면 직원 정보. 관리자 키 자리에 들어온 값을 확인할 때 쓴다."""
    if not token or not token.startswith(STAFF_PREFIX):
        return None
    r = db.one("""SELECT a.id, a.name, a.login_id, COALESCE(a.role, 'staff') AS role, a.disabled_at, s.expires_at FROM staff_sessions s
                  JOIN staff_accounts a ON a.id=s.staff_id WHERE s.token_hash=?""", (_token_hash(token),))
    if not r or r["disabled_at"]:
        return None
    try:
        if datetime.fromisoformat(r["expires_at"]) <= datetime.now().astimezone():
            return None
    except (ValueError, TypeError):
        return None
    return {"id": r["id"], "name": r["name"], "login_id": r["login_id"], "role": r["role"]}


def staff_logout(token: str | None) -> None:
    if token and token.startswith(STAFF_PREFIX):
        db.execute("DELETE FROM staff_sessions WHERE token_hash=?", (_token_hash(token),))
