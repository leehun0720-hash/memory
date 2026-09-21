"""Family isolation, calendar conversion, outbox safety and downloadable records."""
import io
import json
import zipfile
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from test_mvp import client as base_client, ADMIN
from server import db
from server.community import KST, event_date, local_now, create_due_notifications


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    async def idle(stop):
        await stop.wait()
    with patch('server.notifications.run', idle):
        yield from base_client.__wrapped__(tmp_path_factory)


def actors(client):
    holder = db.one("SELECT * FROM family_members WHERE role='manage' ORDER BY id LIMIT 1")
    did = db.one('SELECT id FROM deceased WHERE contract_id=?',(holder['contract_id'],))['id']
    h = {'X-Family-Token':holder['invite_token']}
    def invite(name):
        result = client.post('/api/family/invite',headers=h,json={'name':name,'role':'chat'})
        assert result.status_code==200, result.text
        member = db.one('SELECT * FROM family_members WHERE id=?',(result.json()['id'],))
        return member, {'X-Family-Token':member['invite_token']}
    a, ah = invite('앨범 작성자')
    b, bh = invite('앨범 열람자')
    other = db.one('SELECT invite_token FROM family_members WHERE contract_id<>? LIMIT 1',(holder['contract_id'],))
    return holder,did,h,a,ah,b,bh,{'X-Family-Token':other['invite_token']}


def test_album_visibility_and_ai_opt_in(client):
    holder,did,h,a,ah,b,bh,other=actors(client)
    result=client.post('/api/family/memories',headers=ah,data={'deceased_id':did,'title':'함께 걷던 길','story':'저녁마다 공원을 걸었습니다.'})
    assert result.status_code==200, result.text
    mid=result.json()['id']
    assert all(r['id']!=mid for r in client.get(f'/api/family/memories?deceased_id={did}',headers=bh).json())
    assert client.get(f'/api/family/memories?deceased_id={did}',headers=other).status_code==404
    assert client.put(f'/api/family/memories/{mid}/review',headers=ah,json={'status':'approved'}).status_code==403
    assert client.put(f'/api/family/memories/{mid}/review',headers=h,json={'status':'approved'}).status_code==200
    assert any(r['id']==mid for r in client.get(f'/api/family/memories?deceased_id={did}',headers=bh).json())
    assert not any(r['id']==mid for r in client.get(f'/api/family/memories/{did}/ai-sources',headers=bh).json())
    assert client.put(f'/api/family/memories/{mid}/review',headers=h,json={'status':'approved','ai_use':True}).status_code==200
    assert any(r['id']==mid for r in client.get(f'/api/family/memories/{did}/ai-sources',headers=bh).json())
    from server.routers.chat import _persona
    person=db.one('SELECT * FROM deceased WHERE id=?',(did,))
    assert '저녁마다 공원' in _persona(person,holder,'').memory_card
    client.delete(f'/api/family/memories/{mid}',headers=ah)
    assert '저녁마다 공원' not in _persona(person,holder,'').memory_card


def test_files_and_archive_scoped(client):
    from PIL import Image
    holder,did,h,a,ah,b,bh,other=actors(client)
    image=io.BytesIO(); Image.new('RGB',(120,80),'#52736a').save(image,'PNG')
    response=client.post('/api/family/memories',headers=ah,data={'deceased_id':did,'title':'비공개 추억','story':'나와 계약자만 보는 이야기','visibility':'private'},files={'file':('photo.png',image.getvalue(),'image/png')})
    assert response.status_code==200,response.text
    mid=response.json()['id']; url=f'/api/family/memories/{mid}/file'
    assert client.get(url,headers=bh).status_code==404
    assert client.get(url,headers=other).status_code==404
    assert client.get(url,headers=ah).headers['content-type']=='image/jpeg'
    assert client.put(f'/api/family/memories/{mid}/review',headers=h,json={'status':'approved','ai_use':True}).status_code==422
    assert client.post('/api/family/memories',headers=ah,data={'deceased_id':did,'title':'x'},files={'file':('x.html',b'<script>bad</script>','text/html')}).status_code==415
    archive=client.get('/api/family/archive.zip',headers=bh)
    assert archive.status_code==200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        meta=json.loads(z.read('family-memories.json'))
        assert not any(r['id']==mid for r in meta['memories'])
        assert not any('memory-'+str(mid)+'.' in path for path in z.namelist())
        assert 'invite_token' not in z.read('family-memories.json').decode()
    pdf=client.get('/api/family/archive.pdf',headers=ah)
    assert pdf.status_code==200,pdf.text[:100] if pdf.status_code!=200 else ''
    assert pdf.content.startswith(b'%PDF')


def test_lunar_and_missing_day_policies():
    assert event_date(2026,8,15,'lunar',False,'regular','last')==date(2026,9,25)
    assert event_date(2023,2,1,'lunar',True,'skip','last')==date(2023,3,22)
    assert event_date(2024,2,1,'lunar',True,'skip','last') is None
    assert event_date(2024,2,1,'lunar',True,'regular','last')==date(2024,3,10)
    assert event_date(2025,2,29,'solar',False,'regular','last')==date(2025,2,28)
    assert event_date(2025,2,29,'solar',False,'regular','skip') is None


def test_calendar_access_and_cancellation(client):
    holder,did,h,a,ah,b,bh,other=actors(client)
    when=local_now()+timedelta(days=1)
    body={'title':'가족 약속','kind':'meeting','year':when.year,'month':when.month,'day':when.day,'hour':15,'recurring':False}
    response=client.post('/api/family/events',headers=ah,json=body)
    assert response.status_code==200,response.text
    eid=response.json()['id']
    assert client.get(f'/api/family/events/{eid}/room',headers=other).status_code==404
    assert client.post(f'/api/family/events/{eid}/presence',headers=bh).status_code==200
    assert client.get(f'/api/family/events/{eid}/room',headers=ah).json()['members'][0]['present']
    assert client.put(f'/api/family/events/{eid}',headers=bh,json=body).status_code==403
    cal=client.get('/api/family/calendar.ics',headers=h)
    assert 'BEGIN:VEVENT' in cal.text and 'DTSTART:' in cal.text and 'TRIGGER:-P7D' in cal.text
    assert 'invite_token' not in cal.text and '?t=' not in cal.text
    assert 'T060000Z' in cal.text  # 15:00 KST
    create_due_notifications();create_due_notifications()
    assert db.one('SELECT COUNT(*) n FROM notifications WHERE event_id=? AND member_id=?',(eid,a['id']))['n']==1
    assert client.delete(f'/api/family/events/{eid}',headers=ah).status_code==200
    assert all(r['event_id']!=eid for r in client.get('/api/family/notifications',headers=ah).json())


def test_invitation_expiry_rotation_revoke(client):
    holder,did,h,a,ah,b,bh,other=actors(client)
    assert a['invite_expires_at']
    assert client.post(f"/api/family/access/{a['id']}",headers=bh,json={'action':'revoke'}).status_code==403
    rotated=client.post(f"/api/family/access/{a['id']}",headers=h,json={'action':'rotate','days':1})
    assert rotated.status_code==200
    assert client.get('/api/family/me',headers=ah).status_code==401
    fresh={'X-Family-Token':rotated.json()['link'].split('?t=')[1]}
    assert client.get('/api/family/me',headers=fresh).status_code==200
    db.execute('UPDATE family_members SET invite_expires_at=? WHERE id=?',((local_now()-timedelta(seconds=1)).isoformat(),a['id']))
    assert client.get('/api/family/me',headers=fresh).status_code==401
    client.post(f"/api/family/access/{b['id']}",headers=h,json={'action':'revoke'})
    assert client.get('/api/family/me',headers=bh).status_code==401
    assert client.post(f"/api/family/access/{holder['id']}",headers=h,json={'action':'revoke'}).status_code==403


def test_kakao_consent_outbox_and_uncertain_send(client,monkeypatch):
    from server import notifications
    holder,did,h,a,ah,b,bh,other=actors(client)
    frozen=local_now().replace(hour=10,minute=0,second=0)
    monkeypatch.setattr(notifications,'local_now',lambda:frozen)
    pref={'kakao':True,'phone':'01000000000','consent':False,'offsets':[1]}
    assert client.put('/api/family/notification-preferences',headers=ah,json=pref).status_code==422
    pref['consent']=True
    assert client.put('/api/family/notification-preferences',headers=ah,json=pref).status_code==200
    when=frozen+timedelta(days=1)
    event=client.post('/api/family/events',headers=h,json={'title':'기일 알림 검증','year':when.year,'month':when.month,'day':when.day}).json()['id']
    monkeypatch.setenv('KAKAO_SEND_ENABLED','0')
    with patch.object(notifications,'provider_request') as send:
        notifications.tick(); send.assert_not_called()
    notice=db.one('SELECT * FROM notifications WHERE event_id=? AND member_id=?',(event,a['id']))
    assert notice['delivery_status']=='blocked'
    for key in notifications.FIELDS: monkeypatch.setenv(key,'test-only')
    monkeypatch.setenv('KAKAO_TEMPLATE_CONTENT','일정 #{title} #{date} #{days}')
    monkeypatch.setenv('KAKAO_SEND_ENABLED','1')
    # Disable all unrelated recipients: tests must never dispatch real HTTP.
    with patch.object(notifications,'provider_request',return_value={'messages':[{'messageId':'test-id','requestStatusCode':'A000'}]}) as send:
        notifications.tick()
        assert any(c.args[0]=='POST' for c in send.call_args_list)
    assert db.one('SELECT delivery_status FROM notifications WHERE id=?',(notice['id'],))['delivery_status']=='submitted'
    with patch.object(notifications,'provider_request',return_value={'messageStatusCode':'0000','messageStatusName':'success'}): notifications.tick()
    assert db.one('SELECT delivery_status FROM notifications WHERE id=?',(notice['id'],))['delivery_status']=='delivered'
    db.execute("UPDATE notifications SET delivery_status='unknown' WHERE id=?",(notice['id'],))
    with patch.object(notifications,'provider_request') as send:
        notifications.tick(); send.assert_not_called()
    assert client.post(f"/api/admin/notifications/{notice['id']}/retry",headers=ADMIN).status_code==409
    admin=client.get('/api/admin/notifications',headers=ADMIN)
    assert admin.status_code==200 and '01000000000' not in admin.text


def test_guides_tributes_and_admin_tasks(client):
    holder,did,h,a,ah,b,bh,other=actors(client)
    assert client.put(f'/api/family/guides/{did}',headers=ah,json={'tradition':'catholic','text':'가족이 정한 문구'}).status_code==403
    assert client.put(f'/api/family/guides/{did}',headers=h,json={'tradition':'catholic','text':'가족이 정한 문구'}).status_code==200
    assert client.get(f'/api/family/guides/{did}',headers=bh).json()['text']=='가족이 정한 문구'
    assert client.post(f'/api/family/tributes/{did}',headers=bh,json={'kind':'candle','message':'기억합니다.'}).status_code==200
    assert client.get(f'/api/family/tributes/{did}',headers=other).status_code==404
    assert client.get('/api/admin/tasks',headers=h).status_code==401
    assert client.get('/api/admin/tasks',headers=ADMIN).status_code==200
