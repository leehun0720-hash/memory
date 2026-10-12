"""인증 의존성. MVP: 관리자 키 · 현장 키 · 가족 초대 토큰."""
import hmac
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Query, Request

from . import config, db, ratelimit

# 사진·영상·생중계 주소에 키·토큰을 싣지 않도록, 화면이 처음 열릴 때 헤더로 확인한 값을 보안 쿠키(HttpOnly·SameSite=Strict)로 받는다.
FAMILY_COOKIE = "mf"
ADMIN_COOKIE = "ma"


def _same(a: str | None, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def require_admin(request: Request, x_admin_key: str | None = Header(default=None), key: str | None = Query(default=None)) -> str:
    k = x_admin_key or request.cookies.get(ADMIN_COOKIE) or key
    if not _same(k, config.ADMIN_KEY):   # 빈 키(설정 누락)는 언제나 거부
        ip = request.client.host if request.client else "?"
        ratelimit.hit(f"admin-fail:{ip}", 20, 600, "관리자 키가 여러 번 틀렸습니다. 10분 뒤 다시 시도해 주세요.")
        raise HTTPException(401, "관리자 키가 올바르지 않습니다.")
    return "admin"


def require_edge(x_edge_key: str | None = Header(default=None)) -> str:
    if not _same(x_edge_key, config.EDGE_KEY):
        raise HTTPException(401, "현장 키가 올바르지 않습니다.")
    return "edge"


def require_member(request: Request, x_family_token: str | None = Header(default=None), t: str | None = Query(default=None)) -> dict:
    tok = x_family_token or request.cookies.get(FAMILY_COOKIE) or t
    if not tok:
        raise HTTPException(401, "초대 링크로 들어와 주세요. 링크가 없으면 계약하신 가족이나 시설 담당자에게 요청해 주세요.")
    m = db.one(
        """SELECT m.*, c.niche_id, c.holder_name, c.plan, n.code AS niche_code, n.camera_id
           FROM family_members m JOIN contracts c ON c.id = m.contract_id
           LEFT JOIN niches n ON n.id = c.niche_id WHERE m.invite_token = ?""",
        (tok,),
    )
    if not m or m.get("revoked_at"):
        raise HTTPException(401, "이 초대 링크로는 들어올 수 없습니다. 계약하신 가족에게 새 초대 링크를 요청해 주세요.")
    if m.get("invite_expires_at") and datetime.fromisoformat(m["invite_expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(401, "초대 링크의 사용 기간이 지났습니다. 계약하신 가족에게 새 링크를 요청해 주세요.")
    db.execute("UPDATE family_members SET last_seen_at=? WHERE id=?", (db.now(), m["id"]))
    return m


def require_role(member: dict, *roles: str) -> None:
    order = {"view": 0, "chat": 1, "manage": 2}
    if order.get(member["role"], 0) < min(order[r] for r in roles):
        raise HTTPException(403, "이 기능은 계약하신 가족의 허락이 필요합니다. 계약자에게 요청해 주세요.")
