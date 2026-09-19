"""MVP 핵심 흐름 테스트. 실행: python -m pytest -q"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LLM_PROVIDER", "mock")

from server import config, db  # noqa: E402
from server.ai import safety  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("data")
    config.DATA_DIR = tmp
    config.SNAPSHOT_DIR = tmp / "snapshots"
    config.FRAME_DIR = tmp / "frames"
    config.MEDIA_DIR = tmp / "media"
    for d in (config.SNAPSHOT_DIR, config.FRAME_DIR, config.MEDIA_DIR):
        d.mkdir(parents=True, exist_ok=True)
    db.reset_for_tests(tmp / "test.db")
    from fastapi.testclient import TestClient
    from server import seed
    from server.main import app
    seed.run()
    with TestClient(app) as c:
        yield c


ADMIN = {"X-Admin-Key": config.ADMIN_KEY}
EDGE = {"X-Edge-Key": config.EDGE_KEY}


def holder_token(name="이미영"):
    return db.one("SELECT invite_token FROM family_members WHERE name=?", (name,))["invite_token"]


def fake_wav(seconds: float = 20.0) -> bytes:
    """테스트용 음성 파일: 220Hz 사인파 모노 16kHz WAV."""
    import io, math, struct, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        n = int(16000 * seconds)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / 16000))) for i in range(n)))
    return buf.getvalue()


# ---------- 안전 점검 ----------

@pytest.mark.parametrize("text,kind", [
    ("나도 엄마 따라가고 싶어", "crisis"),
    ("죽고 싶어요", "crisis"),
    ("엄마 집은 팔아야 할까요", "property"),
    ("유산은 어떻게 나눠요", "property"),
    ("항암 치료를 그만둘까요", "medical"),
    ("형이랑 소송해야 할까요", "legal"),
    ("엄마 보고 싶어요", None),
    ("오늘 밥은 드셨어요?", None),
])
def test_safety_check(text, kind):
    assert safety.check(text).kind == kind


def test_crisis_stops_persona():
    r = safety.check("살기 싫어요")
    assert r.stop_persona and "109" in r.message


def test_scrub_removes_selling():
    assert "공양" not in safety.scrub_reply("잘 지냈니. 공양 신청은 꼭 해라. 밥 잘 먹어.")


# ---------- 인증 ----------

def test_auth_required(client):
    assert client.get("/api/family/me").status_code == 401
    assert client.get("/api/admin/overview").status_code == 401
    assert client.get("/api/edge/config").status_code == 401
    assert client.get("/api/family/me", headers={"X-Family-Token": "nope"}).status_code == 401


# ---------- 원격 참배 ----------

def test_edge_snapshot_then_family_sees_it(client):
    cfg = client.get("/api/edge/config", headers=EDGE).json()
    cam = cfg["cameras"][0]
    niche = next(n for n in cam["niches"] if n["code"] == "A-1-2")
    r = client.post(f"/api/edge/niches/{niche['id']}/snapshot", headers=EDGE, files={"file": ("f.jpg", b"\xff\xd8fake", "image/jpeg")})
    assert r.status_code == 200
    client.post(f"/api/edge/cameras/{cam['id']}/status", headers=EDGE, data={"occupied": "false", "persons": 0, "fps": 10})
    tok = {"X-Family-Token": holder_token()}
    assert client.get("/api/family/niche/snapshot.jpg", headers=tok).status_code == 200
    st = client.get("/api/family/niche/status", headers=tok).json()
    assert st["camera_online"] and not st["occupied"] and st["last_snapshot_at"]


def test_live_blocked_when_visitor_present(client):
    cfg = client.get("/api/edge/config", headers=EDGE).json()
    cam = cfg["cameras"][0]
    tok = {"X-Family-Token": holder_token()}
    client.post(f"/api/edge/cameras/{cam['id']}/status", headers=EDGE, data={"occupied": "true", "persons": 1, "fps": 10})
    assert client.post("/api/family/live/start", headers=tok).status_code == 409
    client.post(f"/api/edge/cameras/{cam['id']}/status", headers=EDGE, data={"occupied": "false", "persons": 0, "fps": 10})
    r = client.post("/api/family/live/start", headers=tok)
    assert r.status_code == 200 and r.json()["seconds"] == config.LIVE_SECONDS
    assert client.get("/api/edge/config", headers=EDGE).json()["live_niche_ids"]


# ---------- 추모 공간 ----------

def test_memorial_hides_memory_card(client):
    tok = {"X-Family-Token": holder_token()}
    m = client.get("/api/family/memorial", headers=tok).json()
    assert m["deceased"] and "memory_card" not in m["deceased"][0]
    r = client.post("/api/family/guestbook", headers=tok, json={"message": "테스트 방명록"})
    assert r.status_code == 200
    assert any(g["message"] == "테스트 방명록" for g in client.get("/api/family/memorial", headers=tok).json()["guestbook"])


# ---------- 대화 ----------

def test_chat_requires_consent_and_ai_enabled(client):
    tok = {"X-Family-Token": holder_token("김태형")}   # 김철수: 대화 기능 닫힘, 동의서 없음
    did = db.one("SELECT id FROM deceased WHERE name='김철수'")["id"]
    r = client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True})
    assert r.status_code == 403


def test_chat_view_role_forbidden(client):
    tok = {"X-Family-Token": holder_token("이하은")}
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    assert client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True}).status_code == 403


def test_chat_flow_and_summary(client):
    tok = {"X-Family-Token": holder_token()}
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    assert client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did}).status_code == 400  # 고지 미확인
    s = client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True, "occasion": "기일"}).json()
    assert s["greeting"] and "AI" in s["notice"]
    t = client.post("/api/family/chat/turn", headers=tok, json={"session_id": s["session_id"], "text": "엄마 보고 싶어요"}).json()
    assert t["reply"] and t["safety"] is None and not t["ended"]
    t = client.post("/api/family/chat/turn", headers=tok, json={"session_id": s["session_id"], "text": "유산은 어떻게 해요"}).json()
    assert t["safety"]["kind"] == "property" and not t["ended"]
    e = client.post("/api/family/chat/end", headers=tok, json={"session_id": s["session_id"]}).json()
    assert e["closing"] and e["summary"]
    row = db.one("SELECT * FROM chat_sessions WHERE id=?", (s["session_id"],))
    assert row["ended_at"] and row["turns"] == 1 and "property" in row["safety_events"]


def test_chat_crisis_ends_session(client):
    tok = {"X-Family-Token": holder_token()}
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    s = client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True}).json()
    t = client.post("/api/family/chat/turn", headers=tok, json={"session_id": s["session_id"], "text": "나도 따라가고 싶어"}).json()
    assert t["ended"] and t["persona_stopped"] and "109" in t["reply"]
    assert client.post("/api/family/chat/turn", headers=tok, json={"session_id": s["session_id"], "text": "다시"}).status_code == 404


# ---------- 가족 초대 · 작별 ----------

def test_invite_and_role(client):
    tok = {"X-Family-Token": holder_token()}
    r = client.post("/api/family/invite", headers=tok, json={"name": "이도윤", "relation": "손자", "role": "view", "is_minor": True})
    assert r.status_code == 200 and "?t=" in r.json()["link"]
    child = {"X-Family-Token": r.json()["link"].split("?t=")[1]}
    assert client.get("/api/family/me", headers=child).json()["member"]["is_minor"] is True
    assert client.post("/api/family/invite", headers=child, json={"name": "x"}).status_code == 403


def test_farewell_closes_chat(client):
    tok = {"X-Family-Token": holder_token()}
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    r = client.post("/api/family/farewell", headers=tok, json={"deceased_id": did, "action": "return", "last_words": "고마웠어요"})
    assert r.status_code == 200 and r.json()["exported"]["memory_card"]
    me = client.get("/api/family/me", headers=tok).json()
    d = next(x for x in me["deceased"] if x["id"] == did)
    assert not d["chat_available"] and not d["consent_valid"]
    assert client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True}).status_code == 403


# ---------- 관리자 ----------

def test_admin_niche_grid_and_contract(client):
    cams = client.get("/api/admin/cameras", headers=ADMIN).json()
    cam = next(c for c in cams if c["kind"] == "wall")
    existing = client.get(f"/api/admin/cameras/{cam['id']}/niches", headers=ADMIN).json()
    body = [{"id": n["id"], "code": n["code"], "row": n["row"], "col": n["col"], "x": n["x"], "y": n["y"], "w": n["w"], "h": n["h"]} for n in existing]
    body.append({"code": "Z-1-1", "row": 1, "col": 1, "x": 0.8, "y": 0.8, "w": 0.1, "h": 0.1})
    r = client.put(f"/api/admin/cameras/{cam['id']}/niches", headers=ADMIN, json=body)
    assert r.status_code == 200 and any(n["code"] == "Z-1-1" for n in r.json())
    # 계약이 있는 칸을 빼고 저장하면 거부
    r = client.put(f"/api/admin/cameras/{cam['id']}/niches", headers=ADMIN, json=[b for b in body if b["code"] != "A-1-2"])
    assert r.status_code == 409
    z = db.one("SELECT id FROM niches WHERE code='Z-1-1'")
    assert z, "거부된 저장은 아무것도 바꾸지 않아야 한다"
    c = client.post("/api/admin/contracts", headers=ADMIN, json={"holder_name": "박테스트", "niche_id": z["id"]})
    assert c.status_code == 200 and c.json()["holder_token"]
    assert client.post("/api/admin/contracts", headers=ADMIN, json={"holder_name": "중복", "niche_id": z["id"]}).status_code == 409


def test_admin_usage_and_audit(client):
    u = client.get("/api/admin/usage", headers=ADMIN).json()
    assert u["safety_events"] >= 1
    assert any(a["action"] == "chat.safety" for a in u["audit"])


# ---------- AI 설정 (관리자 콘솔에서 API 키 입력) ----------

def test_ai_settings_roundtrip(client):
    from server.ai import factory
    s = client.get("/api/admin/settings/ai", headers=ADMIN).json()
    assert s["active_provider"] == "mock" and s["api_key_masked"] == ""
    assert client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": "not-a-key", "provider": "auto", "model": "claude-opus-5"}).status_code == 400
    assert client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "auto", "model": "gpt-9"}).status_code == 400
    r = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": "sk-ant-api03-testkey-0000-1234", "provider": "auto", "model": "claude-sonnet-5"}).json()
    assert r["api_key_masked"].startswith("sk-ant-") and r["api_key_masked"].endswith("1234") and "testkey" not in r["api_key_masked"]
    assert r["api_key_source"] == "console" and r["model"] == "claude-sonnet-5"
    assert r["active_provider"] == "anthropic"           # 키가 생기면 자동으로 Claude 공급자
    assert factory.llm().name == "anthropic"
    # 키를 비우면 Mock으로 복귀, 마스킹된 키가 유족 API 어디에도 없음
    r = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": "", "provider": "auto", "model": "claude-opus-5"}).json()
    assert r["active_provider"] == "mock" and r["api_key_source"] == "none"
    assert client.post("/api/admin/settings/ai/test", headers=ADMIN).status_code == 400
    assert client.get("/api/admin/settings/ai").status_code == 401


# ---------- 복제 음성 (ElevenLabs — 네트워크는 가짜로) ----------

def test_voice_register_guards(client):
    did = db.one("SELECT id FROM deceased WHERE name='김철수'")["id"]   # 동의서 없음
    assert client.post(f"/api/admin/deceased/{did}/voice/register", headers=ADMIN).status_code == 403
    client.post(f"/api/admin/deceased/{did}/consents", headers=ADMIN, json={"signer_name": "김태형", "relation": "아들", "kind": "voice"})
    assert client.post(f"/api/admin/deceased/{did}/voice/register", headers=ADMIN).status_code == 400   # 음성 자료 없음


def test_voice_register_and_tts_flow(client, monkeypatch):
    from server.ai import factory
    from server.ai.tts import ElevenLabsTTS
    from server.ai.base import TTSResult
    calls = {}
    monkeypatch.setattr(ElevenLabsTTS, "add_voice", lambda self, name, files, description="": calls.setdefault("added", (name, len(files))) and "voice_abc123")
    monkeypatch.setattr(ElevenLabsTTS, "synthesize", lambda self, text, voice_id: TTSResult(audio=b"ID3fake-mp3-" + voice_id.encode(), mime="audio/mpeg"))
    monkeypatch.setattr(ElevenLabsTTS, "delete_voice", lambda self, voice_id: calls.setdefault("deleted", voice_id))
    monkeypatch.setattr(ElevenLabsTTS, "ping", lambda self: {"tier": "starter", "used": 10, "limit": 30000, "can_clone": True, "all_ok": True,
                                                              "checks": {"user_read": "ok", "voices_read": "ok", "text_to_speech": "ok"}})

    did = db.one("SELECT id FROM deceased WHERE name='김철수'")["id"]
    # 키 저장 → ElevenLabs 공급자 활성
    r = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                                  "elevenlabs_api_key": "sk_test00000000000000000000000000", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2"}).json()
    assert r["active_tts"] == "elevenlabs" and r["elevenlabs_key_masked"]
    assert client.post("/api/admin/settings/tts/test", headers=ADMIN).json()["tier"] == "starter"
    # 음성 자료 업로드 → 등록
    up = client.post(f"/api/admin/deceased/{did}/media?kind=voice&caption=생일영상", headers=ADMIN, files={"file": ("sample.wav", fake_wav(20), "audio/wav")})
    assert up.status_code == 200, up.text
    r = client.post(f"/api/admin/deceased/{did}/voice/register", headers=ADMIN).json()
    assert r["voice_id"] == "voice_abc123" and calls["added"][1] == 1
    assert db.one("SELECT voice_id, voice_provider FROM deceased WHERE id=?", (did,)) == {"voice_id": "voice_abc123", "voice_provider": "elevenlabs"}
    # 미리 듣기
    pv = client.post(f"/api/admin/deceased/{did}/voice/preview", headers=ADMIN)
    assert pv.status_code == 200 and pv.headers["content-type"].startswith("audio/mpeg")
    # 유족 앱: voice_id는 숨기고 has_voice만 노출, 대화 시작 시 voice_available
    db.execute("UPDATE deceased SET ai_enabled=1 WHERE id=?", (did,))
    client.post(f"/api/admin/deceased/{did}/consents", headers=ADMIN, json={"signer_name": "김태형", "relation": "아들", "kind": "ai_chat"})
    tok = {"X-Family-Token": holder_token("김태형")}
    me = client.get("/api/family/me", headers=tok).json()
    d = next(x for x in me["deceased"] if x["id"] == did)
    assert d["has_voice"] is True and "voice_id" not in d
    s = client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True}).json()
    assert s["voice_available"] is True and s["voice_provider"] == "elevenlabs" and s["voice_hint"] == "male"
    a = client.get(f"/api/family/chat/tts?session_id={s['session_id']}&text=잘 지냈니", headers=tok)
    assert a.status_code == 200 and a.content.endswith(b"voice_abc123")
    # 작별(삭제) → 공급자 음성도 삭제, voice_id 비움
    client.post("/api/family/farewell", headers=tok, json={"deceased_id": did, "action": "delete"})
    assert calls["deleted"] == "voice_abc123"
    assert db.one("SELECT voice_id FROM deceased WHERE id=?", (did,))["voice_id"] == ""
    # 키 삭제 → 브라우저 음성으로 복귀
    r = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5", "elevenlabs_api_key": "", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2"}).json()
    assert r["active_tts"] == "browser"


def test_family_voice_register_from_app(client, monkeypatch):
    """유족 앱: 계약자가 직접 녹음 → 동의 → 등록까지 한 번에. 짧은 녹음은 거부."""
    from server.ai.tts import ElevenLabsTTS
    from server.ai.base import TTSResult
    monkeypatch.setattr(ElevenLabsTTS, "add_voice", lambda self, name, files, description="": "voice_app_1")
    monkeypatch.setattr(ElevenLabsTTS, "synthesize", lambda self, text, voice_id: TTSResult(audio=b"ID3app", mime="audio/mpeg"))
    monkeypatch.setattr(ElevenLabsTTS, "delete_voice", lambda self, voice_id: None)
    client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                              "elevenlabs_api_key": "sk_test00000000000000000000000000", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2"})
    tok = {"X-Family-Token": holder_token("김태형")}
    did = db.one("SELECT id FROM deceased WHERE name='김철수'")["id"]
    st = client.get("/api/family/voice", headers=tok).json()
    assert st["provider_ready"] and st["can_manage"] and not st["deceased"][0]["has_voice"]
    # 보기 권한 계정은 등록 불가
    viewer = {"X-Family-Token": holder_token("최은지")}
    r = client.post("/api/family/voice/register", headers=viewer, data={"deceased_id": did, "kind": "lifetime_record", "agree": "true"}, files={"file": ("rec.wav", fake_wav(20), "audio/wav")})
    assert r.status_code == 403
    # 동의 없이 불가
    r = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "lifetime_record", "agree": "false"}, files={"file": ("rec.wav", fake_wav(20), "audio/wav")})
    assert r.status_code == 400
    # 너무 짧은 녹음 거부(ffprobe가 있을 때)
    from server import voice as vmod
    if vmod.FFPROBE:
        r = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "lifetime_record", "agree": "true"}, files={"file": ("rec.wav", fake_wav(5), "audio/wav")})
        assert r.status_code == 400 and "짧" in r.json()["detail"]
    # 정상 등록
    r = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "lifetime_record", "agree": "true", "note": "아버지 생전 녹음"}, files={"file": ("rec.webm", fake_wav(20), "audio/wav")})
    assert r.status_code == 200, r.text
    assert db.one("SELECT voice_id FROM deceased WHERE id=?", (did,))["voice_id"] == "voice_app_1"
    assert db.one("SELECT signer_name, kind FROM consents WHERE deceased_id=? AND kind='lifetime_record' AND revoked_at IS NULL", (did,))["signer_name"] == "김태형"
    st = client.get("/api/family/voice", headers=tok).json()
    assert st["deceased"][0]["has_voice"] and st["deceased"][0]["samples"] >= 1
    pv = client.post("/api/family/voice/preview", headers=tok, json={"deceased_id": did})
    assert pv.status_code == 200 and pv.content == b"ID3app"
    assert client.delete(f"/api/family/voice/{did}", headers=tok).status_code == 200
    assert db.one("SELECT voice_id FROM deceased WHERE id=?", (did,))["voice_id"] == ""


def test_elevenlabs_key_format_rejected(client):
    r = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                                  "elevenlabs_api_key": "2322c97d1f0a4b7c9e8d6f5a4b3c2d1e4130", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2"})
    assert r.status_code == 400 and "sk_" in r.json()["detail"]
    ok = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                                   "elevenlabs_api_key": "0123456789abcdef0123456789abcdef", "tts_provider": "browser", "tts_model": "eleven_multilingual_v2"})
    assert ok.status_code == 200   # 구형 32자리 hex 키는 허용
    client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5", "elevenlabs_api_key": "", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2"})


# ---------- 실시간 아바타 (Simli — 네트워크는 가짜로) ----------

def test_avatar_register_and_session(client, monkeypatch):
    from server.ai.avatar import SimliAvatar
    from server.ai.tts import ElevenLabsTTS
    from server.ai.base import TTSResult
    calls = {}
    monkeypatch.setattr(SimliAvatar, "ping", lambda self: {"faces": 2, "checks": {"faces_list": "ok", "session_token": "ok"}, "all_ok": True, "note": None})
    monkeypatch.setattr(SimliAvatar, "create_face", lambda self, image, name, filename="photo.jpg": calls.setdefault("created", (name, len(image))) and "face_123")
    monkeypatch.setattr(SimliAvatar, "delete_face", lambda self, fid: calls.setdefault("deleted", fid))
    monkeypatch.setattr(SimliAvatar, "session_token", lambda self, fid, max_len=900, max_idle=120: f"tok-{fid}")
    monkeypatch.setattr(SimliAvatar, "ice_servers", lambda self: [{"urls": ["stun:x"]}])
    monkeypatch.setattr(ElevenLabsTTS, "synthesize", lambda self, text, voice_id: TTSResult(audio=b"ID3x", mime="audio/mpeg"))

    # 키 저장 → 공급자 활성
    r = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                                  "elevenlabs_api_key": "sk_test00000000000000000000000000", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2",
                                                                  "simli_api_key": "simli-test-key", "avatar_provider": "auto"}).json()
    assert r["active_avatar"] == "simli" and r["simli_key_masked"]
    assert client.post("/api/admin/settings/avatar/test", headers=ADMIN).json()["all_ok"]

    tok = {"X-Family-Token": holder_token()}          # 이미영 → 김옥순(사진 있음)
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    st = client.get("/api/family/avatar", headers=tok).json()
    assert st["provider_ready"] and st["deceased"][0]["has_photo"] and not st["deceased"][0]["has_face"]
    # 보기 권한은 불가, 동의 없이는 불가
    assert client.post("/api/family/avatar/register", headers={"X-Family-Token": holder_token("이하은")}, json={"deceased_id": did, "agree": True}).status_code == 403
    assert client.post("/api/family/avatar/register", headers=tok, json={"deceased_id": did, "agree": False}).status_code == 400
    # 등록(작별 테스트에서 동의가 철회됐으므로 앱이 초상 동의를 새로 기록)
    r = client.post("/api/family/avatar/register", headers=tok, json={"deceased_id": did, "agree": True, "kind": "likeness"})
    assert r.status_code == 200, r.text
    assert db.one("SELECT face_id, face_provider FROM deceased WHERE id=?", (did,)) == {"face_id": "face_123", "face_provider": "simli"}
    assert calls["created"][0].startswith("memorial-")
    # 대화 시작: 목소리+얼굴+공급자 → avatar_available. 목소리가 없으면 아바타도 없음
    db.execute("UPDATE deceased SET ai_enabled=1, voice_id='v1', voice_provider='elevenlabs' WHERE id=?", (did,))
    client.post(f"/api/admin/deceased/{did}/consents", headers=ADMIN, json={"signer_name": "이미영", "relation": "큰딸", "kind": "ai_chat"})
    s = client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True}).json()
    assert s["avatar_available"] is True and s["avatar_provider"] == "simli"
    sess = client.post("/api/family/chat/avatar-session", headers=tok, json={"session_id": s["session_id"]}).json()
    assert sess["session_token"] == "tok-face_123" and sess["ws_url"].startswith("wss://") and sess["ice_servers"]
    db.execute("UPDATE deceased SET voice_id='' WHERE id=?", (did,))
    s2 = client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True}).json()
    assert s2["avatar_available"] is False
    # 유족 앱 me에는 face_id가 노출되지 않고 has_face만
    me = client.get("/api/family/me", headers=tok).json()
    d = next(x for x in me["deceased"] if x["id"] == did)
    assert d["has_face"] is True and "face_id" not in d
    # 삭제 → 공급자 얼굴도 삭제
    assert client.delete(f"/api/family/avatar/{did}", headers=tok).status_code == 200
    assert calls["deleted"] == "face_123" and db.one("SELECT face_id FROM deceased WHERE id=?", (did,))["face_id"] == ""
    # 공급자 끔
    r = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5", "simli_api_key": "", "avatar_provider": "auto"}).json()
    assert r["active_avatar"] == "none"


def test_avatar_preset_face(client, monkeypatch):
    from server.ai.avatar import SimliAvatar
    monkeypatch.setattr(SimliAvatar, "session_token", lambda self, fid, max_len=900, max_idle=120: f"tok-{fid}")
    monkeypatch.setattr(SimliAvatar, "ice_servers", lambda self: [])
    monkeypatch.setattr(SimliAvatar, "delete_face", lambda self, fid: (_ for _ in ()).throw(AssertionError("기본 얼굴은 공급자 삭제를 부르면 안 됨")))
    client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5", "simli_api_key": "simli-test-key", "avatar_provider": "auto"})
    tok = {"X-Family-Token": holder_token()}
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    presets = client.get("/api/family/avatar", headers=tok).json()["presets"]
    assert presets and presets[0]["id"] == SimliAvatar.PROBE_FACE
    assert client.post("/api/family/avatar/preset", headers=tok, json={"deceased_id": did, "face_id": "not-a-preset"}).status_code == 400
    r = client.post("/api/family/avatar/preset", headers=tok, json={"deceased_id": did, "face_id": presets[0]["id"]})
    assert r.status_code == 200 and r.json()["preset"] is True
    st = client.get("/api/family/avatar", headers=tok).json()["deceased"][0]
    assert st["has_face"] and st["face_is_preset"] and "Nonna" in st["face_label"]
    # 기본 얼굴 삭제는 공급자를 부르지 않고 우리 쪽만 비운다
    assert client.delete(f"/api/family/avatar/{did}", headers=tok).status_code == 200
    assert db.one("SELECT face_id FROM deceased WHERE id=?", (did,))["face_id"] == ""
