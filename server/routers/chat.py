"""기념일 대화(B등급). 입장 확인 → 듣기 → 안전 점검 → 응답 → 마무리. 음성 원본은 서버에 오지 않고, 요약만 남긴다."""
import json
import threading
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import config, db, face
from ..ai import factory, safety
from ..ai.base import Persona, Turn
from ..ai.prompt import build_greeting
from ..deps import require_member, require_role

router = APIRouter(prefix="/api/family/chat", tags=["chat"])

AI_NOTICE = "이 대화의 목소리와 답변은 가족이 남긴 기억으로 만든 AI가 생성한 것입니다. 실제 고인이 아닙니다."

_lock = threading.Lock()
_sessions: dict[str, dict] = {}   # session_id → {persona, history, started, safety_events}


class StartIn(BaseModel):
    deceased_id: int
    occasion: str = Field(default="", max_length=40)
    guardian_present: bool = False
    acknowledged_ai: bool = False


class TurnIn(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=1000)


class EndIn(BaseModel):
    session_id: str


def _persona(d: dict, m: dict, occasion: str) -> Persona:
    return Persona(
        name=d["name"], honorific=d["honorific"], memory_card=d["memory_card"],
        birth_date=d["birth_date"], death_date=d["death_date"],
        member_name=m["name"], member_relation=m["relation"], occasion=occasion,
    )


@router.post("/start")
def start(body: StartIn, m: dict = Depends(require_member)):
    require_role(m, "chat")
    d = db.one("SELECT * FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"]))
    if not d:
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if not d["ai_enabled"]:
        raise HTTPException(403, "이 분의 대화 기능은 열려 있지 않습니다. 관리자에게 문의해 주세요.")
    if not db.one("SELECT id FROM consents WHERE deceased_id=? AND kind='ai_chat' AND revoked_at IS NULL", (d["id"],)):
        raise HTTPException(403, "유효한 가족 동의서가 없어 대화를 열 수 없습니다.")
    if not body.acknowledged_ai:
        raise HTTPException(400, "AI 고지를 확인해 주세요.")
    if m["is_minor"] and not body.guardian_present:
        raise HTTPException(403, "미성년자는 보호자와 함께 이용해 주세요.")

    notices = []
    try:
        days = (datetime.now().date() - datetime.fromisoformat(d["death_date"]).date()).days
        if days < d["chat_min_days_after_death"]:
            notices.append(f"첫 대화는 49재 이후를 권장합니다. (별세 후 {days}일)")
    except (ValueError, TypeError):
        pass

    sid = db.token(12)
    persona = _persona(d, m, body.occasion)
    greeting = build_greeting(persona)
    with _lock:
        _sessions[sid] = {"persona": persona, "history": [Turn("assistant", greeting)], "started": time.time(),
                          "safety_events": [], "deceased_id": d["id"], "member_id": m["id"]}
    db.execute("INSERT INTO chat_sessions(id, deceased_id, member_id, started_at, provider) VALUES (?,?,?,?,?)",
               (sid, d["id"], m["id"], db.now(), factory.llm().name))
    db.audit(f"member:{m['id']}", "chat.start", f"deceased:{d['id']}", body.occasion)
    voice_available = bool(d["voice_id"]) and factory.tts().name != "browser"
    avatar_available = voice_available and bool(d["face_id"]) and face.provider_ready()   # 아바타는 서버 음성이 있을 때만
    return {
        "avatar_available": avatar_available, "avatar_provider": factory.avatar().name if avatar_available else None,
        "session_id": sid, "greeting": greeting, "notice": AI_NOTICE, "notices": notices,
        "max_seconds": config.CHAT_MAX_MINUTES * 60, "provider": factory.llm().name,
        "photo_url": f"/api/family/deceased/{d['id']}/photo.jpg" if d["photo_path"] else None,
        "voice_available": voice_available, "voice_provider": factory.tts().name if voice_available else "browser",
        "voice_hint": "female" if any(k in (d["honorific"] or "") for k in ("어머니", "엄마", "할머니", "아내", "누나", "언니", "이모", "고모")) else
                      "male" if any(k in (d["honorific"] or "") for k in ("아버지", "아빠", "할아버지", "남편", "형", "오빠", "삼촌")) else "any",
    }


def _closing(persona: Persona) -> str:
    who = persona.member_name or "우리 가족"
    return f"{who}, 오늘 이렇게 이야기 나눠서 참 좋았다. 밥 잘 챙겨 먹고, 몸 건강해라. 또 보자."


@router.post("/turn")
def turn(body: TurnIn, m: dict = Depends(require_member)):
    with _lock:
        s = _sessions.get(body.session_id)
    if not s or s["member_id"] != m["id"]:
        raise HTTPException(404, "대화 세션이 없습니다. 다시 시작해 주세요.")
    elapsed = time.time() - s["started"]
    limit = config.CHAT_MAX_MINUTES * 60
    remaining = max(0, int(limit - elapsed))
    persona: Persona = s["persona"]

    check = safety.check(body.text, persona.honorific)
    if check.kind:
        s["safety_events"].append({"kind": check.kind, "at": db.now()})
        db.audit(f"member:{m['id']}", "chat.safety", f"session:{body.session_id}", check.kind)
        s["history"].append(Turn("user", body.text))
        s["history"].append(Turn("assistant", check.message))
        if check.stop_persona:
            _finish(body.session_id, s)
            return {"reply": check.message, "safety": {"kind": check.kind, "hotline": safety.CRISIS_LINE},
                    "persona_stopped": True, "ended": True, "remaining_seconds": 0}
        return {"reply": check.message, "safety": {"kind": check.kind}, "persona_stopped": False, "ended": False, "remaining_seconds": remaining}

    if remaining <= 0:
        reply = _closing(persona)
        s["history"].append(Turn("user", body.text))
        s["history"].append(Turn("assistant", reply))
        _finish(body.session_id, s)
        return {"reply": reply, "safety": None, "persona_stopped": False, "ended": True, "remaining_seconds": 0}

    reply = safety.scrub_reply(factory.llm().reply(persona, s["history"], body.text))
    s["history"].append(Turn("user", body.text))
    s["history"].append(Turn("assistant", reply))
    db.execute("UPDATE chat_sessions SET turns=turns+1 WHERE id=?", (body.session_id,))
    return {"reply": reply, "safety": None, "persona_stopped": False, "ended": False, "remaining_seconds": remaining}


def _finish(sid: str, s: dict) -> None:
    summary = factory.llm().summarize(s["persona"], s["history"])
    db.execute("UPDATE chat_sessions SET ended_at=?, summary=?, safety_events=? WHERE id=?",
               (db.now(), summary, json.dumps(s["safety_events"], ensure_ascii=False), sid))
    with _lock:
        _sessions.pop(sid, None)   # 대화 원문은 메모리에서 지운다. 요약만 남는다.


@router.post("/end")
def end(body: EndIn, m: dict = Depends(require_member)):
    with _lock:
        s = _sessions.get(body.session_id)
    if not s or s["member_id"] != m["id"]:
        row = db.one("SELECT summary FROM chat_sessions WHERE id=? AND member_id=?", (body.session_id, m["id"]))
        if row:
            return {"ok": True, "closing": None, "summary": row["summary"]}
        raise HTTPException(404)
    closing = _closing(s["persona"])
    s["history"].append(Turn("assistant", closing))
    _finish(body.session_id, s)
    row = db.one("SELECT summary FROM chat_sessions WHERE id=?", (body.session_id,))
    return {"ok": True, "closing": closing, "summary": row["summary"] if row else ""}


@router.get("/history")
def history(m: dict = Depends(require_member)):
    """지난 대화 요약 목록(원문 없음)."""
    return db.rows(
        """SELECT s.id, s.started_at, s.ended_at, s.turns, s.summary, d.name AS deceased_name
           FROM chat_sessions s JOIN deceased d ON d.id=s.deceased_id
           WHERE s.member_id=? ORDER BY s.started_at DESC LIMIT 20""", (m["id"],))


@router.get("/tts")
def tts(session_id: str, text: str, m: dict = Depends(require_member)):
    """진행 중인 세션의 고인 복제 음성으로 합성한 오디오. 공급자가 없으면 204(브라우저 음성 합성으로 대체)."""
    from ..ai.tts import TTSError
    with _lock:
        s = _sessions.get(session_id)
    if not s or s["member_id"] != m["id"]:
        raise HTTPException(404, "대화 세션이 없습니다.")
    d = db.one("SELECT voice_id FROM deceased WHERE id=?", (s["deceased_id"],))
    if not d or not d["voice_id"]:
        return Response(status_code=204)
    try:
        r = factory.tts().synthesize(text[:400], d["voice_id"])
    except TTSError as e:
        db.audit(f"member:{m['id']}", "tts.error", f"session:{session_id}", e.message)
        return Response(status_code=204, headers={"X-TTS-Error": "provider"})
    if r.audio is None:
        return Response(status_code=204)
    return Response(content=r.audio, media_type=r.mime, headers={"Cache-Control": "no-store"})


class AvatarSessionIn(BaseModel):
    session_id: str


@router.post("/avatar-session")
def avatar_session(body: AvatarSessionIn, m: dict = Depends(require_member)):
    """실시간 아바타 세션 토큰. API 키는 서버에만 있고 브라우저에는 토큰만 간다."""
    with _lock:
        s = _sessions.get(body.session_id)
    if not s or s["member_id"] != m["id"]:
        raise HTTPException(404, "대화 세션이 없습니다.")
    sess = face.session(s["deceased_id"])
    if not sess:
        raise HTTPException(404, "실시간 아바타를 쓸 수 없습니다. 사진 아바타로 진행합니다.")
    db.audit(f"member:{m['id']}", "avatar.session", f"session:{body.session_id}", sess["provider"])
    return sess


class AvatarSpeakIn(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=400)


@router.post("/avatar-speak")
def avatar_speak(body: AvatarSpeakIn, m: dict = Depends(require_member)):
    """D-ID 아바타용: 복제 음성으로 합성 → D-ID 임시 저장소 업로드 → 브라우저 SDK가 speak(audio_url)."""
    with _lock:
        s = _sessions.get(body.session_id)
    if not s or s["member_id"] != m["id"]:
        raise HTTPException(404, "대화 세션이 없습니다.")
    d = db.one("SELECT voice_id FROM deceased WHERE id=?", (s["deceased_id"],))
    if not d or not d["voice_id"]:
        raise HTTPException(400, "복제 음성이 없습니다.")
    url, secs = face.speech_url(body.text, d["voice_id"])
    return {"audio_url": url, "seconds": secs}
