"""API 키가 없을 때 쓰는 규칙 기반 대화. 시연 흐름(고지 → 듣기 → 안전 점검 → 응답 → 마무리)을 그대로 보여 준다."""
import random
import re

from .base import Persona, Turn


class MockLLM:
    name = "mock"

    _RULES = [
        (r"(잘\s*지내|안녕|괜찮|건강)", ["나야 늘 편안하지. 너는 밥은 잘 챙겨 먹고 다니니?", "여기는 조용하고 좋아. 너희만 건강하면 나는 걱정이 없다."]),
        (r"(보고\s*싶|그리워|생각나)", ["나도 네 생각 많이 한다. 그래도 너무 오래 슬퍼하지는 말고.", "보고 싶다는 말 들으니 고맙구나. 나는 늘 네 곁에 있어."]),
        (r"(힘들|지쳐|우울|외로)", ["많이 힘들었구나. 오늘은 푹 쉬어. 내일은 조금 나아질 거야.", "그럴 땐 잠깐 쉬어도 돼. 네가 잘하고 있는 거 나는 다 안다."]),
        (r"(밥|식사|먹)", ["끼니 거르지 마라. 뭐든 따뜻하게 먹고 다녀.", "밥은 꼭 챙겨 먹어야 해. 그게 제일 중요하다."]),
        (r"(고마|감사)", ["고맙긴. 이렇게 와 준 게 나는 제일 고맙지.", "내가 더 고맙다. 잘 커 줘서."]),
        (r"(기억|옛날|그때|어릴)", ["그때 생각하면 나도 웃음이 나. 좋은 시절이었지.", "그 얘기 기억하는구나. 나도 잊은 적이 없다."]),
        (r"(가족|형|누나|동생|언니|오빠|엄마|아빠|아버지|어머니)", ["가족들끼리 서로 잘 챙겨. 그게 내 바람이야.", "다들 잘 지내지? 서로 의지하면서 살아라."]),
        (r"\?$|(뭐|왜|어떻|언제|어디)", ["글쎄, 그건 내가 잘 기억이 안 나네. 네가 더 잘 알 거야.", "그건 잘 모르겠구나. 그래도 네 마음은 알겠다."]),
    ]
    _DEFAULT = ["그래, 그렇구나. 더 얘기해 봐.", "응, 듣고 있어. 천천히 말해도 돼.", "그랬구나. 네 얘기 들으니 좋다."]

    def reply(self, persona: Persona, history: list[Turn], user_text: str) -> str:
        t = user_text.strip()
        for pattern, answers in self._RULES:
            if re.search(pattern, t):
                text = random.choice(answers)
                break
        else:
            text = random.choice(self._DEFAULT)
        # 기억 카드에 호칭이 있으면 살짝 섞어 준다
        m = re.search(r"(?:호칭|부르던 말)\s*[:：]\s*([^\n,]+)", persona.memory_card)
        if m and random.random() < 0.5:
            text = f"{m.group(1).strip()}, {text}"
        return text

    def summarize(self, persona: Persona, history: list[Turn]) -> str:
        user_lines = [h.text for h in history if h.role == "user"]
        n = len(user_lines)
        first = user_lines[0][:40] if user_lines else ""
        return f"{persona.member_name or '가족'}이(가) {persona.name}님과 {n}번 말을 주고받았습니다. " + (f"'{first}'로 시작해 안부와 근황을 나누었습니다." if first else "")
