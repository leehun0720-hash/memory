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
