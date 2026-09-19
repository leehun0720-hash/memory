"""음성 합성 공급자.
- BrowserTTS: 서버는 아무것도 만들지 않고 클라이언트가 window.speechSynthesis로 읽는다(0원, 기본).
- ElevenLabsTTS: 고인 음성 복제(Instant Voice Clone). 관리자 콘솔에 키를 넣고, 고인별로 음성 샘플을 등록하면 켜진다.
  약관상 '본인 동의'가 전제이므로(계획서 4장) 시연은 생전 기록 자원자(본인 목소리)로 하고, 고인 적용은 법률 자문 뒤에 한다.
"""
import logging

import requests

from .base import TTSResult

log = logging.getLogger(__name__)


class TTSError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class BrowserTTS:
    name = "browser"

    def synthesize(self, text: str, voice_id: str | None) -> TTSResult:
        return TTSResult(audio=None)


class ElevenLabsTTS:
    name = "elevenlabs"
    BASE = "https://api.elevenlabs.io"
    MODELS = ["eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_v3"]

    def __init__(self, api_key: str, model: str = "eleven_multilingual_v2") -> None:
        self.key = api_key
        self.model = model if model in self.MODELS else self.MODELS[0]
        self.s = requests.Session()
        self.s.headers["xi-api-key"] = api_key

    # 우리가 쓰는 엔드포인트와 필요한 키 권한(ElevenLabs 키 제한 화면 기준)
    PERMISSIONS = "텍스트 음성 변환=접근, 음성(Voices)=쓰기, 사용자(User)=읽기"

    def _raise(self, r: requests.Response) -> None:
        if r.ok:
            return
        status, msg = "", ""
        try:
            detail = r.json().get("detail")
            if isinstance(detail, dict):
                status, msg = str(detail.get("status", "")), str(detail.get("message", ""))
            else:
                msg = str(detail)
        except ValueError:
            msg = r.text[:200]
        log.warning("ElevenLabs %s %s: %s %s", r.request.method, r.request.path_url, r.status_code, msg)
        if status == "missing_permissions" or "permission" in msg.lower():
            msg = f"키에 권한이 부족합니다 ({msg}). ElevenLabs 키 설정에서 {self.PERMISSIONS} 를 켜 주세요."
        elif r.status_code == 401:
            msg = f"ElevenLabs 키가 올바르지 않습니다 ({status or msg or '인증 실패'})."
        elif r.status_code == 402 or status in ("quota_exceeded", "voice_limit_reached") or "quota" in msg.lower():
            msg = f"ElevenLabs 크레딧·한도가 부족합니다 ({msg}). 요금제를 확인하세요."
        raise TTSError(r.status_code, msg or f"ElevenLabs 오류 {r.status_code}")

    def ping(self) -> dict:
        """연결 확인. 사용자 읽기 권한이 없으면 음성 목록으로 대신 확인한다."""
        r = self.s.get(f"{self.BASE}/v1/user/subscription", timeout=15)
        if r.ok:
            j = r.json()
            return {"tier": j.get("tier"), "used": j.get("character_count"), "limit": j.get("character_limit"),
                    "can_clone": bool(j.get("can_use_instant_voice_cloning", True))}
        try:
            self._raise(r)
        except TTSError as first:
            if "권한" not in first.message:
                raise
            r2 = self.s.get(f"{self.BASE}/v1/voices", params={"page_size": 1}, timeout=15)
            if r2.ok:
                return {"tier": None, "used": None, "limit": None, "can_clone": True,
                        "note": "키는 통하지만 '사용자 읽기' 권한이 없어 요금제·크레딧은 표시하지 못합니다."}
            self._raise(r2)
            raise first

    def synthesize(self, text: str, voice_id: str | None) -> TTSResult:
        if not voice_id:
            return TTSResult(audio=None)
        body = {"text": text, "model_id": self.model,
                "voice_settings": {"stability": 0.55, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True}}
        if "v2_5" in self.model or "flash" in self.model or "turbo" in self.model:
            body["language_code"] = "ko"     # multilingual_v2는 이 필드를 받지 않는다
        r = self.s.post(f"{self.BASE}/v1/text-to-speech/{voice_id}", params={"output_format": "mp3_44100_64"},
                        json=body, timeout=40)
        self._raise(r)
        return TTSResult(audio=r.content, mime="audio/mpeg")

    def add_voice(self, name: str, files: list[tuple[str, bytes, str]], description: str = "") -> str:
        """Instant Voice Clone 등록. files: (파일명, 바이트, MIME). 1~2분 깨끗한 음성이면 충분하다."""
        r = self.s.post(f"{self.BASE}/v1/voices/add",
                        data={"name": name, "description": description or "memorial voice (family consent on file)",
                              "remove_background_noise": "false", "labels": '{"language": "ko", "use_case": "memorial"}'},
                        files=[("files", f) for f in files], timeout=120)
        self._raise(r)
        return r.json()["voice_id"]

    def delete_voice(self, voice_id: str) -> None:
        r = self.s.delete(f"{self.BASE}/v1/voices/{voice_id}", timeout=15)
        if r.status_code not in (200, 404):
            self._raise(r)


# 파일럿에서 추가할 자리:
# class SupertoneTTS: ...    # 국내 음성(수퍼톤) — 고인 음성 적용 가능 여부 서면 확인 필요. 같은 인터페이스로 구현.
