"""Opt-in Kakao Alimtalk outbox via NAVER Cloud SENS. Never retry uncertain sends."""
import asyncio
import base64
import hashlib
import hmac
import logging
import os
import re
import time
from datetime import datetime
from urllib.parse import quote

import httpx

from . import db
from .community import create_due_notifications, local_now, preferences

FIELDS = ('NCP_ACCESS_KEY', 'NCP_SECRET_KEY', 'KAKAO_SERVICE_ID', 'KAKAO_CHANNEL_ID',
          'KAKAO_TEMPLATE_CODE', 'KAKAO_TEMPLATE_CONTENT')
log = logging.getLogger(__name__)


def provider_status():
    missing = [key for key in FIELDS if not os.getenv(key)]
    enabled = os.getenv('KAKAO_SEND_ENABLED', '0') == '1'
    return {'provider': 'NAVER Cloud SENS', 'ready': enabled and not missing,
            'enabled': enabled, 'missing': missing,
            'note': '승인된 카카오 채널·템플릿과 수신 동의가 필요합니다. 발송 시간은 한국 시간 09~20시입니다.'}


def provider_request(method, suffix='', payload=None):
    path = '/alimtalk/v2/services/' + quote(os.environ['KAKAO_SERVICE_ID'], safe=':') + '/messages' + suffix
    timestamp = str(int(time.time()*1000))
    access = os.environ['NCP_ACCESS_KEY']
    signature = base64.b64encode(hmac.new(os.environ['NCP_SECRET_KEY'].encode(),
                 f'{method} {path}\n{timestamp}\n{access}'.encode(), hashlib.sha256).digest()).decode()
    with httpx.Client(timeout=12) as client:
        response = client.request(method, 'https://sens.apigw.ntruss.com'+path, json=payload,
                   headers={'x-ncp-apigw-timestamp':timestamp, 'x-ncp-iam-access-key':access,
                            'x-ncp-apigw-signature-v2':signature})
        response.raise_for_status()
        return response.json()


def update(nid, status, error='', provider_id=None):
    if provider_id is None:
        db.execute('UPDATE notifications SET delivery_status=?,delivery_error=? WHERE id=?', (status,error,nid))
    else:
        db.execute('UPDATE notifications SET delivery_status=?,delivery_error=?,provider_id=? WHERE id=?', (status,error,provider_id,nid))


def tick():
    now = local_now()
    create_due_notifications(now)
    ready = provider_status()['ready']
    for notice in db.rows("SELECT * FROM notifications WHERE delivery_status IN ('pending','blocked') ORDER BY id LIMIT 100"):
        nid = notice['id']
        member = db.one('SELECT * FROM family_members WHERE id=?', (notice['member_id'],))
        event = db.one('SELECT * FROM family_events WHERE id=?', (notice['event_id'],))
        pref = preferences(notice['member_id'])
        attendance = db.one('SELECT response FROM event_attendance WHERE event_id=? AND member_id=?', (event['id'],member['id']))
        if (member['revoked_at'] or (member['invite_expires_at'] and datetime.fromisoformat(member['invite_expires_at']) <= now)
            or event['cancelled'] or not pref['enabled'] or not pref['kakao'] or not pref['consent_at']
            or not re.fullmatch(r'010\d{8}', pref['phone']) or event['kind'] not in pref['kinds']
            or notice['days_before'] not in pref['offsets'] or (pref['paused_until'] and pref['paused_until'] >= now.date().isoformat())
            or (attendance and attendance['response']=='no')):
            update(nid,'cancelled'); continue
        if datetime.fromisoformat(notice['created_at']).date() != now.date():
            update(nid,'expired','발송 날짜가 지났습니다.'); continue
        if not ready:
            update(nid,'blocked','발송 서비스 설정 대기'); continue
        if not 9 <= now.hour < 20:
            continue
        content = os.environ['KAKAO_TEMPLATE_CONTENT'].replace('\\n','\n')
        replacements = {'title':event['title'], 'date':datetime.fromisoformat(notice['occurrence']).strftime('%Y-%m-%d %H:%M'),
                        'days':str(notice['days_before'])}
        content = re.sub(r'#\{(title|date|days)\}', lambda match: replacements[match[1]], content)
        if re.search(r'#\{[^}]+\}',content) or len(content)>1000:
            update(nid,'failed','템플릿 변수 또는 길이를 확인해 주세요.'); continue
        with db.tx() as conn:
            claimed = conn.execute("UPDATE notifications SET delivery_status='sending' WHERE id=? AND delivery_status IN ('pending','blocked')",(nid,)).rowcount
        if not claimed:
            continue
        try:
            result = provider_request('POST', payload={'plusFriendId':os.environ['KAKAO_CHANNEL_ID'],
                    'templateCode':os.environ['KAKAO_TEMPLATE_CODE'], 'messages':[{'countryCode':'82',
                    'to':pref['phone'], 'content':content, 'useSmsFailover':False}]})
            message = (result.get('messages') or [{}])[0]
            if message.get('requestStatusCode') == 'A000' and message.get('messageId'):
                update(nid,'submitted',provider_id=message['messageId'])
            elif message.get('requestStatusCode') and message['requestStatusCode']!='A000':
                update(nid,'failed','접수 거절: '+str(message['requestStatusCode']))
            else:
                update(nid,'unknown','접수 여부 확인 필요. 자동 재발송하지 않습니다.')
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            update(nid,'failed' if 400<=code<500 else 'unknown',f'공급자 응답 HTTP {code}')
        except (httpx.RequestError, ValueError):
            update(nid,'unknown','통신 결과 불명확. 공급자 발송 이력을 확인해 주세요.')
    if ready:
        for notice in db.rows("SELECT * FROM notifications WHERE delivery_status='submitted' LIMIT 100"):
            try:
                result = provider_request('GET','/'+quote(notice['provider_id'],safe=''))
                if result.get('messageStatusCode') == '0000':
                    update(notice['id'],'delivered')
                elif result.get('messageStatusName') == 'fail':
                    update(notice['id'],'failed','수신 실패: '+str(result.get('messageStatusCode','')))
            except (httpx.HTTPError, ValueError):
                pass  # Keep submitted, not delivered. Read-only polling is safe to retry.


async def run(stop):
    # A crashed send can have reached Kakao. Preserve that uncertainty across restarts.
    db.execute("UPDATE notifications SET delivery_status='unknown',delivery_error='서버 재시작 전 발송 결과 확인 필요' WHERE delivery_status='sending'")
    while not stop.is_set():
        try:
            await asyncio.to_thread(tick)
        except Exception:
            log.error('알림 작업 처리 실패. 다음 주기에 다시 확인합니다.')
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
