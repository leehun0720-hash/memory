"""시연 카메라: 현장 웹캠(edge/agent.py)이 없을 때 서버가 직접 '시연 화면'을 만들어 원격 참배·생중계를 시연한다.

- 안치실(벽면) 카메라는 윤회당 봉안실 사진, 제례 카메라는 윤회당 법당 사진(사용 허락 받음)을 쓴다.
- 사진에 아주 느린 이동·확대와 촛불 같은 밝기 변화를 줘서 실시간 화면처럼 보이게 하되,
  화면 왼쪽 위에 '시연 화면'을 새겨 실제 현장 중계로 오해하지 않게 한다(유족 앱에도 표시).
- 설정 `demo_camera`: auto(기본, 실제 카메라가 없을 때만) · on(항상) · off(끔).
- 실제 현장 프로그램이 상태를 보내는 동안(auto)에는 그 카메라를 건드리지 않는다.
"""
from __future__ import annotations

import io
import logging
import math
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import config, db
from .state import state

log = logging.getLogger(__name__)

IMAGES = Path(__file__).parent / "static" / "images" / "demo-camera"
SOURCES = {"wall": IMAGES / "niche-wall.jpg", "ritual": IMAGES / "ritual-hall.jpg"}
LIVE_FPS = 8
FONT_CANDIDATES = (
    "C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
)


def mode() -> str:
    m = (db.get_setting("demo_camera") or os.getenv("DEMO_CAMERA", "auto")).strip().lower()
    return m if m in ("auto", "on", "off") else "auto"


def _font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return None


class DemoCamera:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._base: dict[str, Image.Image] = {}
        self._last_snapshot = 0.0
        self._last_full = 0.0
        self.active: set[int] = set()      # 지금 시연 화면을 내보내는 카메라 id
        self._seen: dict[int, float] = {}
        self._font = _font(22)
        self._font_small = _font(16)

    # ---------- 수명 ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="demo-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    # ---------- 그림 ----------
    def _source(self, kind: str) -> Image.Image:
        kind = kind if kind in SOURCES else "wall"
        if kind not in self._base:
            self._base[kind] = Image.open(SOURCES[kind]).convert("RGB")
        return self._base[kind]

    def frame(self, kind: str, t: float, size: tuple[int, int] = (1280, 720)) -> Image.Image:
        """t초 시점의 시연 화면. 24초 주기로 아주 느리게 확대·이동하고 촛불처럼 밝기가 흔들린다."""
        src = self._source(kind)
        W, H = src.size
        phase = (t % 24.0) / 24.0 * 2 * math.pi
        zoom = 1.06 + 0.04 * math.sin(phase)
        cw, ch = W / zoom, H / zoom
        cx = W / 2 + (W - cw) / 2 * 0.8 * math.sin(phase * 0.5)
        cy = H / 2 + (H - ch) / 2 * 0.6 * math.cos(phase)
        img = src.crop((int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2))).resize(size, Image.BILINEAR)
        flicker = 1.0 + 0.025 * math.sin(t * 7.3) + 0.015 * math.sin(t * 13.1 + 1.7)
        return ImageEnhance.Brightness(img).enhance(flicker)

    def _stamp(self, img: Image.Image, label: str) -> Image.Image:
        d = ImageDraw.Draw(img, "RGBA")
        text = f"시연 화면 · {label} · {datetime.now().strftime('%H:%M:%S')}"
        if self._font:
            box = d.textbbox((0, 0), text, font=self._font)
            w, h = box[2] - box[0], box[3] - box[1]
            x = img.width - w - 36   # 오른쪽 위(왼쪽 위는 유족 앱의 '실시간'·'방금 찍은 사진' 표시 자리)
            d.rounded_rectangle((x - 12, 12, x + w + 12, 12 + h + 18), radius=8, fill=(20, 18, 16, 170))
            d.text((x, 18 - box[1] + 2), text, font=self._font, fill=(245, 235, 210, 255))
        else:  # 한글 글꼴이 없는 서버: 유족 앱의 '시연 화면' 표시로 대신한다
            x = img.width - 150
            d.rounded_rectangle((x, 12, x + 138, 44), radius=8, fill=(20, 18, 16, 170))
            d.text((x + 12, 22), "DEMO " + datetime.now().strftime("%H:%M:%S"), fill=(245, 235, 210, 255))
        return img

    @staticmethod
    def _jpeg(img: Image.Image, quality: int = 78) -> bytes:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()

    def niche_view(self, full: Image.Image, n: dict, blur: bool, max_width: int = 720) -> Image.Image:
        """현장 프로그램(crop_niche)과 같은 방식: 내 칸 주변을 잘라 키우고, 운용 모드면 바깥을 흐린다."""
        W, H = full.size
        x, y, w, h = n["x"] * W, n["y"] * H, n["w"] * W, n["h"] * H
        m = 0.35
        x0, y0 = max(0, x - w * m), max(0, y - h * m)
        x1, y1 = min(W, x + w * (1 + m)), min(H, y + h * (1 + m))
        region = full.crop((int(x0), int(y0), int(x1), int(y1)))
        s = max_width / region.width
        region = region.resize((max_width, max(1, int(region.height * s))), Image.BILINEAR)
        sx, sy = int((x - x0) * s), int((y - y0) * s)
        ex, ey = int((x + w - x0) * s), int((y + h - y0) * s)
        if blur:
            blurred = region.filter(ImageFilter.GaussianBlur(10))
            blurred.paste(region.crop((sx, sy, ex, ey)), (sx, sy))
            region = blurred
        ImageDraw.Draw(region).rectangle((sx, sy, ex - 1, ey - 1), outline=(220, 190, 150), width=3)
        return region

    # ---------- 반복 ----------
    def _cameras(self) -> list[dict]:
        cams = db.rows("SELECT id, kind FROM cameras ORDER BY id")
        m = mode()
        if m == "off":
            return []
        out = []
        for c in cams:
            st = state.camera(c["id"])
            real_online = st.online and not st.virtual
            if m == "on" or not real_online:
                out.append(c)
        return out

    def _run(self) -> None:
        log.info("시연 카메라를 시작합니다(설정: %s).", mode())
        while not self._stop.is_set():
            started = time.time()
            try:
                self.tick(started)
            except Exception:  # 시연 화면 오류가 서버를 멈추게 하지 않는다
                log.exception("시연 카메라 프레임 생성 실패")
                self._stop.wait(2)
            self._stop.wait(max(0.02, 1 / LIVE_FPS - (time.time() - started)))

    def tick(self, now: float) -> None:
        from .routers.edge import edge_config   # 실제 현장 프로그램과 같은 규칙으로 송출 대상을 정한다
        cams = self._cameras()
        self.active = {c["id"] for c in cams}
        if not cams:
            return
        cfg = edge_config()
        live_niches = set(cfg["live_niche_ids"])
        ritual_cams = set(cfg["ritual_live_camera_ids"])
        blur = cfg["blur_outside"]
        snap_due = now - self._last_snapshot >= max(3, config.SNAPSHOT_INTERVAL)
        full_due = now - self._last_full >= 5
        for c in cams:
            state.set_camera(c["id"], False, 0, float(LIVE_FPS), -1.0, virtual=True)
            kind = c["kind"] or "wall"
            niches = [n for n in cfg_niches(cfg, c["id"])]
            # 보는 사람(열린 스트림)이 있을 때만 실시간 장면을 만든다(아무도 안 보면 CPU·디스크를 쓰지 않게)
            wants_live = [n for n in niches if n["id"] in live_niches and state.is_watched(n["id"])]
            ritual_live = c["id"] in ritual_cams and state.is_watched(-c["id"])
            if not (snap_due or full_due or wants_live or ritual_live):
                continue
            full = self.frame(kind, now)
            if full_due:
                data = self._jpeg(full, 82)
                state.push_full(c["id"], data)
                _atomic_write(config.FRAME_DIR / f"cam_{c['id']}.jpg", data)
            if snap_due:
                for n in niches:
                    _atomic_write(config.SNAPSHOT_DIR / f"{n['id']}.jpg",
                                  self._jpeg(self._stamp(self.niche_view(full, n, blur), f"{n['code']} 봉안함"), 82))
                    db.execute("UPDATE niches SET last_snapshot_at=? WHERE id=?", (db.now(), n["id"]))
            for n in wants_live:
                state.push_live(n["id"], self._jpeg(self._stamp(self.niche_view(full, n, blur), f"{n['code']} 실시간 보기"), 72))
            if ritual_live:
                state.push_live(-c["id"], self._jpeg(self._stamp(full.resize((960, 540), Image.BILINEAR), "제례 공간 생중계"), 72))
            if now - self._seen.get(c["id"], 0) >= 5:   # 마지막 신호 기록은 5초에 한 번
                self._seen[c["id"]] = now
                db.execute("UPDATE cameras SET last_seen_at=? WHERE id=?", (db.now(), c["id"]))
        if snap_due:
            self._last_snapshot = now
        if full_due:
            self._last_full = now


def cfg_niches(cfg: dict, cam_id: int) -> list[dict]:
    for c in cfg["cameras"]:
        if c["id"] == cam_id:
            return c["niches"]
    return []


def _atomic_write(path: Path, data: bytes) -> None:
    """임시 파일에 쓴 뒤 바꿔 끼운다. 윈도우에서는 누가 그 파일을 읽는 중이면 바꿔 끼우기가 잠깐 실패하므로 몇 번 다시 해 보고,
    그래도 안 되면 이번 장면은 건너뛴다(다음 장면이 곧 온다)."""
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.03 * (attempt + 1))
    try:
        tmp.unlink()
    except OSError:
        pass


camera = DemoCamera()
