"""AI 공급자 인터페이스. 언어 모델·음성 합성을 각각 갈아 끼울 수 있게 분리한다(계획서 5장)."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Turn:
    role: str      # user | assistant
    text: str


@dataclass
class Persona:
    name: str
    honorific: str
    memory_card: str
    birth_date: str = ""
    death_date: str = ""
    member_name: str = ""
    member_relation: str = ""
    occasion: str = ""      # 기일 · 명절 · 생신 등


class LLMProvider(Protocol):
    name: str

    def reply(self, persona: Persona, history: list[Turn], user_text: str) -> str: ...

    def summarize(self, persona: Persona, history: list[Turn]) -> str: ...


@dataclass
class TTSResult:
    audio: bytes | None      # None이면 브라우저 음성 합성 사용
    mime: str = "audio/mpeg"


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, voice_id: str | None) -> TTSResult: ...
