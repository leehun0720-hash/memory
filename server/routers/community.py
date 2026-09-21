"""Family albums, calendars, meetings, keepsakes and access management."""
import io
import json
import re
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, model_validator
from PIL import Image, ImageOps, UnidentifiedImageError

from .. import config, db
from ..community import KST, approved_ai_memories, deceased_for, events_for, local_now, media_path, memory_visible, occurrences, preferences, create_due_notifications
from ..deps import require_member, require_role

router = APIRouter(prefix='/api/family', tags=['family-community'])


def memory_for(mid, m):
    row = db.one('''SELECT mm.*,f.name AS author FROM memories mm JOIN deceased d ON d.id=mm.deceased_id
                    JOIN family_members f ON f.id=mm.member_id WHERE mm.id=? AND d.contract_id=?''', (mid,m['contract_id']))
    if not row or not memory_visible(row,m):
        raise HTTPException(404, '기억을 찾을 수 없습니다.')
    return row


@router.get('/memories')
def memories(deceased_id: int, m: dict = Depends(require_member)):
    deceased_for(deceased_id,m)
    rows = db.rows('''SELECT mm.*,f.name AS author FROM memories mm JOIN family_members f ON f.id=mm.member_id
                     WHERE mm.deceased_id=? ORDER BY mm.id DESC''', (deceased_id,))
    return [{k:v for k,v in r.items() if k != 'path'} | {'has_file':bool(r['path'])} for r in rows if memory_visible(r,m)]


@router.post('/memories')
async def add_memory(deceased_id: int = Form(...), title: str = Form(...,min_length=1,max_length=120),
                     story: str = Form('',max_length=5000), occurred_on: str = Form(''),
                     visibility: Literal['family','private'] = Form('family'),
                     file: UploadFile | None = File(None), m: dict = Depends(require_member)):
    deceased_for(deceased_id,m)
    if not title.strip():
        raise HTTPException(422,'제목을 적어 주세요.')
    if occurred_on:
        try: date.fromisoformat(occurred_on)
        except ValueError: raise HTTPException(422,'날짜를 확인해 주세요.')
    if not story.strip() and (not file or not file.filename):
        raise HTTPException(422,'이야기 또는 사진·영상·음성을 남겨 주세요.')
    path, kind = '', 'story'
    if file and file.filename:
        content = bytearray()
        while chunk := await file.read(1024*1024):
            content.extend(chunk)
            if len(content) > 30*1024*1024:
                raise HTTPException(413,'파일은 30MB까지 올릴 수 있습니다.')
        raw = bytes(content)
        ext = ''
        try:
            with Image.open(io.BytesIO(raw)) as im:
                if im.width * im.height > 25_000_000: raise HTTPException(413,'사진 크기가 너무 큽니다.')
                im.verify()
            with Image.open(io.BytesIO(raw)) as im:
                out=io.BytesIO(); ImageOps.exif_transpose(im).convert('RGB').save(out,'JPEG',quality=90)
                raw=out.getvalue()  # Strip EXIF / GPS and active metadata.
            ext,kind='.jpg','photo'
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError):
            name=(file.filename or '').lower()
            if raw[:4] == b'RIFF' and raw[8:12] == b'WAVE': ext,kind='.wav','voice'
            elif name.endswith('.mp3') and (raw[:3] == b'ID3' or (len(raw)>2 and raw[0]==255 and raw[1]&224==224)): ext,kind='.mp3','voice'
            elif len(raw)>12 and raw[4:8] == b'ftyp' and name.endswith(('.mp4','.m4a','.mov')):
                ext,kind=('.m4a','voice') if name.endswith('.m4a') else ('.mp4','video')
            elif raw[:4] == b'\x1aE\xdf\xa3' and name.endswith('.webm'): ext,kind='.webm','video'
            else: raise HTTPException(415,'사진 또는 mp3·wav·m4a·mp4·mov·webm 파일을 선택해 주세요.')
        path=f'family-{uuid.uuid4().hex}{ext}'
        (config.MEDIA_DIR/path).write_bytes(raw)
    try:
        mid=db.execute('''INSERT INTO memories(deceased_id,member_id,title,story,occurred_on,path,kind,visibility,status,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)''',(deceased_id,m['id'],title.strip(),story.strip(),occurred_on,path,kind,visibility,
                           'approved' if m['role']=='manage' else 'pending',db.now()))
    except Exception:
        if path: (config.MEDIA_DIR/path).unlink(missing_ok=True)
        raise
    db.audit(f"member:{m['id']}",'memory.add',f'memory:{mid}')
    return {'id':mid}


@router.get('/memories/{mid}/file')
def memory_file(mid:int,m:dict=Depends(require_member)):
    row=memory_for(mid,m)
    return FileResponse(media_path(row['path']),headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


class ReviewIn(BaseModel):
    status: Literal['approved','rejected']
    ai_use: bool=False
    note: str=Field('',max_length=300)


@router.put('/memories/{mid}/review')
def review_memory(mid:int,body:ReviewIn,m:dict=Depends(require_member)):
    require_role(m,'manage'); row=memory_for(mid,m)
    if body.ai_use and (body.status!='approved' or row['visibility']!='family' or not row['story'].strip()):
        raise HTTPException(422,'가족 공개로 승인된 이야기만 AI 기억으로 사용할 수 있습니다.')
    db.execute('UPDATE memories SET status=?,ai_use=?,review_note=? WHERE id=?',(body.status,int(body.ai_use),body.note,mid))
    db.audit(f"member:{m['id']}",'memory.review',f'memory:{mid}',body.status)
    return {'ok':True}


@router.delete('/memories/{mid}')
def remove_memory(mid:int,m:dict=Depends(require_member)):
    row=memory_for(mid,m)
    if row['member_id']!=m['id'] and m['role']!='manage': raise HTTPException(403)
    db.execute("UPDATE memories SET status='deleted',ai_use=0 WHERE id=?",(mid,))
    return {'ok':True}


class EventIn(BaseModel):
    title:str=Field(min_length=1,max_length=100)
    kind:Literal['anniversary','birthday','holiday','meeting']='anniversary'
    deceased_id:int|None=None
    calendar:Literal['solar','lunar']='solar'
    year:int=Field(ge=1900,le=2050)
    month:int=Field(ge=1,le=12)
    day:int=Field(ge=1,le=31)
    hour:int=Field(9,ge=0,le=23)
    minute:int=Field(0,ge=0,le=59)
    recurring:bool=True
    leap:bool=False
    leap_policy:Literal['regular','skip']='regular'
    missing_day:Literal['last','skip']='last'
    note:str=Field('',max_length=1000)

    @model_validator(mode='after')
    def valid_date(self):
        if not self.title.strip(): raise ValueError('제목을 적어 주세요.')
        if self.calendar=='solar': date(self.year,self.month,self.day)
        else:
            from korean_lunar_calendar import KoreanLunarCalendar
            cal=KoreanLunarCalendar()
            if self.day>30 or not cal.setLunarDate(self.year,self.month,self.day,self.leap) or cal.isIntercalation!=self.leap:
                raise ValueError('기준 연도에 존재하지 않는 음력 날짜 또는 윤달입니다.')
        if self.kind=='meeting' and (self.calendar!='solar' or self.recurring):
            raise ValueError('함께 참배 약속은 양력의 한 번 일정으로 등록해 주세요.')
        return self


def event_for(eid,m):
    row=db.one('SELECT * FROM family_events WHERE id=? AND contract_id=? AND cancelled=0',(eid,m['contract_id']))
    if not row: raise HTTPException(404,'일정을 찾을 수 없습니다.')
    return row


def save_event(body,m,eid=None):
    if body.deceased_id: deceased_for(body.deceased_id,m)
    data=body.model_dump()
    if body.calendar=='lunar':
        from korean_lunar_calendar import KoreanLunarCalendar
        cal=KoreanLunarCalendar()
        if not cal.setLunarDate(body.year,body.month,body.day,body.leap) or cal.isIntercalation!=body.leap:
            raise HTTPException(422,'기준 연도에 존재하지 않는 음력 날짜 또는 윤달입니다.')
    if body.kind=='meeting':
        when=datetime(body.year,body.month,body.day,body.hour,body.minute,tzinfo=KST)
        if when<local_now()-timedelta(minutes=5): raise HTTPException(422,'미래의 약속 시간을 선택해 주세요.')
    keys=list(data)
    if eid:
        with db.tx() as conn:
            conn.execute(f"UPDATE family_events SET {','.join(k+'=?' for k in keys)} WHERE id=?",[*data.values(),eid])
            conn.execute("DELETE FROM notifications WHERE event_id=? AND delivery_status IN ('in_app','pending','blocked','cancelled','expired','failed')",(eid,))
    else:
        eid=db.execute(f"INSERT INTO family_events({','.join(keys)},contract_id,member_id,created_at) VALUES({','.join('?' for _ in range(len(keys)+3))})",[*data.values(),m['contract_id'],m['id'],db.now()])
    return {'id':eid,'occurrences':[d.isoformat() for d in occurrences(data)]}


@router.get('/events')
def get_events(m:dict=Depends(require_member)):
    return events_for(m)


@router.post('/events/preview')
def preview_event(body:EventIn,m:dict=Depends(require_member)):
    # No write: validate conversion before committing the family calendar.
    if body.deceased_id: deceased_for(body.deceased_id,m)
    return {'occurrences':[d.isoformat() for d in occurrences(body.model_dump(),days=730)]}


@router.post('/events')
def add_event(body:EventIn,m:dict=Depends(require_member)):
    if body.kind!='meeting': require_role(m,'manage')
    return save_event(body,m)


@router.put('/events/{eid}')
def edit_event(eid:int,body:EventIn,m:dict=Depends(require_member)):
    event=event_for(eid,m)
    if m['role']!='manage' and (event['member_id']!=m['id'] or event['kind']!='meeting' or body.kind!='meeting'): raise HTTPException(403)
    return save_event(body,m,eid)


@router.delete('/events/{eid}')
def cancel_event(eid:int,m:dict=Depends(require_member)):
    event=event_for(eid,m)
    if m['role']!='manage' and event['member_id']!=m['id']: raise HTTPException(403)
    with db.tx() as conn:
        conn.execute('UPDATE family_events SET cancelled=1 WHERE id=?',(eid,))
        conn.execute("UPDATE notifications SET delivery_status='cancelled' WHERE event_id=? AND delivery_status IN ('pending','blocked')",(eid,))
    return {'ok':True}


class AttendanceIn(BaseModel):
    response:Literal['yes','no']


@router.put('/events/{eid}/attendance')
def attend(eid:int,body:AttendanceIn,m:dict=Depends(require_member)):
    event_for(eid,m)
    db.execute('INSERT INTO event_attendance(event_id,member_id,response) VALUES(?,?,?) ON CONFLICT(event_id,member_id) DO UPDATE SET response=excluded.response', (eid,m['id'],body.response))
    return {'ok':True}


@router.post('/events/{eid}/presence')
def presence(eid:int,m:dict=Depends(require_member)):
    event=event_for(eid,m)
    if event['kind']!='meeting': raise HTTPException(422,'함께 참배 약속이 아닙니다.')
    db.execute("INSERT INTO event_attendance(event_id,member_id,response,last_seen_at) VALUES(?,?,'yes',?) ON CONFLICT(event_id,member_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,response='yes'",(eid,m['id'],db.now()))
    return room(eid,m)


@router.get('/events/{eid}/room')
def room(eid:int,m:dict=Depends(require_member)):
    event=event_for(eid,m)
    members=db.rows('''SELECT f.name,a.response,a.last_seen_at FROM event_attendance a JOIN family_members f ON f.id=a.member_id
                       WHERE a.event_id=? AND f.revoked_at IS NULL''',(eid,))
    for member in members:
        member['present']=bool(member['last_seen_at'] and (local_now()-datetime.fromisoformat(member['last_seen_at'])).total_seconds()<45)
    return {'event':event,'members':members}


class PrefIn(BaseModel):
    enabled:bool=True
    offsets:list[int]=Field(default_factory=lambda:[7,1,0],max_length=3)
    kinds:list[Literal['anniversary','birthday','holiday','meeting']]=Field(default_factory=lambda:['anniversary','birthday','holiday','meeting'],max_length=4)
    paused_until:str=''
    phone:str=Field('',max_length=20)
    kakao:bool=False
    consent:bool=False


@router.get('/notification-preferences')
def get_pref(m:dict=Depends(require_member)):
    from ..notifications import provider_status
    return preferences(m['id']) | {'provider':provider_status()}


@router.put('/notification-preferences')
def put_pref(body:PrefIn,m:dict=Depends(require_member)):
    if set(body.offsets)-{0,1,7}: raise HTTPException(422,'알림은 7일 전·전날·당일 중 선택합니다.')
    if body.paused_until:
        try: date.fromisoformat(body.paused_until)
        except ValueError: raise HTTPException(422,'쉬는 날짜를 확인해 주세요.')
    phone=re.sub(r'[- ]','',body.phone)
    if phone and not re.fullmatch(r'010\d{8}',phone): raise HTTPException(422,'010으로 시작하는 휴대폰 번호를 확인해 주세요.')
    if body.kakao and (not body.consent or not phone): raise HTTPException(422,'알림톡 수신 동의와 휴대폰 번호가 필요합니다.')
    db.execute('''INSERT INTO notification_preferences(member_id,enabled,offsets,paused_until,kinds,phone,kakao,consent_at) VALUES(?,?,?,?,?,?,?,?)
                 ON CONFLICT(member_id) DO UPDATE SET enabled=excluded.enabled,offsets=excluded.offsets,paused_until=excluded.paused_until,kinds=excluded.kinds,phone=excluded.phone,kakao=excluded.kakao,consent_at=excluded.consent_at''',
                 (m['id'],int(body.enabled),json.dumps(sorted(set(body.offsets))),body.paused_until,json.dumps(body.kinds),phone,int(body.kakao),db.now() if body.kakao else None))
    if not body.kakao or not body.enabled or body.paused_until:
        db.execute("UPDATE notifications SET delivery_status='cancelled' WHERE member_id=? AND delivery_status IN ('pending','blocked')",(m['id'],))
    return {'ok':True}


@router.get('/notifications')
def get_notifications(m:dict=Depends(require_member)):
    create_due_notifications()
    return db.rows('''SELECT n.id,n.event_id,n.title,n.body,n.read_at,n.created_at,n.delivery_status FROM notifications n
                    JOIN family_events e ON e.id=n.event_id WHERE n.member_id=? AND e.cancelled=0 ORDER BY n.id DESC LIMIT 100''',(m['id'],))


@router.post('/notifications/{nid}/read')
def read_notification(nid:int,m:dict=Depends(require_member)):
    db.execute('UPDATE notifications SET read_at=? WHERE id=? AND member_id=?',(db.now(),nid,m['id']))
    return {'ok':True}


def ics_escape(text):
    return text.replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


@router.get('/calendar.ics')
def export_calendar(m:dict=Depends(require_member)):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Memorial//Family Calendar//KO','CALSCALE:GREGORIAN']
    pref=preferences(m['id'])
    for event in events_for(m):
        for when in occurrences(event,days=730):
            stamp=when.astimezone(timezone.utc)
            lines+=['BEGIN:VEVENT',f"UID:family-{m['contract_id']}-{event['id']}-{when.date()}@memorial.local",
                    'DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                    'DTSTART:'+stamp.strftime('%Y%m%dT%H%M%SZ'),'DTEND:'+(stamp+timedelta(minutes=30)).strftime('%Y%m%dT%H%M%SZ'),
                    'SUMMARY:'+ics_escape(event['title']),'DESCRIPTION:'+ics_escape(event['note']+'\n한국 시간 기준. 음력 일정은 변환된 날짜로 저장됩니다.')]
            if pref['enabled'] and (not pref['paused_until'] or when.date().isoformat()>pref['paused_until']) and event['kind'] in pref['kinds'] and event.get('response')!='no':
                for offset in pref['offsets']:
                    lines+=['BEGIN:VALARM',f'TRIGGER:-P{offset}D','ACTION:DISPLAY','DESCRIPTION:가족 일정','END:VALARM']
            lines+=['END:VEVENT']
    lines+=['END:VCALENDAR']
    # RFC 5545 fold without splitting UTF-8 code points.
    folded=[]
    for line in lines:
        part=''
        for char in line:
            if len((part+char).encode('utf-8'))>73: folded.append(part); part=' '+char
            else: part+=char
        folded.append(part)
    return Response('\r\n'.join(folded)+'\r\n',media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="family-calendar.ics"','Cache-Control':'no-store'})


class AccessIn(BaseModel):
    action:Literal['rotate','revoke','role']
    role:Literal['view','chat']='view'
    days:int=Field(30,ge=1,le=365)


@router.get('/access')
def get_access(m:dict=Depends(require_member)):
    require_role(m,'manage')
    return db.rows('SELECT id,name,relation,role,revoked_at,invite_expires_at,last_seen_at FROM family_members WHERE contract_id=?',(m['contract_id'],))


@router.post('/access/{mid}')
def update_access(mid:int,body:AccessIn,request:Request,m:dict=Depends(require_member)):
    require_role(m,'manage')
    target=db.one('SELECT * FROM family_members WHERE id=? AND contract_id=?',(mid,m['contract_id']))
    if not target: raise HTTPException(404)
    if target['role']=='manage' or mid==m['id']: raise HTTPException(403,'계약자 계정은 이 화면에서 변경할 수 없습니다.')
    result={'ok':True}
    if body.action=='rotate':
        token=db.token(24); expiry=(local_now()+timedelta(days=body.days)).isoformat()
        db.execute('UPDATE family_members SET invite_token=?,revoked_at=NULL,invite_expires_at=? WHERE id=?',(token,expiry,mid))
        result.update(link=f'{str(request.base_url).rstrip("/")}/?t={token}',expires_at=expiry)
    elif body.action=='revoke':
        db.execute('UPDATE family_members SET revoked_at=? WHERE id=?',(db.now(),mid))
        db.execute("UPDATE notifications SET delivery_status='cancelled' WHERE member_id=? AND delivery_status IN ('pending','blocked')",(mid,))
    else: db.execute('UPDATE family_members SET role=? WHERE id=?',(body.role,mid))
    db.audit(f"member:{m['id']}",f'access.{body.action}',f'member:{mid}')
    return result


class GuideIn(BaseModel):
    tradition:Literal['classic','buddhist','catholic','christian']='classic'
    text:str=Field('',max_length=3000)


@router.get('/guides/{did}')
def get_guide(did:int,m:dict=Depends(require_member)):
    theme=deceased_for(did,m)['theme']
    return db.one('SELECT * FROM memorial_guides WHERE deceased_id=?',(did,)) or {'tradition':theme or 'classic','text':''}


@router.put('/guides/{did}')
def set_guide(did:int,body:GuideIn,m:dict=Depends(require_member)):
    require_role(m,'manage'); deceased_for(did,m)
    db.execute('INSERT INTO memorial_guides(deceased_id,tradition,text,updated_at) VALUES(?,?,?,?) ON CONFLICT(deceased_id) DO UPDATE SET tradition=excluded.tradition,text=excluded.text,updated_at=excluded.updated_at',(did,body.tradition,body.text,db.now()))
    return {'ok':True}


class TributeIn(BaseModel):
    kind:Literal['flower','candle','bow','letter']
    message:str=Field('',max_length=1000)


@router.get('/tributes/{did}')
def get_tributes(did:int,m:dict=Depends(require_member)):
    deceased_for(did,m)
    return db.rows('SELECT t.id,t.kind,t.message,t.created_at,f.name AS author FROM tributes t JOIN family_members f ON f.id=t.member_id WHERE t.deceased_id=? ORDER BY t.id DESC LIMIT 50',(did,))


@router.post('/tributes/{did}')
def add_tribute(did:int,body:TributeIn,m:dict=Depends(require_member)):
    deceased_for(did,m)
    return {'id':db.execute('INSERT INTO tributes(deceased_id,member_id,kind,message,created_at) VALUES(?,?,?,?,?)',(did,m['id'],body.kind,body.message,db.now()))}


@router.get('/memories/{did}/ai-sources')
def ai_sources(did:int,m:dict=Depends(require_member)):
    deceased_for(did,m)
    return approved_ai_memories(did)


def archive_data(m):
    deceased=db.rows('SELECT id,name,honorific,birth_date,death_date,photo_path FROM deceased WHERE contract_id=?',(m['contract_id'],))
    albums=[]; assets=[]; media_items=[]
    for d in deceased:
        if d['photo_path']: assets.append((d['photo_path'],f"originals/{d['id']}-portrait{Path(d['photo_path']).suffix}"))
        rows=db.rows('SELECT * FROM memories WHERE deceased_id=?',(d['id'],))
        for row in rows:
            if not memory_visible(row,m): continue
            export_file=f"originals/memory-{row['id']}{Path(row['path']).suffix}" if row['path'] else ''
            if row['path']: assets.append((row['path'],export_file))
            albums.append({k:v for k,v in row.items() if k!='path'} | {'export_file':export_file})
        for row in db.rows('SELECT * FROM media WHERE deceased_id=?',(d['id'],)):
            export_file=f"originals/media-{row['id']}{Path(row['path']).suffix}"
            assets.append((row['path'],export_file))
            media_items.append({k:v for k,v in row.items() if k!='path'} | {'export_file':export_file})
        d.pop('photo_path')
    return {'deceased':deceased,'memories':albums,'media':media_items,'guestbook':db.rows('SELECT author,message,created_at FROM guestbook WHERE contract_id=? ORDER BY id',(m['contract_id'],))},assets


@router.get('/archive.zip')
def archive_zip(m:dict=Depends(require_member)):
    data,assets=archive_data(m); output=io.BytesIO(); total=0; missing=[]
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for relative,name in assets:
            try: path=media_path(relative)
            except HTTPException: missing.append(name); continue
            total+=path.stat().st_size
            if total>250*1024*1024: raise HTTPException(413,'자료가 250MB를 넘습니다. 개별 자료를 내려받거나 관리자에게 문의해 주세요.')
            z.write(path,name)
        data['missing_files']=missing
        z.writestr('family-memories.json',json.dumps(data,ensure_ascii=False,indent=2))
        z.writestr('README.txt','가족 추모 자료 보관함\noriginals: 등록된 자료 파일\nfamily-memories.json: 고인 정보, 이야기, 방명록\n사진은 등록 시 위치 정보를 제거한 보관본입니다.\n누락 파일은 missing_files에 표시됩니다.\n')
    db.audit(f"member:{m['id']}",'archive.download',f"contract:{m['contract_id']}")
    return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="family-memories.zip"','Cache-Control':'no-store'})


@router.get('/archive.pdf')
def archive_pdf(m:dict=Depends(require_member)):
    from ..keepsake import make_pdf
    data,_=archive_data(m)
    for memory in data['memories']:
        if memory['kind']=='photo':
            memory['image_path'] = db.one('SELECT path FROM memories WHERE id=?',(memory['id'],))['path']
    return Response(make_pdf(data),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="family-memories.pdf"','Cache-Control':'no-store'})
