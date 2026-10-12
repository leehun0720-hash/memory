"""추모 제단 아이템 그림 생성기 (2026-10-12).

가족이 추모 공간 제단에 놓는 꽃·빛·스티커 16가지를 SVG 로 만든다. 손으로 고치지 말고 이 스크립트를 고쳐 다시 만든다.
  python scripts/make_altar_items.py
결과: server/static/images/altar/<이름>.svg (160×160, 투명 바탕). 이름은 server/routers/family.py 의 ALTAR_ITEMS 와 같다.
      server/static/images/services/<이름>.svg : 추모 서비스(유료) 그림(상차림·액자·화분·연등).
"""
from __future__ import annotations

import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "server" / "static" / "images" / "altar"
S = 160


def f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def doc(defs: str, body: str) -> str:
    shadow = '<filter id="sh" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#2a1d10" flood-opacity=".28"/></filter>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" width="{S}" height="{S}"><defs>{shadow}{defs}</defs>'
            f'<g filter="url(#sh)">{body}</g></svg>\n')


def petal(length: float, width: float) -> str:
    w, l = width, length
    return f'M0 0C{f(w)} {f(-l*.3)} {f(w*.85)} {f(-l*.8)} 0 {f(-l)}C{f(-w*.85)} {f(-l*.8)} {f(-w)} {f(-l*.3)} 0 0Z'


def ring(cx, cy, n, length, width, fill, stroke, offset=0, sw=1):
    p = petal(length, width)
    return "".join(f'<path d="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" transform="translate({f(cx)} {f(cy)}) rotate({f(offset + i * 360 / n)})"/>' for i in range(n))


def stem(leaf_fill="#6f8f4e"):
    return (f'<path d="M80 96C78 118 74 136 70 154" fill="none" stroke="#5c7a3f" stroke-width="4" stroke-linecap="round"/>'
            f'<path d="M76 128C62 120 50 122 42 132C56 136 68 134 76 128Z" fill="{leaf_fill}"/>'
            f'<path d="M74 140C86 130 100 130 108 138C96 144 84 144 74 140Z" fill="{leaf_fill}"/>')


def chrysanthemum(fill, edge, center, center2):
    body = stem()
    body += ring(80, 70, 22, 46, 6, fill, edge, 0, .8) + ring(80, 70, 18, 36, 6, fill, edge, 9, .8) + ring(80, 70, 14, 25, 5.5, fill, edge, 4, .8)
    body += ring(80, 70, 10, 15, 4.5, center2, edge, 12, .6)
    body += f'<circle cx="80" cy="70" r="7" fill="{center}"/>'
    return doc("", body)


def carnation():
    body = stem()
    for r, c in ((40, "#b82a40"), (32, "#d0405a"), (24, "#e2607a"), (15, "#ef8aa0")):
        pts = []
        for i in range(48):
            a = 2 * math.pi * i / 48
            rr = r + (4 if i % 2 else -2)
            pts.append(f"{f(80 + rr * math.cos(a))},{f(68 + rr * math.sin(a) * .9)}")
        body += f'<polygon points="{" ".join(pts)}" fill="{c}" stroke="#8e1f33" stroke-width=".8" stroke-linejoin="round"/>'
    return doc("", body)


def rose_white():
    body = stem()
    body += '<circle cx="80" cy="68" r="40" fill="#f7f0e4" stroke="#d9cdb8" stroke-width="1.2"/>'
    for i, r in enumerate((34, 27, 20, 13, 7)):
        a0 = i * 47
        body += (f'<path d="M{f(80 + r * math.cos(math.radians(a0)))} {f(68 + r * math.sin(math.radians(a0)))}'
                 f'A{r} {r} 0 1 1 {f(80 + r * math.cos(math.radians(a0 + 250)))} {f(68 + r * math.sin(math.radians(a0 + 250)))}" '
                 f'fill="{["#fbf6ec", "#f6eee0", "#f1e7d6", "#ecdfca", "#e5d4b9"][i]}" stroke="#cdbfa6" stroke-width="1.3"/>')
    return doc("", body)


def lily():
    defs = '<linearGradient id="lp" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#f6d9de"/><stop offset=".55" stop-color="#fffdf8"/></linearGradient>'
    body = stem()
    body += ring(80, 72, 6, 52, 13, "url(#lp)", "#d9c9c0", 0, 1)
    body += "".join(f'<path d="M80 72L{f(80 + 22 * math.cos(math.radians(a)))} {f(72 + 22 * math.sin(math.radians(a)))}" stroke="#b9764a" stroke-width="1.6" stroke-linecap="round"/>'
                    f'<ellipse cx="{f(80 + 24 * math.cos(math.radians(a)))}" cy="{f(72 + 24 * math.sin(math.radians(a)))}" rx="3" ry="2" fill="#a0522d"/>' for a in range(-150, -20, 26))
    return doc(defs, body)


def lotus():
    defs = '<linearGradient id="lo" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#f7e3e6"/><stop offset="1" stop-color="#e98aa4"/></linearGradient>'
    body = '<ellipse cx="80" cy="126" rx="56" ry="12" fill="#6f8f4e"/><ellipse cx="80" cy="122" rx="50" ry="8" fill="#89a865"/>'
    for a, l, w in ((-70, 56, 16), (70, 56, 16), (-40, 66, 18), (40, 66, 18), (-14, 72, 18), (14, 72, 18), (0, 76, 18)):
        body += f'<path d="{petal(l, w)}" fill="url(#lo)" stroke="#c9667f" stroke-width="1" transform="translate(80 118) rotate({a})"/>'
    return doc(defs, body)


def candle():
    defs = ('<radialGradient id="gl"><stop offset="0" stop-color="#ffd27a" stop-opacity=".75"/><stop offset="1" stop-color="#ffd27a" stop-opacity="0"/></radialGradient>'
            '<linearGradient id="fl" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#ff8a1f"/><stop offset=".6" stop-color="#ffc94a"/><stop offset="1" stop-color="#fff3c4"/></linearGradient>'
            '<linearGradient id="wx" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#efe6d4"/><stop offset=".5" stop-color="#fffaf0"/><stop offset="1" stop-color="#e3d7c0"/></linearGradient>')
    body = ('<circle cx="80" cy="44" r="40" fill="url(#gl)"/>'
            '<rect x="62" y="62" width="36" height="78" rx="5" fill="url(#wx)" stroke="#d2c4a8"/>'
            '<ellipse cx="80" cy="63" rx="18" ry="5" fill="#f7efe0" stroke="#d2c4a8"/>'
            '<path d="M80 60V52" stroke="#3b3024" stroke-width="2"/>'
            '<path d="M80 22C90 36 92 46 80 56C68 46 70 36 80 22Z" fill="url(#fl)"/>'
            '<ellipse cx="80" cy="146" rx="32" ry="6" fill="#b89a66"/>')
    return doc(defs, body)


def incense():
    body = ""
    for x, top in ((66, 30), (80, 22), (94, 32)):
        body += f'<path d="M{x} 118L{x} {top}" stroke="#7a4a2a" stroke-width="3" stroke-linecap="round"/><circle cx="{x}" cy="{top}" r="2.6" fill="#e2552b"/>'
        body += f'<path d="M{x} {top - 4}C{x - 10} {top - 16} {x + 10} {top - 24} {x} {top - 36}" fill="none" stroke="#9a948a" stroke-width="2" stroke-opacity=".55" stroke-linecap="round"/>'
    body += '<path d="M40 112H120L112 142H48Z" fill="#8a6a3c" stroke="#5e4523" stroke-width="1.5"/><path d="M40 112H120" stroke="#c9a66b" stroke-width="4"/>'
    body += '<ellipse cx="80" cy="113" rx="40" ry="5" fill="#d8cdb6"/>'
    return doc("", body)


def heart():
    defs = '<linearGradient id="h" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f27a8c"/><stop offset="1" stop-color="#c23a52"/></linearGradient>'
    body = ('<path d="M80 136C40 108 22 86 22 62C22 44 36 30 52 30C64 30 74 37 80 48C86 37 96 30 108 30C124 30 138 44 138 62C138 86 120 108 80 136Z" fill="url(#h)"/>'
            '<path d="M46 48C40 52 38 60 40 66" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-opacity=".55"/>')
    return doc(defs, body)


def star():
    defs = '<linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe08a"/><stop offset="1" stop-color="#d9a02a"/></linearGradient>'
    pts = " ".join(f"{f(80 + (60 if i % 2 == 0 else 26) * math.cos(math.radians(-90 + i * 36)))},{f(82 + (60 if i % 2 == 0 else 26) * math.sin(math.radians(-90 + i * 36)))}" for i in range(10))
    return doc(defs, f'<polygon points="{pts}" fill="url(#s)" stroke="#b9861d" stroke-width="2" stroke-linejoin="round"/>')


def butterfly():
    defs = ('<linearGradient id="b1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9fc3ea"/><stop offset="1" stop-color="#5a78c8"/></linearGradient>'
            '<linearGradient id="b2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#c7b2ea"/><stop offset="1" stop-color="#7a5cc0"/></linearGradient>')
    body = ('<path d="M78 76C60 40 22 34 22 60C22 80 48 86 78 80Z" fill="url(#b1)"/><path d="M82 76C100 40 138 34 138 60C138 80 112 86 82 80Z" fill="url(#b1)"/>'
            '<path d="M78 84C56 90 36 112 50 124C62 132 74 112 78 92Z" fill="url(#b2)"/><path d="M82 84C104 90 124 112 110 124C98 132 86 112 82 92Z" fill="url(#b2)"/>'
            '<rect x="77" y="62" width="6" height="56" rx="3" fill="#3b2f2a"/><path d="M79 62C74 50 68 44 62 42M81 62C86 50 92 44 98 42" fill="none" stroke="#3b2f2a" stroke-width="2" stroke-linecap="round"/>'
            '<circle cx="44" cy="58" r="6" fill="#fff" fill-opacity=".55"/><circle cx="116" cy="58" r="6" fill="#fff" fill-opacity=".55"/>')
    return doc(defs, body)


def dove():
    body = ('<path d="M30 92C44 70 70 62 92 66L118 44C124 40 130 44 128 50L114 70C126 78 130 90 124 100C108 120 70 122 44 110L22 118C18 118 18 112 22 110Z" fill="#fbfaf6" stroke="#bfb8aa" stroke-width="2" stroke-linejoin="round"/>'
            '<path d="M60 84C74 70 96 70 108 78C96 92 74 96 60 84Z" fill="#ece8de" stroke="#bfb8aa" stroke-width="1.5"/>'
            '<circle cx="112" cy="56" r="2.6" fill="#2b2620"/><path d="M128 50L138 52L128 56Z" fill="#e0a23a"/>'
            '<path d="M136 54C142 62 146 70 144 78" fill="none" stroke="#5c7a3f" stroke-width="2.4" stroke-linecap="round"/>'
            '<path d="M142 64C148 62 152 66 150 70C146 70 142 68 142 64Z" fill="#6f8f4e"/><path d="M144 74C150 74 152 78 150 82C146 80 144 78 144 74Z" fill="#6f8f4e"/>')
    return doc("", body)


def hands():
    defs = '<linearGradient id="hd" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f3d6bd"/><stop offset=".5" stop-color="#fae6d2"/><stop offset="1" stop-color="#ecc9ab"/></linearGradient>'
    body = ('<path d="M79 22C70 24 66 34 64 50L58 92C56 104 50 112 44 120L40 132H79Z" fill="url(#hd)" stroke="#c9a081" stroke-width="2" stroke-linejoin="round"/>'
            '<path d="M81 22C90 24 94 34 96 50L102 92C104 104 110 112 116 120L120 132H81Z" fill="url(#hd)" stroke="#c9a081" stroke-width="2" stroke-linejoin="round"/>'
            '<path d="M80 22V132" stroke="#c9a081" stroke-width="1.6"/>'
            '<path d="M36 132H124V146H36Z" fill="#8f3b2b" fill-opacity=".85"/>'
            '<circle cx="80" cy="76" r="62" fill="none" stroke="#e9c77a" stroke-width="2" stroke-opacity=".6"/>')
    return doc(defs, body)


def text_sticker(text, bg, ink, edge):
    body = (f'<rect x="8" y="50" width="144" height="60" rx="30" fill="{bg}" stroke="{edge}" stroke-width="2.5"/>'
            f'<text x="80" y="88" text-anchor="middle" font-family="Gowun Batang, Noto Serif KR, serif" font-size="21" font-weight="700" fill="{ink}">{text}</text>'
            f'<path d="M24 62C20 70 20 80 24 88" fill="none" stroke="#fff" stroke-width="3" stroke-opacity=".6" stroke-linecap="round"/>')
    return doc("", body)


ITEMS = {
    "chrysanthemum-white": lambda: chrysanthemum("#fffdf7", "#cfc8b8", "#c9b04a", "#f3eccd"),
    "chrysanthemum-yellow": lambda: chrysanthemum("#f6cf55", "#c99a1e", "#a8700f", "#f9e08e"),
    "carnation": carnation, "rose-white": rose_white, "lily": lily, "lotus": lotus,
    "candle": candle, "incense": incense,
    "heart": heart, "star": star, "butterfly": butterfly, "dove": dove, "hands": hands,
    "text-miss": lambda: text_sticker("보고 싶어요", "#fde8ec", "#9a2f45", "#e9a3b2"),
    "text-love": lambda: text_sticker("사랑합니다", "#fff1dc", "#8a4f12", "#e8c08a"),
    "text-thanks": lambda: text_sticker("고맙습니다", "#e6f1ea", "#2f5a45", "#9cc5ac"),
}


# ── 추모 서비스(유료) 그림: server/static/images/services/<이름>.svg (제단 아이템이 아님)
def table_set():
    body = ('<path d="M18 104H142L134 116H26Z" fill="#7a4a2a"/><rect x="14" y="96" width="132" height="10" rx="3" fill="#9a6236"/>'
            '<path d="M32 116V146M128 116V146" stroke="#6a3f22" stroke-width="7" stroke-linecap="round"/>'
            '<ellipse cx="42" cy="90" rx="16" ry="5" fill="#e9e1d0"/><circle cx="36" cy="80" r="9" fill="#d8402e"/><circle cx="48" cy="80" r="9" fill="#e2552b"/><circle cx="42" cy="70" r="9" fill="#c9302a"/>'
            '<ellipse cx="80" cy="90" rx="18" ry="5" fill="#e9e1d0"/><rect x="66" y="64" width="28" height="24" rx="4" fill="#f4ede0" stroke="#d9cdb8"/><path d="M66 72H94M66 80H94" stroke="#d9cdb8"/>'
            '<ellipse cx="118" cy="90" rx="16" ry="5" fill="#e9e1d0"/><circle cx="112" cy="80" r="9" fill="#e7b43a"/><circle cx="124" cy="80" r="9" fill="#f0c24e"/><circle cx="118" cy="70" r="9" fill="#dca12e"/>'
            '<path d="M80 44V60" stroke="#3b3024" stroke-width="2"/><path d="M80 30C86 38 86 44 80 48C74 44 74 38 80 30Z" fill="#ffb53a"/>')
    return doc("", body)


def frame_icon():
    body = ('<rect x="34" y="22" width="92" height="112" rx="6" fill="#9a7346" stroke="#6d4f2c" stroke-width="2"/>'
            '<rect x="46" y="34" width="68" height="88" rx="3" fill="#efe6d4"/>'
            '<circle cx="80" cy="66" r="14" fill="#cdbfa6"/><path d="M58 112C60 94 70 86 80 86C90 86 100 94 102 112Z" fill="#cdbfa6"/>'
            '<path d="M70 134L64 150M90 134L96 150" stroke="#6d4f2c" stroke-width="4" stroke-linecap="round"/>')
    return doc("", body)


def plant_icon():
    body = ('<path d="M52 104H108L100 146H60Z" fill="#c9895a" stroke="#9a6236" stroke-width="2"/><rect x="48" y="96" width="64" height="12" rx="3" fill="#b5764a"/>'
            '<path d="M80 96C80 70 80 56 80 40" stroke="#5c7a3f" stroke-width="3"/>'
            '<path d="M80 70C62 64 52 50 54 34C70 38 80 52 80 70Z" fill="#7aa05a"/><path d="M80 62C98 56 108 42 106 26C90 30 80 44 80 62Z" fill="#6f8f4e"/>'
            '<path d="M80 88C66 86 58 78 56 68C70 68 78 76 80 88Z" fill="#89a865"/><path d="M80 84C94 82 102 74 104 64C90 64 82 72 80 84Z" fill="#7aa05a"/>'
            '<circle cx="80" cy="36" r="6" fill="#f2b8c6"/>')
    return doc("", body)


def lamp_icon():
    defs = '<radialGradient id="lg"><stop offset="0" stop-color="#ffe9a8"/><stop offset="1" stop-color="#ff9a5a"/></radialGradient>'
    body = ('<path d="M80 8V30" stroke="#6d4f2c" stroke-width="2"/>'
            '<path d="M44 74C44 46 60 30 80 30C100 30 116 46 116 74C116 102 100 118 80 118C60 118 44 102 44 74Z" fill="url(#lg)" stroke="#d2603a" stroke-width="2"/>'
            '<path d="M80 30C70 52 70 96 80 118M80 30C90 52 90 96 80 118M50 56H110M48 92H112" stroke="#d2603a" stroke-width="1.5" fill="none"/>'
            '<rect x="66" y="118" width="28" height="8" rx="2" fill="#8f3b2b"/><path d="M72 126V150M80 126V154M88 126V150" stroke="#c9a66b" stroke-width="2"/>')
    return doc(defs, body)


SERVICE_ICONS = {"table": table_set, "frame": frame_icon, "plant": plant_icon, "lamp": lamp_icon}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in ITEMS.items():
        text = make()
        (OUT / f"{name}.svg").write_text(text, encoding="utf-8")
        print(f"{name}.svg: {len(text):,} 바이트")
    svc = OUT.parent / "services"
    svc.mkdir(parents=True, exist_ok=True)
    for name, make in SERVICE_ICONS.items():
        (svc / f"{name}.svg").write_text(make(), encoding="utf-8")
        print(f"services/{name}.svg")


if __name__ == "__main__":
    main()
