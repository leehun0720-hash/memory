"""실시간 립싱크 아바타 공급자 (A등급).
- SimliAvatar: 사진 1장으로 얼굴을 만들고, 대화 중 우리가 만든 음성(PCM16 16kHz)을 보내면 입을 맞춘 영상이 WebRTC로 돌아온다.
  API 키는 서버에만 있고, 브라우저에는 짧은 세션 토큰만 내려간다.
  문서(2026-09-19 확인): https://docs.simli.com/api-reference/simli-webrtc.md
"""
import logging

import requests

log = logging.getLogger(__name__)


class AvatarError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class NoAvatar:
    name = "none"


class SimliAvatar:
    name = "simli"
    BASE = "https://api.simli.ai"
    WS_URL = "wss://api.simli.ai/compose/webrtc/p2p"
    # 연결 테스트용 기본 제공 얼굴(Simli 'Nonna'). 세션 토큰 발급만 확인하고 실제로 연결하지는 않는다.
    PROBE_FACE = "c2f1d5d7-074b-405d-be4c-df52cd52166a"
    # Simli 기본 제공 얼굴(무료 플랜에서도 사용 가능). 문서 2026-09-19 확인: https://docs.simli.com/api-reference/preset-faces.md
    PRESET_FACES = [
        {"id": "c2f1d5d7-074b-405d-be4c-df52cd52166a", "label": "노년 여성 (Nonna)"},
        {"id": "121cd5ae-7df7-4ea3-a389-401a9463db52", "label": "노년 여성 2 (Edna)"},
        {"id": "cace3ef7-a4c4-425d-a8cf-a5358eb0c427", "label": "동양 여성 (Tina)"},
        {"id": "d2a5c7c6-fed9-4f55-bcb3-062f7cd20103", "label": "여성 (Kate)"},
        {"id": "f1abe833-b44c-4650-a01c-191b9c3c43b8", "label": "남성 (Tony)"},
        {"id": "dd10cb5a-d31d-4f12-b69f-6db3383c006e", "label": "남성 2 (Hank)"},
        {"id": "7e74d6e7-d559-4394-bd56-4923a3ab75ad", "label": "남성 3 (Sabour)"},
    ]
    PRESET_IDS = {f["id"] for f in PRESET_FACES}

    def __init__(self, api_key: str) -> None:
        self.key = api_key
        self.s = requests.Session()
        self.s.headers["x-simli-api-key"] = api_key

    @staticmethod
    def _msg(r: requests.Response) -> str:
        try:
            j = r.json()
            d = j.get("detail") if isinstance(j, dict) else None
            if isinstance(d, list):
                d = "; ".join(str(x.get("msg", x)) for x in d)
            return str(d or j)[:300]
        except ValueError:
            return r.text[:300]

    def _raise(self, r: requests.Response) -> None:
        if r.ok:
            return
        msg = self._msg(r)
        log.warning("Simli %s %s: %s %s", r.request.method, r.request.path_url, r.status_code, msg)
        if "max number of" in msg.lower() and "face" in msg.lower():
            msg = ("현재 Simli 요금제에서는 사진으로 얼굴을 더 만들 수 없습니다(무료 플랜은 맞춤 얼굴 불가). "
                   "'기본 얼굴'로 시연하거나, app.simli.com 에서 유료 플랜으로 올린 뒤 다시 시도하세요. "
                   f"(원문: {msg})")
        elif r.status_code in (401, 403):
            msg = f"Simli 키가 올바르지 않거나 권한이 없습니다 ({msg})."
        elif r.status_code == 402 or "credit" in msg.lower() or "balance" in msg.lower():
            msg = f"Simli 크레딧이 부족합니다 ({msg}). app.simli.com 에서 잔액을 확인하세요."
        raise AvatarError(r.status_code, msg)

    # ---------- 연결 확인 ----------

    def ping(self) -> dict:
        """키 유효성(얼굴 목록)과 세션 토큰 발급을 확인한다."""
        r = self.s.get(f"{self.BASE}/faces", timeout=15)
        self._raise(r)
        faces = r.json() if isinstance(r.json(), list) else []
        checks = {"faces_list": "ok", "session_token": "ok"}
        note = None
        try:
            self.session_token(self.PROBE_FACE, max_len=60, max_idle=10)
        except AvatarError as e:
            checks["session_token"] = "error"
            note = e.message
        return {"faces": len(faces), "checks": checks, "all_ok": checks["session_token"] == "ok", "note": note}

    # ---------- 얼굴 ----------

    def list_faces(self) -> list[str]:
        r = self.s.get(f"{self.BASE}/faces", timeout=15)
        self._raise(r)
        j = r.json()
        return [f.get("id") for f in j if isinstance(f, dict) and f.get("id")] if isinstance(j, list) else []

    def preprocess(self, image: bytes, filename: str = "photo.jpg") -> bytes:
        """구도 보정(머리 중앙, 위아래 여백 균등). 실패하면 원본을 그대로 쓴다."""
        r = self.s.post(f"{self.BASE}/faces/trinity/preprocess", files={"image": (filename, image)}, timeout=120)
        if not r.ok:
            log.warning("Simli preprocess failed (%s) → 원본 사용: %s", r.status_code, self._msg(r))
            return image
        return r.content

    def create_face(self, image: bytes, name: str, filename: str = "photo.jpg") -> str:
        """사진 1장 → Trinity 얼굴. 응답에 id가 없으면 얼굴 목록의 차이로 찾는다."""
        before = set(self.list_faces())
        fixed = self.preprocess(image, filename)
        r = self.s.post(f"{self.BASE}/faces/trinity", data={"face_name": name, "gsVersion": "GSA_1.0"},
                        files={"image": ("face.png", fixed, "image/png")}, timeout=300)
        self._raise(r)
        try:
            j = r.json()
        except ValueError:
            j = {}
        fid = None
        if isinstance(j, dict):
            fid = j.get("face_id") or j.get("faceId") or j.get("id") or (j.get("face") or {}).get("id") if j else None
        if not fid:
            new = [f for f in self.list_faces() if f not in before]
            fid = new[0] if new else None
        if not fid:
            raise AvatarError(502, "얼굴은 만들어졌지만 ID를 받지 못했습니다. app.simli.com 의 얼굴 목록에서 ID를 확인해 수동으로 넣어 주세요.")
        return fid

    def delete_face(self, face_id: str) -> None:
        r = self.s.delete(f"{self.BASE}/faces/{face_id}", timeout=15)
        if r.status_code not in (200, 204, 404):
            self._raise(r)

    # ---------- 세션 ----------

    def session_token(self, face_id: str, max_len: int = 900, max_idle: int = 120) -> str:
        r = self.s.post(f"{self.BASE}/compose/token", json={
            "faceId": face_id, "apiVersion": "v2", "handleSilence": True,
            "maxSessionLength": max_len, "maxIdleTime": max_idle, "audioInputFormat": "pcm16",
        }, timeout=20)
        self._raise(r)
        tok = r.json().get("session_token")
        if not tok or tok == "FAIL TOKEN":
            raise AvatarError(502, f"Simli 세션 토큰 발급 실패 ({self._msg(r)})")
        return tok

    def ice_servers(self) -> list[dict]:
        try:
            r = self.s.get(f"{self.BASE}/compose/ice", timeout=10)
            if r.ok and isinstance(r.json(), list) and r.json():
                return r.json()
        except requests.RequestException:
            pass
        return [{"urls": ["stun:stun.l.google.com:19302"]}]


class DIDAvatar:
    """D-ID 사진 아바타(Agents Streams V1). 실제 사진 그대로를 움직이므로 닮음이 가장 확실하다.
    문서(2026-09-19 확인): https://docs.d-id.com/reference/agent-create.md , /reference/agents-sdk-overview.md , /docs/api-keys.md
    - 인증: Authorization: Basic <API_USER:API_PASSWORD> (Studio가 보여 주는 키 그대로)
    - 사진 → POST /images → url → POST /agents(presenter.type=talk) → agent id
    - 대화: 세션마다 짧은 클라이언트 키(POST /agents/{id}/client-keys, 도메인 제한 없음·TTL) → 브라우저 SDK가 WebRTC 연결
    - 음성: 우리가 만든 mp3를 POST /audios 로 올려 audio_url 로 말하게 한다
    """
    name = "did"
    BASE = "https://api.d-id.com"
    SDK_URL = "https://cdn.jsdelivr.net/npm/@d-id/client-sdk@2.0.10/+esm"

    def __init__(self, api_key: str) -> None:
        self.key = api_key
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Basic {api_key}"
        self.s.headers["Accept"] = "application/json"

    @staticmethod
    def _msg(r: requests.Response) -> str:
        try:
            j = r.json()
            if isinstance(j, dict):
                return str(j.get("description") or j.get("message") or j.get("kind") or j)[:300]
            return str(j)[:300]
        except ValueError:
            return r.text[:300]

    def _raise(self, r: requests.Response) -> None:
        if r.ok:
            return
        msg = self._msg(r)
        log.warning("D-ID %s %s: %s %s", r.request.method, r.request.path_url, r.status_code, msg)
        if r.status_code == 401:
            msg = f"D-ID 키가 올바르지 않습니다 ({msg}). Studio → Account settings 에서 만든 키를 'API_USER:API_PASSWORD' 형태 그대로 넣어야 합니다."
        elif r.status_code == 402 or "credit" in msg.lower() or "insufficient" in msg.lower():
            msg = f"D-ID 크레딧이 부족합니다 ({msg}). studio.d-id.com 에서 잔여 크레딧을 확인하세요."
        elif r.status_code == 451 or "moderation" in msg.lower():
            msg = ("D-ID 자동 검열이 이 사진을 거부했습니다. 정면·단독·선명한 얼굴 사진으로 바꾸거나, D-ID 지원팀에 수동 심사를 요청해야 합니다. "
                   f"(원문: {msg})")
        elif r.status_code == 400 and "face" in msg.lower():
            msg = f"사진에서 얼굴을 찾지 못했습니다 ({msg}). 정면을 보는 선명한 사진을 올려 주세요."
        raise AvatarError(r.status_code, msg)

    # ---------- 연결 확인 ----------

    def ping(self) -> dict:
        r = self.s.get(f"{self.BASE}/agents", params={"limit": 1}, timeout=15)
        self._raise(r)
        checks = {"agents_list": "ok", "credits": "unknown"}
        credits = None
        try:
            c = self.s.get(f"{self.BASE}/credits", timeout=15)
            if c.ok:
                j = c.json()
                credits = j.get("remaining", j.get("total"))
                checks["credits"] = "ok"
        except requests.RequestException:
            pass
        return {"checks": checks, "all_ok": True, "credits": credits, "note": None if credits is None else f"남은 크레딧 {credits}"}

    # ---------- 얼굴(에이전트) ----------

    def upload_image(self, image: bytes, filename: str = "photo.jpg") -> str:
        mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        r = self.s.post(f"{self.BASE}/images", files={"image": (filename, image, mime)}, timeout=120)
        self._raise(r)
        return r.json()["url"]

    def upload_audio(self, audio: bytes, filename: str = "speech.mp3") -> str:
        r = self.s.post(f"{self.BASE}/audios", files={"audio": (filename, audio, "audio/mpeg")}, timeout=120)
        self._raise(r)
        return r.json()["url"]

    def create_face(self, image: bytes, name: str, filename: str = "photo.jpg") -> str:
        """사진 → 이미지 업로드 → 사진 아바타 에이전트. 반환값은 agent id."""
        url = self.upload_image(image, filename)
        body = {
            "presenter": {"type": "talk", "source_url": url, "thumbnail": url,
                          "voice": {"type": "microsoft", "voice_id": "ko-KR-SunHiNeural"}},   # 텍스트로 말할 일은 없지만 필수 항목
            "preview_name": name[:50],
        }
        r = self.s.post(f"{self.BASE}/agents", json=body, timeout=120)
        self._raise(r)
        j = r.json()
        aid = j.get("id")
        if not aid:
            raise AvatarError(502, f"D-ID 에이전트 ID를 받지 못했습니다 ({self._msg(r)})")
        return aid

    def delete_face(self, agent_id: str) -> None:
        r = self.s.delete(f"{self.BASE}/agents/{agent_id}", timeout=15)
        if r.status_code not in (200, 202, 204, 404):
            self._raise(r)

    # ---------- 세션 ----------

    def client_key(self, agent_id: str, ttl: int = 3600) -> str:
        """도메인 제한 없는 짧은 클라이언트 키(브라우저용). API 키는 서버에만 남는다."""
        r = self.s.post(f"{self.BASE}/agents/{agent_id}/client-keys", json={"allowed_domains": [], "ttl_seconds": max(60, min(ttl, 86400))}, timeout=20)
        self._raise(r)
        return r.json()["client_key"]
