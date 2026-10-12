"""MVP 핵심 흐름 테스트. 실행: python -m pytest -q"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("DEMO_CAMERA", "off")   # 시연 카메라는 test_demo_camera_* 에서만 직접 돌린다

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


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from server import ratelimit
    ratelimit.reset()
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
    assert s["greeting"] and "인공지능" in s["notice"]
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
    # 대화에서 나온 말(첫 인사)만 고인 목소리로 합성한다. 아무 문장은 거부(딥페이크 방지)
    assert client.get(f"/api/family/chat/tts?session_id={s['session_id']}&text=아무 말이나 해 봐", headers=tok).status_code == 403
    a = client.get(f"/api/family/chat/tts", params={"session_id": s["session_id"], "text": s["greeting"]}, headers=tok)
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
    # 너무 짧은 자료는 거부(파일 하나 3초 미만, 또는 모두 합쳐 15초 미만)
    from server import voice as vmod
    if vmod.FFMPEG:
        r = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "lifetime_record", "agree": "true"}, files={"file": ("rec.wav", fake_wav(1.5), "audio/wav")})
        assert r.status_code == 400 and "짧" in r.json()["detail"]
        r = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "lifetime_record", "agree": "true"}, files={"file": ("rec.wav", fake_wav(5), "audio/wav")})
        assert r.status_code == 400 and "15초" in r.json()["detail"]
        db.execute("DELETE FROM media WHERE deceased_id=? AND kind='voice'", (did,))   # 짧은 시험 자료는 치운다
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
    client.post(f"/api/admin/deceased/{did}/consents", headers=ADMIN, json={"signer_name": "김태형", "relation": "아들", "kind": "voice"})   # 목소리는 음성 동의가 있어야 쓴다
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


def test_did_avatar_flow(client, monkeypatch):
    from server.ai.avatar import DIDAvatar
    from server.ai.tts import ElevenLabsTTS
    from server.ai.base import TTSResult
    calls = {}
    monkeypatch.setattr(DIDAvatar, "ping", lambda self: {"checks": {"agents_list": "ok"}, "all_ok": True, "credits": 12, "note": "남은 크레딧 12"})
    monkeypatch.setattr(DIDAvatar, "create_face", lambda self, image, name, filename="photo.jpg": calls.setdefault("agent", name) and "agt_test1")
    monkeypatch.setattr(DIDAvatar, "delete_face", lambda self, aid: calls.setdefault("deleted", aid))
    monkeypatch.setattr(DIDAvatar, "client_key", lambda self, aid, ttl=3600: f"ck-{aid}")
    monkeypatch.setattr(DIDAvatar, "upload_audio", lambda self, audio, filename="speech.mp3": calls.setdefault("audio", len(audio)) and "https://d-id.example/audio.wav")
    monkeypatch.setattr(ElevenLabsTTS, "synthesize", lambda self, text, voice_id: TTSResult(audio=b"ID3did", mime="audio/mpeg"))
    # 키 형식 검사(콜론 필수) → 저장 → auto면 D-ID 우선
    bad = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5", "did_api_key": "nocolon", "avatar_provider": "auto"})
    assert bad.status_code == 400
    r = client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                                  "elevenlabs_api_key": "sk_test00000000000000000000000000", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2",
                                                                  "simli_api_key": "simli-test-key", "did_api_key": "dXNlcg==:secret", "avatar_provider": "auto"}).json()
    assert r["active_avatar"] == "did" and r["did_key_masked"]
    assert client.post("/api/admin/settings/did/test", headers=ADMIN).json()["credits"] == 12
    tok = {"X-Family-Token": holder_token()}
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    st = client.get("/api/family/avatar", headers=tok).json()
    assert st["provider"] == "did" and st["presets"] == []      # D-ID에는 기본 얼굴이 없다
    assert client.post("/api/family/avatar/preset", headers=tok, json={"deceased_id": did, "face_id": "x"}).status_code == 400
    r = client.post("/api/family/avatar/register", headers=tok, json={"deceased_id": did, "agree": True, "kind": "likeness"})
    assert r.status_code == 200 and r.json()["provider"] == "did"
    assert db.one("SELECT face_id FROM deceased WHERE id=?", (did,))["face_id"] == "agt_test1"
    db.execute("UPDATE deceased SET ai_enabled=1, voice_id='v1', voice_provider='elevenlabs' WHERE id=?", (did,))
    s = client.post("/api/family/chat/start", headers=tok, json={"deceased_id": did, "acknowledged_ai": True}).json()
    assert s["avatar_available"] and s["avatar_provider"] == "did"
    sess = client.post("/api/family/chat/avatar-session", headers=tok, json={"session_id": s["session_id"]}).json()
    assert sess["provider"] == "did" and sess["agent_id"] == "agt_test1" and sess["client_key"] == "ck-agt_test1" and sess["sdk_url"].startswith("https://cdn.jsdelivr.net/")
    assert client.post("/api/family/chat/avatar-speak", headers=tok, json={"session_id": s["session_id"], "text": "아무 말이나"}).status_code == 403
    sp = client.post("/api/family/chat/avatar-speak", headers=tok, json={"session_id": s["session_id"], "text": s["greeting"]}).json()
    assert sp["audio_url"].startswith("https://") and calls["audio"] == len(b"ID3did")
    client.delete(f"/api/family/avatar/{did}", headers=tok)
    assert calls["deleted"] == "agt_test1"
    client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5", "did_api_key": "", "simli_api_key": "", "avatar_provider": "auto"})


# ---------- 추모 테마 · 로컬 시작 화면 · 음성 세부 설정 ----------

def test_theme_set_by_manager_only(client):
    h = {"X-Family-Token": holder_token("이미영")}
    me = client.get("/api/family/me", headers=h).json()
    did = me["deceased"][0]["id"]
    assert me["deceased"][0]["theme"] == "classic"
    assert client.post("/api/family/theme", headers=h, json={"deceased_id": did, "theme": "buddhist"}).status_code == 200
    assert client.get("/api/family/me", headers=h).json()["deceased"][0]["theme"] == "buddhist"
    # 보기·대화 권한은 못 바꾼다
    r = client.post("/api/family/theme", headers={"X-Family-Token": holder_token("이준호")}, json={"deceased_id": did, "theme": "catholic"})
    assert r.status_code == 403
    # 목록에 없는 테마는 거부
    assert client.post("/api/family/theme", headers=h, json={"deceased_id": did, "theme": "islam"}).status_code == 422
    # 관리자 콘솔 고인 편집에서도 저장된다
    d = client.get(f"/api/admin/contracts/{me['contract']['id']}", headers=ADMIN).json()["deceased"][0]
    body = {k: d[k] for k in ("contract_id", "name", "honorific", "birth_date", "death_date", "memory_card", "voice_note", "chat_min_days_after_death")}
    body.update(ai_enabled=bool(d["ai_enabled"]), theme="christian")
    assert client.put(f"/api/admin/deceased/{did}", headers=ADMIN, json=body).status_code == 200
    assert client.get("/api/family/me", headers=h).json()["deceased"][0]["theme"] == "christian"


def test_launcher_only_for_local_direct_access(client):
    # 기본 테스트 클라이언트는 호스트가 testserver → 닫힘
    assert client.get("/api/launcher").status_code == 404
    from fastapi.testclient import TestClient
    from server.main import app
    local = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 40000))   # with 없이: lifespan 재실행 안 함
    r = local.get("/api/launcher")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["admin_url"].endswith(config.ADMIN_KEY)
    assert any(m["name"] == "이미영" and m["url"].startswith("/?t=") and m["deceased_names"] for m in j["members"])
    # 프록시를 거친 요청(X-Forwarded-For)에는 닫힌다
    assert local.get("/api/launcher", headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 404


def test_tts_voice_settings_roundtrip_and_v3_snap(client, monkeypatch):
    r = client.put("/api/admin/settings/ai", headers=ADMIN,
                   json={"tts_voice_settings": {"stability": 1.7, "similarity_boost": -1, "style": 0.3, "speed": 0.5, "bogus": 1}})
    assert r.status_code == 200, r.text
    vs = r.json()["tts_voice_settings"]
    assert vs["stability"] == 1.0 and vs["similarity_boost"] == 0.0 and vs["style"] == 0.3 and vs["speed"] == 0.7 and "bogus" not in vs
    assert client.get("/api/admin/settings/ai", headers=ADMIN).json()["tts_voice_settings"]["speed"] == 0.7
    from server.ai.tts import ElevenLabsTTS
    t = ElevenLabsTTS("sk_test", "eleven_v3", {"stability": 0.4, "speed": 0.9})
    v3 = t._voice_settings("eleven_v3")
    assert v3["stability"] == 0.5 and "speed" not in v3          # v3는 0/0.5/1 세 단계, 속도 없음
    v2 = t._voice_settings("eleven_multilingual_v2")
    assert v2["stability"] == 0.4 and v2["speed"] == 0.9
    # 미리 듣기: 저장하지 않고 넘어온 설정·모델로 첫 등록 음성을 합성한다
    from server.ai.tts import TTSResult
    captured = {}
    def fake_synth(self, text, voice_id, settings=None, model=None):
        captured.update(text=text, voice_id=voice_id, settings=settings, model=model)
        return TTSResult(audio=b"ID3preview", mime="audio/mpeg")
    monkeypatch.setattr(ElevenLabsTTS, "synthesize", fake_synth)
    assert client.put("/api/admin/settings/ai", headers=ADMIN, json={"elevenlabs_api_key": "sk_" + "b" * 40, "tts_provider": "auto"}).status_code == 200
    db.execute("UPDATE deceased SET voice_id='v_prev', voice_provider='elevenlabs' WHERE id=?", (1,))
    r = client.post("/api/admin/settings/tts/preview", headers=ADMIN, json={"text": "안녕", "model": "eleven_v3", "settings": {"style": 0.9}})
    assert r.status_code == 200 and r.content == b"ID3preview", r.text
    assert captured["model"] == "eleven_v3" and captured["settings"]["style"] == 0.9 and captured["voice_id"] == "v_prev"
    db.execute("UPDATE deceased SET voice_id='', voice_provider='' WHERE id=?", (1,))
    # ElevenLabs가 꺼져 있으면 미리 듣기는 400
    assert client.put("/api/admin/settings/ai", headers=ADMIN, json={"elevenlabs_api_key": ""}).status_code == 200
    assert client.post("/api/admin/settings/tts/preview", headers=ADMIN, json={}).status_code == 400


# ---------- 실시간 보기 보호 스위치 · 현장 프로그램 처리 속도 ----------

def test_live_protect_toggle(client):
    cfg = client.get("/api/edge/config", headers=EDGE).json()
    cam = cfg["cameras"][0]
    tok = {"X-Family-Token": holder_token()}
    client.post(f"/api/edge/cameras/{cam['id']}/status", headers=EDGE, data={"occupied": "true", "persons": 1, "fps": 10})
    assert client.post("/api/family/live/start", headers=tok).status_code == 409          # 운용 기본: 사람 있으면 거부
    assert client.put("/api/admin/settings/live", headers=ADMIN, json={"protect": False}).json()["protect"] is False
    assert client.get("/api/edge/config", headers=EDGE).json()["live_ignore_occupied"] is True
    assert client.get("/api/admin/settings/live", headers=ADMIN).json()["protect"] is False
    assert client.post("/api/family/live/start", headers=tok).status_code == 200          # 시연 모드: 사람 있어도 시작
    assert client.get("/api/family/niche/status", headers=tok).json()["live_protect"] is False
    assert client.get("/api/admin/overview", headers=ADMIN).json()["live_protect"] is False
    client.put("/api/admin/settings/live", headers=ADMIN, json={"protect": True})
    assert client.get("/api/edge/config", headers=EDGE).json()["live_ignore_occupied"] is False
    client.post(f"/api/edge/cameras/{cam['id']}/status", headers=EDGE, data={"occupied": "false", "persons": 0, "fps": 10})


def test_edge_crop_is_fast_and_bounded():
    import time
    import numpy as np
    from edge.agent import crop_niche, jpeg
    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    rect = {"x": 0.4, "y": 0.2, "w": 0.18, "h": 0.26}
    out = crop_niche(frame, rect)
    assert out.shape[1] <= 720 and out.ndim == 3
    assert len(jpeg(out, 75)) > 1000
    t = time.perf_counter()
    for _ in range(5):
        jpeg(crop_niche(frame, rect), 75)
    assert (time.perf_counter() - t) / 5 < 0.05      # 한 장에 50ms 미만(1080p 큰 반경 흐림은 66ms였다)


# ---------- 제사 생중계: 신청 가족만 · 봉행 순서(고인·상주) · 가족 메시지/반응 쌍방향 ----------

def test_ritual_live_flow(client):
    from datetime import datetime
    tok = {"X-Family-Token": holder_token("이미영")}
    tok2 = {"X-Family-Token": holder_token("김태형")}
    ritual_cam = next(c for c in client.get("/api/edge/config", headers=EDGE).json()["cameras"] if c["kind"] == "ritual")
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    rid = client.post("/api/admin/rituals", headers=ADMIN, json={"title": "테스트 합동 제사", "kind": "memorial", "access": "applied", "scheduled_at": now_iso, "camera_id": ritual_cam["id"]}).json()["id"]
    # 신청 전: 목록에는 보이지만 볼 수 없다
    mine = next(x for x in client.get("/api/family/rituals", headers=tok).json() if x["id"] == rid)
    assert mine["access"] == "applied" and mine["can_watch"] is False and mine["my_participation"] is None
    assert client.get(f"/api/family/rituals/{rid}/live", headers=tok).status_code == 403
    assert client.get(f"/api/family/rituals/{rid}/stream", headers=tok).status_code == 403
    # 참여 신청 → 순서 1번, 상주 기본은 계약자 이름
    assert client.post(f"/api/family/rituals/{rid}/join", headers=tok, json={"mourner_name": ""}).json()["order_no"] == 1
    assert client.post(f"/api/family/rituals/{rid}/join", headers=tok, json={}).status_code == 409
    client.post(f"/api/family/rituals/{rid}/join", headers=tok2, json={"mourner_name": "김태형"})
    mine = next(x for x in client.get("/api/family/rituals", headers=tok).json() if x["id"] == rid)
    assert mine["can_watch"] and mine["my_participation"]["mourner_name"] == "이미영" and len(mine["participants"]) == 2
    # 진행자가 현재 차례를 1번으로 → 라이브 payload에 고인 이름·생년월일·상주
    assert client.post(f"/api/admin/rituals/{rid}/current", headers=ADMIN, json={"order_no": 1}).json()["current_order"] == 1
    live = client.get(f"/api/family/rituals/{rid}/live?since=0&rseq=0", headers=tok).json()
    assert live["current"]["deceased_name"] == "김옥순" and live["current"]["is_mine"] and live["current"]["mourner_name"] == "이미영"
    assert live["current"]["birth_date"] and live["order"][1]["deceased_name"] == "김철수"
    # 쌍방향: 가족 메시지(연타 제한) ↔ 진행자 공지, 반응
    assert client.post(f"/api/family/rituals/{rid}/messages", headers=tok, json={"message": "어머니, 저희 왔어요"}).status_code == 200
    assert client.post(f"/api/family/rituals/{rid}/messages", headers=tok, json={"message": "연타"}).status_code == 429
    client.post(f"/api/admin/rituals/{rid}/messages", headers=ADMIN, json={"message": "지금 김옥순 님 차례입니다", "kind": "notice"})
    seq = client.post(f"/api/family/rituals/{rid}/reactions", headers=tok2, json={"emoji": "🙏"}).json()["seq"]
    assert client.post(f"/api/family/rituals/{rid}/reactions", headers=tok2, json={"emoji": "😀"}).status_code == 400
    live2 = client.get(f"/api/family/rituals/{rid}/live?since=0&rseq={seq - 1}", headers=tok2).json()
    kinds = [(x["sender"], x["kind"]) for x in live2["messages"]]
    assert ("family", "chat") in kinds and ("site", "notice") in kinds
    assert live2["reactions"] and live2["reactions"][-1]["emoji"] == "🙏" and live2["viewer_count"] >= 1
    # 다음 차례 → 2번(김철수), 그 다음은 마침
    assert client.post(f"/api/admin/rituals/{rid}/next", headers=ADMIN).json()["current_order"] == 2
    assert client.post(f"/api/admin/rituals/{rid}/next", headers=ADMIN).json()["finished"] is True
    # 진행 콘솔·현장 화면 payload
    con = client.get(f"/api/admin/rituals/{rid}/console", headers=ADMIN).json()
    assert len(con["participants"]) == 2 and con["contracts"]
    assert client.get(f"/api/admin/rituals/{rid}/live?since=0", headers=ADMIN).json()["order"][0]["deceased_name"] == "김옥순"
    # 반려하면 볼 수 없다
    pid2 = next(x["id"] for x in con["participants"] if x["holder_name"] == "김태형")
    client.put(f"/api/admin/rituals/{rid}/participants/{pid2}", headers=ADMIN, json={"status": "rejected"})
    assert client.get(f"/api/family/rituals/{rid}/live", headers=tok2).status_code == 403
    # 법회(누구나)는 신청 없이 본다
    r2 = client.post("/api/admin/rituals", headers=ADMIN, json={"title": "테스트 법회", "kind": "event", "access": "open", "scheduled_at": now_iso, "camera_id": ritual_cam["id"]}).json()
    assert client.get(f"/api/family/rituals/{r2['id']}/live", headers=tok2).status_code == 200
    assert client.get("/screen").status_code == 200


def test_blur_outside_toggle_and_crop_clear(client):
    import numpy as np
    from edge.agent import crop_niche
    r = client.put("/api/admin/settings/live", headers=ADMIN, json={"protect": True, "blur": False}).json()
    assert r["blur"] is False and r["protect"] is True
    assert client.get("/api/edge/config", headers=EDGE).json()["blur_outside"] is False
    assert client.get("/api/admin/overview", headers=ADMIN).json()["blur_outside"] is False
    client.put("/api/admin/settings/live", headers=ADMIN, json={"protect": True, "blur": True})
    assert client.get("/api/edge/config", headers=EDGE).json()["blur_outside"] is True
    # 시연 모드(blur=False)에서는 바깥을 어둡게·흐리게 하지 않는다
    frame = np.full((720, 1280, 3), 200, dtype=np.uint8)
    rect = {"x": 0.4, "y": 0.2, "w": 0.18, "h": 0.26}
    clear, blurred = crop_niche(frame, rect, blur=False), crop_niche(frame, rect, blur=True)
    assert clear.shape[1] == 960 and blurred.shape[1] <= 720                     # 시연: 화면 전체(960) · 운용: 내 칸 잘라내기
    assert clear[5, 5].tolist() == [200, 200, 200] and blurred[5, 5][0] < 130   # 모서리(내 칸 밖): 선명 vs 어두움


def test_camera_sharpness_warning(client):
    cam = client.get("/api/edge/config", headers=EDGE).json()["cameras"][0]
    client.post(f"/api/edge/cameras/{cam['id']}/status", headers=EDGE, data={"occupied": "false", "persons": 0, "fps": 10, "sharpness": 12.3})
    c = next(x for x in client.get("/api/admin/overview", headers=ADMIN).json()["cameras"] if x["id"] == cam["id"])
    assert c["sharpness"] == 12.3 and c["blurry"] is True
    client.post(f"/api/edge/cameras/{cam['id']}/status", headers=EDGE, data={"occupied": "false", "persons": 0, "fps": 10, "sharpness": 180})
    c = next(x for x in client.get("/api/admin/overview", headers=ADMIN).json()["cameras"] if x["id"] == cam["id"])
    assert c["blurry"] is False


def test_start_now_assigns_camera_and_demo_mode_keeps_live(client):
    tok = {"X-Family-Token": holder_token("이미영")}
    rid = client.post("/api/admin/rituals", headers=ADMIN, json={"title": "카메라 없는 기일 제사", "kind": "memorial", "access": "open", "scheduled_at": "2020-01-01T10:00:00+09:00"}).json()["id"]
    r = client.post(f"/api/admin/rituals/{rid}/start-now", headers=ADMIN).json()
    assert r["camera_id"] and r["camera_assigned"]
    mine = next(x for x in client.get("/api/family/rituals", headers=tok).json() if x["id"] == rid)
    assert mine["is_live_window"] and not mine["is_past"] and mine["camera_id"] == r["camera_id"]
    # 오래된 일정이라도 시연 모드면 카메라 일정은 중계 창이 열려 있다
    client.put(f"/api/admin/rituals/{rid}", headers=ADMIN, json={"title": "카메라 없는 기일 제사", "kind": "memorial", "scheduled_at": "2020-01-01T10:00:00+09:00", "camera_id": r["camera_id"]})
    mine = next(x for x in client.get("/api/family/rituals", headers=tok).json() if x["id"] == rid)
    assert mine["is_past"] and not mine["is_live_window"]
    client.put("/api/admin/settings/live", headers=ADMIN, json={"protect": False})
    mine = next(x for x in client.get("/api/family/rituals", headers=tok).json() if x["id"] == rid)
    assert mine["is_live_window"] and not mine["is_past"]
    assert r["camera_id"] in client.get("/api/edge/config", headers=EDGE).json()["ritual_live_camera_ids"]
    client.put("/api/admin/settings/live", headers=ADMIN, json={"protect": True})


# ---------- 시연 카메라(현장 웹캠 없이 원격 참배·생중계 시연) ----------

def test_demo_camera_feeds_snapshot_live_and_ritual(client):
    import time
    from server.demo_camera import DemoCamera
    from server.state import state
    tok = {"X-Family-Token": holder_token()}
    cam_id = db.one("SELECT camera_id FROM niches WHERE code='A-1-2'")["camera_id"]
    state.cameras.pop(cam_id, None)
    db.set_setting("demo_camera", "auto")
    niche_key = db.one("SELECT id FROM niches WHERE code='A-1-2'")["id"]
    ritual_key = -db.one("SELECT id FROM cameras WHERE kind='ritual'")["id"]
    state.watch(niche_key, +1); state.watch(ritual_key, +1)   # 가족이 실시간 보기·생중계를 열어 둔 상태
    try:
        cam = DemoCamera()
        cam.tick(time.time())
        st = client.get("/api/family/niche/status", headers=tok).json()
        assert st["camera_online"] and st["demo_camera"] and st["last_snapshot_at"]
        snap = client.get("/api/family/niche/snapshot.jpg", headers=tok)
        assert snap.status_code == 200 and snap.content[:2] == bytes([0xFF, 0xD8])
        assert client.post("/api/family/live/start", headers=tok).status_code == 200
        before = state.live_frames.get(db.one("SELECT id FROM niches WHERE code='A-1-2'")["id"])
        cam.tick(time.time())
        after = state.live_frames.get(db.one("SELECT id FROM niches WHERE code='A-1-2'")["id"])
        assert after is not None and (before is None or after.seq > before.seq)
        # 진행 중인 제례(시드: '지금 진행 중인 시연 법회')의 제례 카메라도 시연 화면을 받는다
        ritual_cam = db.one("SELECT id FROM cameras WHERE kind='ritual'")["id"]
        assert state.live_frames.get(-ritual_cam) is not None
        # 실제 현장 프로그램이 연결되면 auto 모드의 시연 카메라는 비켜 선다
        client.post(f"/api/edge/cameras/{cam_id}/status", headers=EDGE, data={"occupied": "false", "persons": 0, "fps": 10})
        cam.tick(time.time())
        assert cam_id not in cam.active
        assert client.get("/api/family/niche/status", headers=tok).json()["demo_camera"] is False
        assert client.put("/api/admin/settings/demo-camera", headers=ADMIN, json={"mode": "off"}).json()["mode"] == "off"
        assert client.get("/api/admin/overview", headers=ADMIN).json()["demo_camera"] == "off"
    finally:
        state.watch(niche_key, -1); state.watch(ritual_key, -1)
        db.set_setting("demo_camera", "off")


# ---------- 몽환 Lottie 장면(2026-10-12): 움직임은 Lottie 만, 장면 파일은 생성기로 ----------

def test_dream_scenes_are_generated_lottie_and_css_has_no_keyframes():
    import json, re
    static = ROOT / "server" / "static"
    scenes = json.loads((static / "lottie" / "dream" / "scenes.json").read_text(encoding="utf-8"))
    names = [f"entry-{t}" for t in ("classic", "buddhist", "catholic", "christian")] + ["offering", "shrine", "voice"] + \
            [f"reaction-{k}" for k in ("hands", "candle", "flower", "heart")]
    for name in names:
        assert name in scenes
        data = json.loads((static / "lottie" / "dream" / f"{name}.json").read_text(encoding="utf-8"))
        assert data["fr"] == 30 and data["layers"]
        for a in data["assets"]:
            if "p" in a:   # 이미지 레이어는 모두 webp 로, 실제 파일이 있어야 한다
                assert a["p"].endswith(".webp") and (static / "lottie" / "dream" / "img" / a["p"]).is_file()
    # 반복 구간이 있는 장면은 정지 장면이 그 안에 있다(앱 '움직임 줄이기' → 정지 화면)
    for name in ("entry-buddhist", "offering", "shrine"):
        a, b = scenes[name]["loop"]
        assert a <= scenes[name]["still"] < b
    # 인공지능 생성 이미지가 든 장면은 화면에 표시한다
    assert "인공지능 생성" in scenes["entry-classic"]["credit"] and "윤회당" in scenes["entry-buddhist"]["credit"]
    # 예전 CSS 움직임(키프레임)은 모두 걷어냈다
    for css in (static / "css").glob("*.css"):
        assert not re.search(r"@keyframes", css.read_text(encoding="utf-8")), css.name
    assert not (static / "js" / "brand.js").exists()


def test_demo_portrait_replaces_only_seed_placeholder(client, tmp_path):
    from server import seed
    d = db.one("SELECT photo_path FROM deceased WHERE name='김옥순'")
    p = config.MEDIA_DIR / d["photo_path"]
    assert p.exists() and not seed._is_placeholder(p)            # 새 시연 데이터는 처음부터 가상 인물 초상
    seed._portrait(p, "", (0, 0, 0))                               # 예전 '사진 자리' 그림이었다면
    assert seed._is_placeholder(p)
    assert seed.refresh_demo_photos() == 1 and not seed._is_placeholder(p)
    assert seed.refresh_demo_photos() == 0                         # 실제(또는 이미 바꾼) 사진은 건드리지 않음



# ---------- 목소리 등록: 실시간 녹음·여러 형식 파일·여러 개 합치기·기능이 꺼져 있을 때 저장 (2026-10-12) ----------

def _convert(wav: bytes, ext: str) -> bytes:
    """시험용: wav 를 ffmpeg 로 다른 형식(m4a·ogg·flac·mp4 영상 등)으로 바꾼다."""
    import subprocess, tempfile, os
    from server import voice as vmod
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in.wav"), os.path.join(d, "out" + ext)
        open(src, "wb").write(wav)
        args = [vmod.FFMPEG, "-y", "-loglevel", "error", "-i", src]
        if ext == ".mp4":   # 소리가 든 짧은 영상
            args = [vmod.FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=12", "-i", src, "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        subprocess.run(args + [dst], check=True, capture_output=True, timeout=120)
        return open(dst, "rb").read()


def test_voice_samples_many_formats_and_pending(client, monkeypatch):
    import pytest as _pt
    from server import voice as vmod
    from server.ai.tts import ElevenLabsTTS
    if not vmod.FFMPEG:
        _pt.skip("ffmpeg 없음")
    sent = {}
    monkeypatch.setattr(ElevenLabsTTS, "add_voice", lambda self, name, files, description="": sent.setdefault("files", files) and "voice_multi")
    monkeypatch.setattr(ElevenLabsTTS, "delete_voice", lambda self, voice_id: None)
    tok = {"X-Family-Token": holder_token("이미영")}
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    db.execute("DELETE FROM media WHERE deceased_id=? AND kind='voice'", (did,))
    # 1) 음성 복제가 꺼져 있으면: 자료(여러 형식)와 동의만 저장하고 '대기'로 돌려준다
    client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5", "elevenlabs_api_key": "",
                                                              "tts_provider": "browser", "tts_model": "eleven_multilingual_v2"})
    st = client.get("/api/family/voice", headers=tok).json()
    assert st["provider_ready"] is False and ".m4a" in st["accept"] and "amr" in st["formats"]
    files = [("file", ("통화녹음.m4a", _convert(fake_wav(8), ".m4a"), "audio/mp4")),
             ("file", ("음성메시지.ogg", _convert(fake_wav(6), ".ogg"), "audio/ogg")),
             ("file", ("가족영상.mp4", _convert(fake_wav(10), ".mp4"), "video/mp4"))]
    r = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "voice", "agree": "true"}, files=files)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["pending"] is True and j["files"] == 3 and 20 <= j["seconds"] <= 28
    rows = db.rows("SELECT path FROM media WHERE deceased_id=? AND kind='voice'", (did,))
    assert len(rows) == 3 and all(x["path"].endswith(".mp3") for x in rows)          # 모두 mp3 로 바뀜(영상은 소리만)
    assert client.get("/api/family/voice", headers=tok).json()["deceased"][0]["sample_seconds"] >= 20
    assert client.post(f"/api/family/voice/{did}/build", headers=tok).status_code == 400   # 아직 꺼져 있음
    # 2) 시설이 켜면 저장해 둔 자료로 바로 만든다
    client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                              "elevenlabs_api_key": "sk_test00000000000000000000000000", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2"})
    r = client.post(f"/api/family/voice/{did}/build", headers=tok)
    assert r.status_code == 200, r.text
    assert len(sent["files"]) == 3 and all(f[2] == "audio/mpeg" and f[0].endswith(".mp3") for f in sent["files"])
    assert db.one("SELECT voice_id FROM deceased WHERE id=?", (did,))["voice_id"] == "voice_multi"
    # 3) 소리가 아닌 파일·손상된 파일은 알아듣게 거부
    bad = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "voice", "agree": "true"},
                      files={"file": ("메모.txt", b"x" * 5000, "text/plain")})
    assert bad.status_code == 400 and "음성이나 영상" in bad.json()["detail"]
    broken = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "voice", "agree": "true"},
                         files={"file": ("망가진.m4a", b"\x00not-audio" * 800, "audio/mp4")})
    assert broken.status_code == 400 and "소리를 읽지 못" in broken.json()["detail"]
    client.delete(f"/api/family/voice/{did}", headers=tok)


def test_admin_voice_upload_records_consent_and_builds(client, monkeypatch):
    """관리자 콘솔 '목소리 녹음 · 파일 올리기': 동의서가 없으면 이름을 받아 기록하고, 자료를 mp3 로 저장해 바로 등록한다."""
    import pytest as _pt
    from server import voice as vmod
    from server.ai.tts import ElevenLabsTTS
    if not vmod.FFMPEG:
        _pt.skip("ffmpeg 없음")
    monkeypatch.setattr(ElevenLabsTTS, "add_voice", lambda self, name, files, description="": "voice_admin_1")
    monkeypatch.setattr(ElevenLabsTTS, "delete_voice", lambda self, voice_id: None)
    client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                              "elevenlabs_api_key": "sk_test00000000000000000000000000", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2"})
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    db.execute("UPDATE consents SET revoked_at=? WHERE deceased_id=? AND kind IN ('voice','lifetime_record')", (db.now(), did))
    db.execute("DELETE FROM media WHERE deceased_id=? AND kind='voice'", (did,))
    up = lambda data: client.post(f"/api/admin/deceased/{did}/voice/upload", headers=ADMIN, data=data,
                                  files=[("file", ("녹음 1.m4a", _convert(fake_wav(9), ".m4a"), "audio/mp4")), ("file", ("녹음 2.webm", _convert(fake_wav(9), ".webm"), "audio/webm"))])
    r = up({"kind": "voice", "agree": "true"})                       # 동의서도, 서명자도 없음
    assert r.status_code == 400 and "동의" in r.json()["detail"]
    r = up({"kind": "voice", "agree": "true", "signer_name": "이미영", "relation": "큰딸"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["pending"] is False and j["files"] == 2 and j["seconds"] >= 15
    assert db.one("SELECT voice_id FROM deceased WHERE id=?", (did,))["voice_id"] == "voice_admin_1"
    c = db.one("SELECT signer_name, relation, kind FROM consents WHERE deceased_id=? AND kind='voice' AND revoked_at IS NULL", (did,))
    assert c == {"signer_name": "이미영", "relation": "큰딸", "kind": "voice"}
    client.delete(f"/api/admin/deceased/{did}/voice", headers=ADMIN)


# ---------- ECC 점검 1차 수정(2026-10-12) ----------

def test_consent_revoke_closes_voice_and_face(client, monkeypatch):
    """동의 철회 → 그 동의가 필요한 복제 음성·고인 얼굴을 바로 지운다(화면 안내와 일치)."""
    from server.ai.tts import ElevenLabsTTS
    deleted = {}
    monkeypatch.setattr(ElevenLabsTTS, "delete_voice", lambda self, voice_id: deleted.setdefault("voice", voice_id))
    client.put("/api/admin/settings/ai", headers=ADMIN, json={"api_key": None, "provider": "mock", "model": "claude-opus-5",
                                                              "elevenlabs_api_key": "sk_test00000000000000000000000000", "tts_provider": "auto", "tts_model": "eleven_multilingual_v2"})
    did = db.one("SELECT id FROM deceased WHERE name='김철수'")["id"]
    db.execute("UPDATE consents SET revoked_at=? WHERE deceased_id=? AND kind IN ('voice','lifetime_record')", (db.now(), did))
    client.post(f"/api/admin/deceased/{did}/consents", headers=ADMIN, json={"signer_name": "김태형", "relation": "아들", "kind": "voice"})
    cid = db.one("SELECT id FROM consents WHERE deceased_id=? AND kind='voice' AND revoked_at IS NULL", (did,))["id"]
    db.execute("UPDATE deceased SET voice_id='v_revoke', voice_provider='elevenlabs' WHERE id=?", (did,))
    r = client.post(f"/api/admin/consents/{cid}/revoke", headers=ADMIN).json()
    assert r["ok"] and "복제 음성" in r["closed"] and deleted["voice"] == "v_revoke"
    assert db.one("SELECT voice_id FROM deceased WHERE id=?", (did,))["voice_id"] == ""


def test_voice_preview_is_manage_only(client):
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    viewer = {"X-Family-Token": holder_token("이하은")}      # '보기' 권한(미성년)
    r = client.post("/api/family/voice/preview", headers=viewer, json={"deceased_id": did, "text": "아무 말"})
    assert r.status_code == 403


def test_provider_connection_error_becomes_korean_503(monkeypatch):
    import requests as rq
    from server.ai.tts import ElevenLabsTTS, TTSError
    def boom(self, *a, **k):
        raise rq.ConnectionError("down")
    monkeypatch.setattr(rq.Session, "request", boom)
    with pytest.raises(TTSError) as ei:
        ElevenLabsTTS("sk_x", "eleven_multilingual_v2").synthesize("안녕", "v1")
    assert ei.value.status == 503 and "연결하지 못했습니다" in ei.value.message


def test_unhandled_error_and_validation_are_korean(client):
    from fastapi.testclient import TestClient
    from server.main import app
    if not any(getattr(r, "path", "") == "/__test_boom" for r in app.routes):
        app.add_api_route("/__test_boom", lambda: 1 / 0, methods=["GET"])
    r = TestClient(app, raise_server_exceptions=False).get("/__test_boom")
    assert r.status_code == 500 and "서버에 문제가 생겨" in r.json()["detail"]
    v = client.post("/api/family/guestbook", headers={"X-Family-Token": holder_token()}, json={})
    assert v.status_code == 422 and "입력한 값을 다시 확인" in v.json()["detail"]


def test_access_log_drops_query_secrets():
    import logging
    from server.main import _DropQuery
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", "/api/admin/cameras/1/frame.jpg?key=SECRET", "1.1", 200), None)
    _DropQuery().filter(rec)
    assert "SECRET" not in rec.getMessage() and "/frame.jpg" in rec.getMessage()


def test_mjpeg_is_async_and_skips_stale_frames():
    import asyncio, time
    from server.routers.family import _mjpeg
    from server.state import state
    async def first(key):
        agen = _mjpeg(key, time.time() + 2, None)
        try:
            return await asyncio.wait_for(agen.__anext__(), 1.5)
        except (StopAsyncIteration, asyncio.TimeoutError):
            return None
        finally:
            await agen.aclose()
    state.push_live(-999, b"FRESHJPEG")
    assert b"FRESHJPEG" in asyncio.run(first(-999))
    state.live_frames[-998] = type(state.live_frames[-999])(b"OLDJPEG", state.live_frames[-999].seq + 1, time.time() - 60)
    assert asyncio.run(first(-998)) is None          # 1분 지난 장면은 '실시간'으로 내보내지 않는다


# ---------- ECC 점검 2차 수정(2026-10-12) ----------

def test_family_and_admin_cookie_sessions(client):
    """처음에 헤더로 확인한 뒤에는 보안 쿠키로 다닌다(사진·생중계 주소에 ?t= · ?key= 를 싣지 않게)."""
    from fastapi.testclient import TestClient
    from server.main import app
    c = TestClient(app)
    tok = holder_token()
    assert c.get("/api/family/me").status_code == 401
    r = c.post("/api/family/session", headers={"X-Family-Token": tok})
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert c.get("/api/family/me").status_code == 200                      # 쿠키만으로
    c.delete("/api/family/session")
    assert c.get("/api/family/me").status_code == 401
    assert c.get("/api/admin/overview").status_code == 401
    assert c.post("/api/admin/session", headers=ADMIN).status_code == 200
    assert c.get("/api/admin/overview").status_code == 200                 # 쿠키만으로


def test_rate_limits_and_admin_key_guessing(client):
    tok = {"X-Family-Token": holder_token()}
    codes = [client.post("/api/family/live/start", headers=tok).status_code for _ in range(31)]
    assert codes[-1] == 429 and 429 not in codes[:30]
    bad = [client.get("/api/admin/overview", headers={"X-Admin-Key": "wrong"}).status_code for _ in range(21)]
    assert bad[:20] == [401] * 20 and bad[20] == 429


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and "object-src 'none'" in r.headers["content-security-policy"]


def test_applied_ritual_hides_links_and_other_families(client):
    tok2 = {"X-Family-Token": holder_token("김태형")}
    fid = db.one("SELECT id FROM facilities LIMIT 1")["id"]
    rid = db.execute("INSERT INTO rituals(facility_id, contract_id, title, kind, access, scheduled_at, stream_url, replay_url, note) VALUES (?,?,?,?,?,?,?,?,?)",
                     (fid, None, "비공개 합동 제사", "memorial", "applied", "2030-01-01T10:00:00+09:00", "https://youtu.be/private", "https://youtu.be/replay", ""))
    row = next(x for x in client.get("/api/family/rituals", headers=tok2).json() if x["id"] == rid)
    assert row["can_watch"] is False and row["stream_url"] == "" and row["replay_url"] == ""
    # 순서표: 신청한 가족은 다른 가족의 계약자 이름·메모를 받지 않는다
    seq_rid = db.one("SELECT id FROM rituals WHERE title LIKE '합동 기제사%'")["id"]
    live = client.get(f"/api/family/rituals/{seq_rid}/live", headers=tok2).json()
    assert live["order"] and all("holder_name" not in x and "note" not in x and "contract_id" not in x for x in live["order"])


def test_ritual_links_must_be_http(client):
    fid = db.one("SELECT id FROM facilities LIMIT 1")["id"]
    r = client.post("/api/admin/rituals", headers=ADMIN, json={"title": "t", "scheduled_at": "2030-01-01T10:00:00+09:00", "stream_url": "javascript:alert(1)"})
    assert r.status_code == 422


def test_playlist_files_rejected(client):
    tok = {"X-Family-Token": holder_token("이미영")}
    did = db.one("SELECT id FROM deceased WHERE name='김옥순'")["id"]
    body = b"#EXTM3U\n#EXTINF:10,\nhttp://169.254.169.254/latest\n" + b" " * 3000
    r = client.post("/api/family/voice/register", headers=tok, data={"deceased_id": did, "kind": "voice", "agree": "true"}, files={"file": ("x.wav", body, "audio/wav")})
    assert r.status_code == 400 and "재생 목록" in r.json()["detail"]


def test_demo_entry_and_redesigned_shell(client):
    # /demo: 홈페이지·플랫폼의 'MVP 바로가기'가 여는 시작 화면(같은 가족 앱 HTML)
    r = client.get("/demo")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    html = r.text
    assert 'id="topTools"' in html and 'class="brand" href="/"' in html
    assert "/static/css/serene.css?v=" in html   # 새 디자인 층도 수정 시각으로 캐시를 깬다
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "server" / "static"
    app_js = (static / "js" / "app.js").read_text(encoding="utf-8")
    assert 'location.pathname === "/demo"' in app_js and "HOME_QUICK" in app_js and "history.pushState" in app_js
    assert "community.js?v=20261012-serene" in app_js
    # 관리자 콘솔: 메뉴 묶음, 제목 막대, 화면 안 키 입력(브라우저 팝업 없음)
    admin = client.get("/admin").text
    assert admin.count('class="nav-group"') == 4 and 'id="consoleTitle"' in admin and "/static/css/console.css?v=" in admin
    admin_js = (static / "js" / "admin.js").read_text(encoding="utf-8")
    assert "prompt(" not in admin_js and 'id="keyForm"' in admin_js
    for page in ("overview", "tasks", "contracts", "deceased", "rituals", "calib", "usage", "aisettings"):
        assert f'data-page="{page}"' in admin
