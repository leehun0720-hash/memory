"""실시간 아바타 얼굴 등록 공통 로직. 관리자 콘솔과 유족 앱이 같이 쓴다.
고인의 대표 사진 → 공급자(Simli)에 얼굴 생성 → deceased.face_id 저장. 초상 사용(likeness) 또는 생전 기록 동의가 있어야 한다."""
from fastapi import HTTPException

from . import config, db
from .ai import factory
from .ai.avatar import AvatarError


def provider_ready() -> bool:
    return factory.avatar().name != "none"


def register(deceased_id: int, actor: str) -> dict:
    d = db.one("SELECT * FROM deceased WHERE id=?", (deceased_id,))
    if not d:
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if not db.one("SELECT id FROM consents WHERE deceased_id=? AND kind IN ('likeness','lifetime_record') AND revoked_at IS NULL", (deceased_id,)):
        raise HTTPException(403, "초상 사용(또는 생전 기록) 동의서가 없어 얼굴을 등록할 수 없습니다.")
    if not provider_ready():
        raise HTTPException(400, "봉안당에서 아직 실시간 아바타 기능을 켜지 않았습니다(관리자 콘솔 → AI 설정 → Simli 키).")
    if not d["photo_path"]:
        raise HTTPException(400, "대표 사진이 없습니다. 정면 얼굴 사진을 먼저 등록해 주세요.")
    fp = config.MEDIA_DIR / d["photo_path"]
    if not fp.exists():
        raise HTTPException(400, "대표 사진 파일을 찾을 수 없습니다.")
    if fp.stat().st_size > 5 * 1024 * 1024:
        raise HTTPException(400, "사진이 5MB를 넘습니다. 더 작은 사진으로 바꿔 주세요.")
    provider = factory.avatar()
    try:
        if d["face_id"] and d["face_provider"] == provider.name:
            provider.delete_face(d["face_id"])
        fid = provider.create_face(fp.read_bytes(), f"memorial-{deceased_id}-{d['name']}", fp.name)
    except AvatarError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.message)
    db.execute("UPDATE deceased SET face_id=?, face_provider=? WHERE id=?", (fid, provider.name, deceased_id))
    db.audit(actor, "face.register", f"deceased:{deceased_id}", provider.name)
    return {"face_id": fid, "provider": provider.name}


def delete(deceased_id: int, actor: str) -> None:
    d = db.one("SELECT face_id, face_provider FROM deceased WHERE id=?", (deceased_id,))
    if not d or not d["face_id"]:
        return
    try:
        p = factory.avatar()
        if d["face_provider"] == p.name and p.name != "none":
            p.delete_face(d["face_id"])
    except Exception as e:
        db.audit(actor, "face.delete_failed", f"deceased:{deceased_id}", str(e)[:200])
    db.execute("UPDATE deceased SET face_id='', face_provider='' WHERE id=?", (deceased_id,))
    db.audit(actor, "face.delete", f"deceased:{deceased_id}")


def session(deceased_id: int) -> dict | None:
    """대화용 세션. 얼굴이 없거나 공급자가 꺼져 있으면 None(사진 아바타로)."""
    d = db.one("SELECT face_id, face_provider FROM deceased WHERE id=?", (deceased_id,))
    if not d or not d["face_id"] or not provider_ready():
        return None
    p = factory.avatar()
    if d["face_provider"] != p.name:
        return None
    try:
        tok = p.session_token(d["face_id"], max_len=config.CHAT_MAX_MINUTES * 60 + 60, max_idle=180)
    except AvatarError as e:
        db.audit("system", "avatar.session_failed", f"deceased:{deceased_id}", e.message)
        return None
    return {"provider": p.name, "session_token": tok, "ws_url": p.WS_URL, "ice_servers": p.ice_servers()}
