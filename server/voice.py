"""복제 음성 등록 공통 로직. 관리자 콘솔과 유족 앱이 같이 쓴다.
흐름: 음성 자료 저장(→ mp3 변환) → 동의서 확인 → 공급자에 등록 → deceased.voice_id 저장."""
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import HTTPException

from . import config, db
from .ai import factory
from .ai.tts import TTSError


def _find_ffmpeg() -> str | None:
    """시스템 ffmpeg → 없으면 imageio-ffmpeg 가 함께 설치한 ffmpeg(Railway 등 서버에서도 동작). 둘 다 없으면 None."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG = _find_ffmpeg()
# 휴대폰 녹음 앱·음성 메시지·통화 녹음·영상에서 흔히 나오는 형식. 모두 mp3(모노·44.1kHz·128kbps)로 바꿔 공급자에 보낸다.
AUDIO_EXTS = {
    ".mp3", ".m4a", ".aac", ".wav", ".wave", ".flac", ".ogg", ".oga", ".opus", ".webm", ".weba", ".wma",
    ".amr", ".3gp", ".3ga", ".3g2", ".caf", ".aif", ".aiff", ".aifc", ".mka", ".spx",
    ".mp4", ".m4v", ".mov", ".mkv", ".avi", ".wmv", ".mpeg", ".mpg", ".ts",
}
AUDIO_EXT_LABEL = "mp3 · m4a · aac · wav · flac · ogg · opus · webm · wma · amr · 3gp · caf · aiff, 영상(mp4 · mov · mkv · avi 등)"
MIME_EXT = {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac", "audio/wav": ".wav",
            "audio/x-wav": ".wav", "audio/wave": ".wav", "audio/flac": ".flac", "audio/x-flac": ".flac", "audio/ogg": ".ogg", "audio/opus": ".opus",
            "audio/webm": ".webm", "video/webm": ".webm", "audio/amr": ".amr", "audio/3gpp": ".3gp", "video/3gpp": ".3gp", "audio/x-ms-wma": ".wma",
            "audio/aiff": ".aiff", "audio/x-aiff": ".aiff", "audio/x-caf": ".caf", "video/mp4": ".mp4", "video/quicktime": ".mov"}
MAX_BYTES = 100 * 1024 * 1024    # 영상 파일까지 받으므로 넉넉히. 변환 뒤에는 앞 5분만 쓴다
MAX_SECONDS = 300                # 공급자에 보내는 한 파일의 최대 길이(목소리 복제는 1~3분이면 충분)
MIN_FILE_SECONDS = 3             # 파일 하나가 이보다 짧으면 소리가 거의 없는 것으로 본다
MIN_SECONDS = 15                 # 등록에 쓰는 자료 전체 길이의 최소값(여러 파일을 합쳐서)
MIME = {".mp3": "audio/mpeg"}


def _duration(path: Path) -> float | None:
    """ffmpeg 로 길이를 잰다(ffprobe 가 없어도 됨)."""
    if not FFMPEG:
        return None
    try:
        r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr or "")
        if not m:
            return None
        h, mi, se = m.groups()
        return int(h) * 3600 + int(mi) * 60 + float(se)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def _to_mp3(src: Path) -> Path:
    """어떤 형식이든 공급자가 확실히 받는 mp3(모노·44.1kHz·128kbps)로 바꾼다. 영상이면 소리만 꺼낸다.
    낮은 웅웅거림을 걸러 내고(70Hz 이하) 소리 크기를 고르게 맞춘다. 앞 5분만 쓴다."""
    if not FFMPEG:
        if src.suffix.lower() == ".mp3":
            return src
        src.unlink(missing_ok=True)
        raise HTTPException(503, "서버에 음성 변환 도구(ffmpeg)가 없어 mp3 파일만 받을 수 있습니다. 시설 담당자에게 알려 주세요.")
    dest = src.with_name(src.stem + "-voice.mp3")
    try:
        r = subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-t", str(MAX_SECONDS), "-vn", "-sn", "-dn",
                            "-af", "highpass=f=70,loudnorm=I=-18:TP=-2:LRA=11", "-ac", "1", "-ar", "44100", "-b:a", "128k", str(dest)],
                           capture_output=True, timeout=300)
        ok = r.returncode == 0 and dest.exists() and dest.stat().st_size > 1000
    except (subprocess.SubprocessError, OSError):
        ok = False
    src.unlink(missing_ok=True)
    if not ok:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "이 파일에서 소리를 읽지 못했습니다. 파일이 손상되었거나 소리가 없는 영상일 수 있습니다. "
                                 "휴대폰 녹음 앱에서 다시 내보내거나 다른 파일로 올려 주세요.")
    return dest


def _ext_of(filename: str, content_type: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in AUDIO_EXTS:
        return ext
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in MIME_EXT:
        return MIME_EXT[ct]
    if not ext and (ct.startswith("audio/") or ct.startswith("video/")):
        return ".bin"           # 확장자 없는 녹음 파일: ffmpeg 가 내용을 보고 판단한다
    raise HTTPException(400, f"음성이나 영상 파일만 올릴 수 있습니다({AUDIO_EXT_LABEL}).")


def save_sample(deceased_id: int, filename: str, data: bytes, caption: str, content_type: str | None = None) -> dict:
    ext = _ext_of(filename, content_type)
    if len(data) > MAX_BYTES:
        raise HTTPException(400, f"파일이 너무 큽니다({len(data) / 1024 / 1024:.0f}MB). 100MB 이하로 올려 주세요. 영상이면 소리만 있는 파일로 바꾸면 작아집니다.")
    if len(data) < 2000:
        raise HTTPException(400, "녹음이 비어 있습니다. 다시 녹음해 주세요.")
    folder = config.MEDIA_DIR / "voice"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    path = _to_mp3(path)
    secs = _duration(path)
    if secs is not None and secs < MIN_FILE_SECONDS:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"‘{filename or '녹음'}’은 {secs:.0f}초라 너무 짧습니다. 또렷한 목소리가 담긴 파일을 올려 주세요.")
    rel = f"voice/{path.name}"
    mid = db.execute("INSERT INTO media(deceased_id, kind, path, caption, ai_generated, created_at) VALUES (?,?,?,?,0,?)",
                     (deceased_id, "voice", rel, caption + (f" ({secs:.0f}초)" if secs else ""), db.now()))
    return {"media_id": mid, "path": rel, "seconds": secs}


def samples(deceased_id: int, limit: int = 5) -> list[dict]:
    """등록에 쓸 최근 음성 자료(최대 5개)와 길이."""
    out = []
    for smp in db.rows("SELECT id, path, caption, created_at FROM media WHERE deceased_id=? AND kind='voice' ORDER BY id DESC LIMIT ?", (deceased_id, limit)):
        fp = config.MEDIA_DIR / smp["path"]
        if fp.exists():
            out.append({**smp, "file": fp, "seconds": _duration(fp)})
    return out


def provider_ready() -> bool:
    return factory.tts().name != "browser"


def register(deceased_id: int, actor: str) -> dict:
    d = db.one("SELECT * FROM deceased WHERE id=?", (deceased_id,))
    if not d:
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if not db.one("SELECT id FROM consents WHERE deceased_id=? AND kind IN ('voice','lifetime_record') AND revoked_at IS NULL", (deceased_id,)):
        raise HTTPException(403, "음성 사용(또는 생전 기록) 동의서가 없어 등록할 수 없습니다.")
    if not provider_ready():
        raise HTTPException(400, "시설에서 아직 목소리 등록 기능을 켜지 않았습니다(관리자 콘솔 → 인공지능 설정 → ElevenLabs 키).")
    found = samples(deceased_id)
    if not found:
        raise HTTPException(400, "먼저 음성 자료를 올려 주세요. 깨끗한 목소리 1~2분이면 충분합니다.")
    total = sum(x["seconds"] or 0 for x in found)
    if FFMPEG and total < MIN_SECONDS:
        raise HTTPException(400, f"음성 자료가 모두 합쳐 {total:.0f}초입니다. {MIN_SECONDS}초 이상(1분 정도 권장) 되도록 더 녹음하거나 올려 주세요.")
    files = [(x["file"].name, x["file"].read_bytes(), MIME.get(x["file"].suffix.lower(), "audio/mpeg")) for x in found]
    provider = factory.tts()
    try:
        if d["voice_id"] and d["voice_provider"] == provider.name:
            provider.delete_voice(d["voice_id"])
        vid = provider.add_voice(f"memorial-{deceased_id}-{d['name']}", files, f"{d['name']} ({d['honorific']})")
    except TTSError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.message)
    db.execute("UPDATE deceased SET voice_id=?, voice_provider=? WHERE id=?", (vid, provider.name, deceased_id))
    db.audit(actor, "voice.register", f"deceased:{deceased_id}", f"{provider.name} {len(files)} files")
    return {"voice_id": vid, "provider": provider.name, "files": len(files), "seconds": round(total) if total else None}


def delete(deceased_id: int, actor: str) -> None:
    d = db.one("SELECT voice_id, voice_provider FROM deceased WHERE id=?", (deceased_id,))
    if not d or not d["voice_id"]:
        return
    try:
        p = factory.tts()
        if d["voice_provider"] == p.name and p.name != "browser":
            p.delete_voice(d["voice_id"])
    except Exception as e:  # 공급자 쪽 삭제 실패는 기록만 하고 우리 쪽은 지운다
        db.audit(actor, "voice.delete_failed", f"deceased:{deceased_id}", str(e)[:200])
    db.execute("UPDATE deceased SET voice_id='', voice_provider='' WHERE id=?", (deceased_id,))
    db.audit(actor, "voice.delete", f"deceased:{deceased_id}")


def preview(deceased_id: int, text: str) -> tuple[bytes, str]:
    d = db.one("SELECT voice_id FROM deceased WHERE id=?", (deceased_id,))
    if not d or not d["voice_id"]:
        raise HTTPException(404, "등록된 음성이 없습니다.")
    try:
        r = factory.tts().synthesize(text[:200], d["voice_id"])
    except TTSError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.message)
    if r.audio is None:
        raise HTTPException(400, "복제 음성 공급자가 꺼져 있습니다.")
    return r.audio, r.mime
