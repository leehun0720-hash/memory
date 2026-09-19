"""유족 웹앱 API. 초대 토큰 하나로 계약·칸·고인이 결정된다."""
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import config, db, face, voice
from ..ai.avatar import SimliAvatar  # 기본 얼굴 목록
from ..deps import require_member, require_role
from ..state import state

router = APIRouter(prefix="/api/family", tags=["family"])


def _deceased_for(contract_id: int) -> list[dict]:
    rows = db.rows("SELECT * FROM deceased WHERE contract_id=? ORDER BY id", (contract_id,))
    for d in rows:
        d["has_photo"] = bool(d["photo_path"])
        d["consent_valid"] = db.one(
            "SELECT id FROM consents WHERE deceased_id=? AND kind='ai_chat' AND revoked_at IS NULL", (d["id"],)
        ) is not None
        d["chat_available"] = bool(d["ai_enabled"]) and d["consent_valid"]
        d["days_since_death"] = _days_since(d["death_date"])
        d["has_voice"] = bool(d.get("voice_id"))
        d["has_face"] = bool(d.get("face_id"))
        d.pop("memory_card", None)   # 기억 카드는 유족 화면에 노출하지 않음
        d.pop("voice_id", None); d.pop("voice_provider", None); d.pop("face_id", None); d.pop("face_provider", None)
    return rows


def _days_since(date_str: str) -> int | None:
    try:
        return (datetime.now().date() - datetime.fromisoformat(date_str).date()).days
    except (ValueError, TypeError):
        return None


@router.get("/me")
def me(m: dict = Depends(require_member)):
    cam = state.camera(m["camera_id"]) if m["camera_id"] else None
    return {
        "member": {"id": m["id"], "name": m["name"], "relation": m["relation"], "role": m["role"], "is_minor": bool(m["is_minor"])},
        "contract": {"id": m["contract_id"], "holder_name": m["holder_name"], "plan": m["plan"]},
        "niche": {"id": m["niche_id"], "code": m["niche_code"]} if m["niche_id"] else None,
        "camera": {"online": cam.online, "occupied": cam.occupied} if cam else None,
        "deceased": _deceased_for(m["contract_id"]),
        "live_seconds": config.LIVE_SECONDS,
        "chat_max_minutes": config.CHAT_MAX_MINUTES,
        "tts_provider": config.TTS_PROVIDER,
    }


THEMES = ("classic", "buddhist", "catholic", "christian")


class ThemeIn(BaseModel):
    deceased_id: int
    theme: str = Field(pattern="^(classic|buddhist|catholic|christian)$")


@router.post("/theme")
def set_theme(body: ThemeIn, m: dict = Depends(require_member)):
    """추모 공간 테마(전통·불교·천주교·기독교). 계약자만 바꿀 수 있고 가족 모두에게 적용된다."""
    require_role(m, "manage")
    if not db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"])):
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    db.execute("UPDATE deceased SET theme=? WHERE id=?", (body.theme, body.deceased_id))
    db.audit(f"member:{m['id']}", "theme.set", f"deceased:{body.deceased_id}", body.theme)
    return {"ok": True, "theme": body.theme}


# ---------- 원격 참배 ----------

@router.get("/niche/status")
def niche_status(m: dict = Depends(require_member)):
    if not m["niche_id"]:
        raise HTTPException(404, "연결된 봉안함이 없습니다.")
    n = db.one("SELECT last_snapshot_at FROM niches WHERE id=?", (m["niche_id"],))
    cam = state.camera(m["camera_id"])
    live = db.one("SELECT expires_at FROM live_sessions WHERE niche_id=? AND member_id=? AND expires_at > ? ORDER BY expires_at DESC",
                  (m["niche_id"], m["id"], db.now()))
    return {
        "last_snapshot_at": n["last_snapshot_at"],
        "camera_online": cam.online,
        "occupied": cam.occupied,
        "live_until": live["expires_at"] if live else None,
    }


@router.get("/niche/snapshot.jpg")
def niche_snapshot(m: dict = Depends(require_member)):
    if not m["niche_id"]:
        raise HTTPException(404)
    p = config.SNAPSHOT_DIR / f"{m['niche_id']}.jpg"
    if not p.exists():
        raise HTTPException(404, "아직 사진이 없습니다.")
    # 현장 프로그램이 10초마다 덮어쓰므로 한 번에 읽어서 보낸다(FileResponse는 길이 불일치 오류가 남)
    return Response(content=p.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/live/start")
def live_start(m: dict = Depends(require_member)):
    if not m["niche_id"]:
        raise HTTPException(404, "연결된 봉안함이 없습니다.")
    cam = state.camera(m["camera_id"])
    if not cam.online:
        raise HTTPException(503, "현장 카메라가 연결되어 있지 않습니다. 마지막 사진을 보여 드립니다.")
    if cam.occupied:
        raise HTTPException(409, "지금 현장에 다른 참배객이 계십니다. 잠시 뒤 다시 시도해 주세요.")
    sid = db.token(12)
    started = datetime.now().astimezone()
    expires = started + timedelta(seconds=config.LIVE_SECONDS)
    db.execute("INSERT INTO live_sessions(id, niche_id, member_id, started_at, expires_at) VALUES (?,?,?,?,?)",
               (sid, m["niche_id"], m["id"], started.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")))
    db.audit(f"member:{m['id']}", "live.start", f"niche:{m['niche_code']}")
    return {"session_id": sid, "seconds": config.LIVE_SECONDS, "expires_at": expires.isoformat(timespec="seconds")}


def _mjpeg(key: int, deadline: float, cam_id: int | None):
    boundary = b"--frame"
    seq = 0
    idle_since = time.time()
    while time.time() < deadline:
        if cam_id is not None and state.camera(cam_id).occupied:
            break   # 참배객 보호: 사람 감지 시 송출 중단 → 클라이언트가 사진 화면으로 전환
        f = state.wait_live(key, seq, timeout=1.0)
        if f is None:
            if time.time() - idle_since > 8:
                break
            continue
        idle_since = time.time()
        seq = f.seq
        yield boundary + b"\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(f.data)).encode() + b"\r\n\r\n" + f.data + b"\r\n"


@router.get("/live/stream")
def live_stream(sid: str, m: dict = Depends(require_member)):
    s = db.one("SELECT * FROM live_sessions WHERE id=? AND member_id=?", (sid, m["id"]))
    if not s:
        raise HTTPException(404)
    deadline = datetime.fromisoformat(s["expires_at"]).timestamp()
    if deadline < time.time():
        raise HTTPException(410, "실시간 보기 시간이 끝났습니다.")
    return StreamingResponse(_mjpeg(s["niche_id"], deadline, m["camera_id"]),
                             media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


# ---------- 추모 공간 ----------

@router.get("/memorial")
def memorial(m: dict = Depends(require_member)):
    deceased = _deceased_for(m["contract_id"])
    for d in deceased:
        d["media"] = db.rows("SELECT id, kind, path, caption, ai_generated, created_at FROM media WHERE deceased_id=? ORDER BY id DESC", (d["id"],))
    guestbook = db.rows("SELECT id, author, message, created_at FROM guestbook WHERE contract_id=? ORDER BY id DESC LIMIT 50", (m["contract_id"],))
    upcoming = db.rows(
        """SELECT * FROM rituals WHERE (contract_id=? OR contract_id IS NULL) AND scheduled_at >= date('now','-1 day')
           ORDER BY scheduled_at LIMIT 10""", (m["contract_id"],))
    return {"deceased": deceased, "guestbook": guestbook, "upcoming": upcoming}


@router.get("/deceased/{deceased_id}/photo.jpg")
def deceased_photo(deceased_id: int, m: dict = Depends(require_member)):
    d = db.one("SELECT photo_path FROM deceased WHERE id=? AND contract_id=?", (deceased_id, m["contract_id"]))
    if not d or not d["photo_path"]:
        raise HTTPException(404)
    return FileResponse(config.MEDIA_DIR / d["photo_path"])


@router.get("/media/{media_id}")
def media_file(media_id: int, m: dict = Depends(require_member)):
    r = db.one("SELECT md.path FROM media md JOIN deceased d ON d.id=md.deceased_id WHERE md.id=? AND d.contract_id=?", (media_id, m["contract_id"]))
    if not r:
        raise HTTPException(404)
    return FileResponse(config.MEDIA_DIR / r["path"])


class GuestbookIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@router.post("/guestbook")
def guestbook_add(body: GuestbookIn, m: dict = Depends(require_member)):
    gid = db.execute("INSERT INTO guestbook(contract_id, member_id, author, message, created_at) VALUES (?,?,?,?,?)",
                     (m["contract_id"], m["id"], m["name"], body.message.strip(), db.now()))
    return {"id": gid}


# ---------- 제사 일정·중계 ----------

@router.get("/rituals")
def rituals(m: dict = Depends(require_member)):
    rows = db.rows(
        "SELECT * FROM rituals WHERE contract_id=? OR contract_id IS NULL ORDER BY scheduled_at", (m["contract_id"],))
    now = datetime.now().astimezone()
    for r in rows:
        try:
            t = datetime.fromisoformat(r["scheduled_at"])
            if t.tzinfo is None:
                t = t.astimezone()
            r["is_live_window"] = t - timedelta(minutes=30) <= now <= t + timedelta(hours=3)
            r["is_past"] = t < now - timedelta(hours=3)
        except ValueError:
            r["is_live_window"] = False
            r["is_past"] = False
        r["has_camera"] = r["camera_id"] is not None and state.camera(r["camera_id"]).online
    return rows


@router.get("/rituals/{ritual_id}/stream")
def ritual_stream(ritual_id: int, m: dict = Depends(require_member)):
    r = db.one("SELECT * FROM rituals WHERE id=? AND (contract_id=? OR contract_id IS NULL)", (ritual_id, m["contract_id"]))
    if not r or r["camera_id"] is None:
        raise HTTPException(404)
    db.audit(f"member:{m['id']}", "ritual.watch", f"ritual:{ritual_id}")
    return StreamingResponse(_mjpeg(-r["camera_id"], time.time() + 60 * 60, None),
                             media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


# ---------- 공양·헌화 신청 ----------

class OfferingIn(BaseModel):
    kind: str = Field(pattern="^(offering|flower|prayer)$")
    ritual_id: int | None = None
    amount: int = Field(ge=0, le=5_000_000, default=0)
    note: str = Field(default="", max_length=300)


@router.get("/offerings")
def offerings(m: dict = Depends(require_member)):
    return db.rows(
        """SELECT o.*, r.title AS ritual_title FROM offerings o LEFT JOIN rituals r ON r.id=o.ritual_id
           WHERE o.contract_id=? ORDER BY o.id DESC""", (m["contract_id"],))


@router.post("/offerings")
def offering_add(body: OfferingIn, m: dict = Depends(require_member)):
    oid = db.execute(
        "INSERT INTO offerings(contract_id, member_id, ritual_id, kind, amount, note, status, created_at) VALUES (?,?,?,?,?,?,'requested',?)",
        (m["contract_id"], m["id"], body.ritual_id, body.kind, body.amount, body.note, db.now()))
    db.audit(f"member:{m['id']}", "offering.request", f"offering:{oid}", body.kind)
    return {"id": oid, "status": "requested", "payment": "mvp-mock"}


# ---------- 가족 초대·설정 ----------

class InviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    relation: str = Field(default="", max_length=20)
    role: str = Field(default="view", pattern="^(view|chat)$")
    is_minor: bool = False


@router.get("/members")
def members(m: dict = Depends(require_member)):
    return db.rows("SELECT id, name, relation, role, is_minor, created_at, last_seen_at FROM family_members WHERE contract_id=? ORDER BY id", (m["contract_id"],))


@router.post("/invite")
def invite(body: InviteIn, request: Request, m: dict = Depends(require_member)):
    require_role(m, "manage")
    tok = db.token(16)
    mid = db.execute(
        "INSERT INTO family_members(contract_id, name, relation, role, invite_token, is_minor, created_at) VALUES (?,?,?,?,?,?,?)",
        (m["contract_id"], body.name, body.relation, body.role, tok, int(body.is_minor), db.now()))
    db.audit(f"member:{m['id']}", "family.invite", f"member:{mid}")
    base = str(request.base_url).rstrip("/")
    return {"id": mid, "link": f"{base}/?t={tok}"}


class FarewellIn(BaseModel):
    deceased_id: int
    action: str = Field(pattern="^(return|delete)$")
    last_words: str = Field(default="", max_length=500)


@router.post("/farewell")
def farewell(body: FarewellIn, m: dict = Depends(require_member)):
    """작별 절차: 대화 기능을 닫고 등록 자료를 돌려주거나 삭제한다."""
    require_role(m, "manage")
    d = db.one("SELECT * FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"]))
    if not d:
        raise HTTPException(404)
    exported = None
    if body.action == "return":
        exported = {"name": d["name"], "memory_card": d["memory_card"], "voice_note": d["voice_note"],
                    "media": db.rows("SELECT kind, path, caption FROM media WHERE deceased_id=?", (d["id"],))}
    voice.delete(d["id"], f"member:{m['id']}")   # 공급자 쪽 복제 음성도 지운다
    face.delete(d["id"], f"member:{m['id']}")    # 아바타 얼굴도 지운다
    with db.tx() as conn:
        conn.execute("UPDATE deceased SET ai_enabled=0, memory_card='', voice_note='', voice_id='', voice_provider='', face_id='', face_provider='' WHERE id=?", (d["id"],))
        conn.execute("UPDATE consents SET revoked_at=? WHERE deceased_id=? AND revoked_at IS NULL", (db.now(), d["id"]))
        if body.action == "delete":
            for r in conn.execute("SELECT path FROM media WHERE deceased_id=? AND kind IN ('voice','message_video')", (d["id"],)).fetchall():
                p = config.MEDIA_DIR / r["path"]
                if p.exists():
                    p.unlink()
            conn.execute("DELETE FROM media WHERE deceased_id=? AND kind IN ('voice','message_video')", (d["id"],))
    if body.last_words.strip():
        db.execute("INSERT INTO guestbook(contract_id, member_id, author, message, created_at) VALUES (?,?,?,?,?)",
                   (m["contract_id"], m["id"], m["name"], f"[작별 인사] {body.last_words.strip()}", db.now()))
    db.audit(f"member:{m['id']}", "farewell", f"deceased:{d['id']}", body.action)
    return {"ok": True, "exported": exported}


# ---------- 목소리 등록 (유족 앱에서 직접 · 생전 기록 포함) ----------

VOICE_KINDS = {"lifetime_record": "생전 기록(본인 녹음)", "voice": "고인 음성 자료(가족 동의)"}


@router.get("/voice")
def voice_status(m: dict = Depends(require_member)):
    out = []
    for d in db.rows("SELECT id, name, honorific, voice_id, voice_provider FROM deceased WHERE contract_id=? ORDER BY id", (m["contract_id"],)):
        out.append({
            "id": d["id"], "name": d["name"], "honorific": d["honorific"],
            "has_voice": bool(d["voice_id"]), "provider": d["voice_provider"] or None,
            "samples": db.one("SELECT COUNT(*) AS n FROM media WHERE deceased_id=? AND kind='voice'", (d["id"],))["n"],
            "consent": db.one("SELECT kind, signer_name, signed_at FROM consents WHERE deceased_id=? AND kind IN ('voice','lifetime_record') AND revoked_at IS NULL ORDER BY id DESC", (d["id"],)),
        })
    return {"provider_ready": voice.provider_ready(), "can_manage": m["role"] == "manage", "deceased": out, "min_seconds": voice.MIN_SECONDS}


@router.post("/voice/register")
async def voice_register(deceased_id: int = Form(...), kind: str = Form("lifetime_record"), agree: bool = Form(False),
                         note: str = Form(""), file: UploadFile = File(...), m: dict = Depends(require_member)):
    """녹음 파일 하나로 자료 저장 → 동의서 → 공급자 등록까지 한 번에."""
    require_role(m, "manage")
    if kind not in VOICE_KINDS:
        raise HTTPException(400, "kind")
    d = db.one("SELECT id, name FROM deceased WHERE id=? AND contract_id=?", (deceased_id, m["contract_id"]))
    if not d:
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if not voice.provider_ready():
        raise HTTPException(400, "봉안당에서 아직 음성 복제 기능을 켜지 않았습니다. 사무실에 문의해 주세요.")
    if not agree:
        raise HTTPException(400, "동의 확인이 필요합니다.")
    data = await file.read()
    saved = voice.save_sample(d["id"], file.filename or "recording.webm", data, note.strip() or ("앱에서 직접 녹음" if kind == "lifetime_record" else "앱에서 올린 음성 자료"))
    if not db.one("SELECT id FROM consents WHERE deceased_id=? AND kind=? AND revoked_at IS NULL", (d["id"], kind)):
        db.execute("INSERT INTO consents(deceased_id, signer_name, relation, kind, signed_at, note) VALUES (?,?,?,?,?,?)",
                   (d["id"], m["name"], m["relation"], kind, db.now(), f"유족 앱에서 동의 · {VOICE_KINDS[kind]}"))
        db.audit(f"member:{m['id']}", "consent.create", f"deceased:{d['id']}", kind)
    r = voice.register(d["id"], f"member:{m['id']}")
    return {"ok": True, "seconds": saved["seconds"], "files": r["files"], "provider": r["provider"]}


class VoicePreviewIn(BaseModel):
    deceased_id: int
    text: str = Field(default="", max_length=200)


@router.post("/voice/preview")
def voice_preview(body: VoicePreviewIn, m: dict = Depends(require_member)):
    d = db.one("SELECT id, name FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"]))
    if not d:
        raise HTTPException(404)
    text = body.text.strip() or f"{m['name']}, 잘 지냈니? 밥은 먹었고? 오늘 목소리 들으니 참 좋다."
    audio, mime = voice.preview(d["id"], text)
    db.audit(f"member:{m['id']}", "voice.preview", f"deceased:{d['id']}")
    return Response(content=audio, media_type=mime, headers={"Cache-Control": "no-store"})


@router.delete("/voice/{deceased_id}")
def voice_remove(deceased_id: int, m: dict = Depends(require_member)):
    require_role(m, "manage")
    if not db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (deceased_id, m["contract_id"])):
        raise HTTPException(404)
    voice.delete(deceased_id, f"member:{m['id']}")
    return {"ok": True}


# ---------- 실시간 아바타 얼굴 등록 (유족 앱) ----------

@router.get("/avatar")
def avatar_status(m: dict = Depends(require_member)):
    out = []
    for d in db.rows("SELECT id, name, honorific, photo_path, face_id, face_provider, voice_id FROM deceased WHERE contract_id=? ORDER BY id", (m["contract_id"],)):
        out.append({
            "id": d["id"], "name": d["name"], "honorific": d["honorific"],
            "has_photo": bool(d["photo_path"]), "has_face": bool(d["face_id"]), "has_voice": bool(d["voice_id"]),
            "consent": db.one("SELECT kind, signer_name FROM consents WHERE deceased_id=? AND kind IN ('likeness','lifetime_record') AND revoked_at IS NULL ORDER BY id DESC", (d["id"],)),
        })
    for o in out:
        fid = db.one("SELECT face_id FROM deceased WHERE id=?", (o["id"],))["face_id"]
        o["face_is_preset"] = fid in SimliAvatar.PRESET_IDS
        o["face_label"] = next((f["label"] for f in SimliAvatar.PRESET_FACES if f["id"] == fid), "사진으로 만든 얼굴" if fid else None)
    from ..ai import factory
    return {"provider_ready": face.provider_ready(), "provider": factory.avatar().name, "can_manage": m["role"] == "manage", "deceased": out, "presets": face.presets()}


class PresetIn(BaseModel):
    deceased_id: int
    face_id: str


@router.post("/avatar/preset")
def avatar_preset(body: PresetIn, m: dict = Depends(require_member)):
    """사진 대신 기본 제공 얼굴로 실시간 아바타를 쓴다(무료 플랜 시연용)."""
    require_role(m, "manage")
    if not db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"])):
        raise HTTPException(404)
    return face.set_preset(body.deceased_id, body.face_id, f"member:{m['id']}")


class FaceRegisterIn(BaseModel):
    deceased_id: int
    agree: bool = False
    kind: str = Field(default="likeness", pattern="^(likeness|lifetime_record)$")


@router.post("/avatar/register")
def avatar_register(body: FaceRegisterIn, m: dict = Depends(require_member)):
    """대표 사진으로 얼굴을 만든다. 동의(초상 사용/생전 기록)를 함께 기록한다."""
    require_role(m, "manage")
    d = db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"]))
    if not d:
        raise HTTPException(404)
    if not body.agree:
        raise HTTPException(400, "동의 확인이 필요합니다.")
    if not db.one("SELECT id FROM consents WHERE deceased_id=? AND kind=? AND revoked_at IS NULL", (d["id"], body.kind)):
        db.execute("INSERT INTO consents(deceased_id, signer_name, relation, kind, signed_at, note) VALUES (?,?,?,?,?,?)",
                   (d["id"], m["name"], m["relation"], body.kind, db.now(), "유족 앱에서 동의 · 실시간 아바타"))
        db.audit(f"member:{m['id']}", "consent.create", f"deceased:{d['id']}", body.kind)
    return face.register(d["id"], f"member:{m['id']}")


@router.post("/avatar/photo")
async def avatar_photo(deceased_id: int = Form(...), file: UploadFile = File(...), m: dict = Depends(require_member)):
    """앱에서 정면 사진을 올려 대표 사진으로 쓴다(얼굴 등록 전 단계)."""
    require_role(m, "manage")
    d = db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (deceased_id, m["contract_id"]))
    if not d:
        raise HTTPException(404)
    from pathlib import Path
    import uuid
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "jpg·png·webp 사진만 올릴 수 있습니다.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "사진이 5MB를 넘습니다.")
    rel = f"photos/{uuid.uuid4().hex}{ext}"
    dest = config.MEDIA_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    db.execute("UPDATE deceased SET photo_path=? WHERE id=?", (rel, d["id"]))
    db.audit(f"member:{m['id']}", "photo.update", f"deceased:{d['id']}")
    return {"ok": True}


@router.delete("/avatar/{deceased_id}")
def avatar_remove(deceased_id: int, m: dict = Depends(require_member)):
    require_role(m, "manage")
    if not db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (deceased_id, m["contract_id"])):
        raise HTTPException(404)
    face.delete(deceased_id, f"member:{m['id']}")
    return {"ok": True}
