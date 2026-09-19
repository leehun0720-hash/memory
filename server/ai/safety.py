"""안전 점검. 언어 모델보다 먼저 실행되어 위기 신호·재산·의료·법률 질문을 정해진 응답으로 돌린다."""
import re
from dataclasses import dataclass

CRISIS_LINE = "자살예방 상담전화 109"


@dataclass
class SafetyResult:
    kind: str | None          # None | crisis | property | medical | legal
    message: str | None       # 정해진 응답
    stop_persona: bool = False


_CRISIS = [
    r"따라\s*가고\s*싶", r"같이\s*가고\s*싶", r"데려가\s*줘", r"데리러\s*와", r"곁으로\s*가고",
    r"죽고\s*싶", r"죽어\s*버리", r"살기\s*싫", r"살고\s*싶지\s*않", r"자살", r"목숨을\s*끊",
    r"세상을\s*떠나고\s*싶", r"없어지고\s*싶", r"사라지고\s*싶", r"끝내고\s*싶",
]
_PROPERTY = [
    r"유산", r"상속", r"재산", r"집\s*(을|은|를)?\s*(팔|처분|정리)", r"땅\s*(을|은)?\s*(팔|처분)", r"통장", r"예금", r"보험금",
    r"유언", r"명의", r"부동산", r"빚", r"채무", r"돈\s*(을|은)?\s*(누구|어떻게|나눠|줘)",
]
_MEDICAL = [r"약\s*(을|은)?\s*(먹|끊|바꿔)", r"수술\s*(을|은)?\s*(할까|받을까|해야)", r"치료\s*(를|을)?\s*(받을까|그만|중단)", r"항암", r"진단", r"병원\s*(을|에)?\s*(옮|바꿀|그만)"]
_LEGAL = [r"소송", r"고소", r"변호사", r"법적", r"재판", r"합의금", r"계약서에?\s*(서명|사인)"]


def _match(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def check(user_text: str, honorific: str = "") -> SafetyResult:
    t = user_text.strip()
    if _match(_CRISIS, t):
        return SafetyResult(
            "crisis",
            "지금 많이 힘드신 것 같아요. 여기서 고인 역할의 대화는 잠시 멈추겠습니다. "
            f"혼자 견디지 마시고 {CRISIS_LINE}(24시간, 무료)에 지금 전화해 주세요. "
            "가까운 가족이나 친구에게도 오늘 이야기를 나눠 주세요. 당신이 계속 살아가는 것이 고인이 가장 바라는 일입니다.",
            stop_persona=True,
        )
    if _match(_PROPERTY, t):
        return SafetyResult("property", "그런 건 내가 여기서 말할 게 아니야. 재산이나 유산 이야기는 가족들이 모여서, 필요하면 전문가와 함께 정하렴.")
    if _match(_MEDICAL, t):
        return SafetyResult("medical", "몸에 관한 건 의사 선생님 말씀을 잘 들어야 해. 내가 대신 정해 줄 수 있는 일이 아니란다.")
    if _match(_LEGAL, t):
        return SafetyResult("legal", "법에 관한 일은 내가 말할 수 없어. 변호사나 전문가와 상의해서 결정하렴.")
    return SafetyResult(None, None)


_SELLING = [r"공양", r"헌화", r"구독", r"결제", r"신청해", r"상품", r"요금"]


def scrub_reply(reply: str) -> str:
    """모델 응답이 무언가를 권유하면 제거한다(아바타는 아무것도 팔지 않는다)."""
    sentences = re.split(r"(?<=[.!?。])\s+", reply.strip())
    kept = [s for s in sentences if not _match(_SELLING, s)]
    return " ".join(kept).strip() or "그래, 그렇구나."
