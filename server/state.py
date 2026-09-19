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

    def push_full(self, cam_id: int, data: bytes) -> None:
        with self._lock:
            self._seq += 1
            self.full_frames[cam_id] = LiveFrame(data, self._seq, time.time())

    def full(self, cam_id: int) -> LiveFrame | None:
        with self._lock:
            return self.full_frames.get(cam_id)


state = State()
