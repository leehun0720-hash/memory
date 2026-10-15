"""아이디·비밀번호 로그인 (2026-10-14). 규칙과 저장 방식은 server/accounts.py.

- /api/login/family : 가족 로그인 → 초대 토큰(가족 화면이 지금처럼 씀)
- /api/login/staff  : 직원 로그인 → 12시간 세션 토큰(관리자 콘솔이 관리자 키 자리에 씀)
- /api/family/account : 가족이 본인 아이디·비밀번호를 정함(초대 링크로 들어온 뒤)
- /api/admin/staff  : 직원 계정 관리(관리자 키로만)
틀린 시도는 접속 주소·아이디마다 10분에 10번까지. 아이디가 없을 때와 비밀번호가 틀릴 때 같은 안내를 준다.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import accounts, config, db, ratelimit
from ..deps import admin_credential, require_member, require_owner

router = APIRouter(tags=["login"])
WRONG = "아이디 또는 비밀번호가 맞지 않습니다."


class LoginIn(BaseModel):
    login_id: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


def _ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")


def _limit(request: Request, kind: str, login_id: str) -> None:
    msg = "로그인을 여러 번 틀렸습니다. 10분 뒤 다시 시도해 주세요."
    ratelimit.hit(f"login-{kind}-ip:{_ip(request)}", 10, 600, msg)
    ratelimit.hit(f"login-{kind}-id:{login_id.strip().lower()}", 10, 600, msg)


@router.post("/api/login/family")
def login_family(body: LoginIn, request: Request):
    _limit(request, "family", body.login_id)
    m = accounts.family_login(body.login_id, body.password)
    if not m:
        raise HTTPException(401, WRONG)
    db.audit(f"member:{m['id']}", "login.family", f"member:{m['id']}")
    return {"token": m["invite_token"], "name": m["name"]}


@router.post("/api/login/staff")
def login_staff(body: LoginIn, request: Request):
    _limit(request, "staff", body.login_id)
    got = accounts.staff_login(body.login_id, body.password)
    if not got:
        raise HTTPException(401, WRONG)
    token, staff = got
    db.audit(f"staff:{staff['id']}", "login.staff", f"staff:{staff['id']}")
    return {"token": token, "name": staff["name"], "role": staff["role"], "hours": accounts.STAFF_HOURS}


@router.post("/api/login/staff/logout")
def logout_staff(request: Request):
    accounts.staff_logout(admin_credential(request, request.headers.get("x-admin-key")))
    return {"ok": True}


@router.get("/api/login/hint")
def login_hint(request: Request):
    """시연용 가족 로그인 안내. 공개 시연(PUBLIC_DEMO)이거나 서버를 켠 컴퓨터에서 직접 열었을 때만."""
    local = (not config.REQUIRE_STRONG_KEYS and not request.headers.get("x-forwarded-for")
             and (request.client.host if request.client else "") in ("127.0.0.1", "::1"))
    if not (config.PUBLIC_DEMO or local):
        raise HTTPException(404)
    d = accounts.DEMO_LOGIN
    if not db.one("SELECT id FROM family_members WHERE login_id=?", (d["login_id"],)):
        raise HTTPException(404)
    return {"login_id": d["login_id"], "password": d["password"], "member": d["member"]}


# ---------- 가족: 내 로그인 정하기 ----------

class FamilyAccountIn(BaseModel):
    login_id: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


@router.get("/api/family/account")
def family_account(m: dict = Depends(require_member)):
    return {"login_id": accounts.family_login_of(m["id"])}


@router.put("/api/family/account")
def family_account_set(body: FamilyAccountIn, m: dict = Depends(require_member)):
    ratelimit.hit(f"family-account:{m['id']}", 10, 3600, "로그인 정보는 한 시간에 10번까지 바꿀 수 있습니다.")
    try:
        lid = accounts.set_family_login(m["id"], body.login_id, body.password)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    db.audit(f"member:{m['id']}", "account.set", f"member:{m['id']}", lid)
    return {"ok": True, "login_id": lid}


# ---------- 직원 계정 관리(관리자 키 또는 시설 운영자 마스터 로그인) ----------

staff_router = APIRouter(prefix="/api/admin/staff", tags=["staff"], dependencies=[Depends(require_owner)])


class StaffIn(BaseModel):
    login_id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)
    role: Literal["staff", "master"] = "staff"   # master = 시설 운영자 마스터(직원 계정 관리까지)


class StaffPasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@staff_router.get("")
def staff_list():
    return accounts.staff_list()


@staff_router.post("")
def staff_create(body: StaffIn, actor: str = Depends(require_owner)):
    try:
        sid = accounts.staff_create(body.login_id, body.name, body.password, body.role)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    db.audit(actor, "staff.create", f"staff:{sid}", f"{body.login_id.strip().lower()} ({body.role})")
    return {"ok": True, "id": sid}


def _staff_or_404(sid: int) -> None:
    if not db.one("SELECT id FROM staff_accounts WHERE id=?", (sid,)):
        raise HTTPException(404, "직원 계정을 찾을 수 없습니다.")


@staff_router.post("/{sid}/password")
def staff_password(sid: int, body: StaffPasswordIn):
    _staff_or_404(sid)
    try:
        accounts.staff_set_password(sid, body.password)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    db.audit("admin", "staff.password", f"staff:{sid}")
    return {"ok": True}


@staff_router.post("/{sid}/disable")
def staff_disable(sid: int):
    _staff_or_404(sid)
    accounts.staff_set_disabled(sid, True)
    db.audit("admin", "staff.disable", f"staff:{sid}")
    return {"ok": True}


@staff_router.post("/{sid}/enable")
def staff_enable(sid: int):
    _staff_or_404(sid)
    accounts.staff_set_disabled(sid, False)
    db.audit("admin", "staff.enable", f"staff:{sid}")
    return {"ok": True}
