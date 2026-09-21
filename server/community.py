"""Shared family calendar and memory authorization. All schedule dates use Korea time."""
import calendar
import json
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from korean_lunar_calendar import KoreanLunarCalendar
from . import config, db

KST = timezone(timedelta(hours=9))

def local_now():
    return datetime.now(KST)


def deceased_for(did, member):
    result = db.one('SELECT * FROM deceased WHERE id=? AND contract_id=?', (did, member['contract_id']))
    if not result:
        raise HTTPException(404, '고인 정보를 찾을 수 없습니다.')
    return result


def memory_visible(row, member):
    return row['status'] != 'deleted' and (member['role'] == 'manage' or row['member_id'] == member['id'] or
            (row['status'] == 'approved' and row['visibility'] == 'family'))


def media_path(relative):
    base = config.MEDIA_DIR.resolve()
    path = (base / relative).resolve()
    if not relative or not path.is_relative_to(base) or not path.is_file():
        raise HTTPException(404, '파일을 찾을 수 없습니다.')
    return path


@lru_cache(maxsize=4096)
def event_date(year, month, day, system, leap, leap_policy, missing_day):
    if system == 'solar':
        try:
            return date(year, month, day)
        except ValueError:
            if missing_day == 'last':
                return date(year, month, calendar.monthrange(year, month)[1])
            return None
    cal = KoreanLunarCalendar()
    for is_leap in ([True, False] if leap and leap_policy == 'regular' else [bool(leap)]):
        for candidate_day in ([day, 29] if day == 30 and missing_day == 'last' else [day]):
            if cal.setLunarDate(year, month, candidate_day, is_leap) and cal.isIntercalation == is_leap:
                return date.fromisoformat(cal.SolarIsoFormat())
    return None


def occurrences(event, start=None, days=400):
    start = start or local_now().date()
    end = start + timedelta(days=days)
    years = range(max(event['year'], start.year - 1), end.year + 1) if event['recurring'] else [event['year']]
    results = []
    for year in years:
        d = event_date(year, event['month'], event['day'], event['calendar'], event['leap'], event['leap_policy'], event['missing_day'])
        if d and start <= d <= end:
            results.append(datetime(d.year, d.month, d.day, event['hour'], event['minute'], tzinfo=KST))
    return sorted(results)


def events_for(member):
    rows = db.rows('SELECT * FROM family_events WHERE contract_id=? AND cancelled=0 ORDER BY id DESC', (member['contract_id'],))
    for row in rows:
        upcoming = occurrences(row)
        row['next_at'] = upcoming[0].isoformat() if upcoming else None
        row['occurrences'] = [d.isoformat() for d in upcoming]
        row['response'] = (db.one('SELECT response FROM event_attendance WHERE event_id=? AND member_id=?', (row['id'], member['id'])) or {}).get('response')
    return sorted(rows, key=lambda row: row['next_at'] or '9999')


def preferences(mid):
    row = db.one('SELECT * FROM notification_preferences WHERE member_id=?', (mid,))
    if not row:
        row = dict(member_id=mid, enabled=1, offsets='[7,1,0]', paused_until='', kinds='["anniversary","birthday","holiday","meeting"]', phone='', kakao=0, consent_at=None)
    row['offsets'] = json.loads(row['offsets'])
    row['kinds'] = json.loads(row['kinds'])
    return row


def create_due_notifications(now=None):
    now = now or local_now()
    today = now.date()
    # A single process lock / database unique constraint makes polling idempotent.
    for event in db.rows('SELECT * FROM family_events WHERE cancelled=0'):
        for occurrence in occurrences(event, today, 7):
            delta = (occurrence.date() - today).days
            if occurrence.date() == today and occurrence < now - timedelta(hours=12):
                continue
            for member in db.rows('SELECT * FROM family_members WHERE contract_id=? AND revoked_at IS NULL', (event['contract_id'],)):
                if member['invite_expires_at'] and datetime.fromisoformat(member['invite_expires_at']) <= now:
                    continue
                pref = preferences(member['id'])
                if not pref['enabled'] or (pref['paused_until'] and pref['paused_until'] >= today.isoformat()):
                    continue
                if delta not in pref['offsets'] or event['kind'] not in pref['kinds']:
                    continue
                attendance = db.one('SELECT response FROM event_attendance WHERE event_id=? AND member_id=?', (event['id'], member['id']))
                if attendance and attendance['response'] == 'no':
                    continue
                # External reminders go out from 09:00 KST, never in the middle of the night.
                delivery = 'pending' if pref['kakao'] and pref['phone'] and pref['consent_at'] else 'in_app'
                body = f"{event['title']} · {occurrence.strftime('%Y-%m-%d %H:%M')} (한국 시간)"
                db.execute('''INSERT OR IGNORE INTO notifications(member_id,event_id,occurrence,days_before,title,body,created_at,delivery_status)
                              VALUES (?,?,?,?,?,?,?,?)''', (member['id'], event['id'], occurrence.isoformat(), delta,
                              '오늘의 가족 일정' if delta == 0 else f'{delta}일 뒤 가족 일정', body, now.isoformat(), delivery))


def approved_ai_memories(did):
    return db.rows('''SELECT mm.id,mm.title,mm.story,mm.occurred_on,f.name AS author FROM memories mm
                      JOIN family_members f ON f.id=mm.member_id
                      WHERE mm.deceased_id=? AND mm.status='approved' AND mm.visibility='family' AND mm.ai_use=1
                      ORDER BY mm.id DESC LIMIT 20''', (did,))
