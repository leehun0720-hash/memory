"""현장 소형 컴퓨터 프로그램. 웹캠 → 사람 감지 → 칸별 잘라내기·흐림 → 서버 업로드.
원본 전체 화면은 관리자 좌표 등록용으로만, 사람이 없을 때만 보낸다. 모든 연결은 현장 → 서버 방향(밖으로만).

실행: python -m edge.agent
"""
import logging
import os
import queue
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from dotenv import load_dotenv

from .detector import PersonDetector

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
log = logging.getLogger("edge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SERVER = os.getenv("SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
EDGE_KEY = os.getenv("EDGE_KEY", "edge1234")
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
CAPTURE_W = int(os.getenv("CAPTURE_WIDTH", "1280"))   # 720p면 흐림·압축이 1080p의 절반 비용. 칸 좌표는 비율이라 해상도와 무관
CAPTURE_H = int(os.getenv("CAPTURE_HEIGHT", "720"))
JPEG_Q = int(os.getenv("JPEG_QUALITY", "85"))
SHOW_PREVIEW = os.getenv("EDGE_PREVIEW", "0") == "1"

session = requests.Session()
session.headers["X-Edge-Key"] = EDGE_KEY


# ---------- 영상 처리 ----------

def crop_niche(frame: np.ndarray, rect: dict, margin: float = 0.35, max_width: int = 720, blur: bool = True) -> np.ndarray:
    """내 칸은 선명하게, 그 바깥(옆 칸)은 흐리고 어둡게. 옆 칸의 이름·사진·날짜가 읽히지 않게 한다.
    먼저 720px로 줄인 뒤 1/4 크기에서 흐리고 다시 키운다(큰 반경 가우시안과 보기엔 같지만 비용은 1/10)."""
    H, W = frame.shape[:2]
    x, y = int(rect["x"] * W), int(rect["y"] * H)
    w, h = max(8, int(rect["w"] * W)), max(8, int(rect["h"] * H))
    if not blur:
        # 시연 모드: 잘라내지 않고 화면 전체를 선명하게(작은 칸을 키우면 흐려 보인다). 내 칸은 테두리로만 표시.
        fs = min(1.0, 960 / W)
        out = cv2.resize(frame, (int(W * fs), int(H * fs)), interpolation=cv2.INTER_AREA) if fs < 1 else frame.copy()
        cv2.rectangle(out, (int(x * fs), int(y * fs)), (int((x + w) * fs) - 1, int((y + h) * fs) - 1), (150, 190, 220), 2)
        return out
    mx, my = int(w * margin), int(h * margin)
    x0, y0, x1, y1 = max(0, x - mx), max(0, y - my), min(W, x + w + mx), min(H, y + h + my)
    region = frame[y0:y1, x0:x1]
    s = 1.0
    if region.shape[1] > max_width:
        s = max_width / region.shape[1]
        region = cv2.resize(region, (max_width, max(1, int(region.shape[0] * s))), interpolation=cv2.INTER_AREA)
    rh, rw = region.shape[:2]
    sx, sy = int((x - x0) * s), int((y - y0) * s)
    ex, ey = min(sx + max(1, int(w * s)), rw), min(sy + max(1, int(h * s)), rh)
    tiny = cv2.resize(region, (max(1, rw // 4), max(1, rh // 4)), interpolation=cv2.INTER_AREA)
    tiny = cv2.GaussianBlur(tiny, (0, 0), sigmaX=3)
    out = cv2.resize(tiny, (rw, rh), interpolation=cv2.INTER_LINEAR)
    out = cv2.convertScaleAbs(out, alpha=0.55)
    out[sy:ey, sx:ex] = region[sy:ey, sx:ex]
    cv2.rectangle(out, (sx, sy), (ex - 1, ey - 1), (150, 190, 220), 2)
    return out


def jpeg(img: np.ndarray, quality: int = JPEG_Q) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""


# ---------- 서버 통신 ----------

class Uploader(threading.Thread):
    """서버 전송을 캡처 루프와 분리한다. 보내는 동안 캡처가 멈추지 않고, 큐가 차면 오래된 프레임부터 버려 지연이 쌓이지 않는다."""

    def __init__(self, maxsize: int = 64) -> None:
        super().__init__(daemon=True, name="uploader")
        self.q: queue.Queue = queue.Queue(maxsize=maxsize)
        self.s = requests.Session()
        self.s.headers["X-Edge-Key"] = EDGE_KEY
        self.dropped = 0
        self.sent = 0

    def submit(self, path: str, data: bytes, drop_if_full: bool = True) -> None:
        """drop_if_full=False(사진)는 큐가 차도 기다려서 반드시 보낸다. 실시간 프레임만 오래된 것을 버린다."""
        if not drop_if_full:
            self.q.put((path, data))
            return
        try:
            self.q.put_nowait((path, data))
        except queue.Full:
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass
            self.dropped += 1
            try:
                self.q.put_nowait((path, data))
            except queue.Full:
                pass

    def run(self) -> None:
        while True:
            path, data = self.q.get()
            try:
                self.s.post(f"{SERVER}{path}", files={"file": ("f.jpg", data, "image/jpeg")}, timeout=5)
                self.sent += 1
            except requests.RequestException as e:
                log.warning("upload failed %s: %s", path, e)
                time.sleep(0.5)


uploader = Uploader()

def post_file(path: str, data: bytes) -> bool:
    try:
        r = session.post(f"{SERVER}{path}", files={"file": ("f.jpg", data, "image/jpeg")}, timeout=5)
        return r.ok
    except requests.RequestException as e:
        log.warning("upload failed %s: %s", path, e)
        return False


def post_status(cam_id: int, occupied: bool, persons: int, fps: float) -> None:
    try:
        session.post(f"{SERVER}/api/edge/cameras/{cam_id}/status",
                     data={"occupied": str(occupied).lower(), "persons": persons, "fps": round(fps, 1)}, timeout=3)
    except requests.RequestException as e:
        log.warning("status failed: %s", e)


def fetch_config() -> dict | None:
    try:
        r = session.get(f"{SERVER}/api/edge/config", timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.warning("config failed: %s", e)
        return None


# ---------- 카메라 ----------

def open_camera(index: int) -> cv2.VideoCapture:
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_H)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise RuntimeError(f"카메라 {index}를 열 수 없습니다.")
    w, h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    log.info("camera %d opened at %dx%d", index, w, h)
    return cap


def main() -> None:
    cap = open_camera(CAMERA_INDEX)
    detector = PersonDetector()
    log.info("detectors: %s", ", ".join(detector.names))

    cfg: dict | None = None
    cfg_at = 0.0
    last_snapshot = 0.0
    last_live = 0.0
    last_status = 0.0
    last_occupied: bool | None = None
    fps_t, fps_n, fps = time.time(), 0, 0.0
    uploader.start()

    while True:
        ok, frame = cap.read()
        if not ok:
            log.warning("frame read failed; reopening camera")
            cap.release()
            time.sleep(2)
            cap = open_camera(CAMERA_INDEX)
            continue
        now = time.time()
        fps_n += 1
        if now - fps_t >= 2:
            fps, fps_t, fps_n = fps_n / (now - fps_t), now, 0
            if uploader.dropped >= 30:      # 2초에 30장 넘게 버릴 때만(전송이 심하게 밀림) 알린다
                log.info("전송이 캡처를 못 따라가 프레임 %d장을 건너뛰었습니다(최신 화면 우선)", uploader.dropped)
            uploader.dropped = 0

        # 설정(카메라·칸·라이브 요청)은 1초마다 새로 받는다
        if cfg is None or now - cfg_at > 1.0:
            new = fetch_config()
            if new:
                cfg, cfg_at = new, now
        if not cfg:
            time.sleep(1)
            continue

        # 이 웹캠 인덱스를 쓰는 카메라들(시연에서는 벽면·제례 카메라가 웹캠을 공유)
        my_cams = [c for c in cfg["cameras"] if c["device_index"] == CAMERA_INDEX]
        if not my_cams:
            if now - last_status > 5:
                log.info("서버에 device_index=%d 카메라가 없습니다. 관리자 콘솔에서 카메라를 등록하세요.", CAMERA_INDEX)
                last_status = now
            continue

        occupied, persons = detector.update(frame)
        if occupied != last_occupied or now - last_status > 5:
            for c in my_cams:
                post_status(c["id"], occupied, persons, fps)
            if occupied != last_occupied:
                log.info("occupied=%s persons=%d", occupied, persons)
            last_occupied, last_status = occupied, now

        wall_cams = [c for c in my_cams if c["kind"] == "wall"]
        ritual_cams = [c for c in my_cams if c["kind"] == "ritual"]

        # 사진 갱신(사람 없을 때만). 전체 화면은 관리자 좌표용, 칸별 사진은 유족용.
        # 시연 모드(live_ignore_occupied)에서는 사람이 앞에 있어도 사진을 갱신한다(노트북 앞에 앉은 사람 = 시연자).
        if (not occupied or cfg.get("live_ignore_occupied")) and now - last_snapshot >= cfg["snapshot_interval"]:
            for c in wall_cams:
                uploader.submit(f"/api/edge/cameras/{c['id']}/frame", jpeg(frame, 80), drop_if_full=False)
                for n in c["niches"]:
                    uploader.submit(f"/api/edge/niches/{n['id']}/snapshot", jpeg(crop_niche(frame, n, blur=cfg.get("blur_outside", True))), drop_if_full=False)
            last_snapshot = now

        # 실시간 보기(30초 세션이 열린 칸만) · 제례 중계
        live_ids = set(cfg.get("live_niche_ids", []))
        ritual_ids = set(cfg.get("ritual_live_camera_ids", []))
        # 참배객 보호가 켜져 있으면(운용 기본) 사람이 감지되는 동안 실시간 프레임을 보내지 않는다. 관리자 콘솔에서 시연용으로 끌 수 있다.
        if (live_ids or ritual_ids) and now - last_live >= 1.0 / max(1, cfg["live_fps"]):
            if not occupied or cfg.get("live_ignore_occupied"):
                for c in wall_cams:
                    for n in c["niches"]:
                        if n["id"] in live_ids:
                            uploader.submit(f"/api/edge/niches/{n['id']}/live", jpeg(crop_niche(frame, n, blur=cfg.get("blur_outside", True)), 75))
            for c in ritual_cams:
                if c["id"] in ritual_ids:
                    small = cv2.resize(frame, (960, int(frame.shape[0] * 960 / frame.shape[1])), interpolation=cv2.INTER_AREA)
                    uploader.submit(f"/api/edge/cameras/{c['id']}/ritual-live", jpeg(small, 70))
            last_live = now

        if SHOW_PREVIEW:
            view = cv2.resize(frame, (960, int(frame.shape[0] * 960 / frame.shape[1])))
            H, W = view.shape[:2]
            for c in wall_cams:
                for n in c["niches"]:
                    x, y, w, h = int(n["x"] * W), int(n["y"] * H), int(n["w"] * W), int(n["h"] * H)
                    cv2.rectangle(view, (x, y), (x + w, y + h), (0, 200, 255), 1)
                    cv2.putText(view, n["code"], (x + 3, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
            cv2.putText(view, f"{'OCCUPIED' if occupied else 'clear'}  fps {fps:.1f}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 255) if occupied else (0, 200, 0), 2)
            cv2.imshow("edge preview (q to quit)", view)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
