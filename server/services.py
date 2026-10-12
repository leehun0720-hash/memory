"""추모 서비스(유료) 주문 (2026-10-12): 봉안함 헌화 · 선물하기 · 제사 상차림 · 기도.

가격은 시연용 예시이며 결제도 시연 결제다(카드 번호 등 결제 정보를 받지 않고, 돈이 오가지 않는다).
흐름: 가족이 고르고 주문(시연 결제 → paid) → 직원이 '준비 중'(preparing) → '완료'(done, 완료 사진) / 취소·환불(refunded).
헌화가 완료되면 온라인 추모 제단에도 흰 국화가 놓인다(주문한 가족 이름으로).
"""
from __future__ import annotations

import random
import secrets
from datetime import datetime

from fastapi import HTTPException

from . import db

# 이름, 분류, 설명, 단가(원), 단위, 의례 선택 필요(ritual), 날짜 선택(date), 선물 가능(gift), 편지 칸(letter), 수량 최대
CATALOG: dict[str, dict] = {
    "flower-one": dict(category="flower", name="봉안함 생화 헌화 · 국화 한 송이", price=10000, unit="송이", max_qty=10,
                       desc="직원이 봉안함 앞에 생화 국화를 놓고 사진을 보내 드립니다.", date=True, gift=True),
    "flower-bouquet": dict(category="flower", name="생화 꽃다발 헌화", price=35000, unit="다발", max_qty=3,
                           desc="계절 꽃으로 만든 작은 꽃다발을 봉안함 앞에 올립니다. 메시지 카드를 함께 놓습니다.", date=True, gift=True),
    "flower-monthly": dict(category="flower", name="매달 헌화 정기 · 3개월", price=75000, unit="회", max_qty=1,
                           desc="석 달 동안 매달 정한 날에 생화를 올리고 사진을 보내 드립니다.", date=True, gift=True),
    "gift-frame": dict(category="gift", name="추억 사진 액자 놓아 드리기", price=45000, unit="개", max_qty=2,
                       desc="가족 앨범의 사진 한 장을 작은 액자로 만들어 봉안함 곁에 놓습니다(시설 규정 크기).", gift=True),
    "gift-plant": dict(category="gift", name="사계절 작은 화분(조화)", price=25000, unit="개", max_qty=2,
                       desc="시들지 않는 작은 화분을 봉안함 앞에 놓습니다.", gift=True),
    "gift-letter": dict(category="gift", name="손편지 인쇄 · 봉안함 앞 놓기", price=8000, unit="장", max_qty=5,
                        desc="적어 주신 편지를 한지에 인쇄해 봉안함 앞에 놓고 사진을 보내 드립니다.", gift=True, letter=True),
    "table-simple": dict(category="table", name="간소 상차림 · 과일·떡·술", price=120000, unit="상", max_qty=1,
                         desc="제례실에 과일·떡·술을 올린 간소한 상을 차립니다.", ritual=True),
    "table-standard": dict(category="table", name="기본 제사상 · 3열", price=250000, unit="상", max_qty=1,
                           desc="메·갱·적·전·나물·과일을 갖춘 3열 제사상을 차립니다.", ritual=True),
    "table-full": dict(category="table", name="정성 제사상 · 5열", price=450000, unit="상", max_qty=1,
                       desc="전통 5열 진설(조율이시·홍동백서)로 정성껏 차립니다. 상차림 사진을 보내 드립니다.", ritual=True),
    "prayer-memorial": dict(category="prayer", name="추모 기도 올리기", price=30000, unit="회", max_qty=3,
                            desc="시설 법당·기도실에서 고인을 위한 기도를 올립니다(종교에 맞춰 봉행).", date=True),
    "prayer-lamp": dict(category="prayer", name="인등(연등) 공양 · 1년", price=100000, unit="등", max_qty=1,
                        desc="한 해 동안 고인의 이름으로 등을 밝힙니다."),
}
CATEGORIES = {"flower": "헌화", "gift": "선물하기", "table": "제사 상차림", "prayer": "기도 · 공양"}
PAY_METHODS = {"card": "신용·체크카드", "easy": "간편결제", "transfer": "계좌이체"}
STATUS = {"paid": "결제 완료 · 접수", "preparing": "준비 중", "done": "완료", "cancelled": "취소", "refunded": "취소 · 환불"}


def catalog() -> list[dict]:
    return [{"id": sid, "category": c["category"], "category_name": CATEGORIES[c["category"]], "name": c["name"], "desc": c["desc"],
             "price": c["price"], "unit": c["unit"], "max_qty": c["max_qty"], "needs_ritual": bool(c.get("ritual")),
             "date": bool(c.get("date")), "gift": bool(c.get("gift")), "letter": bool(c.get("letter"))} for sid, c in CATALOG.items()]


def create(m: dict, body) -> dict:
    """가족 주문. 금액은 서버가 계산한다(화면이 보낸 금액은 믿지 않음)."""
    c = CATALOG.get(body.service)
    if not c:
        raise HTTPException(400, "없는 서비스입니다.")
    d = db.one("SELECT id, name FROM deceased WHERE id=? AND contract_id=?", (body.deceased_id, m["contract_id"]))
    if not d:
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if not 1 <= body.qty <= c["max_qty"]:
        raise HTTPException(400, f"수량은 1~{c['max_qty']}{c['unit']}까지 고를 수 있습니다.")
    ritual_id = None
    if c.get("ritual"):
        if not body.ritual_id:
            raise HTTPException(400, "상차림은 어느 의례에 올릴지 골라 주세요.")
        r = db.one("SELECT id FROM rituals WHERE id=? AND (contract_id=? OR contract_id IS NULL) AND scheduled_at >= date('now','-1 day')", (body.ritual_id, m["contract_id"]))
        if not r:
            raise HTTPException(400, "고른 의례를 찾을 수 없습니다. 다가오는 의례에서 골라 주세요.")
        ritual_id = r["id"]
    deliver_on = None
    if c.get("date") and body.deliver_on:
        try:
            day = datetime.strptime(body.deliver_on, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "날짜 모양이 맞지 않습니다.")
        if day < datetime.now().date():
            raise HTTPException(400, "지난 날짜는 고를 수 없습니다.")
        deliver_on = day.isoformat()
    gift_to = None
    if body.gift_to:
        if not c.get("gift"):
            raise HTTPException(400, "이 서비스는 선물로 보낼 수 없습니다.")
        g = db.one("SELECT id FROM family_members WHERE id=? AND contract_id=? AND revoked_at IS NULL", (body.gift_to, m["contract_id"]))
        if not g or g["id"] == m["id"]:
            raise HTTPException(400, "선물 받을 가족을 다시 골라 주세요.")
        gift_to = g["id"]
    if body.pay_method not in PAY_METHODS:
        raise HTTPException(400, "결제 방법을 골라 주세요.")
    total = c["price"] * body.qty
    receipt = f"시연-{datetime.now():%Y%m%d}-{secrets.token_hex(3).upper()}"
    now = db.now()
    oid = db.execute(
        """INSERT INTO service_orders(contract_id, member_id, deceased_id, service, qty, unit_price, total, ritual_id, deliver_on, gift_to,
           card_message, note, pay_method, status, receipt, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'paid',?,?,?)""",
        (m["contract_id"], m["id"], d["id"], body.service, body.qty, c["price"], total, ritual_id, deliver_on, gift_to,
         body.card_message.strip(), body.note.strip(), body.pay_method, receipt, now, now))
    db.audit(f"member:{m['id']}", "order.paid_demo", f"order:{oid}", f"{body.service} x{body.qty} = {total}")
    return get(oid)


def get(oid: int) -> dict:
    r = db.one("""SELECT o.*, f.name AS member_name, g.name AS gift_to_name, d.name AS deceased_name, r.title AS ritual_title, r.scheduled_at AS ritual_at,
                         c.holder_name
                  FROM service_orders o JOIN family_members f ON f.id=o.member_id JOIN deceased d ON d.id=o.deceased_id
                  JOIN contracts c ON c.id=o.contract_id
                  LEFT JOIN family_members g ON g.id=o.gift_to LEFT JOIN rituals r ON r.id=o.ritual_id WHERE o.id=?""", (oid,))
    if not r:
        raise HTTPException(404, "주문을 찾을 수 없습니다.")
    c = CATALOG.get(r["service"], {})
    r["service_name"] = c.get("name", r["service"])
    r["category"] = c.get("category", "")
    r["category_name"] = CATEGORIES.get(r["category"], "")
    r["unit"] = c.get("unit", "")
    r["status_name"] = STATUS.get(r["status"], r["status"])
    r["pay_method_name"] = PAY_METHODS.get(r["pay_method"], r["pay_method"])
    r["has_photo"] = bool(r.pop("done_photo", None))
    return r


def set_status(oid: int, status: str, staff_note: str = "", photo: str | None = None) -> dict:
    o = db.one("SELECT * FROM service_orders WHERE id=?", (oid,))
    if not o:
        raise HTTPException(404, "주문을 찾을 수 없습니다.")
    if o["status"] in ("cancelled", "refunded"):
        raise HTTPException(400, "취소된 주문은 바꿀 수 없습니다.")
    sets, args = ["status=?", "updated_at=?"], [status, db.now()]
    if staff_note:
        sets.append("staff_note=?"); args.append(staff_note[:300])
    if photo:
        sets.append("done_photo=?"); args.append(photo)
    db.execute(f"UPDATE service_orders SET {', '.join(sets)} WHERE id=?", (*args, oid))
    # 헌화가 처음 완료되면 온라인 추모 제단에도 흰 국화를 놓는다(주문한 가족 이름으로).
    if status == "done" and o["status"] != "done" and CATALOG.get(o["service"], {}).get("category") == "flower":
        db.execute("INSERT INTO altar_items(deceased_id, member_id, item, x, y, rot, scale, message, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (o["deceased_id"], o["member_id"], "chrysanthemum-white", round(random.uniform(20, 80), 1), round(random.uniform(78, 90), 1),
                    round(random.uniform(-10, 10), 1), 1.1, "봉안함 앞에 생화를 올렸습니다(헌화 서비스)", db.now()))
    return get(oid)
