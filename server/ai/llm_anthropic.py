"""Anthropic Claude 공급자. 대화는 짧고 빠르게(낮은 effort), 요약은 별도 호출."""
import logging

import anthropic

from .base import Persona, Turn
from .llm_mock import MockLLM
from .prompt import SUMMARY_TEMPLATE, build_system

log = logging.getLogger(__name__)


def is_credit_error(e: anthropic.APIStatusError) -> bool:
    return "credit balance" in (e.message or "").lower()


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, model: str = "claude-opus-5", api_key: str | None = None) -> None:
        self.model = model
        # api_key=None이면 SDK가 환경변수·프로필에서 찾는다.
        self.client = anthropic.Anthropic(api_key=api_key, timeout=30.0, max_retries=1)

    def ping(self) -> str:
        """키·모델이 실제로 통하는지 아주 짧은 호출로 확인한다. 실패하면 예외."""
        r = self.client.messages.create(model=self.model, max_tokens=16, messages=[{"role": "user", "content": "안녕"}])
        return "".join(b.text for b in r.content if b.type == "text")[:40]

    def _create(self, system: str, messages: list[dict], max_tokens: int, effort: str):
        # 정책상 거절(refusal)이 나면 서버가 자동으로 다른 모델로 이어서 답하도록 fallbacks를 켠다.
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

    @staticmethod
    def _text(response) -> str:
        if response.stop_reason == "refusal":
            return "미안하구나, 그 이야기는 여기서 하기 어렵겠다. 다른 이야기 해 볼까?"
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def reply(self, persona: Persona, history: list[Turn], user_text: str) -> str:
        messages = [{"role": h.role, "content": h.text} for h in history[-20:]]
        messages.append({"role": "user", "content": user_text})
        try:
            r = self._create(build_system(persona), messages, max_tokens=300, effort="low")
            return self._text(r) or "응, 듣고 있어."
        except anthropic.RateLimitError:
            return "잠깐만, 숨 좀 고르고. 조금 있다가 다시 말해 줄래?"
        except anthropic.BadRequestError as e:
            if is_credit_error(e):
                # 계정 크레딧 부족: 시연이 끊기지 않도록 이번 답만 규칙 기반으로 대신한다.
                log.warning("Anthropic 크레딧 부족 → Mock 응답으로 대체")
                return MockLLM().reply(persona, history, user_text)
            log.warning("anthropic bad request: %s", e.message)
            return "지금은 말이 잘 안 나오네. 잠시 뒤에 다시 이야기하자."
        except anthropic.APIStatusError as e:
            log.warning("anthropic status error %s: %s", e.status_code, e.message)
            return "지금은 말이 잘 안 나오네. 잠시 뒤에 다시 이야기하자."
        except anthropic.APIConnectionError:
            return "연결이 잠깐 끊긴 것 같아. 조금 있다 다시 이야기하자."

    def summarize(self, persona: Persona, history: list[Turn]) -> str:
        if not history:
            return ""
        transcript = "\n".join(f"{'가족' if h.role == 'user' else persona.name}: {h.text}" for h in history)
        try:
            r = self._create("당신은 추모 대화 기록을 정리하는 조력자입니다.", [{"role": "user", "content": SUMMARY_TEMPLATE.format(transcript=transcript)}], max_tokens=400, effort="low")
            return self._text(r)
        except anthropic.APIError as e:
            log.warning("summary failed: %s", e)
            return f"{len([h for h in history if h.role == 'user'])}번의 대화를 나누었습니다."
