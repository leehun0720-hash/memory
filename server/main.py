"""FastAPI 앱. 유족 웹앱(/), 관리자 콘솔(/admin), API(/api/*)."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import admin, chat, edge, family

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC = Path(__file__).parent / "static"



@asynccontextmanager
async def lifespan(_: FastAPI):
    db.connect()
    if config.EPHEMERAL:
        logging.getLogger(__name__).warning("데이터 폴더가 읽기 전용이라 %s 를 씁니다. 서버리스에서는 인스턴스가 바뀌면 데이터가 사라집니다.", config.DATA_DIR)
    if config.AUTO_SEED and not db.one("SELECT id FROM facilities LIMIT 1"):
        from . import seed
        seed.run(quiet=True)
        logging.getLogger(__name__).info("AUTO_SEED: 시연 데이터를 만들었습니다.")
    yield


app = FastAPI(title="봉안함 원격 참배·AI 추모 대화 MVP", version="0.1.0", lifespan=lifespan)
app.include_router(edge.router)
app.include_router(family.router)
app.include_router(chat.router)
app.include_router(admin.router)


def _page(name: str) -> HTMLResponse:
    """정적 HTML을 내보내되 js/css 주소에 수정 시각을 붙여 브라우저 캐시가 옛 파일을 쓰지 않게 한다."""
    html = (STATIC / name).read_text(encoding="utf-8")
    for rel in ("css/app.css", "js/app.js", "js/admin.js"):
        f = STATIC / rel
        if f.exists():
            html = html.replace(f"/static/{rel}", f"/static/{rel}?v={int(f.stat().st_mtime)}")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
def family_app():
    return _page("index.html")


@app.get("/admin", include_in_schema=False)
def admin_app():
    return _page("admin.html")


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")
