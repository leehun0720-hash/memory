"""몽환적 실사 Lottie 장면 만들기 (2026-10-12).

사용: 저장소 루트에서  python scripts/make_dream_lottie.py [원본 이미지 폴더]
  원본 폴더 기본값: ../_assets/dream-2026-10-12  (yoonhd/ = 여해원 제공 사진, generated/ = 인공지능 생성 이미지)

만드는 파일 (server/static/ 아래, 같은 입력이면 항상 같은 결과):
  lottie/dream/img/*.webp            장면에 쓰는 사진·꽃·촛불·연기·안개·빛망울 (Lottie 이미지 레이어, assetsPath 로 경로 지정)
  lottie/dream/entry-{classic,buddhist,catholic,christian}.json
                                     첫 화면: 배경 사진 아주 느린 확대·이동(불교는 노을→별밤 교차), 전경 꽃 미세 흔들림,
                                     연기 사진으로 만든 안개 흐름, 빛망울, 빛 번짐, 가장자리 어둡게. 1.5초 밝아짐 + 24초 끊김 없는 반복.
  lottie/dream/offering.json         참배 실시간 보기 위: 양쪽 촛불 빛 흔들림 + 가운데 향 연기 (2초 밝아짐 + 12초 반복)
  lottie/dream/shrine.json           인공지능 대화 고인 사진 위: 후광·안개·빛망울 (3초 + 16초 반복)
  lottie/dream/voice.json            말하기(0~30)·듣기(30~90)·쉬기(90) 표시
  lottie/dream/reaction-{hands,candle,flower,heart}.json   생중계 반응(합장·촛불·헌화·마음), 2.5초 한 번
  lottie/dream/scenes.json           재생 정보(밝아짐 끝·반복 구간·정지 장면·대체 그림·출처 표시) — js/dream.js 가 읽는다
  images/demo/portrait-fictional.jpg 시연 고인(김옥순) 사진: 인공지능 생성 가상 인물, 그림 안에 표시를 새김

인공지능 생성 이미지가 들어간 장면은 scenes.json 의 credit 으로 화면에 '인공지능 생성 이미지'를 표시한다.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "_assets" / "dream-2026-10-12"
STATIC = ROOT / "server" / "static"
OUT = STATIC / "lottie" / "dream"
IMG = OUT / "img"
FR = 30


# ───────────────────────── 이미지 준비 ─────────────────────────

def save_webp(im: Image.Image, name: str, q: int = 76) -> tuple[int, int]:
    IMG.mkdir(parents=True, exist_ok=True)
    im.save(IMG / name, "WEBP", quality=q, method=6)
    return im.size


def fit(path: Path, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(Image.open(path).convert("RGB"), size, Image.LANCZOS)


def trim(im: Image.Image, pad: int = 4) -> Image.Image:
    box = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if not box:
        return im
    x0, y0, x1, y1 = box
    return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)))


def by_height(im: Image.Image, h: int) -> Image.Image:
    return im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)


def luminance_alpha(path: Path, lo: int, hi: int, tint: tuple[int, int, int] | None = None, gain: float = 1.0) -> Image.Image:
    """검은 바탕 사진(촛불·연기) → 밝기를 투명도로. lo 이하 투명, hi 이상 불투명."""
    rgb = Image.open(path).convert("RGB")
    lum = rgb.convert("L")
    alpha = lum.point(lambda v: 0 if v <= lo else 255 if v >= hi else round((v - lo) / (hi - lo) * 255 * gain))
    alpha = alpha.point(lambda v: min(255, v))
    if tint:
        rgb = Image.new("RGB", rgb.size, tint)
    else:  # 어두운 가장자리 색을 밝혀 검은 테두리가 남지 않게
        rgb = ImageChops.lighter(rgb, Image.new("RGB", rgb.size, (40, 30, 22)))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return trim(out)


def radial(size: int, color: tuple[int, int, int], power: float = 1.6, peak: float = 1.0) -> Image.Image:
    im = Image.new("RGBA", (size, size), color + (0,))
    px = im.load()
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            a = max(0.0, 1 - d) ** power * peak
            px[x, y] = color + (round(a * 255),)
    return im


def bokeh(size: int = 96) -> Image.Image:
    """빛망울: 가장자리가 살짝 밝은 둥근 빛 + 부드러운 번짐."""
    im = Image.new("RGBA", (size, size), (255, 236, 200, 0))
    d = ImageDraw.Draw(im)
    m = size * 0.18
    d.ellipse((m, m, size - m, size - m), fill=(255, 238, 205, 120), outline=(255, 246, 225, 200), width=max(1, size // 32))
    return im.filter(ImageFilter.GaussianBlur(size / 26))


def ring(size: int, color: tuple[int, int, int], width: float = 0.06, blur: float = 0.035) -> Image.Image:
    im = Image.new("RGBA", (size, size), color + (0,))
    d = ImageDraw.Draw(im)
    m = size * 0.12
    d.ellipse((m, m, size - m, size - m), outline=color + (210,), width=max(2, round(size * width)))
    return im.filter(ImageFilter.GaussianBlur(size * blur))


def vignette(w: int, h: int, strength: float = 0.72) -> Image.Image:
    im = Image.new("RGBA", (w, h), (8, 9, 7, 0))
    px = im.load()
    for y in range(h):
        for x in range(w):
            dx, dy = (x - w / 2) / (w / 2), (y - h / 2) / (h / 2)
            d = math.sqrt(dx * dx * 0.85 + dy * dy)
            a = max(0.0, min(1.0, (d - 0.55) / 0.75)) ** 1.5 * strength
            px[x, y] = (8, 9, 7, round(a * 255))
    return im


def mist_band(smoke: Image.Image, w: int, h: int) -> Image.Image:
    """연기 사진을 눕히고 크게 흐려 낮게 깔리는 안개 띠로."""
    band = smoke.rotate(90, expand=True).resize((w, h), Image.LANCZOS)
    a = band.getchannel("A").filter(ImageFilter.GaussianBlur(h / 10)).point(lambda v: min(255, round(v * 1.6)))
    out = Image.new("RGBA", band.size, (238, 234, 226, 0))
    out.putalpha(a)
    return out


def demo_portrait(src: Path, dst: Path) -> None:
    im = ImageOps.fit(Image.open(src).convert("RGB"), (800, 1000), Image.LANCZOS, centering=(0.5, 0.35))
    d = ImageDraw.Draw(im, "RGBA")
    text = "인공지능 생성 가상 인물"
    font = None
    for f in ("C:/Windows/Fonts/malgun.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(f).exists():
            font = ImageFont.truetype(f, 26)
            break
    if font:
        box = d.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        x, y = (800 - tw) // 2, 770
        d.rounded_rectangle((x - 16, y - 10, x + tw + 16, y + th + 16), radius=18, fill=(18, 20, 16, 150))
        d.text((x, y - box[1] + 2), text, font=font, fill=(242, 235, 221, 235))
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=86)


def prepare_images() -> dict[str, tuple[int, int]]:
    y, g = SRC / "yoonhd", SRC / "generated"
    sizes: dict[str, tuple[int, int]] = {}
    for name, path in {"bg-buddhist-dusk": y / "25.jpg", "bg-buddhist-night": y / "37.jpg", "bg-classic": g / "classic-bg.png",
                       "bg-catholic": g / "catholic-bg.png", "bg-christian": g / "christian-bg.png"}.items():
        sizes[name] = save_webp(fit(path, (1600, 900)), name + ".webp", 74)
    for name, path, h in (("fg-lotus", g / "lotus-fg.png", 560), ("fg-lily", g / "lily-fg.png", 540), ("fg-chrysanthemum", g / "chrysanthemum-fg.png", 540)):
        sizes[name] = save_webp(by_height(trim(Image.open(path).convert("RGBA")), h), name + ".webp", 80)
    candle = luminance_alpha(g / "candle.png", 10, 70)
    sizes["candle"] = save_webp(by_height(candle, 420), "candle.webp", 82)
    # 불꽃만 따로(흔들리는 빛): 아주 밝은 부분 주변
    raw = Image.open(g / "candle.png").convert("RGB")
    fb = raw.convert("L").point(lambda v: 255 if v > 200 else 0).getbbox()
    x0, y0, x1, y1 = fb
    fw, fh = x1 - x0, y1 - y0
    flame_box = (x0 - fw, y0 - fh * 0.5, x1 + fw, y1 + fh * 0.25)
    flame = raw.crop(tuple(round(v) for v in flame_box))
    fl = flame.convert("L").point(lambda v: 0 if v < 60 else min(255, round((v - 60) * 1.6)))
    flame_rgba = flame.convert("RGBA")
    flame_rgba.putalpha(fl)
    # 촛불 그림(candle.webp) 안에서 불꽃 위치를 기록해 두고 같은 배율로 줄인다
    cbox = Image.open(g / "candle.png").convert("L").point(lambda v: 255 if v > 10 else 0).getbbox()
    cs = 420 / ((cbox[3] + 4) - max(0, cbox[1] - 4))
    flame_small = flame_rgba.resize((max(1, round(flame_rgba.width * cs)), max(1, round(flame_rgba.height * cs))), Image.LANCZOS)
    sizes["flame"] = save_webp(flame_small, "flame.webp", 84)
    FLAME_AT["x"] = ((flame_box[0] + flame_box[2]) / 2 - (max(0, cbox[0] - 4))) * cs
    FLAME_AT["y"] = (flame_box[3] - max(0, cbox[1] - 4)) * cs        # 불꽃 그림 아래 끝(흔들림 기준점)
    smoke = luminance_alpha(g / "smoke.png", 14, 150, tint=(245, 242, 236), gain=0.9)
    sizes["smoke"] = save_webp(by_height(smoke, 640), "smoke.webp", 74)
    sizes["mist"] = save_webp(mist_band(smoke, 1800, 520), "mist.webp", 70)
    sizes["glow-warm"] = save_webp(radial(256, (255, 196, 120), 1.7), "glow-warm.webp", 80)
    sizes["glow-gold"] = save_webp(radial(256, (255, 228, 170), 1.4, 0.9), "glow-gold.webp", 80)
    sizes["glow-blue"] = save_webp(radial(256, (190, 220, 255), 1.6, 0.9), "glow-blue.webp", 80)
    sizes["halo-ring"] = save_webp(ring(400, (255, 232, 180)), "halo-ring.webp", 80)
    sizes["bokeh"] = save_webp(bokeh(96), "bokeh.webp", 82)
    sizes["vignette"] = save_webp(vignette(400, 225), "vignette.webp", 80)
    demo_portrait(g / "portrait-fictional.png", STATIC / "images" / "demo" / "portrait-fictional.jpg")
    return sizes


FLAME_AT: dict[str, float] = {}


# ───────────────────────── Lottie 도우미 ─────────────────────────

SMOOTH = ({"x": [0.42], "y": [0]}, {"x": [0.58], "y": [1]})
LINEAR = ({"x": [0.0], "y": [0.0]}, {"x": [1.0], "y": [1.0]})


def r(n: float) -> float:
    return round(n, 2)


def vec(v) -> list:
    return [r(x) for x in v] if isinstance(v, (list, tuple)) else [r(v)]


def static(v) -> dict:
    return {"a": 0, "k": vec(v) if isinstance(v, (list, tuple)) else r(v)}


def anim(points: list[tuple]) -> dict:
    """points: (프레임, 값, 'smooth'|'linear'|'hold'). 프레임 순으로 정렬해 키프레임으로."""
    pts = sorted(points, key=lambda p: p[0])
    out = []
    for i, (t, v, ease) in enumerate(pts):
        k = {"t": r(t), "s": vec(v)}
        if i < len(pts) - 1:
            if ease == "hold":
                k["h"] = 1
            else:
                o, inn = SMOOTH if ease == "smooth" else LINEAR
                k["o"], k["i"] = o, inn
        out.append(k)
    return {"a": 1, "k": out}


def periodic(cycle: list[tuple], period: float, phase: float, t0: float, t1: float) -> list[tuple]:
    """한 주기(0~period)의 점들을 [t0, t1] 전체에 반복해 깐다. phase 만큼 민다."""
    out = []
    k = math.floor((t0 - phase) / period) - 1
    while phase + k * period <= t1 + period:
        base = phase + k * period
        out += [(base + t, v, e) for t, v, e in cycle]
        k += 1
    return out


def osc(a, b, period: float, phase: float, t0: float, t1: float) -> list[tuple]:
    """a ↔ b 를 period 주기로 부드럽게 오간다(사인 비슷)."""
    return periodic([(0, a, "smooth"), (period / 2, b, "smooth")], period, phase, t0, t1)


def flicker(rng: random.Random, lo: float, hi: float, period: float, t0: float, t1: float, step=(4, 9)) -> list[tuple]:
    """촛불처럼 불규칙하지만 period 마다 똑같이 반복되는 흔들림."""
    cyc, t = [], 0.0
    first = rng.uniform(lo, hi)
    while t < period - step[1]:
        cyc.append((t, first if t == 0 else rng.uniform(lo, hi), "smooth"))
        t += rng.uniform(*step)
    return periodic(cyc, period, 0, t0, t1)


def tf(p=(0, 0), a=(0, 0), s=100, o=100, rot=0) -> dict:
    """정적 또는 애니메이션 값을 받아 변형(ks)을 만든다. dict 이면 그대로 쓴다."""
    def prop(v, dims):
        if isinstance(v, dict):
            return v
        if dims == 3 and isinstance(v, (int, float)):
            return static([v, v, 100])
        if dims == 3:
            return static(list(v) + [0] * (3 - len(v)))
        return static(v)
    return {"o": prop(o, 1), "r": prop(rot, 1), "p": prop(p, 3), "a": prop(a, 3), "s": prop(s, 3)}


class Comp:
    def __init__(self, sizes: dict, w: int, h: int, op: int):
        self.sizes, self.w, self.h, self.op = sizes, w, h, op
        self.layers: list[dict] = []
        self.assets: dict[str, dict] = {}

    def asset(self, name: str) -> str:
        w, h = self.sizes[name]
        self.assets[name] = {"id": name, "w": w, "h": h, "u": "", "p": name + ".webp", "e": 0}
        return name

    def image(self, name: str, nm: str, p, s=100, o=100, rot=0, anchor=None, bm=0, ip=0, op=None) -> dict:
        w, h = self.sizes[name]
        a = anchor if anchor is not None else (w / 2, h / 2)
        layer = {"ddd": 0, "ty": 2, "nm": nm, "refId": self.asset(name), "sr": 1, "ks": tf(p, a, s, o, rot), "ao": 0,
                 "ip": ip, "op": self.op if op is None else op, "st": 0, "bm": bm}
        self.layers.append(layer)
        return layer

    def shape(self, nm: str, items: list, p, s=100, o=100, rot=0, ip=0, op=None, bm=0) -> dict:
        layer = {"ddd": 0, "ty": 4, "nm": nm, "sr": 1, "ks": tf(p, (0, 0), s, o, rot), "ao": 0, "shapes": items,
                 "ip": ip, "op": self.op if op is None else op, "st": 0, "bm": bm}
        self.layers.append(layer)
        return layer

    def finish(self, top_first: bool = False) -> list[dict]:
        ls = self.layers if top_first else list(reversed(self.layers))  # 추가한 순서 = 아래→위
        for i, l in enumerate(ls, start=1):
            l["ind"] = i
        return ls


def lottie(name: str, comp: Comp, intro: int, fade_from: float = 0) -> dict:
    """내용 전체를 미리 합성(precomp)으로 묶고, 처음 intro 프레임 동안 밝아지게 한다."""
    inner = comp.finish()
    root_o = anim([(0, fade_from, "smooth"), (intro, 100, "hold"), (comp.op, 100, "hold")]) if intro else 100
    root = {"ddd": 0, "ind": 1, "ty": 0, "nm": "scene", "refId": "scene", "sr": 1, "ks": tf((comp.w / 2, comp.h / 2), (comp.w / 2, comp.h / 2), 100, root_o),
            "ao": 0, "w": comp.w, "h": comp.h, "ip": 0, "op": comp.op, "st": 0, "bm": 0}
    return {"v": "5.7.4", "fr": FR, "ip": 0, "op": comp.op, "w": comp.w, "h": comp.h, "nm": name, "ddd": 0,
            "assets": list(comp.assets.values()) + [{"id": "scene", "layers": inner}], "layers": [root], "markers": []}


# 도형(벡터) 도우미
def fill(rgb, o=100):
    return {"ty": "fl", "c": static(list(rgb) + [1]), "o": static(o), "r": 1, "nm": "fill"}


def stroke(rgb, w, o=100):
    return {"ty": "st", "c": static(list(rgb) + [1]), "o": static(o), "w": static(w), "lc": 2, "lj": 2, "nm": "stroke"}


def group(items, p=(0, 0), rot=0, s=100, o=100):
    return {"ty": "gr", "nm": "g", "it": items + [{"ty": "tr", "p": static([p[0], p[1]]), "a": static([0, 0]),
            "s": s if isinstance(s, dict) else static([s, s]), "r": rot if isinstance(rot, dict) else static(rot),
            "o": o if isinstance(o, dict) else static(o), "sk": static(0), "sa": static(0), "nm": "tr"}]}


def path(v, i=None, o=None, closed=True):
    n = len(v)
    return {"ty": "sh", "nm": "path", "ks": static_shape({"v": [vec(p) for p in v], "i": [vec(p) for p in (i or [[0, 0]] * n)],
                                                          "o": [vec(p) for p in (o or [[0, 0]] * n)], "c": closed})}


def static_shape(k):
    return {"a": 0, "k": k}


def ellipse(cx, cy, w, h):
    return {"ty": "el", "nm": "el", "p": static([cx, cy]), "s": static([w, h]), "d": 1}


def rect(cx, cy, w, h, rr=0):
    return {"ty": "rc", "nm": "rc", "p": static([cx, cy]), "s": static([w, h]), "r": static(rr), "d": 1}


def drop(cx, tip, bottom, w):
    h = bottom - tip
    mid = tip + h * 0.68
    return path([[cx, tip], [cx + w, mid], [cx, bottom], [cx - w, mid]],
                i=[[-w * 0.3, h * 0.24], [0, -h * 0.28], [w * 0.55, 0], [0, h * 0.18]],
                o=[[w * 0.3, h * 0.24], [0, h * 0.18], [-w * 0.55, 0], [0, -h * 0.28]])


# ───────────────────────── 장면 ─────────────────────────

ENTRY = {
    "classic": {"bg": ["bg-classic"], "fg": "fg-chrysanthemum", "mirror": False, "glow": (0.24, 0.18),
                "credit": "인공지능 생성 이미지"},
    "buddhist": {"bg": ["bg-buddhist-dusk", "bg-buddhist-night"], "fg": "fg-lotus", "mirror": False, "glow": (0.62, 0.30),
                 "credit": "사진: 지장대사 여해원 · 연꽃: 인공지능 생성 이미지"},
    "catholic": {"bg": ["bg-catholic"], "fg": "fg-lily", "mirror": False, "glow": (0.55, 0.12),
                 "credit": "인공지능 생성 이미지"},
    "christian": {"bg": ["bg-christian"], "fg": "fg-lily", "mirror": True, "glow": (0.30, 0.10),
                  "credit": "인공지능 생성 이미지"},
}
E_INTRO, E_LOOP = 45, 720          # 1.5초 밝아짐 + 24초 반복


def bokeh_field(c: Comp, rng: random.Random, n: int, area, periods, y_range, size=(30, 110), peak=(35, 80), t0=0, bm=2):
    x0, x1 = area
    for k in range(n):
        P = rng.choice(periods)
        phase = rng.uniform(0, P)
        x = rng.uniform(x0, x1)
        dx = rng.uniform(-60, 60)
        sc = rng.uniform(*size)
        pk = rng.uniform(*peak)
        yb, yt = y_range
        yb += rng.uniform(-40, 60)
        yt += rng.uniform(-60, 40)
        pos = {"a": 0, "k": [0, 0, 0]}
        # 위치(x, y)를 함께: 한 주기에 아래→위 직선 + 끝에서 바로 아래로(투명할 때)
        cyc = [(0, [x, yb, 0], "linear"), (P / 2, [x + dx, (yb + yt) / 2, 0], "linear"), (P - 1, [x, yt, 0], "hold")]
        pos = anim(periodic(cyc, P, phase, t0 - P, c.op + P))
        op = anim(periodic([(0, 0, "smooth"), (P * 0.5, pk, "smooth"), (P - 1, 0, "hold")], P, phase, t0 - P, c.op + P))
        c.image("bokeh", f"bokeh {k}", pos, s=sc, o=op, bm=bm)


def entry(theme: str, sizes: dict) -> tuple[dict, dict]:
    cfg = ENTRY[theme]
    W, H = 1600, 900
    c = Comp(sizes, W, H, E_INTRO + E_LOOP)
    rng = random.Random("entry-" + theme)
    t0, t1 = 0, c.op
    L = E_LOOP
    # 배경: 아주 느린 확대·이동 (24초 한 바퀴, 가장자리가 드러나지 않게 106~112%)
    kb_s = anim(osc([107, 107, 100], [112, 112, 100], L, E_INTRO, t0, t1))
    kb_p = anim(osc([W / 2 - 18, H / 2 + 10, 0], [W / 2 + 18, H / 2 - 10, 0], L, E_INTRO, t0, t1))
    for i, bg in enumerate(cfg["bg"]):
        o = 100
        if i == 1:  # 노을 → 별밤 → 노을 (밤이 길게 머문다)
            o = anim(periodic([(0, 0, "smooth"), (L * 0.18, 0, "smooth"), (L * 0.42, 100, "smooth"), (L * 0.70, 100, "smooth"), (L * 0.94, 0, "smooth")], L, E_INTRO, t0, t1))
        c.image(bg, bg, kb_p, s=kb_s, o=o)
    # 빛 번짐: 따뜻한 빛이 천천히 숨 쉰다
    gx, gy = cfg["glow"]
    c.image("glow-gold", "light bloom", (W * gx, H * gy), s=anim(osc([520, 520, 100], [600, 600, 100], L / 2, E_INTRO, t0, t1)),
            o=anim(osc(32, 58, L / 2, E_INTRO, t0, t1)), bm=2)
    # 안개: 연기 사진으로 만든 띠 두 겹이 서로 반대로 흐른다
    mw, mh = sizes["mist"]
    c.image("mist", "mist far", anim(osc([W / 2 - 140, H * 0.70, 0], [W / 2 + 140, H * 0.66, 0], L, E_INTRO, t0, t1)), s=110,
            o=anim(osc(26, 46, L / 2, E_INTRO + L / 4, t0, t1)))
    # 빛망울(뒤쪽 큰 것)
    bokeh_field(c, rng, 9, (60, W - 60), (L / 2, L / 3, L), (H + 60, H * 0.15), size=(60, 150), peak=(20, 45))
    # 전경 꽃: 오른쪽 아래, 밑동을 기준으로 미세하게 흔들림
    fw, fh = sizes[cfg["fg"]]
    fx = W * 0.78
    sway = anim(osc(-1.1, 1.1, L / 3, E_INTRO, t0, t1))
    breathe = anim(osc([100 * (-1 if cfg["mirror"] else 1), 100, 100], [101.5 * (-1 if cfg["mirror"] else 1), 101.5, 100], L / 4, E_INTRO + 30, t0, t1))
    c.image(cfg["fg"], "flower", (fx, H + 26), s=breathe, rot=sway, anchor=(fw / 2, fh))
    # 안개(앞쪽, 꽃 밑동을 감쌈)
    c.image("mist", "mist near", anim(osc([W / 2 + 160, H * 0.94, 0], [W / 2 - 160, H * 0.97, 0], L * 1.0, E_INTRO + L / 3, t0, t1)), s=125,
            o=anim(osc(40, 62, L / 3, E_INTRO, t0, t1)))
    # 빛망울(앞쪽 작은 것)
    bokeh_field(c, rng, 12, (40, W - 40), (L / 4, L / 3, L / 2), (H + 40, H * 0.25), size=(18, 52), peak=(45, 90))
    # 가장자리 어둡게
    c.image("vignette", "vignette", (W / 2, H / 2), s=400)
    meta = {"intro": E_INTRO, "loop": [E_INTRO, E_INTRO + L], "still": E_INTRO + round(L * 0.08), "poster": cfg["bg"][0] + ".webp",
            "credit": cfg["credit"], "label": "몽환적인 추모 장면이 아주 천천히 움직이는 그림"}
    return lottie("entry-" + theme, c, E_INTRO), meta


O_INTRO, O_LOOP = 60, 360          # 2초 + 12초 반복


def offering(sizes: dict) -> tuple[dict, dict]:
    W, H = 1000, 800
    c = Comp(sizes, W, H, O_INTRO + O_LOOP)
    rng = random.Random("offering")
    L, t0, t1 = O_LOOP, 0, c.op
    # 향 연기: 가운데 아래에서 피어오르는 세 줄기(엇갈린 6초·12초 주기)
    sw, sh = sizes["smoke"]
    for k, (P, ph, x, sc) in enumerate(((L / 2, 0, W * 0.50, 70), (L / 2, L / 4, W * 0.52, 82), (L, L / 3, W * 0.48, 95))):
        cyc = [(0, [x, H + 40, 0], "linear"), (P - 1, [x + rng.uniform(-40, 40), H - 170, 0], "hold")]
        pos = anim(periodic(cyc, P, O_INTRO + ph, t0 - P, t1 + P))
        scl = anim(periodic([(0, [sc, sc, 100], "linear"), (P - 1, [sc * 1.5, sc * 1.25, 100], "hold")], P, O_INTRO + ph, t0 - P, t1 + P))
        op = anim(periodic([(0, 0, "smooth"), (P * 0.35, 42, "smooth"), (P * 0.75, 22, "smooth"), (P - 1, 0, "hold")], P, O_INTRO + ph, t0 - P, t1 + P))
        c.image("smoke", f"incense {k}", pos, s=scl, o=op, anchor=(sw / 2, sh), bm=2)
    # 양쪽 촛불(사진) + 불꽃 흔들림 + 따뜻한 빛
    cw, ch = sizes["candle"]
    for side, x in (("left", W * 0.12), ("right", W * 0.88)):
        base_y = H + 30
        fw, fh = sizes["flame"]
        fy = base_y - ch * 0.62 + FLAME_AT["y"] * 0.62
        fx = x - cw * 0.62 / 2 + FLAME_AT["x"] * 0.62
        c.image("glow-warm", f"glow {side}", (fx, fy - 30), s=anim([(t, [v, v, 100], e) for t, v, e in flicker(rng, 330, 390, L, t0, t1)]),
                o=anim(flicker(rng, 55, 85, L, t0, t1)), bm=2)
        c.image("candle", f"candle {side}", (x, base_y), s=62, anchor=(cw / 2, ch))
        c.image("flame", f"flame {side}", (fx, fy), anchor=(fw / 2, fh),
                s=anim([(t, [62, v, 100], e) for t, v, e in flicker(rng, 56, 70, L, t0, t1, step=(3, 7))]),
                rot=anim(flicker(rng, -4, 4, L, t0, t1, step=(5, 11))), o=anim(flicker(rng, 70, 100, L, t0, t1, step=(3, 6))), bm=2)
    # 빛망울 몇 개
    bokeh_field(c, rng, 7, (60, W - 60), (L / 2, L), (H + 30, H * 0.2), size=(14, 40), peak=(30, 70))
    meta = {"intro": O_INTRO, "loop": [O_INTRO, O_INTRO + L], "still": O_INTRO + 40, "poster": None, "credit": "촛불·연기: 인공지능 생성 이미지",
            "label": "봉안함 사진 양쪽에 촛불이 흔들리고 가운데 향 연기가 오르는 그림"}
    return lottie("offering", c, O_INTRO), meta


S_INTRO, S_LOOP = 90, 480          # 3초 + 16초 반복


def shrine(sizes: dict) -> tuple[dict, dict]:
    W, H = 800, 1000
    c = Comp(sizes, W, H, S_INTRO + S_LOOP)
    rng = random.Random("shrine")
    L, t0, t1 = S_LOOP, 0, c.op
    # 후광: 아치 위쪽을 감싸는 빛과 고리
    c.image("glow-gold", "halo", (W / 2, H * 0.30), s=anim(osc([330, 330, 100], [370, 370, 100], L / 2, S_INTRO, t0, t1)),
            o=anim(osc(30, 52, L / 2, S_INTRO, t0, t1)), bm=2)
    c.image("halo-ring", "halo ring", (W / 2, H * 0.33), s=anim(osc([150, 150, 100], [156, 156, 100], L / 2, S_INTRO + 20, t0, t1)),
            o=anim(osc(18, 34, L / 4, S_INTRO, t0, t1)), bm=2)
    # 아래 안개(얼굴은 가리지 않게 아래쪽만)
    c.image("mist", "mist low", anim(osc([W / 2 - 90, H * 0.93, 0], [W / 2 + 90, H * 0.90, 0], L, S_INTRO, t0, t1)), s=70,
            o=anim(osc(46, 70, L / 2, S_INTRO, t0, t1)))
    c.image("mist", "mist side", anim(osc([W / 2 + 120, H * 0.62, 0], [W / 2 - 120, H * 0.66, 0], L, S_INTRO + L / 3, t0, t1)), s=55,
            o=anim(osc(8, 20, L / 2, S_INTRO, t0, t1)))
    # 빛망울: 가장자리 위주
    bokeh_field(c, rng, 8, (20, 220), (L / 2, L / 4, L), (H + 40, H * 0.1), size=(16, 46), peak=(40, 85))
    bokeh_field(c, rng, 8, (580, 780), (L / 2, L / 4, L), (H + 40, H * 0.1), size=(16, 46), peak=(40, 85))
    meta = {"intro": S_INTRO, "loop": [S_INTRO, S_INTRO + L], "still": S_INTRO + 30, "poster": None, "credit": "",
            "label": "고인 사진 둘레에 후광과 안개, 빛망울이 머무는 그림"}
    return lottie("shrine", c, S_INTRO, fade_from=0), meta


def voice(sizes: dict) -> tuple[dict, dict]:
    W, H = 360, 90
    c = Comp(sizes, W, H, 91)
    gold, blue = (0.93, 0.80, 0.55), (0.62, 0.80, 1.0)
    # 말하기(0~30): 금빛 막대 9개가 물결처럼
    for k in range(9):
        x = W / 2 + (k - 4) * 22
        amp = 1 - abs(k - 4) / 6
        ph = (k * 7) % 30
        sy = anim(periodic([(0, [100, 30], "smooth"), (15, [100, 30 + 70 * amp + 10], "smooth")], 30, ph, -30, 60))
        c.shape(f"bar {k}", [group([rect(0, 0, 9, 52, 4.5), fill(gold, 95)], s=sy)], (x, H / 2), ip=0, op=30)
    c.image("glow-warm", "speak glow", (W / 2, H / 2), s=[140, 40, 100], o=anim(osc(30, 55, 30, 0, -30, 60)), bm=2, ip=0, op=30)
    # 듣기(30~90): 파란 고리가 퍼진다
    for k in range(3):
        sc = anim(periodic([(0, [20, 20], "linear"), (59, [110, 110], "hold")], 60, 30 + k * 20, -60, 150))
        op = anim(periodic([(0, 0, "smooth"), (12, 80, "smooth"), (59, 0, "hold")], 60, 30 + k * 20, -60, 150))
        c.shape(f"ring {k}", [group([ellipse(0, 0, 80, 80), stroke(blue, 3, 100)], s=sc, o=op)], (W / 2, H / 2), ip=30, op=90)
    c.image("glow-blue", "listen glow", (W / 2, H / 2), s=[60, 60, 100], o=60, bm=2, ip=30, op=90)
    # 쉬기(90): 낮은 점선
    for k in range(9):
        c.shape(f"idle {k}", [group([rect(0, 0, 9, 9, 4.5), fill(gold, 45)])], (W / 2 + (k - 4) * 22, H / 2), ip=90, op=91)
    meta = {"segments": {"speaking": [0, 30], "listening": [30, 90], "idle": [90, 91]}, "still": 90}
    return lottie("voice", c, 0), meta


def reaction(kind: str, sizes: dict) -> tuple[dict, dict]:
    W, H = 240, 480
    OP = 75
    c = Comp(sizes, W, H, OP)
    rng = random.Random("reaction-" + kind)
    ivory, gold, rose, flame_o, flame_y = (0.98, 0.95, 0.88), (0.86, 0.70, 0.40), (0.93, 0.55, 0.52), (1.0, 0.62, 0.22), (1.0, 0.88, 0.45)
    drift = rng.uniform(-30, 30)
    pos = anim([(0, [W / 2, H - 50, 0], "smooth"), (OP - 1, [W / 2 + drift, 70, 0], "smooth")])
    scl = anim([(0, [55, 55, 100], "smooth"), (12, [112, 112, 100], "smooth"), (24, [100, 100, 100], "smooth"), (OP - 1, [92, 92, 100], "smooth")])
    op = anim([(0, 0, "smooth"), (9, 100, "smooth"), (48, 100, "smooth"), (OP - 1, 0, "smooth")])
    # 위로 함께 오르는 빛망울
    for k in range(4):
        x = W / 2 + rng.uniform(-70, 70)
        st = rng.uniform(4, 20)
        c.image("bokeh", f"spark {k}", anim([(st, [x, H - 40, 0], "smooth"), (OP - 1, [x + rng.uniform(-20, 20), rng.uniform(60, 200), 0], "smooth")]),
                s=rng.uniform(14, 30), o=anim([(st, 0, "smooth"), (st + 10, 80, "smooth"), (OP - 1, 0, "smooth")]), bm=2)
    c.image("glow-gold" if kind != "candle" else "glow-warm", "glow", pos, s=anim([(0, [60, 60, 100], "smooth"), (15, [130, 130, 100], "smooth"), (OP - 1, [110, 110, 100], "smooth")]), o=op, bm=2)
    if kind == "heart":
        icon = [group([ellipse(-19, -8, 42, 42), ellipse(19, -8, 42, 42), path([[-39, 0], [39, 0], [0, 42]]), fill(rose)]),
                group([ellipse(-24, -14, 10, 10), fill(ivory, 70)])]
    elif kind == "flower":
        petals = [group([ellipse(0, -26, 20, 40), fill(ivory), stroke(gold, 1.5, 70)], rot=a) for a in range(0, 360, 30)]
        icon = petals + [group([ellipse(0, 0, 24, 24), fill(gold)])]
    elif kind == "candle":
        fl = anim(periodic([(0, [100, 100], "smooth"), (5, [92, 110], "smooth"), (9, [104, 96], "smooth")], 14, 0, -14, OP + 14))
        icon = [group([rect(0, 16, 34, 64, 5), fill(ivory), stroke(gold, 2, 80)]),
                group([drop(0, -58, -14, 13), fill(flame_o)], s=fl), group([drop(0, -46, -18, 6), fill(flame_y)], s=fl)]
    else:  # 합장: 두 손바닥이 마주 닿은 모양
        palm = lambda sgn: group([drop(0, -52, 40, 17), fill(ivory), stroke(gold, 2, 85)], p=(sgn * 9, 0), rot=sgn * 9)
        icon = [palm(-1), palm(1), group([rect(0, 46, 46, 14, 7), fill(gold, 90)])]
    c.shape("icon", icon, pos, s=scl, o=op)
    return lottie("reaction-" + kind, c, 0), {"once": True}


def main() -> None:
    sizes = prepare_images()
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = {}
    jobs = [(f"entry-{t}", lambda t=t: entry(t, sizes)) for t in ENTRY] + [
        ("offering", lambda: offering(sizes)), ("shrine", lambda: shrine(sizes)), ("voice", lambda: voice(sizes))] + [
        (f"reaction-{k}", lambda k=k: reaction(k, sizes)) for k in ("hands", "candle", "flower", "heart")]
    for name, make in jobs:
        data, meta = make()
        (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        scenes[name] = meta
    (OUT / "scenes.json").write_text(json.dumps(scenes, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"만들었습니다: {len(jobs)}개 장면, 이미지 {len(list(IMG.glob('*.webp')))}장, 합계 {total / 1024:.0f}KB → {OUT}")


if __name__ == "__main__":
    main()
