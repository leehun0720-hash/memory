"""복제 음성 등록 공통 로직. 관리자 콘솔과 유족 앱이 같이 쓴다.
흐름: 음성 자료 저장(→ mp3 변환) → 동의서 확인 → 공급자에 등록 → deceased.voice_id 저장."""
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import HTTPException

from . import config, db
from .ai import factory
from .ai.tts import TTSError

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".webm", ".ogg", ".mp4", ".aac", ".flac"}
MAX_BYTES = 25 * 1024 * 1024
MIN_SECONDS = 15          # 이보다 짧으면 복제 품질이 나빠 거부
MIME = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg", ".mp4": "video/mp4", ".aac": "audio/aac", ".flac": "audio/flac"}


def _duration(path: Path) -> float | None:
    if not FFPROBE:
        return None
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except (subprocess.SubprocessError, ValueError):
        return None


def _to_mp3(src: Path) -> Path:
    """브라우저 녹음(webm/opus, mp4)을 공급자가 확실히 받는 mp3(모노 44.1k)로 바꾼다. ffmpeg가 없으면 원본 그대로."""
    if src.suffix.lower() == ".mp3" or not FFMPEG:
        return src
    dest = src.with_suffix(".mp3")
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k", str(dest)],
                       capture_output=True, timeout=180)
    if r.returncode != 0 or not dest.exists():
        return src
    src.unlink(missing_ok=True)
    return dest


def save_sample(deceased_id: int, filename: str, data: bytes, caption: str) -> dict:
    ext = Path(filename or "").suffix.lower() or ".webm"
    if ext not in AUDIO_EXTS:
        raise HTTPException(400, "음성 파일(mp3, m4a, wav, webm, ogg)만 올릴 수 있습니다.")
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "파일이 너무 큽니다(25MB 이하).")
    if len(data) < 2000:
        raise HTTPException(400, "녹음이 비어 있습니다. 다시 녹음해 주세요.")
    folder = config.MEDIA_DIR / "voice"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    path = _to_mp3(path)
    secs = _duration(path)
    if secs is not None and secs < MIN_SECONDS:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"녹음이 {secs:.0f}초라 너무 짧습니다. {MIN_SECONDS}초 이상, 1분 정도가 좋습니다.")
    rel = f"voice/{path.name}"
    mid = db.execute("INSERT INTO media(deceased_id, kind, path, caption, ai_generated, created_at) VALUES (?,?,?,?,0,?)",
                     (deceased_id, "voice", rel, caption + (f" ({secs:.0f}초)" if secs else ""), db.now()))
    return {"media_id": mid, "path": rel, "seconds": secs}


def provider_ready() -> bool:
    return factory.tts().name != "browser"


def register(deceased_id: int, actor: str) -> dict:
    d = db.one("SELECT * FROM deceased WHERE id=?", (deceased_id,))
    if not d:
        raise HTTPException(404, "고인 정보를 찾을 수 없습니다.")
    if not db.one("SELECT id FROM consents WHERE deceased_id=? AND kind IN ('voice','lifetime_record') AND revoked_at IS NULL", (deceased_id,)):
        raise HTTPException(403, "음성 사용(또는 생전 기록) 동의서가 없어 등록할 수 없습니다.")
    if not provider_ready():
        raise HTTPException(400, "봉안당에서 아직 음성 복제 기능을 켜지 않았습니다(관리자 콘솔 → AI 설정 → ElevenLabs 키).")
    samples = db.rows("SELECT path FROM media WHERE deceased_id=? AND kind='voice' ORDER BY id DESC LIMIT 5", (deceased_id,))
    files = []
    for smp in samples:
        fp = config.MEDIA_DIR / smp["path"]
        if fp.exists():
            files.append((fp.name, fp.read_bytes(), MIME.get(fp.suffix.lower(), "application/octet-stream")))
    if not files:
        raise HTTPException(400, "먼저 음성 자료를 올려 주세요. 깨끗한 목소리 1~2분이면 충분합니다.")
    provider = factory.tts()
    try:
        if d["voice_id"] and d["voice_provider"] == provider.name:
            provider.delete_voice(d["voice_id"])
        vid = provider.add_voice(f"memorial-{deceased_id}-{d['name']}", files, f"{d['name']} ({d['honorific']})")
    except TTSError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.message)
    db.execute("UPDATE deceased SET voice_id=?, voice_provider=? WHERE id=?", (vid, provider.name, deceased_id))
    db.audit(actor, "voice.register", f"deceased:{deceased_id}", f"{provider.name} {len(files)} files")
    return {"voice_id": vid, "provider": provider.name, "files": len(files)}


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
