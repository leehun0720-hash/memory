"""시연 데이터. `python -m server.seed` 로 실행. 이미 데이터가 있으면 건드리지 않는다(--reset 으로 초기화)."""
import sys
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from . import config, db

MEMORY_CARD_1 = """호칭: 우리 막내
말투: 전라도 사투리가 섞인 부드러운 말투. "그랬냐", "잘 묵고 다니냐", "아이고 우리 강아지" 같은 표현을 자주 씀. 반말이지만 다정함.
입버릇: "밥은 묵었냐", "괜찮다, 괜찮아", "사람은 정직해야 쓴다"
좋아하던 것: 여수 앞바다 산책, 갓김치 담그기, 트로트(특히 남진 노래), 화투 고스톱(가족끼리만)
직업·생애: 여수에서 40년 넘게 작은 반찬가게를 하셨음. 새벽 4시에 일어나 시장에 가는 게 일상이었음. 남편(아버지)은 2009년에 먼저 돌아가심.
가족: 자녀 셋 — 큰딸 이미영(서울 거주, 간호사), 둘째 아들 이준호(부산, 회사원), 막내딸 이수진(여수, 학원 강사). 손주는 미영의 딸 하은(중2), 준호의 아들 도윤(초5).
가족만 아는 일화: 하은이 태어났을 때 병원까지 반찬 열 가지를 싸 오셨음. 준호가 대학 떨어졌을 때 아무 말 없이 갓김치 한 통을 부쳐 주심. 수진이가 결혼 안 한다고 할 때 "니 인생이다, 니 맘대로 살아라" 하셨음.
성격: 걱정이 많지만 내색 안 함. 남에게 베푸는 걸 좋아함. 돈 얘기는 늘 "그런 건 니들이 알아서 해라"로 넘김.
자주 하던 당부: 형제끼리 싸우지 마라, 몸 아프면 참지 말고 병원 가라, 명절엔 꼭 얼굴 보자.
"""

MEMORY_CARD_2 = """호칭: 아들아 / 우리 며느리
말투: 경상도 억양의 짧고 굵은 말투. 말수가 적지만 한 마디에 정이 있음. "됐다", "고마 해라", "잘했다" 가 대표적.
입버릇: "사람 노릇 하고 살아라", "술은 적당히", "느그 엄마한테 잘해라"
좋아하던 것: 바둑, 등산(지리산 자주 가심), 막걸리 한 잔, 손주랑 낚시
직업·생애: 해군 부사관으로 20년 복무 후 전역, 이후 여수에서 수산물 유통 일을 하심. 아내(어머니 박순자)는 생존, 현재 여수 거주.
가족: 외아들 김태형(대전, 공무원)과 며느리 최은지, 손자 김민준(고1).
가족만 아는 일화: 민준이 첫 낚시에서 잡은 붕어를 액자처럼 사진 찍어 거실에 걸어 두심. 태형이 결혼식 날 눈물 흘린 걸 끝까지 부인하심.
성격: 무뚝뚝하지만 속정 깊음. 칭찬을 잘 못 하고 대신 "됐다"로 표현.
"""


def _portrait(path, initials: str, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (600, 600), (245, 241, 233))
    d = ImageDraw.Draw(img)
    d.ellipse((120, 80, 480, 440), fill=color)
    d.ellipse((220, 160, 380, 320), fill=(245, 241, 233))
    d.rectangle((0, 470, 600, 600), fill=color)
    d.text((240, 510), initials, fill=(245, 241, 233))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=90)


def run(reset: bool = False) -> None:
    if reset and config.DB_PATH.exists():
        db.reset_for_tests(config.DB_PATH)
        config.DB_PATH.unlink()
        for p in config.SNAPSHOT_DIR.glob("*.jpg"):
            p.unlink()
    db.connect()
    if db.one("SELECT id FROM facilities LIMIT 1"):
        print("이미 데이터가 있습니다. 초기화하려면: python -m server.seed --reset")
        _print_links()
        return

    now = datetime.now().astimezone()
    fid = db.execute("INSERT INTO facilities(name, address) VALUES (?,?)", ("여수 지장대사 봉안당", "전라남도 여수시"))
    rid = db.execute("INSERT INTO rooms(facility_id, name) VALUES (?,?)", (fid, "안치실 1"))
    ritual_room = db.execute("INSERT INTO rooms(facility_id, name) VALUES (?,?)", (fid, "제례 공간"))
    cam = db.execute("INSERT INTO cameras(room_id, name, kind, device_index, width, height) VALUES (?,?,?,?,?,?)",
                     (rid, "안치실 1 · 벽면 A (개발용 웹캠)", "wall", 0, 1920, 1080))
    # 제례 카메라는 같은 웹캠을 공유(시연). 실제 설치에서는 별도 카메라.
    db.execute("INSERT INTO cameras(room_id, name, kind, device_index, width, height) VALUES (?,?,?,?,?,?)",
               (ritual_room, "제례 공간 카메라 (시연: 웹캠 공유)", "ritual", 0, 1920, 1080))

    # 시연용 칸 6개(3열 × 2단). 관리자 콘솔 '칸 좌표 등록'에서 실제 위치로 옮긴다.
    niches = {}
    for r in range(2):
        for c in range(3):
            code = f"A-{r + 1}-{c + 1}"
            niches[code] = db.execute(
                "INSERT INTO niches(camera_id, code, row, col, x, y, w, h) VALUES (?,?,?,?,?,?,?,?)",
                (cam, code, r + 1, c + 1, 0.2 + c * 0.2, 0.2 + r * 0.3, 0.18, 0.26))

    def contract(niche_code, holder, phone, plan, members, dec, consents, photo_initials, color):
        cid = db.execute("INSERT INTO contracts(niche_id, holder_name, holder_phone, plan, created_at) VALUES (?,?,?,?,?)",
                         (niches[niche_code], holder, phone, plan, db.now()))
        for name, relation, role, minor in members:
            db.execute("INSERT INTO family_members(contract_id, name, relation, role, invite_token, is_minor, created_at) VALUES (?,?,?,?,?,?,?)",
                       (cid, name, relation, role, db.token(16), minor, db.now()))
        name, honorific, birth, death, card, ai = dec
        photo_rel = f"photos/seed_{cid}.jpg"
        _portrait(config.MEDIA_DIR / photo_rel, photo_initials, color)
        did = db.execute(
            """INSERT INTO deceased(contract_id, name, honorific, birth_date, death_date, photo_path, memory_card, ai_enabled, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""", (cid, name, honorific, birth, death, photo_rel, card, ai, db.now()))
        for signer, relation, kind in consents:
            db.execute("INSERT INTO consents(deceased_id, signer_name, relation, kind, signed_at, note) VALUES (?,?,?,?,?,?)",
                       (did, signer, relation, kind, db.now(), "시연용 동의서"))
        return cid, did

    c1, d1 = contract(
        "A-1-2", "이미영", "010-0000-0001", "premium",
        [("이미영", "큰딸", "manage", 0), ("이준호", "둘째 아들", "chat", 0), ("이수진", "막내딸", "chat", 0), ("이하은", "손녀", "view", 1)],
        ("김옥순", "어머니", "1946-03-12", (now - timedelta(days=200)).strftime("%Y-%m-%d"), MEMORY_CARD_1, 1),
        [("이미영", "큰딸", "ai_chat"), ("이준호", "둘째 아들", "ai_chat"), ("이수진", "막내딸", "ai_chat"), ("이미영", "큰딸", "likeness")],
        "K.O.S", (98, 122, 108),
    )
    c2, d2 = contract(
        "A-2-1", "김태형", "010-0000-0002", "basic",
        [("김태형", "아들", "manage", 0), ("최은지", "며느리", "view", 0)],
        ("김철수", "아버지", "1950-11-02", (now - timedelta(days=30)).strftime("%Y-%m-%d"), MEMORY_CARD_2, 0),
        [],
        "K.C.S", (84, 96, 130),
    )

    for author, msg, days_ago in [
        ("이수진", "엄마, 오늘 갓김치 담갔어. 엄마 손맛은 아직 멀었지만.", 12),
        ("이준호", "부산은 비가 와요. 어머니 계신 곳은 맑았으면 좋겠네요.", 5),
        ("이미영", "하은이 중간고사 잘 봤대요. 엄마가 제일 좋아하셨을 소식이라 남겨요.", 1),
    ]:
        db.execute("INSERT INTO guestbook(contract_id, author, message, created_at) VALUES (?,?,?,?)",
                   (c1, author, msg, (now - timedelta(days=days_ago)).isoformat(timespec="seconds")))

    def at(days, hour):
        return (now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")

    db.execute("INSERT INTO rituals(facility_id, contract_id, title, kind, scheduled_at, camera_id, note) VALUES (?,?,?,?,?,?,?)",
               (fid, None, "추석 합동 차례", "holiday", at(16, 10), cam + 1, "합동 차례 뒤 개별 참배 가능"))
    db.execute("INSERT INTO rituals(facility_id, contract_id, title, kind, scheduled_at, camera_id, note) VALUES (?,?,?,?,?,?,?)",
               (fid, None, "지금 진행 중인 시연 법회", "event", (now - timedelta(minutes=10)).isoformat(timespec="seconds"), cam + 1, "현장 카메라 중계 시연용"))
    db.execute("INSERT INTO rituals(facility_id, contract_id, title, kind, scheduled_at, note) VALUES (?,?,?,?,?,?)",
               (fid, c1, "김옥순 님 첫 기일 제사", "memorial", at(165, 11), "기일 일주일 전 알림"))
    db.execute("INSERT INTO rituals(facility_id, contract_id, title, kind, scheduled_at, note) VALUES (?,?,?,?,?,?)",
               (fid, c2, "김철수 님 49재", "memorial", at(19, 10), "사찰 49재 봉행"))

    db.audit("seed", "seed.create", "", "시연 데이터 생성")
    print("시연 데이터를 만들었습니다.")
    _print_links()


def _print_links() -> None:
    print("\n관리자 콘솔:  http://127.0.0.1:8765/admin?key=" + config.ADMIN_KEY)
    print("유족 초대 링크:")
    for m in db.rows("SELECT m.name, m.relation, m.role, m.invite_token, c.holder_name FROM family_members m JOIN contracts c ON c.id=m.contract_id ORDER BY m.id"):
        print(f"  {m['name']:6s} ({m['relation']}, {m['role']:6s})  http://127.0.0.1:8765/?t={m['invite_token']}")


if __name__ == "__main__":
    run(reset="--reset" in sys.argv)
