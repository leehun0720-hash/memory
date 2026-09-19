"""설정에 따라 공급자를 고른다. 관리자 콘솔(DB 설정)이 .env보다 우선하고, 키가 없으면 Mock으로 조용히 내려간다."""
import logging
import os

from .. import config, db
from .llm_mock import MockLLM
from .tts import BrowserTTS

log = logging.getLogger(__name__)
_llm = None
_llm_sig: tuple | None = None
_tts = None


def effective() -> dict:
    """지금 적용될 설정. DB(관리자 콘솔) → 환경변수 순."""
    return {
        "api_key": db.get_setting("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_AUTH_TOKEN", ""),
        "provider": (db.get_setting("llm_provider") or config.LLM_PROVIDER or "auto").lower(),
        "model": db.get_setting("llm_model") or config.LLM_MODEL,
    }


def build_llm(api_key: str, provider: str, model: str):
    if provider == "anthropic" or (provider == "auto" and api_key):
        try:
            from .llm_anthropic import AnthropicLLM
            return AnthropicLLM(model, api_key=api_key or None)
        except Exception as e:  # SDK 미설치 등
            log.warning("Anthropic 공급자 초기화 실패(%s) → Mock 사용", e)
    return MockLLM()


def llm():
    global _llm, _llm_sig
    e = effective()
    sig = (e["api_key"], e["provider"], e["model"])
    if _llm is None or sig != _llm_sig:
        _llm = build_llm(*sig)
        _llm_sig = sig
        log.info("LLM provider: %s (%s)", _llm.name, e["model"] if _llm.name == "anthropic" else "-")
    return _llm


def reset() -> None:
    global _llm, _llm_sig
    _llm, _llm_sig = None, None


def effective_tts() -> dict:
    """음성 합성 설정. 관리자 콘솔(DB) → 환경변수 순."""
    return {
        "api_key": db.get_setting("elevenlabs_api_key") or os.getenv("ELEVENLABS_API_KEY", ""),
        "provider": (db.get_setting("tts_provider") or config.TTS_PROVIDER or "auto").lower(),   # auto | elevenlabs | browser
        "model": db.get_setting("tts_model") or "eleven_multilingual_v2",
    }


_tts_sig: tuple | None = None


def tts():
    """복제 음성 공급자. 키가 있고(provider auto/elevenlabs) 고인에게 voice_id가 있을 때만 실제로 쓰인다."""
    global _tts, _tts_sig
    e = effective_tts()
    sig = (e["api_key"], e["provider"], e["model"])
    if _tts is None or sig != _tts_sig:
        if e["api_key"] and e["provider"] in ("auto", "elevenlabs"):
            from .tts import ElevenLabsTTS
            _tts = ElevenLabsTTS(e["api_key"], e["model"])
        else:
            _tts = BrowserTTS()
        _tts_sig = sig
        log.info("TTS provider: %s", _tts.name)
    return _tts


def reset_tts() -> None:
    global _tts, _tts_sig
    _tts, _tts_sig = None, None
