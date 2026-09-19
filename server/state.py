"""프로세스 메모리 상태: 라이브 프레임, 카메라 상태. 저장하지 않는다(계획서: 영상 미저장)."""
import threading
import time
from dataclasses import dataclass, field


@dataclass
class CameraStatus:
    occupied: bool = False        # 사람 감지됨 → 송출 중단
    persons: int = 0
    fps: float = 0.0
    updated_at: float = 0.0

    @property
    def online(self) -> bool:
        return time.time() - self.updated_at < 15


@dataclass
class LiveFrame:
    data: bytes
    seq: int
    at: float


class State:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.cameras: dict[int, CameraStatus] = {}
        self.live_frames: dict[int, LiveFrame] = {}
        self.full_frames: dict[int, LiveFrame] = {}   # 관리자 좌표 등록용 전체 화면(사람 없을 때만 갱신)
        self._seq = 0
        self._new_frame = threading.Condition(self._lock)
        self.viewers: dict[int, dict[int, float]] = {}     # 생중계 시청자: ritual_id → {member_id: 마지막 확인 시각}
        self.reactions: dict[int, list] = {}               # 반응(합장·촛불…)은 저장하지 않고 메모리에 최근 200개만
        self._rseq = 0

    def set_camera(self, cam_id: int, occupied: bool, persons: int, fps: float) -> None:
        with self._lock:
            self.cameras[cam_id] = CameraStatus(occupied, persons, fps, time.time())

    def camera(self, cam_id: int) -> CameraStatus:
        with self._lock:
            return self.cameras.get(cam_id, CameraStatus())

    def push_live(self, niche_id: int, data: bytes) -> None:
        with self._new_frame:
            self._seq += 1
            self.live_frames[niche_id] = LiveFrame(data, self._seq, time.time())
            self._new_frame.notify_all()

    def wait_live(self, niche_id: int, after_seq: int, timeout: float = 1.0) -> LiveFrame | None:
        """after_seq 이후의 새 프레임을 timeout까지 기다린다."""
        deadline = time.time() + timeout
        with self._new_frame:
            while True:
                f = self.live_frames.get(niche_id)
                if f and f.seq > after_seq:
                    return f
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._new_frame.wait(remaining)

    # ---- 제사 생중계: 시청자 · 반응 ----
    def touch_viewer(self, ritual_id: int, member_id: int) -> None:
        with self._lock:
            self.viewers.setdefault(ritual_id, {})[member_id] = time.time()

    def viewer_count(self, ritual_id: int, within: float = 8.0) -> int:
        with self._lock:
            now = time.time()
            return sum(1 for t in self.viewers.get(ritual_id, {}).values() if now - t < within)

    def push_reaction(self, ritual_id: int, emoji: str, author: str) -> int:
        with self._lock:
            self._rseq += 1
            lst = self.reactions.setdefault(ritual_id, [])
            lst.append((self._rseq, emoji, author, time.time()))
            del lst[:-200]
            return self._rseq

    def reactions_since(self, ritual_id: int, seq: int) -> list[dict]:
        with self._lock:
            return [{"seq": s, "emoji": e, "author": a} for (s, e, a, _t) in self.reactions.get(ritual_id, []) if s > seq]

    def reaction_seq(self, ritual_id: int) -> int:
        with self._lock:
            lst = self.reactions.get(ritual_id, [])
            return lst[-1][0] if lst else 0

    def push_full(self, cam_id: int, data: bytes) -> None:
        with self._lock:
            self._seq += 1
            self.full_frames[cam_id] = LiveFrame(data, self._seq, time.time())

    def full(self, cam_id: int) -> LiveFrame | None:
        with self._lock:
            return self.full_frames.get(cam_id)


state = State()
