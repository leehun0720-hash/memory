"""유족 웹앱 API. 초대 토큰 하나로 계약·칸·고인이 결정된다."""
import asyncio
import json
from typing import Literal
import time
from datetime import datetime, timedelta

from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from .. import ratelimit
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import config, db, face, music, services, voice
from ..ai.avatar import SimliAvatar  # 기본 얼굴 목록
from ..deps import require_member, require_role
from ..state import state
from .edge import _always_live, _in_window, _live_open, _demo_mode

router = APIRouter(prefix="/api/family", tags=["family"])


def _style_of(raw) -> dict:
    """저장된 테마 세부(JSON)를 검사해 돌려준다. 망가졌거나 비었으면 기본값."""
    try:
        return ThemeStyle(**json.loads(raw)).model_dump() if raw else ThemeStyle().model_dump()
    except Exception:
        return ThemeStyle().model_dump()


def _held_by(deceased_id: int) -> list[dict]:
    """인공지능 대화를 '보류'한(아직 접속이 살아 있는) 가족."""
    return db.rows("""SELECT f.id, f.name FROM ai_family_stances s JOIN family_members f ON f.id=s.member_id
                      WHERE s.deceased_id=? AND s.stance='hold' AND f.revoked_at IS NULL ORDER BY f.id""", (deceased_id,))


def _deceased_for(contract_id: int) -> list[dict]:
    rows = db.rows("SELECT * FROM deceased WHERE contract_id=? ORDER BY id", (contract_id,))
    for d in rows:
        d["has_photo"] = bool(d["photo_path"])
        d["consent_valid"] = db.one(
            "SELECT id FROM consents WHERE deceased_id=? AND kind='ai_chat' AND revoked_at IS NULL", (d["id"],)
        ) is not None
        d["family_hold"] = [r["name"] for r in _held_by(d["id"])]   # 대화를 보류한 가족(한 분이라도 있으면 열리지 않음)
        d["chat_available"] = bool(d["ai_enabled"]) and d["consent_valid"] and not d["family_hold"]
        d["days_since_death"] = _days_since(d["death_date"])
        d["has_voice"] = bool(d.get("voice_id"))
        d["has_face"] = bool(d.get("face_id"))
        d["theme_style"] = _style_of(d.get("theme_style"))
        d.pop("memory_card", None)   # 기억 카드는 유족 화면에 노출하지 않음
        d.pop("voice_id", None); d.pop("voice_provider", None); d.pop("face_id", None); d.pop("face_provider", None)
    return rows


def _days_since(date_str: str) -> int | None:
    try:
        return (datetime.now().date() - datetime.fromisoformat(date_str).date()).days
    except (ValueError, TypeError):
        return None


@router.post("/session")
def session_cookie(request: Request, m: dict = Depends(require_member)):
    """헤더로 확인한 초대 토큰을 보안 쿠키로 준다. 이후 사진·영상·생중계 주소에 ?t= 를 싣지 않는다."""
    from fastapi.responses import JSONResponse
    from ..deps import FAMILY_COOKIE
    resp = JSONResponse({"ok": True})
    resp.set_cookie(FAMILY_COOKIE, m["invite_token"], max_age=30 * 86400, path="/api/family", httponly=True,
                    samesite="strict", secure=request.url.scheme == "https")
    return resp


@router.delete("/session")
def session_cookie_clear():
    from fastapi.responses import JSONResponse
    from ..deps import FAMILY_COOKIE
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(FAMILY_COOKIE, path="/api/family")
    return resp


@router.get("/me")
def me(m: dict = Depends(require_member)):
    cam = state.camera(m["camera_id"]) if m["camera_id"] else None
    return {
        "member": {"id": m["id"], "name": m["name"], "relation": m["relation"], "role": m["role"], "is_minor": bool(m["is_minor"])},
        "contract": {"id": m["contract_id"], "holder_name": m["holder_name"], "plan": m["plan"]},
        "niche": {"id": m["niche_id"], "code": m["niche_code"]} if m["niche_id"] else None,
        "camera": {"online": cam.online, "occupied": cam.occupied, "demo": cam.online and cam.virtual} if cam else None,
        "deceased": _deceased_for(m["contract_id"]),
        "live_seconds": config.LIVE_SECONDS,
        "chat_max_minutes": config.CHAT_MAX_MINUTES,
        "tts_provider": config.TTS_PROVIDER,
    }


THEMES = ("classic", "buddhist", "catholic", "christian")


class ThemeStyle(BaseModel):
    """테마 세부. 글자 크기는 사람마다 달라 각 기기에만 저장한다(서버에 두지 않음)."""
    accent: Literal["1", "2", "3", "4"] = "1"                     # 테마별 강조색 네 가지 중 하나
    pattern: Literal["off", "soft", "clear"] = "soft"              # 배경 문양: 끄기 · 은은하게 · 조금 더 또렷하게
    tone: Literal["hanji", "dawn", "mist"] = "hanji"               # 바탕 빛: 한지 · 새벽 노을 · 고요한 안개
    font: Literal["myeongjo", "batang", "gothic"] = "myeongjo"     # 제목 글꼴: 명조 · 부드러운 바탕 · 또렷한 고딕


class ThemeIn(BaseModel):
    deceased_id: int
    theme: str = Field(pattern="^(classic|buddhist|catholic|christian)$")
    style: ThemeStyle | None = None


@router.post("/theme")
def set_theme(body: ThemeIn, m: dict = Depends(require_member)):
    """추모 공간 테마(전통·불교·천주교·기독교). 계약자만 바꿀 수 있고 가족 모두에게 적용된다."""
    require_role(m, "manage")
    if not db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"])):
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if body.style is None:
        db.execute("UPDATE deceased SET theme=? WHERE id=?", (body.theme, body.deceased_id))
    else:
        db.execute("UPDATE deceased SET theme=?, theme_style=? WHERE id=?", (body.theme, json.dumps(body.style.model_dump()), body.deceased_id))
    db.audit(f"member:{m['id']}", "theme.set", f"deceased:{body.deceased_id}", body.theme)
    style = _style_of(db.one("SELECT theme_style FROM deceased WHERE id=?", (body.deceased_id,))["theme_style"])
    return {"ok": True, "theme": body.theme, "style": style}


# ---------- 원격 참배 ----------

def _live_protect() -> bool:
    """참배객 보호: 현장에 사람이 감지되면 실시간 송출을 멈춘다. 관리자 콘솔에서 시연용으로 끌 수 있다."""
    return db.get_setting("live_ignore_occupied") != "1"


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
        "live_protect": _live_protect(),
        "blurry": cam.online and 0 <= cam.sharpness < 40,
        "camera_online": cam.online,
        "demo_camera": cam.online and cam.virtual,   # 서버가 여해원 사진으로 만든 시연 화면(실제 현장 중계 아님)
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
    ratelimit.hit(f"live:{m['id']}", 30, 3600, "실시간 보기는 한 시간에 30번까지 열 수 있습니다. 잠시 뒤 다시 열어 주세요.")
    if not m["niche_id"]:
        raise HTTPException(404, "연결된 봉안함이 없습니다.")
    cam = state.camera(m["camera_id"])
    if not cam.online:
        raise HTTPException(503, "현장 카메라가 연결되어 있지 않습니다. 마지막 사진을 보여 드립니다.")
    if cam.occupied and _live_protect():
        raise HTTPException(409, "지금 현장에 다른 참배객이 계십니다. 잠시 뒤 다시 시도해 주세요.")
    sid = db.token(12)
    started = datetime.now().astimezone()
    expires = started + timedelta(seconds=config.LIVE_SECONDS)
    db.execute("INSERT INTO live_sessions(id, niche_id, member_id, started_at, expires_at) VALUES (?,?,?,?,?)",
               (sid, m["niche_id"], m["id"], started.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")))
    db.audit(f"member:{m['id']}", "live.start", f"niche:{m['niche_code']}")
    return {"session_id": sid, "seconds": config.LIVE_SECONDS, "expires_at": expires.isoformat(timespec="seconds")}


async def _mjpeg(key: int, deadline: float, cam_id: int | None):
    """실시간 영상(MJPEG). 비동기로 새 장면을 기다려 서버 작업자(스레드)를 붙잡지 않는다(시청자가 많아도 다른 화면이 멈추지 않게).
    5초 넘은 장면은 '실시간'으로 내보내지 않는다(지난 장면이 먼저 보이지 않게)."""
    boundary = b"--frame"
    state.watch(key, +1)
    try:
        async for chunk in _mjpeg_frames(key, deadline, cam_id, boundary):
            yield chunk
    finally:
        state.watch(key, -1)


async def _mjpeg_frames(key: int, deadline: float, cam_id: int | None, boundary: bytes):
    seq = 0
    idle_since = time.time()
    next_check = 0.0
    while time.time() < deadline:
        now = time.time()
        if cam_id is not None and now >= next_check:
            next_check = now + 1.0
            if state.camera(cam_id).occupied and _live_protect():
                break   # 참배객 보호: 사람 감지 시 송출 중단 → 클라이언트가 사진 화면으로 전환
        f = state.live_frames.get(key)
        if f is None or f.seq <= seq or now - f.at >= 5:
            if now - idle_since > 8:
                break
            await asyncio.sleep(0.04)
            continue
        idle_since = now
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
        d["media"] = db.rows("SELECT id, kind, path, caption, ai_generated, created_at FROM media WHERE deceased_id=? AND kind<>'music' ORDER BY id DESC", (d["id"],))
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
        if _always_live(r["camera_id"]):      # 시연 모드·시연 카메라: 카메라 일정은 언제나 중계 중
            r["is_live_window"], r["is_past"] = True, False
        r["has_camera"] = r["camera_id"] is not None and state.camera(r["camera_id"]).online
        r["access"] = r.get("access") or "open"
        r["current_order"] = r.get("current_order") or 0
        parts = _participants(r["id"], m["contract_id"])
        r["participants"] = [{k: x[k] for k in ("order_no", "deceased_name", "mourner_name", "birth_date", "death_date", "status", "is_mine")} for x in parts]
        r["my_participation"] = next((x for x in r["participants"] if x["is_mine"]), None)
        r["can_watch"] = _can_watch(r, m, parts)
        if not r["can_watch"]:   # 신청 가족만 보는 제례: 외부 중계·다시보기 주소를 내려보내지 않는다
            r["stream_url"], r["replay_url"] = "", ""
        r["viewer_count"] = state.viewer_count(r["id"])
    return rows


@router.get("/rituals/{ritual_id}/stream")
def ritual_stream(ritual_id: int, m: dict = Depends(require_member)):
    r = _ritual_visible(ritual_id, m)
    if not _can_watch(r, m, _participants(ritual_id, m["contract_id"])):
        raise HTTPException(403, "참여를 신청한 가족만 볼 수 있는 제사입니다.")
    if r["camera_id"] is None:
        raise HTTPException(404)
    db.audit(f"member:{m['id']}", "ritual.watch", f"ritual:{ritual_id}")
    return StreamingResponse(_mjpeg(-r["camera_id"], time.time() + 60 * 60, None),
                             media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


# ---------- 제사 생중계: 참여 신청 · 봉행 순서 · 가족 메시지 · 반응(틱톡 라이브식 쌍방향) ----------

_last_msg_at: dict[int, float] = {}
REACTIONS = ("🙏", "🕯️", "🌸", "💛")


def _ritual_visible(ritual_id: int, m: dict) -> dict:
    r = db.one("SELECT * FROM rituals WHERE id=? AND (contract_id=? OR contract_id IS NULL)", (ritual_id, m["contract_id"]))
    if not r:
        raise HTTPException(404, "일정을 찾을 수 없습니다.")
    return r


def _participants(ritual_id: int, contract_id: int | None = None) -> list[dict]:
    """봉행 순서(반려 제외). order_no가 0(미정)인 가족은 뒤로."""
    rows = db.rows(
        """SELECT p.id, p.contract_id, p.deceased_id, p.mourner_name, p.order_no, p.status, p.note,
                  d.name AS deceased_name, d.birth_date, d.death_date, c.holder_name
           FROM ritual_participants p JOIN contracts c ON c.id=p.contract_id LEFT JOIN deceased d ON d.id=p.deceased_id
           WHERE p.ritual_id=? AND p.status<>'rejected'
           ORDER BY CASE WHEN p.order_no>0 THEN 0 ELSE 1 END, p.order_no, p.id""", (ritual_id,))
    for x in rows:
        x["is_mine"] = contract_id is not None and x["contract_id"] == contract_id
    return rows


def _can_watch(r: dict, m: dict, parts: list[dict]) -> bool:
    """법회·행사(open)는 누구나, 제사(applied)는 참여를 신청한 가족만."""
    return (r.get("access") or "open") != "applied" or any(x["contract_id"] == m["contract_id"] for x in parts)


def _live_payload(r: dict, parts: list[dict], since: int, rseq: int) -> dict:
    cur_no = r.get("current_order") or 0
    cur = next((x for x in parts if x["order_no"] == cur_no), None) if cur_no else None
    if since:
        msgs = db.rows("SELECT * FROM ritual_messages WHERE ritual_id=? AND id>? ORDER BY id LIMIT 50", (r["id"], since))
    else:
        msgs = list(reversed(db.rows("SELECT * FROM ritual_messages WHERE ritual_id=? ORDER BY id DESC LIMIT 20", (r["id"],))))
    return {"title": r["title"], "access": r.get("access") or "open", "live": _live_open(r),
            "has_camera": r["camera_id"] is not None and state.camera(r["camera_id"]).online,
            "viewer_count": state.viewer_count(r["id"]), "current_order": cur_no, "current": cur, "order": parts,
            "messages": msgs, "reactions": state.reactions_since(r["id"], rseq) if rseq >= 0 else [], "rseq": state.reaction_seq(r["id"])}   # rseq<0: 첫 호출(지난 반응 건너뜀)


class JoinIn(BaseModel):
    deceased_id: int | None = None
    mourner_name: str = ""
    note: str = ""


@router.post("/rituals/{ritual_id}/join")
def ritual_join(ritual_id: int, body: JoinIn, m: dict = Depends(require_member)):
    """제사 참여 신청. 신청한 가족만 생중계를 보고, 봉행 순서에 고인이 올라간다(순서는 사찰이 정함)."""
    require_role(m, "chat")
    r = _ritual_visible(ritual_id, m)
    if (r.get("access") or "open") != "applied":
        raise HTTPException(400, "이 일정은 신청 없이 누구나 볼 수 있습니다.")
    if db.one("SELECT id FROM ritual_participants WHERE ritual_id=? AND contract_id=? AND status<>'rejected'", (ritual_id, m["contract_id"])):
        raise HTTPException(409, "이미 참여를 신청한 제사입니다.")
    d = (db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"])) if body.deceased_id
         else db.one("SELECT id FROM deceased WHERE contract_id=? ORDER BY id LIMIT 1", (m["contract_id"],)))
    if not d:
        raise HTTPException(400, "고인 정보가 없습니다. 봉안당 사무실에 문의해 주세요.")
    nxt = (db.one("SELECT COALESCE(MAX(order_no),0) AS n FROM ritual_participants WHERE ritual_id=?", (ritual_id,))["n"] or 0) + 1
    pid = db.execute("INSERT INTO ritual_participants(ritual_id, contract_id, deceased_id, mourner_name, order_no, status, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (ritual_id, m["contract_id"], d["id"], body.mourner_name.strip() or m["holder_name"], nxt, "requested", body.note, db.now()))
    db.audit(f"member:{m['id']}", "ritual.join", f"ritual:{ritual_id}", f"participant:{pid}")
    return {"id": pid, "order_no": nxt, "status": "requested"}


@router.get("/rituals/{ritual_id}/live")
def ritual_live(ritual_id: int, since: int = 0, rseq: int = -1, m: dict = Depends(require_member)):
    """라이브 화면이 2초마다 부른다: 시청자 수·지금 차례(고인 이름·생년월일·상주)·순서·새 메시지·새 반응."""
    r = _ritual_visible(ritual_id, m)
    parts = _participants(ritual_id, m["contract_id"])
    if not _can_watch(r, m, parts):
        raise HTTPException(403, "참여를 신청한 가족만 볼 수 있는 제사입니다.")
    state.touch_viewer(ritual_id, m["id"])
    # 가족 화면에는 다른 가족의 계약자 이름·메모·계약 번호를 보내지 않는다(관리자 진행 화면은 전체를 본다)
    public = [{k: x[k] for k in ("order_no", "deceased_name", "mourner_name", "birth_date", "death_date", "status", "is_mine")} for x in parts]
    return _live_payload(r, public, since, rseq)


class RitualMessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=200)


@router.post("/rituals/{ritual_id}/messages")
def ritual_message(ritual_id: int, body: RitualMessageIn, m: dict = Depends(require_member)):
    r = _ritual_visible(ritual_id, m)
    if not _can_watch(r, m, _participants(ritual_id, m["contract_id"])):
        raise HTTPException(403, "참여를 신청한 가족만 메시지를 남길 수 있습니다.")
    now = time.time()
    if now - _last_msg_at.get(m["id"], 0) < 1.5:
        raise HTTPException(429, "잠시 뒤에 다시 보내 주세요.")
    _last_msg_at[m["id"]] = now
    author = m["name"] + (f"({m['relation']})" if m.get("relation") else "")
    mid = db.execute("INSERT INTO ritual_messages(ritual_id, contract_id, sender, author, kind, message, created_at) VALUES (?,?,?,?,?,?,?)",
                     (ritual_id, m["contract_id"], "family", author, "chat", body.message.strip(), db.now()))
    return {"id": mid}


class ReactionIn(BaseModel):
    emoji: str


@router.post("/rituals/{ritual_id}/reactions")
def ritual_reaction(ritual_id: int, body: ReactionIn, m: dict = Depends(require_member)):
    r = _ritual_visible(ritual_id, m)
    if body.emoji not in REACTIONS:
        raise HTTPException(400, "허용되지 않는 반응입니다.")
    if not _can_watch(r, m, _participants(ritual_id, m["contract_id"])):
        raise HTTPException(403, "참여를 신청한 가족만 보낼 수 있습니다.")
    ratelimit.hit(f"react:{m['id']}", 30, 60, "마음을 너무 자주 보내셨습니다. 잠시 뒤 다시 보내 주세요.")
    return {"seq": state.push_reaction(ritual_id, body.emoji, m["name"])}


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
    days: int = Field(default=30, ge=1, le=365)


@router.get("/members")
def members(m: dict = Depends(require_member)):
    return db.rows("SELECT id, name, relation, role, is_minor, created_at, last_seen_at FROM family_members WHERE contract_id=? ORDER BY id", (m["contract_id"],))


@router.post("/invite")
def invite(body: InviteIn, request: Request, m: dict = Depends(require_member)):
    require_role(m, "manage")
    tok = db.token(16)
    from ..community import local_now
    from datetime import timedelta
    expiry = (local_now() + timedelta(days=body.days)).isoformat()
    mid = db.execute(
        "INSERT INTO family_members(contract_id, name, relation, role, invite_token, is_minor, created_at, invite_expires_at) VALUES (?,?,?,?,?,?,?,?)",
        (m["contract_id"], body.name, body.relation, body.role, tok, int(body.is_minor), db.now(), expiry))
    db.audit(f"member:{m['id']}", "family.invite", f"member:{mid}")
    base = str(request.base_url).rstrip("/")
    return {"id": mid, "link": f"{base}/?t={tok}", "expires_at": expiry}


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
            conn.execute("DELETE FROM chat_sessions WHERE deceased_id=?", (d["id"],))   # 대화 요약도 함께 지운다
        conn.execute("DELETE FROM ai_family_stances WHERE deceased_id=?", (d["id"],))
    if body.last_words.strip():
        db.execute("INSERT INTO guestbook(contract_id, member_id, author, message, created_at) VALUES (?,?,?,?,?)",
                   (m["contract_id"], m["id"], m["name"], f"[작별 인사] {body.last_words.strip()}", db.now()))
    db.audit(f"member:{m['id']}", "farewell", f"deceased:{d['id']}", body.action)
    return {"ok": True, "exported": exported}


# ---------- 목소리 등록 (유족 앱에서 직접 · 생전 기록 포함) ----------

VOICE_KINDS = voice.VOICE_KINDS


@router.get("/voice")
def voice_status(m: dict = Depends(require_member)):
    out = []
    for d in db.rows("SELECT id, name, honorific, voice_id, voice_provider FROM deceased WHERE contract_id=? ORDER BY id", (m["contract_id"],)):
        out.append({
            "id": d["id"], "name": d["name"], "honorific": d["honorific"],
            "has_voice": bool(d["voice_id"]), "provider": d["voice_provider"] or None,
            "samples": db.one("SELECT COUNT(*) AS n FROM media WHERE deceased_id=? AND kind='voice'", (d["id"],))["n"],
            "sample_seconds": round(sum(x["seconds"] or 0 for x in voice.samples(d["id"]))),
            "consent": db.one("SELECT kind, signer_name, signed_at FROM consents WHERE deceased_id=? AND kind IN ('voice','lifetime_record') AND revoked_at IS NULL ORDER BY id DESC", (d["id"],)),
        })
    return {"provider_ready": voice.provider_ready(), "can_manage": m["role"] == "manage", "deceased": out, "min_seconds": voice.MIN_SECONDS,
            "formats": voice.AUDIO_EXT_LABEL, "accept": ",".join(sorted(voice.AUDIO_EXTS)) + ",audio/*,video/*", "max_mb": voice.MAX_BYTES // (1024 * 1024)}


@router.post("/voice/register")
async def voice_register(deceased_id: int = Form(...), kind: str = Form("lifetime_record"), agree: bool = Form(False),
                         note: str = Form(""), file: list[UploadFile] = File(...), m: dict = Depends(require_member)):
    """실시간 녹음·음성 파일(여러 개, 여러 형식) → mp3 로 바꿔 자료 저장 → 동의서 → 공급자 등록까지 한 번에.
    시설이 아직 음성 복제를 켜지 않았으면 자료와 동의만 저장해 두고(pending), 켜진 뒤 '/voice/{id}/build' 로 만든다."""
    require_role(m, "manage")
    if kind not in VOICE_KINDS:
        raise HTTPException(400, "kind")
    d = db.one("SELECT id, name FROM deceased WHERE id=? AND contract_id=?", (deceased_id, m["contract_id"]))
    if not d:
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if not agree:
        raise HTTPException(400, "동의 확인이 필요합니다.")
    ratelimit.hit(f"voice-up:{m['id']}", 10, 3600, "목소리 자료는 한 시간에 10번까지 올릴 수 있습니다. 잠시 뒤 다시 시도해 주세요.")
    if not file or len(file) > 10:
        raise HTTPException(400, "음성 자료는 한 번에 1~10개까지 올릴 수 있습니다.")
    base = note.strip() or ("앱에서 직접 녹음" if kind == "lifetime_record" else "앱에서 올린 음성 자료")
    datas, total = [], 0
    for f in file:   # 1MB씩 읽고 한도를 넘으면 바로 멈춘다
        b = await voice.read_upload(f)
        total += len(b)
        if total > voice.MAX_REQUEST_BYTES:
            raise HTTPException(413, "한 번에 올리는 자료가 너무 많습니다(모두 합쳐 200MB까지). 나눠서 올려 주세요.")
        datas.append((f, b))
    saved = []
    for f, b in datas:   # 변환(ffmpeg)은 스레드에서: 다른 가족의 화면·생중계를 멈추지 않게
        saved.append(await run_in_threadpool(voice.save_sample, d["id"], f.filename or "recording.webm", b, f"{base} · {f.filename or '녹음'}", f.content_type))
    if not db.one("SELECT id FROM consents WHERE deceased_id=? AND kind=? AND revoked_at IS NULL", (d["id"], kind)):
        db.execute("INSERT INTO consents(deceased_id, signer_name, relation, kind, signed_at, note) VALUES (?,?,?,?,?,?)",
                   (d["id"], m["name"], m["relation"], kind, db.now(), f"유족 앱에서 동의 · {VOICE_KINDS[kind]}"))
        db.audit(f"member:{m['id']}", "consent.create", f"deceased:{d['id']}", kind)
    secs = round(sum(x["seconds"] or 0 for x in saved)) or None
    if not voice.provider_ready():
        db.audit(f"member:{m['id']}", "voice.samples_saved", f"deceased:{d['id']}", f"{len(saved)} files (provider off)")
        return {"ok": True, "pending": True, "seconds": secs, "files": len(saved),
                "message": "목소리 자료와 동의를 저장했습니다. 시설에서 음성 복제 기능을 켜면 '저장한 자료로 목소리 만들기'로 바로 만들 수 있습니다."}
    r = await run_in_threadpool(voice.register, d["id"], f"member:{m['id']}")
    return {"ok": True, "seconds": r.get("seconds") or secs, "files": r["files"], "provider": r["provider"]}


@router.post("/voice/{deceased_id}/build")
def voice_build(deceased_id: int, m: dict = Depends(require_member)):
    """이미 저장한 음성 자료(최근 5개)로 목소리를 만든다. 자료·동의가 있어야 한다."""
    require_role(m, "manage")
    if not db.one("SELECT id FROM deceased WHERE id=? AND contract_id=?", (deceased_id, m["contract_id"])):
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if not voice.provider_ready():
        raise HTTPException(400, "시설에서 아직 음성 복제 기능을 켜지 않았습니다. 자료는 저장되어 있으니 켜진 뒤 다시 눌러 주세요.")
    ratelimit.hit(f"voice-build:{m['id']}", 10, 3600, "목소리 만들기는 한 시간에 10번까지 할 수 있습니다.")
    r = voice.register(deceased_id, f"member:{m['id']}")
    return {"ok": True, "seconds": r.get("seconds"), "files": r["files"], "provider": r["provider"]}


class VoicePreviewIn(BaseModel):
    deceased_id: int
    text: str = Field(default="", max_length=200)


@router.post("/voice/preview")
def voice_preview(body: VoicePreviewIn, m: dict = Depends(require_member)):
    require_role(m, "manage")   # 고인 목소리로 임의 문장을 만드는 기능이라 계약자만
    ratelimit.hit(f"voice-preview:{m['id']}", 20, 3600, "미리 듣기는 한 시간에 20번까지 할 수 있습니다.")
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
    ratelimit.hit(f"face:{m['id']}", 5, 3600, "얼굴 만들기는 한 시간에 5번까지 할 수 있습니다.")
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
    data = await voice.read_upload(file, 5 * 1024 * 1024)
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


# ---------- 생전 좋아하신 노래 (2026-10-12) ----------
# 계약자가 올리고 고르며, 가족 모두가 참배·추모 공간에서 듣는다. 파일은 /api/family/media/{id} 로 받는다.
def _own_deceased(did: int, m: dict) -> dict:
    d = db.one("SELECT id, name, visit_music_id FROM deceased WHERE id=? AND contract_id=?", (did, m["contract_id"]))
    if not d:
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    return d


@router.get("/music")
def music_list(deceased_id: int, m: dict = Depends(require_member)):
    d = _own_deceased(deceased_id, m)
    items = music.songs(d["id"])
    visit = d["visit_music_id"] if any(x["id"] == d["visit_music_id"] for x in items) else None
    return {"items": items, "visit_music_id": visit, "can_manage": m["role"] == "manage", "max": music.MAX_SONGS}


@router.post("/music")
async def music_upload(deceased_id: int = Form(...), title: str = Form(""), file: UploadFile = File(...), m: dict = Depends(require_member)):
    require_role(m, "manage")
    d = _own_deceased(deceased_id, m)
    ratelimit.hit(f"music-up:{m['id']}", 20, 3600, "노래는 한 시간에 20곡까지 올릴 수 있습니다. 잠시 뒤 다시 올려 주세요.")
    data = await voice.read_upload(file)
    item = await run_in_threadpool(music.save, d["id"], file.filename or "song.mp3", data, title, file.content_type)
    if not d["visit_music_id"]:   # 첫 곡은 참배 때 트는 곡으로 정해 둔다
        db.execute("UPDATE deceased SET visit_music_id=? WHERE id=?", (item["id"], d["id"]))
    db.audit(f"member:{m['id']}", "music.add", f"deceased:{d['id']}", item["title"])
    return item


@router.delete("/music/{media_id}")
def music_delete(media_id: int, m: dict = Depends(require_member)):
    require_role(m, "manage")
    r = db.one("SELECT md.id FROM media md JOIN deceased d ON d.id=md.deceased_id WHERE md.id=? AND md.kind='music' AND d.contract_id=?", (media_id, m["contract_id"]))
    if not r:
        raise HTTPException(404, "노래를 찾을 수 없습니다.")
    music.remove(media_id)
    db.audit(f"member:{m['id']}", "music.remove", f"media:{media_id}", "")
    return {"ok": True}


class VisitMusicIn(BaseModel):
    deceased_id: int
    media_id: int | None = None   # 비우면 참배 때 노래를 틀지 않는다


@router.put("/music/visit")
def music_visit(body: VisitMusicIn, m: dict = Depends(require_member)):
    require_role(m, "manage")
    d = _own_deceased(body.deceased_id, m)
    if body.media_id is not None and not db.one("SELECT id FROM media WHERE id=? AND deceased_id=? AND kind='music'", (body.media_id, d["id"])):
        raise HTTPException(404, "노래를 찾을 수 없습니다.")
    db.execute("UPDATE deceased SET visit_music_id=? WHERE id=?", (body.media_id, d["id"]))
    return {"ok": True, "visit_music_id": body.media_id}


# ---------- 추모 제단: 국화·촛불·스티커 놓기 (2026-10-12) ----------
# 그림은 static/images/altar/<item>.svg (scripts/make_altar_items.py). 자리는 판 위 백분율(x·y), 기울기·크기와 함께 저장.
ALTAR_ITEMS = ("chrysanthemum-white", "chrysanthemum-yellow", "carnation", "rose-white", "lily", "lotus", "candle", "incense",
               "heart", "star", "butterfly", "dove", "hands", "text-miss", "text-love", "text-thanks")
ALTAR_SHOWN = 80   # 판에 보이는 최근 아이템 수


class AltarIn(BaseModel):
    item: Literal[ALTAR_ITEMS]  # type: ignore[valid-type]
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    rot: float = Field(0, ge=-45, le=45)
    scale: float = Field(1, ge=.6, le=1.6)
    message: str = Field("", max_length=120)


@router.get("/altar/{deceased_id}")
def altar_list(deceased_id: int, m: dict = Depends(require_member)):
    _own_deceased(deceased_id, m)
    rows = db.rows("""SELECT a.id, a.item, a.x, a.y, a.rot, a.scale, a.message, a.created_at, a.member_id, f.name AS author
                      FROM altar_items a JOIN family_members f ON f.id=a.member_id WHERE a.deceased_id=? ORDER BY a.id DESC LIMIT ?""",
                   (deceased_id, ALTAR_SHOWN))
    for r in rows:
        r["mine"] = r.pop("member_id") == m["id"]
        r["can_remove"] = r["mine"] or m["role"] == "manage"
    total = db.one("SELECT COUNT(*) AS n FROM altar_items WHERE deceased_id=?", (deceased_id,))["n"]
    return {"items": list(reversed(rows)), "total": total, "catalog": list(ALTAR_ITEMS)}


@router.post("/altar/{deceased_id}")
def altar_add(deceased_id: int, body: AltarIn, m: dict = Depends(require_member)):
    _own_deceased(deceased_id, m)
    ratelimit.hit(f"altar:{m['id']}", 30, 3600, "한 시간에 30개까지 놓을 수 있습니다. 잠시 뒤 다시 놓아 주세요.")
    aid = db.execute("INSERT INTO altar_items(deceased_id, member_id, item, x, y, rot, scale, message, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (deceased_id, m["id"], body.item, round(body.x, 2), round(body.y, 2), round(body.rot, 1), round(body.scale, 2), body.message.strip(), db.now()))
    return {"id": aid}


@router.delete("/altar/item/{item_id}")
def altar_remove(item_id: int, m: dict = Depends(require_member)):
    r = db.one("SELECT a.id, a.member_id FROM altar_items a JOIN deceased d ON d.id=a.deceased_id WHERE a.id=? AND d.contract_id=?", (item_id, m["contract_id"]))
    if not r:
        raise HTTPException(404, "찾을 수 없습니다.")
    if r["member_id"] != m["id"] and m["role"] != "manage":
        raise HTTPException(403, "내가 놓은 것만 치울 수 있습니다. 다른 가족이 놓은 것은 계약자가 정리할 수 있습니다.")
    db.execute("DELETE FROM altar_items WHERE id=?", (item_id,))
    return {"ok": True}


# ---------- 추모 서비스(유료): 헌화 · 선물하기 · 제사 상차림 · 기도 (2026-10-12, 시연 결제) ----------
class OrderIn(BaseModel):
    service: str = Field(max_length=40)
    deceased_id: int
    qty: int = Field(1, ge=1, le=10)
    ritual_id: int | None = None
    deliver_on: str | None = Field(None, max_length=10)
    gift_to: int | None = None
    card_message: str = Field("", max_length=100)
    note: str = Field("", max_length=1000)
    pay_method: str = Field(max_length=20)


@router.get("/services")
def services_catalog(m: dict = Depends(require_member)):
    members = db.rows("SELECT id, name, relation FROM family_members WHERE contract_id=? AND revoked_at IS NULL AND id<>? ORDER BY id", (m["contract_id"], m["id"]))
    return {"items": services.catalog(), "categories": services.CATEGORIES, "pay_methods": services.PAY_METHODS, "members": members, "demo": True}


@router.post("/orders")
def order_create(body: OrderIn, m: dict = Depends(require_member)):
    ratelimit.hit(f"order:{m['id']}", 20, 3600, "주문은 한 시간에 20건까지 할 수 있습니다. 잠시 뒤 다시 해 주세요.")
    return services.create(m, body)


@router.get("/orders")
def order_list(m: dict = Depends(require_member)):
    """내 주문 + 내가 받은 선물. 계약자는 가족 모두의 주문을 본다."""
    if m["role"] == "manage":
        ids = db.rows("SELECT id FROM service_orders WHERE contract_id=? ORDER BY id DESC LIMIT 100", (m["contract_id"],))
    else:
        ids = db.rows("SELECT id FROM service_orders WHERE contract_id=? AND (member_id=? OR gift_to=?) ORDER BY id DESC LIMIT 100", (m["contract_id"], m["id"], m["id"]))
    out = []
    for r in ids:
        o = services.get(r["id"])
        o["mine"] = o["member_id"] == m["id"]
        o["gift_for_me"] = o["gift_to"] == m["id"]
        o["can_cancel"] = o["mine"] and o["status"] == "paid"
        out.append(o)
    return out


@router.post("/orders/{order_id}/cancel")
def order_cancel(order_id: int, m: dict = Depends(require_member)):
    o = db.one("SELECT id, member_id, status FROM service_orders WHERE id=? AND contract_id=?", (order_id, m["contract_id"]))
    if not o:
        raise HTTPException(404, "주문을 찾을 수 없습니다.")
    if o["member_id"] != m["id"]:
        raise HTTPException(403, "주문한 분만 취소할 수 있습니다.")
    if o["status"] != "paid":
        raise HTTPException(400, "이미 준비를 시작했거나 끝난 주문은 시설에 전화로 취소를 요청해 주세요.")
    db.execute("UPDATE service_orders SET status='refunded', updated_at=? WHERE id=?", (db.now(), order_id))
    db.audit(f"member:{m['id']}", "order.refund_demo", f"order:{order_id}", "")
    return services.get(order_id)


@router.get("/orders/{order_id}/photo.jpg")
def order_photo(order_id: int, m: dict = Depends(require_member)):
    o = db.one("SELECT done_photo FROM service_orders WHERE id=? AND contract_id=?", (order_id, m["contract_id"]))
    if not o or not o["done_photo"]:
        raise HTTPException(404)
    return FileResponse(config.MEDIA_DIR / o["done_photo"])


# ---------- 인공지능 대화 가족 합의 (2026-10-13) ----------
# 시뮬레이션에서 "계약자 혼자 결정하는 구조가 불편하다"는 반응이 나와, 가족 누구나 '동의'·'보류'를 남기고 한 분이라도 보류하면 대화가 열리지 않게 했다.
AI_RULE = "인공지능 추모 대화는 시설에 등록한 직계가족 동의서가 있고, 가족 중 누구도 '보류'하지 않을 때만 열립니다. 보류는 언제든 남기거나 거둘 수 있습니다."


class StanceIn(BaseModel):
    deceased_id: int
    stance: Literal["agree", "hold", "none"]
    note: str = Field("", max_length=200)


@router.get("/ai-consensus")
def ai_consensus(deceased_id: int, m: dict = Depends(require_member)):
    d = _own_deceased(deceased_id, m)
    rows = db.rows("""SELECT f.id, f.name, f.relation, f.role, s.stance, s.note, s.updated_at FROM family_members f
                      LEFT JOIN ai_family_stances s ON s.member_id=f.id AND s.deceased_id=?
                      WHERE f.contract_id=? AND f.revoked_at IS NULL ORDER BY f.id""", (d["id"], m["contract_id"]))
    for r in rows:
        r["stance"] = r["stance"] or "none"
        r["is_me"] = r["id"] == m["id"]
    held = [r["name"] for r in rows if r["stance"] == "hold"]
    consent = db.one("SELECT id FROM consents WHERE deceased_id=? AND kind='ai_chat' AND revoked_at IS NULL", (d["id"],)) is not None
    return {"deceased_id": d["id"], "members": rows, "held_by": held, "consent_valid": consent,
            "open": consent and not held, "rule": AI_RULE}


@router.put("/ai-consensus")
def ai_consensus_set(body: StanceIn, m: dict = Depends(require_member)):
    d = _own_deceased(body.deceased_id, m)
    if body.stance == "none":
        db.execute("DELETE FROM ai_family_stances WHERE deceased_id=? AND member_id=?", (d["id"], m["id"]))
    else:
        db.execute("""INSERT INTO ai_family_stances(deceased_id, member_id, stance, note, updated_at) VALUES (?,?,?,?,?)
                      ON CONFLICT(deceased_id, member_id) DO UPDATE SET stance=excluded.stance, note=excluded.note, updated_at=excluded.updated_at""",
                   (d["id"], m["id"], body.stance, body.note.strip(), db.now()))
    db.audit(f"member:{m['id']}", "ai.stance", f"deceased:{d['id']}", body.stance)
    return ai_consensus(d["id"], m)


# ---------- 안심 안내: 무엇을 찍고, 무엇을 저장하고, 언제 지우는지 (2026-10-13) ----------
# 화면 문구가 코드와 어긋나지 않도록 설정값에서 사실을 읽어 준다(js/app.js renderPolicy).
@router.get("/policy")
def policy(m: dict = Depends(require_member)):
    from .. import services
    from ..ai import safety
    return {
        "camera": {
            "snapshot_interval": config.SNAPSHOT_INTERVAL,       # 초마다 사진 한 장
            "live_seconds": config.LIVE_SECONDS,                 # 실시간 보기 한 번의 길이
            "keeps_latest_only": True,                           # 봉안함마다 최신 사진 1장만 서버에 두고 새 사진이 오면 덮어쓴다
            "records_video": False,                              # 실시간 영상은 저장하지 않는다
            "protect_visitors": _live_protect(),                 # 현장에 다른 참배객이 있으면 실시간 영상을 멈춘다
            "notice_posted": db.get_setting("camera_notice") == "1",   # 시설이 현장에 촬영 안내문을 게시했다고 확인함
        },
        "ai": {
            "max_minutes": config.CHAT_MAX_MINUTES,
            "stores_transcript": False,                          # 대화 원문은 저장하지 않고 요약만 남긴다
            "crisis_line": safety.CRISIS_LINE,
            "handoff_kinds": ["위기 신호(자해·자살 언급)", "유산·재산", "치료·약", "소송·법률"],   # 고인 역할을 멈추고 안내로 바꾸는 경우
            "rule": AI_RULE,
        },
        "free": ["원격 참배(봉안함 사진 · 실시간 보기)", "추도식 · 법회 생중계와 반응", "추모 공간 · 방명록 · 추모 제단 · 가족 앨범",
                 "인공지능 추모 대화(동의서 · 가족 합의 후)", "생전 좋아하신 노래", "가족 초대 · 일정 · 알림"],
        "paid": services.catalog(),
        "delete": {"farewell_by": "계약자", "voice_face_deleted": True, "summary_deleted_on_delete": True},
    }
