"""인증 의존성. MVP: 관리자 키 · 현장 키 · 가족 초대 토큰."""
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Query

from . import config, db


def require_admin(x_admin_key: str | None = Header(default=None), key: str | None = Query(default=None)) -> str:
    k = x_admin_key or key
    if k != config.ADMIN_KEY:
        raise HTTPException(401, "관리자 키가 올바르지 않습니다.")
    return "admin"


def require_edge(x_edge_key: str | None = Header(default=None)) -> str:
    if x_edge_key != config.EDGE_KEY:
        raise HTTPException(401, "현장 키가 올바르지 않습니다.")
    return "edge"


def require_member(x_family_token: str | None = Header(default=None), t: str | None = Query(default=None)) -> dict:
    tok = x_family_token or t
    if not tok:
        raise HTTPException(401, "초대 링크로 접속해 주세요.")
    m = db.one(
        """SELECT m.*, c.niche_id, c.holder_name, c.plan, n.code AS niche_code, n.camera_id
           FROM family_members m JOIN contracts c ON c.id = m.contract_id
           LEFT JOIN niches n ON n.id = c.niche_id WHERE m.invite_token = ?""",
        (tok,),
    )
    if not m or m.get("revoked_at"):
        raise HTTPException(401, "초대 링크가 유효하지 않습니다.")
    if m.get("invite_expires_at") and datetime.fromisoformat(m["invite_expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(401, "초대 링크가 만료되었습니다. 계약자에게 새 링크를 요청해 주세요.")
    db.execute("UPDATE family_members SET last_seen_at=? WHERE id=?", (db.now(), m["id"]))
    return m


def require_role(member: dict, *roles: str) -> None:
    order = {"view": 0, "chat": 1, "manage": 2}
    if order.get(member["role"], 0) < min(order[r] for r in roles):
        raise HTTPException(403, "권한이 없습니다. 계약자에게 요청해 주세요.")
