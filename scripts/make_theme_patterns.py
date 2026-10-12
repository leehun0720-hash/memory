"""종교별 배경 문양 생성기 (2026-10-12).

가족 화면 바탕에 흐릿하고 아련하게 비치는 문양을 SVG 로 만든다. 손으로 고치지 말고 이 스크립트를 고쳐 다시 만든다.
  python scripts/make_theme_patterns.py
결과: server/static/images/patterns/
  tile-<테마>.svg   : 끝이 이어지는 반복 무늬(320×320). css/serene.css 가 mask 로 써서 강조색으로 칠한다.
  emblem-<테마>.svg : 화면 오른쪽 위에 크게 번지는 상징 하나(600×600).
테마: classic(칠보 무늬, 종교 상징 없음) · buddhist(연꽃·구름) · catholic(장미창·백합·십자) · christian(올리브 가지·십자·빛)
선은 검정 한 색이다(mask 의 투명도만 쓰임). 꽃잎 안은 옅게 채워 번지는 느낌을 준다.
"""
from __future__ import annotations

import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "server" / "static" / "images" / "patterns"


def svg(size: int, body: str, stroke: float) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
            f'<g fill="none" stroke="#000" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>\n')


def f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


# ── 공통 조각
def petal(length: float, width: float) -> str:
    """위쪽(0,-length)을 향한 꽃잎 하나(원점에서 시작)."""
    w, l = width, length
    return f'M0 0C{f(w)} {f(-l*.3)} {f(w*.9)} {f(-l*.78)} 0 {f(-l)}C{f(-w*.9)} {f(-l*.78)} {f(-w)} {f(-l*.3)} 0 0Z'


def rosette(cx: float, cy: float, n: int, length: float, width: float, offset: float = 0, fill: float = .16) -> str:
    p = petal(length, width)
    return "".join(f'<path d="{p}" fill="#000" fill-opacity="{fill}" transform="translate({f(cx)} {f(cy)}) rotate({f(offset + i * 360 / n)})"/>' for i in range(n))


def circle(cx, cy, r, extra=""):
    return f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}"{extra}/>'


def dots_ring(cx, cy, r, n, dot):
    return "".join(circle(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), dot, ' fill="#000" fill-opacity=".35"') for i in range(n))


def cloud(cx, cy, s=1.0, flip=False):
    """구름 문양(소용돌이 구름) 하나."""
    t = f"translate({f(cx)} {f(cy)}) scale({f(-s if flip else s)} {f(s)})"
    return (f'<g transform="{t}"><path d="M-30 8C-38 8-40-4-31-7C-31-18-17-21-12-13C-8-24 10-24 13-12C22-16 31-8 26 1C33 4 30 12 22 12Z"/>'
            f'<path d="M-6 6C-12 2-8-6-1-5C5-4 5 4 0 5"/><path d="M22 12C30 18 36 22 44 20"/></g>')


def lily(cx, cy, s=1.0, rot=0):
    """백합 한 송이(가운데 꽃잎 + 양쪽으로 말린 꽃잎 + 줄기)."""
    return (f'<g transform="translate({f(cx)} {f(cy)}) rotate({f(rot)}) scale({f(s)})">'
            f'<path d="M0 10C-7-6-6-24 0-38C6-24 7-6 0 10Z" fill="#000" fill-opacity=".16"/>'
            f'<path d="M-2 8C-14 2-24-10-28-22C-20-18-12-16-8-20"/><path d="M2 8C14 2 24-10 28-22C20-18 12-16 8-20"/>'
            f'<path d="M0 10V34M0 26C-8 22-14 24-18 30M0 22C8 18 14 20 18 26"/></g>')


def cross(cx, cy, h, w=None, extra=""):
    w = w or h * .62
    return f'<path d="M{f(cx)} {f(cy-h/2)}V{f(cy+h/2)}M{f(cx-w/2)} {f(cy-h/2+h*.3)}H{f(cx+w/2)}"{extra}/>'


def olive_sprig(x1, y1, x2, y2, bend, leaves, leaf=30):
    """곡선 줄기를 따라 양쪽으로 잎이 난 올리브 가지."""
    mx, my = (x1 + x2) / 2 + bend[0], (y1 + y2) / 2 + bend[1]
    out = [f'<path d="M{f(x1)} {f(y1)}Q{f(mx)} {f(my)} {f(x2)} {f(y2)}"/>']
    leaf_d = f'M0 0C{f(leaf*.25)} {f(-leaf*.22)} {f(leaf*.75)} {f(-leaf*.22)} {f(leaf)} 0C{f(leaf*.75)} {f(leaf*.22)} {f(leaf*.25)} {f(leaf*.22)} 0 0Z'
    for i in range(1, leaves + 1):
        t = i / (leaves + 1)
        x = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * mx + t ** 2 * x2
        y = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * my + t ** 2 * y2
        dx = 2 * (1 - t) * (mx - x1) + 2 * t * (x2 - mx)
        dy = 2 * (1 - t) * (my - y1) + 2 * t * (y2 - my)
        a = math.degrees(math.atan2(dy, dx))
        side = 40 if i % 2 else -40
        out.append(f'<path d="{leaf_d}" fill="#000" fill-opacity=".14" transform="translate({f(x)} {f(y)}) rotate({f(a + side)})"/>')
        if i % 3 == 0:
            out.append(circle(x + 9 * math.cos(math.radians(a - 90)), y + 9 * math.sin(math.radians(a - 90)), 4.5, ' fill="#000" fill-opacity=".25"'))
    return "".join(out)


# ── 반복 무늬(320, 네 모서리·네 변 가운데가 서로 맞물려 끊김 없이 이어짐)
T = 320


def tile_classic():
    # 칠보 무늬: 반지름 80 원을 80 간격으로 겹쳐 네 잎 꽃 모양이 이어진다. 가운데에 작은 꽃점.
    body = "".join(circle(x, y, 80) for x in range(0, T + 1, 80) for y in range(0, T + 1, 80))
    body += "".join(circle(x, y, 3.2, ' fill="#000" fill-opacity=".4"') for x in range(40, T, 80) for y in range(40, T, 80))
    return svg(T, body, 1.1)


def tile_buddhist():
    body = rosette(160, 160, 8, 54, 15) + rosette(160, 160, 8, 30, 9, 22.5, .22) + circle(160, 160, 7) + dots_ring(160, 160, 66, 16, 1.6)
    for x, y in ((0, 0), (T, 0), (0, T), (T, T)):
        body += rosette(x, y, 8, 40, 12) + circle(x, y, 6)
    for x, y, fl in ((160, 0, False), (160, T, False), (0, 160, True), (T, 160, True)):
        body += cloud(x, y, .9, fl)
    return svg(T, body, 1.3)


def tile_catholic():
    body = circle(160, 160, 54) + circle(160, 160, 20) + circle(160, 160, 60)
    body += "".join(circle(160 + 37 * math.cos(math.radians(a)), 160 + 37 * math.sin(math.radians(a)), 14) for a in range(0, 360, 45))
    body += "".join(f'<path d="M{f(160 + 20 * math.cos(math.radians(a)))} {f(160 + 20 * math.sin(math.radians(a)))}L{f(160 + 54 * math.cos(math.radians(a)))} {f(160 + 54 * math.sin(math.radians(a)))}"/>' for a in range(22, 360, 45))
    for x, y in ((0, 0), (T, 0), (0, T), (T, T)):
        body += lily(x, y + 4, .9)
    for x, y in ((160, 0), (160, T), (0, 160), (T, 160)):
        body += cross(x, y, 26)
    return svg(T, body, 1.3)


def tile_christian():
    body = olive_sprig(46, 270, 274, 50, (-40, -40), 11, 26)
    body += cross(232, 236, 40) + circle(232, 232, 30, ' stroke-opacity=".45"')
    body += cross(86, 84, 30)
    for x, y in ((0, 0), (T, 0), (0, T), (T, T)):
        body += circle(x, y, 5, ' fill="#000" fill-opacity=".3"')
    return svg(T, body, 1.3)


# ── 큰 상징(600)
E = 600
C = E / 2


def emblem_classic():
    # 둥근 꽃살창: 원 안에 칠보 무늬, 바깥 두 겹 테.
    inner = "".join(circle(x, y, 60) for x in range(0, E + 1, 60) for y in range(0, E + 1, 60))
    body = f'<defs><clipPath id="c"><circle cx="{C}" cy="{C}" r="250"/></clipPath></defs><g clip-path="url(#c)" stroke-opacity=".8">{inner}</g>'
    body += circle(C, C, 252) + circle(C, C, 272) + dots_ring(C, C, 262, 48, 2.4)
    return svg(E, body, 2)


def emblem_buddhist():
    body = rosette(C, C, 16, 250, 34, 0, .08) + rosette(C, C, 12, 175, 30, 15, .11) + rosette(C, C, 8, 105, 24, 22.5, .15)
    body += circle(C, C, 40) + circle(C, C, 26) + dots_ring(C, C, 33, 12, 2.6)
    body += circle(C, C, 270, ' stroke-opacity=".6"') + dots_ring(C, C, 284, 64, 2)
    return svg(E, body, 2.2)


def emblem_catholic():
    body = circle(C, C, 285) + circle(C, C, 262) + circle(C, C, 95) + circle(C, C, 42)
    body += "".join(circle(C + 175 * math.cos(math.radians(a)), C + 175 * math.sin(math.radians(a)), 66) for a in range(0, 360, 30))
    body += "".join(circle(C + 273 * math.cos(math.radians(a)), C + 273 * math.sin(math.radians(a)), 9) for a in range(0, 360, 15))
    body += "".join(f'<path d="M{f(C + 95 * math.cos(math.radians(a)))} {f(C + 95 * math.sin(math.radians(a)))}L{f(C + 262 * math.cos(math.radians(a)))} {f(C + 262 * math.sin(math.radians(a)))}"/>' for a in range(15, 360, 30))
    body += cross(C, C, 60, 40, ' stroke-width="4"')
    return svg(E, body, 2.2)


def emblem_christian():
    rays = "".join(f'<path d="M{f(C + 150 * math.cos(math.radians(a)))} {f(C + 150 * math.sin(math.radians(a)))}L{f(C + (285 if i % 2 else 230) * math.cos(math.radians(a)))} {f(C + (285 if i % 2 else 230) * math.sin(math.radians(a)))}" stroke-opacity="{.7 if i % 2 else .45}"/>' for i, a in enumerate(range(0, 360, 10)))
    body = rays + circle(C, C, 135, ' stroke-opacity=".5"')
    body += f'<path d="M{C-18} {C-120}H{C+18}V{C-40}H{C+78}V{C-6}H{C+18}V{C+130}H{C-18}V{C-6}H{C-78}V{C-40}H{C-18}Z" fill="#000" fill-opacity=".12" stroke-width="3"/>'
    body += olive_sprig(C - 230, C + 120, C - 40, C + 250, (-30, 40), 9, 34) + olive_sprig(C + 230, C + 120, C + 40, C + 250, (30, 40), 9, 34)
    return svg(E, body, 2.2)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    made = {
        "tile-classic.svg": tile_classic(), "tile-buddhist.svg": tile_buddhist(),
        "tile-catholic.svg": tile_catholic(), "tile-christian.svg": tile_christian(),
        "emblem-classic.svg": emblem_classic(), "emblem-buddhist.svg": emblem_buddhist(),
        "emblem-catholic.svg": emblem_catholic(), "emblem-christian.svg": emblem_christian(),
    }
    for name, text in made.items():
        (OUT / name).write_text(text, encoding="utf-8")
        print(f"{name}: {len(text):,} 바이트")


if __name__ == "__main__":
    main()
