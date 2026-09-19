"""현장 프로그램(edge/agent.py) ↔ 서버. 현장에서 밖으로 나가는 요청만 있다."""
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import config, db
from ..deps import require_edge
from ..state import state

def _in_window(scheduled_at: str, before_min: int = 30, after_h: int = 3) -> bool:
    """봉행 30분 전부터 3시간 뒤까지 중계 창을 연다."""
    try:
        t = datetime.fromisoformat(scheduled_at)
    except (TypeError, ValueError):
        return False
    if t.tzinfo is None:
        t = t.astimezone()
    now = datetime.now().astimezone()
    return t - timedelta(minutes=before_min) <= now <= t + timedelta(hours=after_h)


def _atomic_write(path, data: bytes) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


router = APIRouter(prefix="/api/edge", tags=["edge"], dependencies=[Depends(require_edge)])


@router.get("/config")
def edge_config():
    cams = db.rows("SELECT * FROM cameras ORDER BY id")
    for c in cams:
        c["niches"] = db.rows("SELECT id, code, x, y, w, h FROM niches WHERE camera_id=? ORDER BY id", (c["id"],))
    live = db.rows("SELECT DISTINCT niche_id FROM live_sessions WHERE expires_at > ?", (db.now(),))
    ritual_live = [r["camera_id"] for r in db.rows("SELECT camera_id, scheduled_at FROM rituals WHERE camera_id IS NOT NULL") if _in_window(r["scheduled_at"])]
    return {
        "cameras": cams,
        "live_niche_ids": [r["niche_id"] for r in live],
        "ritual_live_camera_ids": sorted(set(ritual_live)),
        "snapshot_interval": config.SNAPSHOT_INTERVAL,
        "live_fps": config.LIVE_FPS,
    }


@router.post("/cameras/{cam_id}/status")
def camera_status(cam_id: int, occupied: bool = Form(...), persons: int = Form(0), fps: float = Form(0.0)):
    if not db.one("SELECT id FROM cameras WHERE id=?", (cam_id,)):
        raise HTTPException(404, "camera")
    state.set_camera(cam_id, occupied, persons, fps)
    db.execute("UPDATE cameras SET last_seen_at=? WHERE id=?", (db.now(), cam_id))
    return {"ok": True}


@router.post("/cameras/{cam_id}/frame")
async def camera_frame(cam_id: int, file: UploadFile = File(...)):
    """관리자 칸 좌표 등록용 전체 화면. 현장 프로그램은 사람이 없을 때만 보낸다."""
    if not db.one("SELECT id FROM cameras WHERE id=?", (cam_id,)):
        raise HTTPException(404, "camera")
    data = await file.read()
    state.push_full(cam_id, data)
    _atomic_write(config.FRAME_DIR / f"cam_{cam_id}.jpg", data)
    return {"ok": True}


@router.post("/niches/{niche_id}/snapshot")
async def niche_snapshot(niche_id: int, file: UploadFile = File(...)):
    """내 칸만 잘라내고 바깥을 흐린 사진. 10초마다 갱신."""
    if not db.one("SELECT id FROM niches WHERE id=?", (niche_id,)):
        raise HTTPException(404, "niche")
    data = await file.read()
    _atomic_write(config.SNAPSHOT_DIR / f"{niche_id}.jpg", data)
    db.execute("UPDATE niches SET last_snapshot_at=? WHERE id=?", (db.now(), niche_id))
    return {"ok": True}


@router.post("/niches/{niche_id}/live")
async def niche_live(niche_id: int, file: UploadFile = File(...)):
    """실시간 보기 프레임. 메모리에만 두고 저장하지 않는다."""
    data = await file.read()
    state.push_live(niche_id, data)
    return {"ok": True}


@router.post("/cameras/{cam_id}/ritual-live")
async def ritual_live(cam_id: int, file: UploadFile = File(...)):
    """제례 공간 카메라 중계 프레임(전체 화면). niche id 대신 음수 카메라 키를 쓴다."""
    data = await file.read()
    state.push_live(-cam_id, data)
    return {"ok": True}
