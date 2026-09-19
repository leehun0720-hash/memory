import time
"""관리자 콘솔 API: 칸 좌표 · 계약·가족 · 고인 프로필·기억 카드·동의서 · 의례 일정 · 이용 현황."""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import config, db, face, voice
from ..ai import factory
from ..deps import require_admin
from ..state import state

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------- 현황 ----------

@router.get("/overview")
def overview():
    cams = db.rows("SELECT c.*, r.name AS room_name FROM cameras c JOIN rooms r ON r.id=c.room_id ORDER BY c.id")
    for c in cams:
        st = state.camera(c["id"])
        c.update(online=st.online, occupied=st.occupied, persons=st.persons, fps=round(st.fps, 1))
        c["niche_count"] = db.one("SELECT COUNT(*) AS n FROM niches WHERE camera_id=?", (c["id"],))["n"]
    counts = {
        "contracts": db.one("SELECT COUNT(*) AS n FROM contracts")["n"],
        "members": db.one("SELECT COUNT(*) AS n FROM family_members")["n"],
        "deceased": db.one("SELECT COUNT(*) AS n FROM deceased")["n"],
        "ai_enabled": db.one("SELECT COUNT(*) AS n FROM deceased WHERE ai_enabled=1")["n"],
        "chat_sessions": db.one("SELECT COUNT(*) AS n FROM chat_sessions")["n"],
        "offerings_pending": db.one("SELECT COUNT(*) AS n FROM offerings WHERE status='requested'")["n"],
        "live_today": db.one("SELECT COUNT(*) AS n FROM live_sessions WHERE started_at >= date('now')")["n"],
    }
    return {"cameras": cams, "counts": counts, "facility": db.one("SELECT * FROM facilities ORDER BY id LIMIT 1"),
            "live_protect": db.get_setting("live_ignore_occupied") != "1"}


class LiveSettingsIn(BaseModel):
    protect: bool   # True=운용(사람 감지 시 실시간 중단) · False=시연(웹캠 앞에 사람이 있어도 계속 송출)


@router.get("/settings/live")
def live_settings_get():
    return {"protect": db.get_setting("live_ignore_occupied") != "1"}


@router.put("/settings/live")
def live_settings_put(body: LiveSettingsIn):
    db.set_setting("live_ignore_occupied", "0" if body.protect else "1")
    db.audit("admin", "settings.live_protect", "live", "on" if body.protect else "off")
    return {"protect": body.protect}


# ---------- 카메라 · 칸 좌표 ----------

class CameraIn(BaseModel):
    name: str
    room_id: int
    kind: str = Field(default="wall", pattern="^(wall|ritual)$")
    device_index: int = 0
    width: int = 1920
    height: int = 1080


@router.get("/rooms")
def rooms():
    return db.rows("SELECT r.*, f.name AS facility_name FROM rooms r JOIN facilities f ON f.id=r.facility_id ORDER BY r.id")


@router.get("/cameras")
def cameras():
    rows = db.rows("SELECT * FROM cameras ORDER BY id")
    for c in rows:
        st = state.camera(c["id"])
        c.update(online=st.online, occupied=st.occupied)
    return rows


@router.post("/cameras")
def camera_create(body: CameraIn):
    cid = db.execute("INSERT INTO cameras(room_id, name, kind, device_index, width, height) VALUES (?,?,?,?,?,?)",
                     (body.room_id, body.name, body.kind, body.device_index, body.width, body.height))
    db.audit("admin", "camera.create", f"camera:{cid}")
    return {"id": cid}


@router.put("/cameras/{cam_id}")
def camera_update(cam_id: int, body: CameraIn):
    db.execute("UPDATE cameras SET room_id=?, name=?, kind=?, device_index=?, width=?, height=? WHERE id=?",
               (body.room_id, body.name, body.kind, body.device_index, body.width, body.height, cam_id))
    return {"ok": True}


@router.delete("/cameras/{cam_id}")
def camera_delete(cam_id: int):
    if db.one("SELECT id FROM niches WHERE camera_id=? LIMIT 1", (cam_id,)):
        raise HTTPException(409, "칸이 등록된 카메라는 삭제할 수 없습니다.")
    db.execute("DELETE FROM cameras WHERE id=?", (cam_id,))
    return {"ok": True}


@router.get("/cameras/{cam_id}/frame.jpg")
def camera_frame(cam_id: int):
    """칸 좌표 등록용 전체 화면. 열람은 기록한다(옆 칸 정보가 보이는 유일한 화면)."""
    db.audit("admin", "frame.view", f"camera:{cam_id}")
    f = state.full(cam_id)
    if f:
        return Response(content=f.data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    p = config.FRAME_DIR / f"cam_{cam_id}.jpg"
    if p.exists():
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    raise HTTPException(404, "아직 카메라 화면이 없습니다. 현장 프로그램이 실행 중인지 확인하세요.")


class NicheIn(BaseModel):
    id: int | None = None
    code: str = Field(min_length=1, max_length=20)
    row: int = 0
    col: int = 0
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


@router.get("/cameras/{cam_id}/niches")
def niches(cam_id: int):
    rows = db.rows("SELECT * FROM niches WHERE camera_id=? ORDER BY row, col, id", (cam_id,))
    for n in rows:
        c = db.one("SELECT id, holder_name FROM contracts WHERE niche_id=?", (n["id"],))
        n["contract"] = c
    return rows


@router.put("/cameras/{cam_id}/niches")
def niches_replace(cam_id: int, body: list[NicheIn]):
    """카메라 한 대의 칸 목록을 통째로 갱신. id가 있으면 수정, 없으면 추가, 목록에 없는 기존 칸은 삭제(계약이 없을 때만)."""
    existing = {n["id"]: n for n in db.rows("SELECT * FROM niches WHERE camera_id=?", (cam_id,))}
    by_code = {n["code"]: n["id"] for n in existing.values()}
    codes = [n.code.strip() for n in body]
    if len(set(codes)) != len(codes):
        raise HTTPException(409, "같은 봉안함 번호가 두 번 있습니다.")
    keep: set[int] = set()
    with db.tx() as conn:
        for n in body:
            nid = n.id if n.id in existing else by_code.get(n.code.strip())
            if nid:
                conn.execute("UPDATE niches SET code=?, row=?, col=?, x=?, y=?, w=?, h=? WHERE id=?",
                             (n.code.strip(), n.row, n.col, n.x, n.y, n.w, n.h, nid))
                keep.add(nid)
            else:
                if conn.execute("SELECT id FROM niches WHERE code=?", (n.code.strip(),)).fetchone():
                    raise HTTPException(409, f"봉안함 번호 {n.code}는 다른 카메라에 이미 있습니다.")
                cur = conn.execute("INSERT INTO niches(camera_id, code, row, col, x, y, w, h) VALUES (?,?,?,?,?,?,?,?)",
                                   (cam_id, n.code.strip(), n.row, n.col, n.x, n.y, n.w, n.h))
                keep.add(cur.lastrowid)
        for nid in existing:
            if nid not in keep:
                if conn.execute("SELECT id FROM contracts WHERE niche_id=?", (nid,)).fetchone():
                    raise HTTPException(409, f"칸 {existing[nid]['code']}에 계약이 있어 삭제할 수 없습니다.")
                conn.execute("DELETE FROM niches WHERE id=?", (nid,))
                p = config.SNAPSHOT_DIR / f"{nid}.jpg"
                if p.exists():
                    p.unlink()
    db.audit("admin", "niches.update", f"camera:{cam_id}", f"{len(body)} niches")
    return niches(cam_id)


# ---------- 계약 · 가족 ----------

class ContractIn(BaseModel):
    holder_name: str
    holder_phone: str = ""
    niche_id: int | None = None
    plan: str = Field(default="basic", pattern="^(basic|premium)$")


class MemberIn(BaseModel):
    name: str
    relation: str = ""
    role: str = Field(default="view", pattern="^(view|chat|manage)$")
    is_minor: bool = False


@router.get("/contracts")
def contracts():
    return db.rows(
        """SELECT c.*, n.code AS niche_code,
                  (SELECT COUNT(*) FROM family_members m WHERE m.contract_id=c.id) AS member_count,
                  (SELECT GROUP_CONCAT(name, ', ') FROM deceased d WHERE d.contract_id=c.id) AS deceased_names
           FROM contracts c LEFT JOIN niches n ON n.id=c.niche_id ORDER BY c.id DESC""")


@router.post("/contracts")
def contract_create(body: ContractIn):
    if body.niche_id and db.one("SELECT id FROM contracts WHERE niche_id=?", (body.niche_id,)):
        raise HTTPException(409, "이미 계약이 연결된 칸입니다.")
    cid = db.execute("INSERT INTO contracts(niche_id, holder_name, holder_phone, plan, created_at) VALUES (?,?,?,?,?)",
                     (body.niche_id, body.holder_name, body.holder_phone, body.plan, db.now()))
    tok = db.token(16)
    db.execute("INSERT INTO family_members(contract_id, name, relation, role, invite_token, created_at) VALUES (?,?,?,?,?,?)",
               (cid, body.holder_name, "계약자", "manage", tok, db.now()))
    db.audit("admin", "contract.create", f"contract:{cid}")
    return {"id": cid, "holder_token": tok}


@router.get("/contracts/{cid}")
def contract_detail(cid: int, request: Request):
    c = db.one("SELECT c.*, n.code AS niche_code FROM contracts c LEFT JOIN niches n ON n.id=c.niche_id WHERE c.id=?", (cid,))
    if not c:
        raise HTTPException(404)
    base = str(request.base_url).rstrip("/")
    members = db.rows("SELECT * FROM family_members WHERE contract_id=? ORDER BY id", (cid,))
    for m in members:
        m["link"] = f"{base}/?t={m['invite_token']}"
    deceased = db.rows("SELECT * FROM deceased WHERE contract_id=? ORDER BY id", (cid,))
    for d in deceased:
        d["consents"] = db.rows("SELECT * FROM consents WHERE deceased_id=? ORDER BY id", (d["id"],))
        d["media"] = db.rows("SELECT * FROM media WHERE deceased_id=? ORDER BY id DESC", (d["id"],))
    return {"contract": c, "members": members, "deceased": deceased,
            "guestbook": db.rows("SELECT * FROM guestbook WHERE contract_id=? ORDER BY id DESC LIMIT 20", (cid,))}


@router.put("/contracts/{cid}")
def contract_update(cid: int, body: ContractIn):
    other = db.one("SELECT id FROM contracts WHERE niche_id=? AND id<>?", (body.niche_id, cid)) if body.niche_id else None
    if other:
        raise HTTPException(409, "이미 계약이 연결된 칸입니다.")
    db.execute("UPDATE contracts SET holder_name=?, holder_phone=?, niche_id=?, plan=? WHERE id=?",
               (body.holder_name, body.holder_phone, body.niche_id, body.plan, cid))
    return {"ok": True}


@router.post("/contracts/{cid}/members")
def member_create(cid: int, body: MemberIn, request: Request):
    tok = db.token(16)
    mid = db.execute("INSERT INTO family_members(contract_id, name, relation, role, invite_token, is_minor, created_at) VALUES (?,?,?,?,?,?,?)",
                     (cid, body.name, body.relation, body.role, tok, int(body.is_minor), db.now()))
    return {"id": mid, "link": f"{str(request.base_url).rstrip('/')}/?t={tok}"}


@router.delete("/members/{mid}")
def member_delete(mid: int):
    db.execute("DELETE FROM family_members WHERE id=?", (mid,))
    return {"ok": True}


# ---------- 고인 프로필 · 기억 카드 · 동의서 ----------

class DeceasedIn(BaseModel):
    contract_id: int
    name: str
    honorific: str = ""
    birth_date: str = ""
    death_date: str = ""
    memory_card: str = Field(default="", max_length=8000)
    voice_note: str = ""
    ai_enabled: bool = False
    chat_min_days_after_death: int = 49
    theme: str = Field(default="classic", pattern="^(classic|buddhist|catholic|christian)$")   # 추모 공간 테마(종교)


@router.post("/deceased")
def deceased_create(body: DeceasedIn):
    did = db.execute(
        """INSERT INTO deceased(contract_id, name, honorific, birth_date, death_date, memory_card, voice_note, ai_enabled, chat_min_days_after_death, theme, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (body.contract_id, body.name, body.honorific, body.birth_date, body.death_date, body.memory_card, body.voice_note,
         int(body.ai_enabled), body.chat_min_days_after_death, body.theme, db.now()))
    db.audit("admin", "deceased.create", f"deceased:{did}")
    return {"id": did}


@router.put("/deceased/{did}")
def deceased_update(did: int, body: DeceasedIn):
    db.execute(
        """UPDATE deceased SET contract_id=?, name=?, honorific=?, birth_date=?, death_date=?, memory_card=?, voice_note=?, ai_enabled=?, chat_min_days_after_death=?, theme=? WHERE id=?""",
        (body.contract_id, body.name, body.honorific, body.birth_date, body.death_date, body.memory_card, body.voice_note,
         int(body.ai_enabled), body.chat_min_days_after_death, body.theme, did))
    db.audit("admin", "deceased.update", f"deceased:{did}")
    return {"ok": True}


def _save_upload(file: UploadFile, sub: str) -> str:
    ext = Path(file.filename or "").suffix.lower() or ".bin"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".m4a", ".mp3", ".wav"}:
        raise HTTPException(400, "지원하지 않는 파일 형식입니다.")
    rel = f"{sub}/{uuid.uuid4().hex}{ext}"
    dest = config.MEDIA_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file.file.read())
    return rel


@router.post("/deceased/{did}/photo")
def deceased_photo(did: int, file: UploadFile = File(...)):
    rel = _save_upload(file, "photos")
    db.execute("UPDATE deceased SET photo_path=? WHERE id=?", (rel, did))
    return {"path": rel}


@router.post("/deceased/{did}/media")
def deceased_media(did: int, kind: str = "photo", caption: str = "", ai_generated: bool = False, file: UploadFile = File(...)):
    if kind not in {"photo", "video", "voice", "message_video"}:
        raise HTTPException(400, "kind")
    if kind == "voice":
        r = voice.save_sample(did, file.filename or "sample.mp3", file.file.read(), caption or "관리자 업로드")
        return {"id": r["media_id"], "path": r["path"], "seconds": r["seconds"]}
    rel = _save_upload(file, kind)
    mid = db.execute("INSERT INTO media(deceased_id, kind, path, caption, ai_generated, created_at) VALUES (?,?,?,?,?,?)",
                     (did, kind, rel, caption, int(ai_generated or kind == "message_video"), db.now()))
    return {"id": mid, "path": rel}


@router.delete("/media/{mid}")
def media_delete(mid: int):
    r = db.one("SELECT path FROM media WHERE id=?", (mid,))
    if r:
        p = config.MEDIA_DIR / r["path"]
        if p.exists():
            p.unlink()
        db.execute("DELETE FROM media WHERE id=?", (mid,))
    return {"ok": True}


@router.get("/media/{mid}")
def media_get(mid: int):
    r = db.one("SELECT path FROM media WHERE id=?", (mid,))
    if not r:
        raise HTTPException(404)
    return FileResponse(config.MEDIA_DIR / r["path"])


@router.get("/deceased/{did}/photo.jpg")
def deceased_photo_get(did: int):
    d = db.one("SELECT photo_path FROM deceased WHERE id=?", (did,))
    if not d or not d["photo_path"]:
        raise HTTPException(404)
    return FileResponse(config.MEDIA_DIR / d["photo_path"])


class ConsentIn(BaseModel):
    signer_name: str
    relation: str = ""
    kind: str = Field(pattern="^(ai_chat|likeness|voice|lifetime_record)$")
    note: str = ""


@router.post("/deceased/{did}/consents")
def consent_create(did: int, body: ConsentIn):
    cid = db.execute("INSERT INTO consents(deceased_id, signer_name, relation, kind, signed_at, note) VALUES (?,?,?,?,?,?)",
                     (did, body.signer_name, body.relation, body.kind, db.now(), body.note))
    db.audit("admin", "consent.create", f"consent:{cid}", body.kind)
    return {"id": cid}


@router.post("/consents/{cid}/revoke")
def consent_revoke(cid: int):
    db.execute("UPDATE consents SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (db.now(), cid))
    db.audit("admin", "consent.revoke", f"consent:{cid}")
    return {"ok": True}


# ---------- 의례 일정 · 중계 ----------

class RitualIn(BaseModel):
    title: str
    kind: str = Field(default="memorial", pattern="^(memorial|holiday|event)$")
    access: str = Field(default="open", pattern="^(open|applied)$")   # open=누구나 생중계 · applied=신청 가족만
    scheduled_at: str
    contract_id: int | None = None
    stream_url: str = ""
    camera_id: int | None = None
    replay_url: str = ""
    note: str = ""


@router.get("/rituals")
def rituals():
    return db.rows("""SELECT r.*, c.holder_name,
                             (SELECT COUNT(*) FROM ritual_participants p WHERE p.ritual_id=r.id AND p.status<>'rejected') AS participant_count
                      FROM rituals r LEFT JOIN contracts c ON c.id=r.contract_id ORDER BY scheduled_at DESC""")


@router.post("/rituals")
def ritual_create(body: RitualIn):
    fac = db.one("SELECT id FROM facilities ORDER BY id LIMIT 1")
    rid = db.execute(
        "INSERT INTO rituals(facility_id, contract_id, title, kind, access, scheduled_at, stream_url, camera_id, replay_url, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (fac["id"], body.contract_id, body.title, body.kind, body.access, body.scheduled_at, body.stream_url, body.camera_id, body.replay_url, body.note))
    return {"id": rid}


@router.put("/rituals/{rid}")
def ritual_update(rid: int, body: RitualIn):
    db.execute("UPDATE rituals SET contract_id=?, title=?, kind=?, access=?, scheduled_at=?, stream_url=?, camera_id=?, replay_url=?, note=? WHERE id=?",
               (body.contract_id, body.title, body.kind, body.access, body.scheduled_at, body.stream_url, body.camera_id, body.replay_url, body.note, rid))
    return {"ok": True}


@router.delete("/rituals/{rid}")
def ritual_delete(rid: int):
    db.execute("DELETE FROM rituals WHERE id=?", (rid,))
    return {"ok": True}


# ---------- 제사 생중계 진행 콘솔: 참여 가족·봉행 순서·현재 차례·가족 메시지·현장 화면 ----------

def _ritual_or_404(rid: int) -> dict:
    r = db.one("SELECT * FROM rituals WHERE id=?", (rid,))
    if not r:
        raise HTTPException(404, "일정이 없습니다.")
    return r


@router.get("/rituals/{rid}/console")
def ritual_console(rid: int):
    r = _ritual_or_404(rid)
    parts = db.rows(
        """SELECT p.*, d.name AS deceased_name, d.birth_date, d.death_date, c.holder_name
           FROM ritual_participants p JOIN contracts c ON c.id=p.contract_id LEFT JOIN deceased d ON d.id=p.deceased_id
           WHERE p.ritual_id=? ORDER BY CASE WHEN p.order_no>0 THEN 0 ELSE 1 END, p.order_no, p.id""", (rid,))
    contracts = db.rows("SELECT c.id, c.holder_name, (SELECT GROUP_CONCAT(d.name, ', ') FROM deceased d WHERE d.contract_id=c.id) AS deceased_names FROM contracts c ORDER BY c.id")
    return {"ritual": r, "participants": parts, "contracts": contracts, "viewer_count": state.viewer_count(rid)}


@router.get("/rituals/{rid}/live")
def ritual_live_admin(rid: int, since: int = 0, rseq: int = -1):
    """진행 콘솔·현장 화면(TV)이 2초마다 부른다. 유족 앱과 같은 payload."""
    from .family import _live_payload, _participants
    r = _ritual_or_404(rid)
    return _live_payload(r, _participants(rid), since, rseq)


@router.get("/rituals/{rid}/stream")
def ritual_stream_admin(rid: int):
    """현장 화면(TV)용 MJPEG. 관리자 키를 ?key= 로 받는다."""
    from .family import _mjpeg
    r = _ritual_or_404(rid)
    if r["camera_id"] is None:
        raise HTTPException(404, "현장 카메라가 없는 일정입니다.")
    return StreamingResponse(_mjpeg(-r["camera_id"], time.time() + 6 * 3600, None),
                             media_type="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-store"})


class ParticipantIn(BaseModel):
    contract_id: int
    deceased_id: int | None = None
    mourner_name: str = ""
    note: str = ""


class ParticipantUpdate(BaseModel):
    order_no: int | None = None
    status: str | None = Field(default=None, pattern="^(requested|accepted|rejected)$")
    mourner_name: str | None = None


@router.post("/rituals/{rid}/participants")
def participant_add(rid: int, body: ParticipantIn):
    _ritual_or_404(rid)
    c = db.one("SELECT holder_name FROM contracts WHERE id=?", (body.contract_id,))
    if not c:
        raise HTTPException(404, "계약이 없습니다.")
    if db.one("SELECT id FROM ritual_participants WHERE ritual_id=? AND contract_id=? AND status<>'rejected'", (rid, body.contract_id)):
        raise HTTPException(409, "이미 참여 중인 가족입니다.")
    d = (db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, body.contract_id)) if body.deceased_id
         else db.one("SELECT id FROM deceased WHERE contract_id=? ORDER BY id LIMIT 1", (body.contract_id,)))
    nxt = (db.one("SELECT COALESCE(MAX(order_no),0) AS n FROM ritual_participants WHERE ritual_id=?", (rid,))["n"] or 0) + 1
    pid = db.execute("INSERT INTO ritual_participants(ritual_id, contract_id, deceased_id, mourner_name, order_no, status, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (rid, body.contract_id, d["id"] if d else None, body.mourner_name.strip() or c["holder_name"], nxt, "accepted", body.note, db.now()))
    return {"id": pid, "order_no": nxt}


@router.put("/rituals/{rid}/participants/{pid}")
def participant_update(rid: int, pid: int, body: ParticipantUpdate):
    x = db.one("SELECT * FROM ritual_participants WHERE id=? AND ritual_id=?", (pid, rid))
    if not x:
        raise HTTPException(404)
    db.execute("UPDATE ritual_participants SET order_no=?, status=?, mourner_name=? WHERE id=?",
               (x["order_no"] if body.order_no is None else max(0, body.order_no), body.status or x["status"],
                x["mourner_name"] if body.mourner_name is None else body.mourner_name.strip(), pid))
    return {"ok": True}


@router.delete("/rituals/{rid}/participants/{pid}")
def participant_delete(rid: int, pid: int):
    db.execute("DELETE FROM ritual_participants WHERE id=? AND ritual_id=?", (pid, rid))
    return {"ok": True}


class CurrentIn(BaseModel):
    order_no: int = 0   # 0 = 시작 전


@router.post("/rituals/{rid}/current")
def ritual_current(rid: int, body: CurrentIn):
    _ritual_or_404(rid)
    db.execute("UPDATE rituals SET current_order=? WHERE id=?", (max(0, body.order_no), rid))
    db.audit("admin", "ritual.current", f"ritual:{rid}", str(body.order_no))
    return {"current_order": max(0, body.order_no)}


@router.post("/rituals/{rid}/next")
def ritual_next(rid: int):
    """다음 차례로. 마지막 다음은 '마침'(목록에 없는 번호)."""
    r = _ritual_or_404(rid)
    orders = [x["order_no"] for x in db.rows("SELECT order_no FROM ritual_participants WHERE ritual_id=? AND status<>'rejected' AND order_no>0 ORDER BY order_no", (rid,))]
    if not orders:
        raise HTTPException(400, "봉행 순서가 없습니다. 참여 가족의 순서 번호를 먼저 정하세요.")
    cur = r.get("current_order") or 0
    nxt = next((o for o in orders if o > cur), None)
    new = nxt if nxt is not None else orders[-1] + 1
    db.execute("UPDATE rituals SET current_order=? WHERE id=?", (new, rid))
    return {"current_order": new, "finished": nxt is None}


class SiteMessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    kind: str = Field(default="chat", pattern="^(chat|notice)$")


@router.post("/rituals/{rid}/messages")
def ritual_site_message(rid: int, body: SiteMessageIn):
    _ritual_or_404(rid)
    mid = db.execute("INSERT INTO ritual_messages(ritual_id, contract_id, sender, author, kind, message, created_at) VALUES (?,?,?,?,?,?,?)",
                     (rid, None, "site", "진행자", body.kind, body.message.strip(), db.now()))
    return {"id": mid}


# ---------- 공양 접수 · 이용 현황 ----------

@router.get("/offerings")
def offerings():
    return db.rows(
        """SELECT o.*, c.holder_name, m.name AS member_name, r.title AS ritual_title
           FROM offerings o JOIN contracts c ON c.id=o.contract_id
           LEFT JOIN family_members m ON m.id=o.member_id LEFT JOIN rituals r ON r.id=o.ritual_id
           ORDER BY o.id DESC LIMIT 200""")


class StatusIn(BaseModel):
    status: str = Field(pattern="^(requested|accepted|done|cancelled)$")


@router.post("/offerings/{oid}/status")
def offering_status(oid: int, body: StatusIn):
    db.execute("UPDATE offerings SET status=? WHERE id=?", (body.status, oid))
    return {"ok": True}


@router.get("/usage")
def usage():
    return {
        "chat_sessions": db.rows(
            """SELECT s.*, d.name AS deceased_name, m.name AS member_name FROM chat_sessions s
               JOIN deceased d ON d.id=s.deceased_id JOIN family_members m ON m.id=s.member_id
               ORDER BY s.started_at DESC LIMIT 50"""),
        "live_sessions": db.rows(
            """SELECT l.*, n.code, m.name AS member_name FROM live_sessions l JOIN niches n ON n.id=l.niche_id
               JOIN family_members m ON m.id=l.member_id ORDER BY l.started_at DESC LIMIT 50"""),
        "audit": db.rows("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100"),
        "safety_events": db.one("SELECT COUNT(*) AS n FROM chat_sessions WHERE safety_events NOT IN ('', '[]')")["n"],
    }


# ---------- AI 설정 (API 키는 관리자 콘솔에서 입력) ----------

MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]


def _mask(key: str) -> str:
    return "" if not key else (key[:7] + "…" + key[-4:] if len(key) > 14 else "•" * len(key))


class AISettingsIn(BaseModel):
    api_key: str | None = None          # None이면 기존 키 유지, ""이면 삭제
    provider: str = Field(default="auto", pattern="^(auto|anthropic|mock)$")
    model: str = Field(default="claude-opus-5")
    elevenlabs_api_key: str | None = None
    tts_provider: str = Field(default="auto", pattern="^(auto|elevenlabs|browser)$")
    tts_model: str = Field(default="eleven_multilingual_v2")
    tts_voice_settings: dict | None = None   # {"stability","similarity_boost","style","speed"} · None이면 유지
    simli_api_key: str | None = None
    did_api_key: str | None = None
    avatar_provider: str = Field(default="auto", pattern="^(auto|did|simli|off)$")


@router.get("/settings/ai")
def ai_settings_get():
    from ..ai.tts import ElevenLabsTTS
    e = factory.effective()
    t = factory.effective_tts()
    active = factory.llm()
    return {
        "api_key_masked": _mask(db.get_setting("anthropic_api_key")),
        "api_key_source": "console" if db.get_setting("anthropic_api_key") else ("env" if e["api_key"] else "none"),
        "provider": e["provider"], "model": e["model"], "models": MODELS,
        "active_provider": active.name,
        "updated_at": (db.one("SELECT updated_at FROM settings WHERE key='anthropic_api_key'") or {}).get("updated_at"),
        "elevenlabs_key_masked": _mask(db.get_setting("elevenlabs_api_key")),
        "elevenlabs_key_source": "console" if db.get_setting("elevenlabs_api_key") else ("env" if t["api_key"] else "none"),
        "tts_provider": t["provider"], "tts_model": t["model"], "tts_models": ElevenLabsTTS.MODELS,
        "tts_voice_settings": ElevenLabsTTS.clean_settings(t.get("voice_settings")), "tts_voice_defaults": ElevenLabsTTS.DEFAULT_SETTINGS,
        "active_tts": factory.tts().name,
        "voices_registered": db.one("SELECT COUNT(*) AS n FROM deceased WHERE voice_id<>''")["n"],
        "simli_key_masked": _mask(db.get_setting("simli_api_key")),
        "simli_key_source": "console" if db.get_setting("simli_api_key") else ("env" if factory.effective_avatar()["api_key"] else "none"),
        "avatar_provider": factory.effective_avatar()["provider"],
        "active_avatar": factory.avatar().name,
        "did_key_masked": _mask(db.get_setting("did_api_key")),
        "did_key_source": "console" if db.get_setting("did_api_key") else ("env" if factory.effective_avatar()["did_api_key"] else "none"),
        "faces_registered": db.one("SELECT COUNT(*) AS n FROM deceased WHERE face_id<>''")["n"],
    }


@router.put("/settings/ai")
def ai_settings_put(body: AISettingsIn):
    if body.model not in MODELS:
        raise HTTPException(400, "지원하지 않는 모델입니다.")
    if body.api_key is not None:
        key = body.api_key.strip()
        if key and not key.startswith("sk-ant-"):
            raise HTTPException(400, "Anthropic API 키는 sk-ant- 로 시작합니다.")
        db.set_setting("anthropic_api_key", key)
        db.audit("admin", "settings.api_key", "anthropic", "set" if key else "cleared")
    db.set_setting("llm_provider", body.provider)
    db.set_setting("llm_model", body.model)
    factory.reset()
    if body.elevenlabs_api_key is not None:
        k = body.elevenlabs_api_key.strip()
        if k and not (k.startswith("sk_") or re.fullmatch(r"[0-9a-f]{32}", k)):
            raise HTTPException(400, f"ElevenLabs 키 형식이 아닙니다(받은 값: {k[:6]}… {len(k)}자). 키는 sk_ 로 시작하며, 키를 만든 직후 한 번만 보이는 전체 값을 복사해야 합니다. 키 목록에 보이는 요약본은 쓸 수 없습니다.")
        db.set_setting("elevenlabs_api_key", k)
        db.audit("admin", "settings.api_key", "elevenlabs", "set" if body.elevenlabs_api_key.strip() else "cleared")
    db.set_setting("tts_provider", body.tts_provider)
    db.set_setting("tts_model", body.tts_model)
    if body.tts_voice_settings is not None:
        import json
        from ..ai.tts import ElevenLabsTTS
        db.set_setting("tts_voice_settings", json.dumps(ElevenLabsTTS.clean_settings(body.tts_voice_settings)))
    factory.reset_tts()
    if body.simli_api_key is not None:
        db.set_setting("simli_api_key", body.simli_api_key.strip())
        db.audit("admin", "settings.api_key", "simli", "set" if body.simli_api_key.strip() else "cleared")
    if body.did_api_key is not None:
        k = body.did_api_key.strip()
        if k and ":" not in k:
            raise HTTPException(400, "D-ID 키 형식이 아닙니다. Studio → Account settings 에서 만든 키는 'API_USER:API_PASSWORD'처럼 콜론(:)이 들어 있습니다. 표시된 값 전체를 복사하세요.")
        db.set_setting("did_api_key", k)
        db.audit("admin", "settings.api_key", "did", "set" if k else "cleared")
    db.set_setting("avatar_provider", body.avatar_provider)
    factory.reset_avatar()
    return ai_settings_get()


@router.post("/settings/did/test")
def did_settings_test():
    from ..ai.avatar import AvatarError, DIDAvatar
    e = factory.effective_avatar()
    if not e["did_api_key"]:
        raise HTTPException(400, "D-ID API 키가 없습니다. 먼저 저장하세요.")
    try:
        info = DIDAvatar(e["did_api_key"]).ping()
        db.audit("admin", "settings.did_test", "did", "ok")
        return {"ok": True, **info}
    except AvatarError as ex:
        raise HTTPException(ex.status if 400 <= ex.status < 600 else 502, ex.message)
    except Exception as ex:
        raise HTTPException(503, f"D-ID에 연결할 수 없습니다: {ex}")


@router.post("/settings/avatar/test")
def avatar_settings_test():
    from ..ai.avatar import AvatarError, SimliAvatar
    e = factory.effective_avatar()
    if not e["api_key"]:
        raise HTTPException(400, "Simli API 키가 없습니다. 먼저 저장하세요.")
    try:
        info = SimliAvatar(e["api_key"]).ping()
        db.audit("admin", "settings.avatar_test", "simli", "ok" if info["all_ok"] else "partial")
        return {"ok": True, **info}
    except AvatarError as ex:
        raise HTTPException(ex.status if 400 <= ex.status < 600 else 502, ex.message)
    except Exception as ex:
        raise HTTPException(503, f"Simli에 연결할 수 없습니다: {ex}")


@router.post("/deceased/{did}/face/register")
def face_register(did: int):
    """대표 사진으로 실시간 아바타 얼굴을 만든다. 초상 사용 동의서가 있어야 한다."""
    return face.register(did, "admin")


@router.delete("/deceased/{did}/face")
def face_delete(did: int):
    face.delete(did, "admin")
    return {"ok": True}


@router.get("/avatar/presets")
def avatar_presets():
    return face.presets()


class PresetIn(BaseModel):
    face_id: str


@router.post("/deceased/{did}/face/preset")
def face_preset(did: int, body: PresetIn):
    return face.set_preset(did, body.face_id, "admin")


class TTSPreviewIn(BaseModel):
    text: str = Field(default="아이고, 우리 강아지 왔냐. 밥은 묵었냐? 요즘 날이 쌀쌀헌디 옷 따숩게 입고 댕겨라.", max_length=300)
    model: str | None = None
    settings: dict | None = None
    deceased_id: int | None = None


@router.post("/settings/tts/preview")
def tts_settings_preview(body: TTSPreviewIn):
    """음성 세부 설정을 저장하기 전에 등록된 복제 음성으로 들어 본다. deceased_id가 없으면 첫 등록 음성."""
    from ..ai.tts import ElevenLabsTTS, TTSError
    t = factory.tts()
    if t.name != "elevenlabs":
        raise HTTPException(400, "ElevenLabs가 꺼져 있습니다. 키를 저장하고 공급자를 '자동'으로 두세요.")
    q = "SELECT voice_id, name FROM deceased WHERE voice_id<>''" + (" AND id=?" if body.deceased_id else "") + " ORDER BY id LIMIT 1"
    d = db.one(q, (body.deceased_id,) if body.deceased_id else ())
    if not d:
        raise HTTPException(404, "등록된 복제 음성이 없습니다. 고인 화면에서 먼저 음성을 등록하세요.")
    try:
        r = t.synthesize(body.text[:300], d["voice_id"], settings=body.settings, model=body.model)
    except TTSError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.message)
    return Response(content=r.audio, media_type=r.mime, headers={"Cache-Control": "no-store", "X-Voice-Name": "preview"})


@router.post("/settings/tts/test")
def tts_settings_test():
    from ..ai.tts import ElevenLabsTTS, TTSError
    t = factory.effective_tts()
    if not t["api_key"]:
        raise HTTPException(400, "ElevenLabs API 키가 없습니다. 먼저 저장하세요.")
    try:
        info = ElevenLabsTTS(t["api_key"], t["model"]).ping()
        db.audit("admin", "settings.tts_test", "elevenlabs", "ok")
        return {"ok": True, **info}
    except TTSError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.message)
    except Exception as e:  # requests 연결 오류 등
        raise HTTPException(503, f"ElevenLabs에 연결할 수 없습니다: {e}")


# ---------- 고인 음성 등록(복제) — 공통 로직은 server/voice.py ----------

@router.post("/deceased/{did}/voice/register")
def voice_register(did: int):
    """등록된 음성 자료(media.kind='voice')로 복제 음성을 만든다. 음성 사용 동의서가 있어야 한다."""
    return voice.register(did, "admin")


@router.delete("/deceased/{did}/voice")
def voice_delete(did: int):
    voice.delete(did, "admin")
    return {"ok": True}


@router.post("/deceased/{did}/voice/preview")
def voice_preview(did: int, text: str = "안녕, 잘 지냈니? 밥은 먹었고?"):
    audio, mime = voice.preview(did, text)
    return Response(content=audio, media_type=mime)


@router.post("/settings/ai/test")
def ai_settings_test():
    """저장된 키·모델로 아주 짧은 호출을 보내 실제로 통하는지 확인한다."""
    e = factory.effective()
    if not e["api_key"]:
        raise HTTPException(400, "API 키가 없습니다. 먼저 저장하세요.")
    import anthropic
    from ..ai.llm_anthropic import AnthropicLLM
    try:
        reply = AnthropicLLM(e["model"], api_key=e["api_key"]).ping()
        db.audit("admin", "settings.api_test", e["model"], "ok")
        return {"ok": True, "model": e["model"], "reply": reply}
    except anthropic.AuthenticationError:
        raise HTTPException(401, "키가 올바르지 않습니다(인증 실패).")
    except anthropic.PermissionDeniedError:
        raise HTTPException(403, "이 키에는 권한이 없습니다.")
    except anthropic.NotFoundError:
        raise HTTPException(404, f"모델 {e['model']}을 찾을 수 없습니다.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "요청 한도 초과. 잠시 뒤 다시 시도하세요.")
    except anthropic.BadRequestError as ex:
        from ..ai.llm_anthropic import is_credit_error
        if is_credit_error(ex):
            raise HTTPException(402, "키는 정상이지만 Anthropic 계정에 크레딧이 없습니다. console.anthropic.com → Plans & Billing에서 충전하세요. 충전 전까지 대화는 자동으로 Mock으로 답합니다.")
        raise HTTPException(400, f"요청 오류: {ex.message}")
    except anthropic.APIStatusError as ex:
        raise HTTPException(502, f"API 오류 {ex.status_code}: {ex.message}")
    except anthropic.APIConnectionError:
        raise HTTPException(503, "Anthropic API에 연결할 수 없습니다. 인터넷 연결을 확인하세요.")
