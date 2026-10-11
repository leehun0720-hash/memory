"""가족 추모 공간 첫 화면 그림 만들기 (2026-10-11).

사용: 저장소 루트에서  python scripts/make_memorial_lottie.py

만드는 파일 (모두 server/static/ 아래):
  lottie/candle-light.json      불교 외 테마(전통·천주교·기독교)의 첫 화면 Lottie. 종교 상징이 없는 선화:
                                도면 원이 그려진 뒤 촛불이 켜지고, 불꽃이 천천히 흔들린다 (반복 8초).
  images/brand/candle-light.svg 위 그림의 마지막 장면(정적 대체 그림, Lottie를 못 불러오거나 움직임을 줄였을 때)
  images/brand/lotus-static.svg 불교 테마 연화문(lottie/lotus-family.json)의 정적 대체 그림

불교 테마 Lottie(lottie/lotus-family.json, 도면 표기 없는 가족용)는 기억과 돌봄 플랫폼(runiq-memory-suite)에서 같은 도형으로 만든 파일을
그대로 복사해 씁니다. 두 Lottie 모두 30fps, 0~90프레임 그리기 → 90~330프레임 반복 구조라 같은 재생 코드(js/brand.js)를 씁니다.
표준 라이브러리만 씁니다. 같은 입력이면 항상 같은 파일이 나옵니다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "server" / "static"
FR, OP, BLOOM = 30, 330, 90
IVORY = [0.95, 0.92, 0.85, 1]
GOLD = [0.79, 0.65, 0.42, 1]
GLOW = [1, 0.88, 0.66, 1]


def r2(n: float) -> float:
    return round(n * 100) / 100


# ── 도형 (Lottie 경로: 꼭짓점 + 꼭짓점 기준 접선)
def poly(pts, closed=False):
    return {"v": [[r2(x), r2(y)] for x, y in pts], "i": [[0, 0] for _ in pts], "o": [[0, 0] for _ in pts], "c": closed}


def circle(cx, cy, r):
    k = r2(0.5523 * r)
    return {"v": [[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]],
            "i": [[-k, 0], [0, -k], [k, 0], [0, k]], "o": [[k, 0], [0, k], [-k, 0], [0, -k]], "c": True}


def drop(cx, tip_y, bottom_y, w):
    """불꽃(물방울) 모양: 위가 뾰족하고 아래가 둥글다."""
    h = bottom_y - tip_y
    mid = tip_y + h * 0.7
    return {"v": [[cx, tip_y], [cx + w, mid], [cx, bottom_y], [cx - w, mid]],
            "o": [[w * 0.3, h * 0.24], [0, h * 0.18], [-w * 0.55, 0], [0, -h * 0.28]],
            "i": [[-w * 0.3, h * 0.24], [0, -h * 0.28], [w * 0.55, 0], [0, h * 0.18]], "c": True}


def rot(p, deg):
    a = math.radians(deg)
    return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a))


def petal(cx, cy, r0, R, w, deg):
    L = R - r0
    at = lambda p: (lambda q: [r2(cx + q[0]), r2(cy + q[1])])(rot(p, deg))
    base, tip = at((0, -r0)), at((0, -R))
    c1, c2 = at((w, -r0 - L * 0.12)), at((w * 0.62, -R + L * 0.3))
    c3, c4 = at((-w * 0.62, -R + L * 0.3)), at((-w, -r0 - L * 0.12))
    sub = lambda a, b: [r2(a[0] - b[0]), r2(a[1] - b[1])]
    return {"v": [base, tip], "o": [sub(c1, base), sub(c3, tip)], "i": [sub(c4, base), sub(c2, tip)], "c": True}


def ring(cx, cy, n, r0, R, w, offset=0.0):
    return [petal(cx, cy, r0, R, w, offset + 360 / n * k) for k in range(n)]


def lotus(cx, cy, s=1.0):
    """기억과 돌봄 플랫폼(server/lotus-art.ts)의 연화문과 같은 좌표."""
    seeds = [(0, 0)] + [rot((0, -17), k * 60) for k in range(6)]
    return {
        "band": ring(cx, cy, 16, 150 * s, 178 * s, 14 * s, 11.25),
        "outer": ring(cx, cy, 8, 40 * s, 150 * s, 58 * s),
        "inner": ring(cx, cy, 8, 30 * s, 100 * s, 36 * s, 22.5),
        "pod": circle(cx, cy, 30 * s),
        "seeds": [(r2(cx + x * s), r2(cy + y * s)) for x, y in seeds],
        "guides": [120 * s, 190 * s],
        "seedR": 2.6 * s,
    }


def svg_path(s):
    f = lambda p: f"{r2(p[0]):g} {r2(p[1]):g}"
    add = lambda a, b: (a[0] + b[0], a[1] + b[1])
    v, i, o = s["v"], s["i"], s["o"]
    d = f"M{f(v[0])}"
    pairs = [(k - 1, k) for k in range(1, len(v))] + ([(len(v) - 1, 0)] if s["c"] else [])
    for a, b in pairs:
        d += f"C{f(add(v[a], o[a]))} {f(add(v[b], i[b]))} {f(v[b])}"
    return d + ("Z" if s["c"] else "")


# ── Lottie 조각
EASE = {"o": {"x": [0.45], "y": [0]}, "i": {"x": [0.2], "y": [1]}}
SOFT = {"o": {"x": [0.42], "y": [0]}, "i": {"x": [0.58], "y": [1]}}


def kf(frames, e=EASE):
    out = []
    for idx, (t, v) in enumerate(frames):
        s = v if isinstance(v, list) else [v]
        out.append({"t": t, "s": s} if idx == len(frames) - 1 else {"t": t, "s": s, **e})
    return {"a": 1, "k": out}


st = lambda v: {"a": 0, "k": v}


def tr(**extra):
    base = {"ty": "tr", "p": st([0, 0]), "a": st([0, 0]), "s": st([100, 100]), "r": st(0), "o": st(100), "sk": st(0), "sa": st(0)}
    base.update(extra)
    return base


sh = lambda s: {"ty": "sh", "ks": st(s)}


def stroke(w, o=100, c=IVORY, dash=None):
    s = {"ty": "st", "c": st(c), "o": st(o), "w": st(w), "lc": 2, "lj": 2, "ml": 4}
    if dash:
        s["d"] = [{"n": "g" if k % 2 else "d", "nm": f"d{k}", "v": st(v)} for k, v in enumerate(dash)]
    return s


fill = lambda c, o=100: {"ty": "fl", "c": st(c), "o": st(o), "r": 1}
trim = lambda e: {"ty": "tm", "s": st(0), "e": e, "o": st(0), "m": 1}
el = lambda cx, cy, w, h=None: {"ty": "el", "p": st([cx, cy]), "s": st([w, h or w]), "d": 1}
group = lambda it, t=None: {"ty": "gr", "it": [*it, t or tr()]}


def ks(o, **extra):
    base = {"o": o, "r": st(0), "p": st([0, 0, 0]), "a": st([0, 0, 0]), "s": st([100, 100, 100])}
    base.update(extra)
    return base


class Builder:
    def __init__(self):
        self.layers, self.ind = [], 0

    def _layer(self, nm, o, shapes):
        self.ind += 1
        self.layers.append({"ddd": 0, "ind": self.ind, "ty": 4, "nm": nm, "sr": 1, "ks": ks(o), "ao": 0,
                            "ip": 0, "op": OP, "st": 0, "bm": 0, "shapes": shapes})

    def draw(self, nm, at, length, shapes, w=1.0, o=80, c=IVORY, dash=None):
        it = [*map(sh, shapes), stroke(w, o, c, dash)]
        if not dash:
            it.append(trim(kf([[at, 0], [at + length, 100]])))
        self._layer(nm, kf([[max(at - 2, 0), 0], [at + 8, 100]]), [group(it)])

    def fill_in(self, nm, shapes, o, c, alpha, t=None):
        self._layer(nm, o, [group([*map(sh, shapes), fill(c, alpha)], t)])

    def glow(self, nm, cx, cy, r, o, alpha=0.3):
        g = {"ty": "gf", "o": st(100), "r": 1, "s": st([cx, cy]), "e": st([cx + r, cy]), "t": 2, "h": st(0), "a": st(0),
             "g": {"p": 2, "k": st([0, *GLOW[:3], 1, *GLOW[:3], 0, alpha, 1, 0])}}
        self._layer(nm, o, [group([el(cx, cy, r * 2), g])])


# ── 촛불 (종교 상징 없음): 800×800, 가운데 400
S, C = 800, 400
FLAME = drop(C, 318, 410, 21)
FLAME_CORE = drop(C, 356, 404, 8)
BODY = poly([(372, 612), (372, 438), (428, 438), (428, 612)], True)
BASE = [poly([(318, 614), (482, 614)]), poly([(344, 628), (456, 628)])]
WICK = poly([(C, 438), (C, 414)])


def candle_lottie():
    b = Builder()
    # 흔들림: 불꽃 아래(심지 끝)를 축으로 크기·기울기를 아주 조금 바꾼다. 90→330 사이에 처음 값으로 돌아와 반복이 매끄럽다.
    pivot = [C, 410]
    flicker = tr(a=st(pivot), p=st(pivot),
                 s=kf([[90, [100, 100]], [130, [97, 105]], [170, [102, 97]], [210, [98, 104]], [250, [101, 98]], [290, [97, 103]], [330, [100, 100]]], SOFT),
                 r=kf([[90, 0], [140, -2], [200, 1.5], [260, -1], [330, 0]], SOFT))
    b.draw("ring-outer", 0, 1, [circle(C, C, 360)], 0.8, 30, IVORY, [3, 6])
    b.draw("guides", 2, 1, [circle(C, C, 210), circle(C, C, 300)], 0.8, 26, IVORY, [4, 5])
    b.draw("cross", 2, 1, [poly([(20, C), (780, C)]), poly([(C, 20), (C, 780)])], 0.8, 22, IVORY, [12, 6, 2, 6])
    b.draw("circle-gold", 6, 44, [circle(C, C, 250)], 1.8, 95, GOLD)
    b.draw("circle-ivory", 14, 40, [circle(C, C, 236)], 0.9, 55, IVORY)
    b.draw("base", 20, 18, BASE, 1.4, 85, IVORY)
    b.draw("candle", 24, 26, [BODY], 1.6, 92, IVORY)
    b.draw("wick", 44, 8, [WICK], 1.4, 90, IVORY)
    b.fill_in("glow-wash", [circle(C, C, 236)], kf([[50, 0], [90, 100]]), GOLD, 5)
    b.glow("flame-glow", C, 372, 220, kf([[48, 0], [90, 80], [210, 100], [330, 80]]), 0.32)
    b.fill_in("flame-fill", [FLAME], kf([[50, 0], [80, 100]]), GOLD, 30, flicker)
    b.fill_in("flame-core", [FLAME_CORE], kf([[58, 0], [84, 100]]), IVORY, 70, flicker)
    # 불꽃 선: 그려진 뒤 같은 흔들림
    b.ind += 1
    b.layers.append({"ddd": 0, "ind": b.ind, "ty": 4, "nm": "flame-line", "sr": 1, "ks": ks(kf([[44, 0], [52, 100]])), "ao": 0,
                     "ip": 0, "op": OP, "st": 0, "bm": 0,
                     "shapes": [group([sh(FLAME), stroke(1.6, 95, GOLD), trim(kf([[46, 0], [66, 100]]))], flicker)]})
    # 위에 놓인 레이어가 앞. 그리는 순서대로 쌓았으므로 뒤집어 앞/뒤를 맞춘다(불꽃 선이 맨 앞).
    layers = list(reversed(b.layers))
    return {"v": "5.12.2", "fr": FR, "ip": 0, "op": OP, "w": S, "h": S, "nm": "가족 추모 공간 촛불", "ddd": 0,
            "assets": [], "layers": layers, "markers": []}


SVG_STYLE = ("<style>.a path,.a circle{fill:none;stroke-linecap:round;stroke-linejoin:round}"
             ".lt-ring,.lt-guide{stroke:#f2ebdd;stroke-width:.9;stroke-dasharray:4 6;opacity:.3}"
             ".lt-gold{stroke:#c9a66b;stroke-width:1.8}.lt-thin{stroke-width:1.1;opacity:.75}"
             ".lt-ivory{stroke:#f2ebdd;stroke-width:1.4;opacity:.9}.a .lt-fill{fill:#c9a66b;stroke:none;opacity:.1}"
             ".a .lt-pod{fill:rgba(201,166,107,.3)}.a .lt-seed{fill:#c9a66b;stroke:none}"
             ".a .lt-flame{fill:rgba(201,166,107,.3)}.a .lt-core{fill:#f2ebdd;stroke:none;opacity:.7}</style>")


def candle_svg():
    p = lambda shapes, cls: f'<path class="{cls}" d="{"".join(svg_path(s) for s in shapes)}"/>'
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" class="a"><title>촛불 선화</title>'
            '<defs><radialGradient id="g"><stop offset="0" stop-color="#ffe0a8" stop-opacity=".3"/><stop offset="1" stop-color="#ffe0a8" stop-opacity="0"/></radialGradient></defs>'
            + SVG_STYLE
            + p([circle(C, C, 360)], "lt-ring") + p([circle(C, C, 210), circle(C, C, 300)], "lt-guide")
            + p([poly([(20, C), (780, C)]), poly([(C, 20), (C, 780)])], "lt-guide")
            + f'<circle cx="{C}" cy="372" r="220" fill="url(#g)" stroke="none"/>'
            + p([circle(C, C, 250)], "lt-gold") + p([circle(C, C, 236)], "lt-ivory lt-thin")
            + p(BASE, "lt-ivory") + p([BODY], "lt-ivory") + p([WICK], "lt-ivory")
            + p([FLAME], "lt-gold lt-flame") + p([FLAME_CORE], "lt-core") + "</svg>")


def lotus_svg():
    lo = lotus(C, C, 1.75)
    p = lambda shapes, cls: f'<path class="{cls}" d="{"".join(svg_path(s) for s in shapes)}"/>'
    seeds = "".join(f'<circle class="lt-seed" cx="{x:g}" cy="{y:g}" r="{r2(lo["seedR"]):g}"/>' for x, y in lo["seeds"])
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" class="a"><title>연화문 선화</title>' + SVG_STYLE
            + p([circle(C, C, 360)], "lt-ring") + p([circle(C, C, r) for r in lo["guides"]], "lt-guide")
            + p([poly([(20, C), (780, C)]), poly([(C, 20), (C, 780)])], "lt-guide")
            + p(lo["outer"] + lo["inner"], "lt-fill") + p(lo["band"], "lt-gold lt-thin") + p(lo["outer"], "lt-gold")
            + p(lo["inner"], "lt-ivory") + p([lo["pod"]], "lt-gold lt-pod") + seeds + "</svg>")


def write(rel: str, text: str) -> None:
    path = STATIC / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"{rel}  {path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    write("lottie/candle-light.json", json.dumps(candle_lottie(), ensure_ascii=False, separators=(",", ":")))
    write("images/brand/candle-light.svg", candle_svg())
    write("images/brand/lotus-static.svg", lotus_svg())
