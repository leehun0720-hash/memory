"""생전 좋아하신 노래 (2026-10-12).

가족(계약자)이 고인이 생전에 좋아하던 노래 파일을 올리면, 참배(실시간으로 뵙기)·추모 공간에서 틀 수 있다.
목소리 복제용 voice.py 와 달리 소리를 그대로 살린다: 스테레오 · 192kbps mp3 · 최대 10분 · 소리 크기만 고르게.
형식 검사·ffmpeg 찾기·길이 재기는 voice.py 의 것을 함께 쓴다. 저장은 media(kind='music', caption=곡 제목).
가족끼리만 듣는 개인 자료이며 밖으로 공유하지 않는다(가족이 가진 음원만 올리도록 화면에서 안내).
"""
from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException

from . import config, db, voice

MAX_SECONDS = 600          # 한 곡 10분까지
MAX_SONGS = 20             # 고인 한 분당(파일 + 링크 합쳐서)
KINDS = ("music", "music_link")   # music = 올린 파일(mp3), music_link = 공식 임베드 링크(path 에 임베드 주소)

# 공식 임베드 재생기만 붙인다(권리 처리는 그 플랫폼이 한다). 가족은 링크만 붙여 넣고, 화면은 iframe 으로 띄운다.
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SP_ID = re.compile(r"^[A-Za-z0-9]{10,40}$")
PROVIDER_NAME = {"youtube": "유튜브", "spotify": "스포티파이", "apple": "애플 뮤직"}


def parse_link(url: str) -> dict:
    """공유 링크 → 공식 임베드 주소. 지원: YouTube(youtu.be · watch · shorts · music), Spotify(track · album · playlist · episode), Apple Music."""
    u = (url or "").strip()
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    try:
        p = urlparse(u)
    except ValueError:
        raise HTTPException(400, "링크 모양이 맞지 않습니다.")
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    parts = [x for x in p.path.split("/") if x]
    if host in ("youtu.be", "youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if host == "youtu.be" and parts:
            vid = parts[0]
        elif parts and parts[0] in ("shorts", "embed", "live", "v") and len(parts) > 1:
            vid = parts[1]
        else:
            vid = (parse_qs(p.query).get("v") or [""])[0]
        if not _YT_ID.match(vid):
            raise HTTPException(400, "유튜브 영상 링크를 찾지 못했습니다. 영상 화면의 '공유' 링크를 붙여 넣어 주세요.")
        return {"provider": "youtube", "provider_name": PROVIDER_NAME["youtube"], "embed_url": f"https://www.youtube-nocookie.com/embed/{vid}", "watch_url": f"https://youtu.be/{vid}"}
    if host == "open.spotify.com":
        q = [x for x in parts if x != "embed"]
        if len(q) >= 2 and q[-2] in ("track", "album", "playlist", "episode") and _SP_ID.match(q[-1]):
            kind, sid = q[-2], q[-1]
            return {"provider": "spotify", "provider_name": PROVIDER_NAME["spotify"], "embed_url": f"https://open.spotify.com/embed/{kind}/{sid}", "watch_url": f"https://open.spotify.com/{kind}/{sid}"}
        raise HTTPException(400, "스포티파이 곡·앨범·재생 목록 링크를 붙여 넣어 주세요.")
    if host in ("music.apple.com", "embed.music.apple.com"):
        if len(parts) >= 3 and parts[1] in ("album", "song", "playlist", "music-video") and re.match(r"^[A-Za-z0-9._%-]+$", parts[0]):
            path = "/" + "/".join(parts)
            q = parse_qs(p.query).get("i")
            tail = f"?i={q[0]}" if q and re.match(r"^[0-9]+$", q[0]) else ""
            return {"provider": "apple", "provider_name": PROVIDER_NAME["apple"], "embed_url": f"https://embed.music.apple.com{path}{tail}", "watch_url": f"https://music.apple.com{path}{tail}"}
        raise HTTPException(400, "애플 뮤직 곡·앨범 링크를 붙여 넣어 주세요.")
    raise HTTPException(400, "유튜브 · 스포티파이 · 애플 뮤직 링크만 넣을 수 있습니다.")


def _count(deceased_id: int) -> int:
    return (db.one("SELECT COUNT(*) AS n FROM media WHERE deceased_id=? AND kind IN ('music','music_link')", (deceased_id,)) or {"n": 0})["n"]


def add_link(deceased_id: int, url: str, title: str) -> dict:
    info = parse_link(url)
    if _count(deceased_id) >= MAX_SONGS:
        raise HTTPException(400, f"노래는 {MAX_SONGS}곡까지 넣을 수 있습니다. 듣지 않는 곡을 먼저 빼 주세요.")
    title = ((title or "").strip() or f"{info['provider_name']} 노래")[:80]
    mid = db.execute("INSERT INTO media(deceased_id, kind, path, caption, ai_generated, created_at) VALUES (?,?,?,?,0,?)",
                     (deceased_id, "music_link", info["embed_url"], title, db.now()))
    return {"id": mid, "title": title, "kind": "link", **info}


def _row(r: dict) -> dict:
    if r.pop("kind") == "music_link":
        embed = r.pop("path")
        host = urlparse(embed).hostname or ""
        prov = "youtube" if "youtube" in host else "spotify" if "spotify" in host else "apple"
        r.update(kind="link", embed_url=embed, provider=prov, provider_name=PROVIDER_NAME[prov])
    else:
        r.pop("path", None)
        r["kind"] = "file"
    return r


def _to_music_mp3(src: Path) -> Path:
    if not voice.FFMPEG:
        if src.suffix.lower() == ".mp3":
            return src
        src.unlink(missing_ok=True)
        raise HTTPException(503, "서버에 음원 변환 도구(ffmpeg)가 없어 mp3 파일만 받을 수 있습니다. 시설 담당자에게 알려 주세요.")
    dest = src.with_name(src.stem + "-music.mp3")
    try:
        r = subprocess.run([voice.FFMPEG, "-y", "-hide_banner", "-nostdin", "-loglevel", "error", "-protocol_whitelist", "file", "-i", str(src),
                            "-t", str(MAX_SECONDS), "-vn", "-sn", "-dn", "-af", "loudnorm=I=-18:TP=-1.5:LRA=14",
                            "-ac", "2", "-ar", "44100", "-b:a", "192k", str(dest)], capture_output=True, timeout=600)
        ok = r.returncode == 0 and dest.exists() and dest.stat().st_size > 1000
    except (subprocess.SubprocessError, OSError):
        ok = False
    src.unlink(missing_ok=True)
    if not ok:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "이 파일에서 소리를 읽지 못했습니다. 파일이 손상되었거나 소리가 없는 영상일 수 있습니다. 다른 파일로 올려 주세요.")
    return dest


def save(deceased_id: int, filename: str, data: bytes, title: str, content_type: str | None = None) -> dict:
    title = (title or "").strip() or Path(filename or "").stem.strip() or "생전 좋아하신 노래"
    title = title[:80]
    if _count(deceased_id) >= MAX_SONGS:
        raise HTTPException(400, f"노래는 {MAX_SONGS}곡까지 올릴 수 있습니다. 듣지 않는 곡을 먼저 빼 주세요.")
    ext = voice._ext_of(filename, content_type)
    if len(data) > voice.MAX_BYTES:
        raise HTTPException(400, f"파일이 너무 큽니다({len(data) / 1024 / 1024:.0f}MB). 100MB 이하로 올려 주세요.")
    if len(data) < 2000:
        raise HTTPException(400, "파일이 비어 있습니다. 다른 파일로 올려 주세요.")
    head = data[:64].lstrip().lower()
    if head.startswith((b"#extm3u", b"ffconcat", b"[playlist]", b"<?xml", b"<asx", b"v=0", b"#ext")):
        raise HTTPException(400, "재생 목록 파일은 올릴 수 없습니다. 실제 음원 파일을 올려 주세요.")
    folder = config.MEDIA_DIR / "music"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    path = _to_music_mp3(path)
    secs = voice._duration(path)
    if secs is not None and secs < 5:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"‘{title}’은 {secs:.0f}초라 너무 짧습니다. 노래 파일을 올려 주세요.")
    rel = f"music/{path.name}"
    mid = db.execute("INSERT INTO media(deceased_id, kind, path, caption, ai_generated, created_at, seconds) VALUES (?,?,?,?,0,?,?)",
                     (deceased_id, "music", rel, title, db.now(), round(secs) if secs else None))
    return {"id": mid, "title": title, "seconds": round(secs) if secs else None}


def songs(deceased_id: int) -> list[dict]:
    return [_row(r) for r in db.rows("SELECT id, kind, path, caption AS title, seconds, created_at FROM media WHERE deceased_id=? AND kind IN ('music','music_link') ORDER BY id", (deceased_id,))]


def remove(media_id: int) -> None:
    r = db.one("SELECT kind, path, deceased_id FROM media WHERE id=? AND kind IN ('music','music_link')", (media_id,))
    if not r:
        return
    if r["kind"] == "music":
        (config.MEDIA_DIR / r["path"]).unlink(missing_ok=True)
    db.execute("DELETE FROM media WHERE id=?", (media_id,))
    db.execute("UPDATE deceased SET visit_music_id=NULL WHERE id=? AND visit_music_id=?", (r["deceased_id"], media_id))
