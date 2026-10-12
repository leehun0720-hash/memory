"""호출 횟수 제한(2026-10-12). 인공지능·음성 요금 남용과 관리자 키 대입을 막는다.
서버 인스턴스가 하나(SQLite)라 메모리 창(sliding window)으로 충분하다. 재시작하면 초기화된다."""
import threading
import time
from collections import deque

from fastapi import HTTPException

_lock = threading.Lock()
_hits: dict[str, deque] = {}


def hit(key: str, limit: int, window: float, message: str = "요청이 너무 많습니다. 잠시 뒤 다시 시도해 주세요.") -> None:
    """key 로 window 초 안에 limit 번까지 허용한다. 넘으면 429."""
    now = time.time()
    with _lock:
        q = _hits.setdefault(key, deque())
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, message)
        q.append(now)
        if len(_hits) > 20000:   # 오래된 키 정리
            for k in [k for k, v in _hits.items() if not v or v[-1] <= now - 86400]:
                _hits.pop(k, None)


def reset() -> None:
    with _lock:
        _hits.clear()
