"""온라인 공개 시연(PUBLIC_DEMO=1, 2026-10-13).

누구나 /demo 에서 시드로 만든 시연 가족(가상 인물)으로 들어와 원격 참배·추도식·추모 대화를 써 볼 수 있게 한다.
여러 방문객이 같은 시연 가족을 함께 쓰므로 다음은 막는다.
- 사진·음원·목소리·얼굴 올리기와 지우기(저장 공간·초상 문제), 초대·권한·작별 절차·인공지능 가족 합의 바꾸기(다른 방문객의 시연을 망가뜨림)
- 비용이 드는 외부 인공지능: 대화는 규칙 기반 시연 대화(MockLLM), 복제 음성·실시간 아바타는 쓰지 않는다
관리자 주소·키는 어디에도 내보내지 않는다. 실제 계약 가족(시드가 아닌 가족)은 이 규칙과 무관하게 평소대로 동작한다.
"""
import re

from fastapi import HTTPException, Request

from . import config, db, ratelimit

# 시연 가족이 쓸 수 없는 바꾸기 요청(GET 은 모두 허용)
_BLOCKED = re.compile(
    r"^/api/family/(invite|farewell|voice/|avatar/|music(/\d+)?$|ai-consensus|access/|memories|guides/|events/\d+$)"
)
BLOCK_MESSAGE = "공개 시연에서는 이 기능을 막아 두었습니다. 실제 서비스에서는 계약하신 가족이 사용할 수 있습니다."


def demo_contract_ids() -> set[int]:
    """시드(server/seed.py)가 만든 시연 계약. 시드 고인 사진은 늘 photos/seed_<계약번호>.jpg 로 저장된다."""
    return {r["contract_id"] for r in db.rows("SELECT DISTINCT contract_id FROM deceased WHERE photo_path LIKE 'photos/seed_%'")}


def is_public(member: dict) -> bool:
    return config.PUBLIC_DEMO and member["contract_id"] in demo_contract_ids()


def guard(request: Request, member: dict) -> None:
    """require_member 에서 부른다. 공개 시연 가족의 위험한 바꾸기를 막고, 쓰기 요청은 접속 주소별로 넉넉히 제한한다."""
    if request.method == "GET" or not is_public(member):
        return
    if _BLOCKED.match(request.url.path) and request.url.path != "/api/family/music/visit":
        raise HTTPException(403, BLOCK_MESSAGE)
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")
    ratelimit.hit(f"public-write:{ip}", 120, 3600, "공개 시연에서는 한 시간에 120번까지 남길 수 있습니다. 잠시 뒤 다시 해 주세요.")


def launcher_members() -> list[dict]:
    """공개 시작 화면에 보일 시연 가족(관리자 정보 없음)."""
    ids = demo_contract_ids()
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return db.rows(
        f"""SELECT m.id, m.name, m.relation, m.role, m.invite_token, c.holder_name, c.plan, n.code AS niche_code,
                  (SELECT GROUP_CONCAT(d.name, ', ') FROM deceased d WHERE d.contract_id=c.id) AS deceased_names
           FROM family_members m JOIN contracts c ON c.id=m.contract_id LEFT JOIN niches n ON n.id=c.niche_id
           WHERE c.id IN ({marks}) AND m.revoked_at IS NULL AND m.is_minor=0 ORDER BY m.id""", tuple(ids))
