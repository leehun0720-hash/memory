"""FastAPI 앱. 유족 웹앱(/), 관리자 콘솔(/admin), API(/api/*)."""
import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import admin, chat, edge, family, community

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
    from .notifications import run
    stop = asyncio.Event()
    worker = asyncio.create_task(run(stop))
    try:
        yield
    finally:
        stop.set()
        await worker


app = FastAPI(title="봉안함 원격 참배·AI 추모 대화 MVP", version="0.1.0", lifespan=lifespan)
app.include_router(edge.router)
app.include_router(family.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(community.router)


def _page(name: str) -> HTMLResponse:
    """정적 HTML을 내보내되 js/css 주소에 수정 시각을 붙여 브라우저 캐시가 옛 파일을 쓰지 않게 한다."""
    html = (STATIC / name).read_text(encoding="utf-8")
    for rel in ("css/app.css", "css/family.css", "css/community.css", "js/community.js", "js/app.js", "js/admin.js", "js/screen.js"):
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


@app.get("/screen", include_in_schema=False)
def screen_page():
    """제례 공간 TV용 현장 화면(/screen?ritual=ID&key=관리자키)."""
    return _page("screen.html")


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}


@app.get("/api/launcher", include_in_schema=False)
def launcher(request: Request):
    """같은 컴퓨터에서 초대 링크 없이 /를 열었을 때 보여 주는 시작 화면용 바로가기(관리자 콘솔·시연 계정).
    로컬(127.0.0.1) 직접 접속에만 열리고, 프록시 뒤·서버리스(EPHEMERAL)·외부 접속에는 404."""
    client = (request.client.host if request.client else "") or ""
    host = request.headers.get("host", "").split(":")[0].strip("[]")
    if (client not in ("127.0.0.1", "::1") or host not in ("127.0.0.1", "localhost", "::1")
            or request.headers.get("x-forwarded-for") or config.EPHEMERAL or config.LAUNCHER_DISABLED):
        raise HTTPException(404)
    members = db.rows(
        """SELECT m.id, m.name, m.relation, m.role, m.invite_token, c.holder_name, c.plan, n.code AS niche_code,
                  (SELECT GROUP_CONCAT(d.name, ', ') FROM deceased d WHERE d.contract_id=c.id) AS deceased_names
           FROM family_members m JOIN contracts c ON c.id=m.contract_id LEFT JOIN niches n ON n.id=c.niche_id ORDER BY m.id""")
    fac = db.one("SELECT name FROM facilities LIMIT 1")
    return {
        "facility": fac["name"] if fac else "",
        "admin_url": f"/admin?key={config.ADMIN_KEY}",
        "members": [{"id": r["id"], "name": r["name"], "relation": r["relation"], "role": r["role"], "holder_name": r["holder_name"],
                     "plan": r["plan"], "niche_code": r["niche_code"], "deceased_names": r["deceased_names"] or "",
                     "url": f"/?t={r['invite_token']}"} for r in members],
    }


app.mount("/static", StaticFiles(directory=STATIC), name="static")
