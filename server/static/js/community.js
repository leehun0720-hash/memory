// Family records, calendar and accessible flows. API authorization remains server-side.
export function createCommunity({api, $, esc, modal, toast, withToken, state, go, view, every}) {
  const base = '/api/family';
  const manage = () => state.me.member.role === 'manage';
  const busy = async (button, action) => {
    if (button.disabled) return;
    button.disabled = true;
    try { await action(); } catch (e) { toast(e.message, 5000); }
    finally { button.disabled = false; }
  };
  const bind = (root, selector, action) => root.querySelectorAll(selector).forEach(b => b.onclick = () => busy(b, () => action(b)));
  const dateText = value => value ? new Intl.DateTimeFormat('ko-KR', {timeZone:'Asia/Seoul',dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : '다가오는 일정 없음';
  const selectedPerson = () => state.me.deceased.find(d => d.id === personId) || state.me.deceased[0];
  let personId, roomId = null;
  const personPicker = () => `<label class="field">기억할 분<select id="communityPerson">${state.me.deceased.map(d => `<option value="${d.id}" ${d.id === selectedPerson()?.id ? 'selected' : ''}>${esc(d.name)} 님</option>`).join('')}</select></label>`;
  const onPerson = render => { const input = $('#communityPerson'); if (input) input.onchange = () => { personId = +input.value; render(); }; };
  const heading = (eyebrow,title,desc) => `<div class="page-heading"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1><p class="muted">${desc}</p></div>`;
  const field = (label,name,type='text',value='',extra='') => `<label class="field">${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
  const check = (name,label,checked=false,value='1') => `<label class="check"><input type="checkbox" name="${name}" value="${esc(value)}" ${checked?'checked':''}>${label}</label>`;
  function form(html, saveText, action) {
    const box = modal(`<form class="community-form">${html}<p class="form-error" role="alert"></p><button type="submit">${saveText}</button></form>`);
    const f = $('form',box);
    f.onsubmit = e => { e.preventDefault(); const b = $('[type=submit]',f); busy(b,async () => {
      $('.form-error',f).textContent='';
      try { await action(new FormData(f),box,f); } catch (error) { $('.form-error',f).textContent=error.message; }
    }); };
    return box;
  }
  function confirmAction(title, description, action, okText='확인') {
    const box = modal(`<h2>${title}</h2><p>${description}</p><div class="modal-actions"><button class="secondary" type="button" data-keep>그대로 두기</button><button class="danger" type="button" data-confirm>${okText}</button></div>`);
    $('[data-keep]',box).onclick=()=>$('.modal-close',box).click();
    bind(box,'[data-confirm]',async()=>{await action();box.remove();});
  }
  async function album() {
    const d=selectedPerson();
    if (!d) {view.innerHTML='<div class="card empty-state"><h2>아직 등록된 고인 정보가 없습니다</h2><p>시설에서 고인 정보를 등록하면 가족 앨범을 쓸 수 있습니다. 시설 담당자에게 문의해 주세요.</p></div>';return;}
    view.innerHTML=heading('가족 앨범','함께 채우는 기억','사진 한 장, 짧은 이야기로 소중한 순간을 이어 갑니다.')+personPicker()+'<div id="albumContent" aria-live="polite">가족 앨범을 불러오는 중입니다…</div>';
    onPerson(album); const target=$('#albumContent');
    try {
      const memories=await api(`${base}/memories?deceased_id=${d.id}`);
      if(!target.isConnected)return;
      target.innerHTML=`<div class="community-actions"><button id="addMemory">기억 남기기</button><button class="secondary" id="sources">인공지능 대화에 쓰는 기록</button></div>
      <p class="muted">가족 공개 자료는 계약자가 확인한 뒤 함께 보입니다. 인공지능 대화에 쓰는 것은 따로 동의합니다.</p>
      <div class="memory-grid">${memories.map(m=>`<article class="card memory-item">
        ${m.has_file ? m.kind==='photo'?`<img loading="lazy" src="${withToken(`${base}/memories/${m.id}/file`)}" alt="${esc(m.title)}">`:m.kind==='voice'?`<audio controls preload="none" src="${withToken(`${base}/memories/${m.id}/file`)}"></audio>`:`<video controls playsinline preload="metadata" src="${withToken(`${base}/memories/${m.id}/file`)}"></video>`:''}
        <div class="memory-copy"><span class="eyebrow">${esc(m.occurred_on || '날짜 미기록')} · ${esc(m.author)}</span><h2>${esc(m.title)}</h2><p class="preserve">${esc(m.story)}</p>
        <div class="muted">${m.visibility==='private'?'나와 계약자만':({pending:'가족 공개 승인 대기',approved:'가족 공개',rejected:'공개 보류'}[m.status])}${m.ai_use?' · 인공지능 활용 동의함':''}</div>${m.review_note?`<p class="muted">확인 메모: ${esc(m.review_note)}</p>`:''}
        <div class="community-actions">${manage()?`<button class="small secondary" data-review="${m.id}">공개·인공지능 활용 관리</button>`:''}${m.has_file?`<a class="btn small ghost" href="${withToken(`${base}/memories/${m.id}/file`)}" download>파일 받기</a>`:''}${manage()||m.member_id===state.me.member.id?`<button class="small ghost" data-delete="${m.id}">삭제</button>`:''}</div></div></article>`).join('')||'<div class="card empty-state"><h2>첫 기억을 기다립니다</h2><p>아직 남긴 기억이 없습니다. 위의 ‘기억 남기기’를 눌러 평소 좋아하시던 음식이나 함께 걸었던 길을 남겨 보세요.</p></div>'}</div>`;
      $('#addMemory').onclick=()=>form(`<h2>기억 남기기</h2>${field('제목','title','text','','required maxlength="120"')}${field('기억 속 날짜 (선택)','occurred_on','date')}<label class="field">이야기<textarea name="story" maxlength="5000" rows="5"></textarea><small class="muted">이날의 기억을 편하게 들려주세요.</small></label><label class="field">사진·영상·음성 (30MB까지)<input type="file" name="file" accept="image/*,.mp3,.wav,.m4a,.mp4,.mov,.webm"></label><label class="field">공개 범위<select name="visibility"><option value="family">가족 공개 · 계약자 확인 후</option><option value="private">나와 계약자만</option></select></label><p class="muted">사진의 위치 정보는 지웁니다. 인공지능 대화에는 자동으로 쓰이지 않습니다.</p>`,'기억 저장',async(fd,box)=>{fd.set('deceased_id',d.id);await api(`${base}/memories`,{method:'POST',body:fd});box.remove();toast('기억을 남겼습니다.');await album();});
      $('#sources').onclick=()=>busy($('#sources'),async()=>{const rows=await api(`${base}/memories/${d.id}/ai-sources`);modal(`<h2>인공지능 대화에 쓰는 가족 기록</h2><p class="muted">대화에 참고하도록 승인한 기록입니다. 답변마다 이 기록을 직접 인용했다는 뜻은 아닙니다.</p>${rows.map(r=>`<details><summary>${esc(r.title)} · ${esc(r.author)}</summary><p class="preserve">${esc(r.story)}</p></details>`).join('')||'<p>아직 대화에 쓰는 기록이 없습니다. 계약자가 기억마다 공개·인공지능 활용을 정할 수 있습니다.</p>'}`);});
      bind(target,'[data-review]',b=>{const m=memories.find(m=>m.id===+b.dataset.review);form(`<h2>공개·인공지능 활용 관리</h2><p>${esc(m.title)}</p><label class="field">가족 공개 승인<select name="status"><option value="approved">승인</option><option value="rejected" ${m.status==='rejected'?'selected':''}>보류</option></select></label>${m.visibility==='family'&&m.story?check('ai_use','이 이야기를 인공지능 대화의 기억으로 활용하는 데 동의합니다.',!!m.ai_use):'<p class="muted">가족 공개 이야기만 인공지능 대화에 쓸 수 있습니다.</p>'}${field('확인 메모','note','text',m.review_note,'maxlength="300"')}`,'저장',async(fd,box)=>{await api(`${base}/memories/${m.id}/review`,{method:'PUT',body:{status:fd.get('status'),ai_use:fd.has('ai_use'),note:fd.get('note')}});box.remove();await album();});});
      bind(target,'[data-delete]',b=>confirmAction('이 기억을 삭제할까요?','이 기억을 삭제하면 되돌릴 수 없습니다. 가족 앨범과 인공지능 대화 기록에서 함께 내려갑니다.',async()=>{await api(`${base}/memories/${b.dataset.delete}`,{method:'DELETE'});await album();toast('기억을 삭제했습니다.');},'삭제'));
    }catch(e){if(target.isConnected)target.textContent=`가족 앨범을 불러오지 못했습니다. ${e.message} 잠시 뒤 다시 열어 주세요.`;}
  }
  const eventKinds={anniversary:'기일',birthday:'생신',holiday:'명절',meeting:'함께 참배'};
  async function calendarPage(){
    view.innerHTML=heading('가족 일정','마음을 모으는 날','기일을 기억하고, 함께 참배할 시간을 약속합니다.')+'<div id="familyCalendar" aria-live="polite">가족 일정을 불러오는 중입니다…</div>';
    const target=$('#familyCalendar');
    try{const events=await api(`${base}/events`);if(!target.isConnected)return;
      target.innerHTML=`<div class="community-actions"><button id="addMeeting">함께 참배 약속</button>${manage()?'<button class="secondary" id="addEvent">기일·생신 등록</button>':''}<a class="btn secondary" href="${withToken(`${base}/calendar.ics`)}" download>휴대폰 달력에 넣기</a></div><p class="muted">한국 시간 기준입니다. 캘린더 파일은 앞으로 2년의 일정을 담으며, 변경 후 다시 내려받아 주세요.</p>
      ${events.map(e=>`<article class="card"><span class="eyebrow">${eventKinds[e.kind]} · ${e.calendar==='lunar'?`음력 ${e.leap?'윤':''}${e.month}월 ${e.day}일`:'양력'}${e.recurring?' · 매년':''}</span><h2>${esc(e.title)}</h2><p>${dateText(e.next_at)}</p>${e.calendar==='lunar'?`<p class="muted">윤달 없는 해: ${e.leap_policy==='regular'?'평달에 기억':'건너뛰기'} · 날짜 없는 해: ${e.missing_day==='last'?'말일':'건너뛰기'}</p>`:''}<p class="preserve">${esc(e.note)}</p><div class="community-actions">${e.kind==='meeting'?`<button class="small" data-room="${e.id}">함께 참배 공간</button><button class="small secondary" data-rsvp="${e.id}" data-answer="yes" aria-pressed="${e.response==='yes'}">참석${e.response==='yes'?' ✓':''}</button><button class="small ghost" data-rsvp="${e.id}" data-answer="no" aria-pressed="${e.response==='no'}">불참${e.response==='no'?' ✓':''}</button>`:''}${manage()||e.member_id===state.me.member.id?`<button class="small ghost" data-edit="${e.id}">수정</button><button class="small ghost" data-cancel="${e.id}">일정 취소</button>`:''}</div></article>`).join('')||'<div class="card empty-state"><h2>함께할 날을 정해 보세요</h2><p>아직 정한 가족 일정이 없습니다. 위의 ‘함께 참배 약속’을 눌러 먼 곳에 있어도 같은 시간에 마음을 모아 보세요.</p></div>'}`;
      $('#addMeeting').onclick=()=>eventForm(null,true);if($('#addEvent'))$('#addEvent').onclick=()=>eventForm();
      bind(target,'[data-edit]',b=>eventForm(events.find(e=>e.id===+b.dataset.edit)));
      bind(target,'[data-cancel]',b=>confirmAction('일정을 취소할까요?','일정을 취소하면 되돌릴 수 없습니다. 가족 일정과 아직 보내지 않은 알림이 함께 취소됩니다.',async()=>{await api(`${base}/events/${b.dataset.cancel}`,{method:'DELETE'});await calendarPage();toast('일정을 취소했습니다.');},'일정 취소'));
      bind(target,'[data-rsvp]',async b=>{await api(`${base}/events/${b.dataset.rsvp}/attendance`,{method:'PUT',body:{response:b.dataset.answer}});await calendarPage();});
      bind(target,'[data-room]',b=>{roomId=+b.dataset.room;go('together');});
    }catch(e){if(target.isConnected)target.textContent=`가족 일정을 불러오지 못했습니다. ${e.message} 잠시 뒤 다시 열어 주세요.`;}
  }
  function eventForm(event=null,meeting=false){
    meeting=meeting||event?.kind==='meeting';
    const now=new Date(new Date().toLocaleString('en-US',{timeZone:'Asia/Seoul'}));
    const e=event||{title:'',year:now.getFullYear(),month:now.getMonth()+1,day:now.getDate(),hour:15,minute:0,calendar:'solar',kind:meeting?'meeting':'anniversary',recurring:!meeting,leap:false,leap_policy:'regular',missing_day:'last',note:''};
    const box=form(`<h2>${event?'일정 수정':meeting?'함께 참배 약속':'기일·생신 등록'}</h2>${field('일정 이름','title','text',e.title,'required maxlength="100"')}<div class="form-two"><label class="field">종류<select name="kind">${Object.entries(eventKinds).filter(([k])=>meeting?k==='meeting':k!=='meeting').map(([k,v])=>`<option value="${k}" ${e.kind===k?'selected':''}>${v}</option>`).join('')}</select></label><label class="field">달력<select name="calendar" ${meeting?'disabled':''}><option value="solar">양력</option><option value="lunar" ${e.calendar==='lunar'?'selected':''}>음력</option></select></label></div><div class="form-three">${field('기준 연도','year','number',e.year,'required min="1900" max="2050"')}${field('월','month','number',e.month,'required min="1" max="12"')}${field('일','day','number',e.day,'required min="1" max="31"')}</div><div class="form-two">${field('시 (한국 시간)','hour','number',e.hour,'required min="0" max="23"')}${field('분','minute','number',e.minute,'required min="0" max="59"')}</div>${meeting?'':check('recurring','매년 기억하기',!!e.recurring)}<div id="lunarOptions">${check('leap','윤달 날짜입니다.',!!e.leap)}<label class="field">윤달이 없는 해<select name="leap_policy"><option value="regular">같은 달의 평달에 기억</option><option value="skip" ${e.leap_policy==='skip'?'selected':''}>그 해는 건너뛰기</option></select></label></div><label class="field">날짜가 없는 해 (2월 29일·음력 30일 등)<select name="missing_day"><option value="last">해당 달의 마지막 날</option><option value="skip" ${e.missing_day==='skip'?'selected':''}>그 해는 건너뛰기</option></select></label><label class="field">가족에게 남길 말<textarea name="note" maxlength="1000">${esc(e.note)}</textarea></label><button class="secondary" type="button" id="previewDates">예정 날짜 확인</button><p id="datePreview" class="muted" aria-live="polite"></p>`,'일정 저장',async(fd,box)=>{await api(`${base}/events${event?'/'+event.id:''}`,{method:event?'PUT':'POST',body:body(fd)});box.remove();toast('가족 일정에 저장했습니다.');await calendarPage();});
    function body(fd){return{title:fd.get('title'),kind:fd.get('kind'),calendar:fd.get('calendar')||'solar',...Object.fromEntries(['year','month','day','hour','minute'].map(k=>[k,+fd.get(k)])),recurring:!meeting&&fd.has('recurring'),leap:fd.get('calendar')==='lunar'&&fd.has('leap'),leap_policy:fd.get('leap_policy'),missing_day:fd.get('missing_day'),note:fd.get('note'),deceased_id:event?.deceased_id||null};}
    const toggle=()=>$('#lunarOptions',box).hidden=$('[name=calendar]',box).value!=='lunar';toggle();$('[name=calendar]',box).onchange=toggle;
    bind(box,'#previewDates',async()=>{const result=await api(`${base}/events/preview`,{method:'POST',body:body(new FormData($('form',box)))});$('#datePreview',box).textContent=result.occurrences.map(dateText).join(' / ')||'앞으로 2년 안에 해당 날짜가 없습니다.';});
  }
  async function together(){
    if(!roomId){go('calendar');return;}
    view.innerHTML=heading('함께 참배','같은 시간, 같은 마음','가족의 접속을 확인하며 함께 마음을 전하세요.')+'<div id="meetingRoom" class="card">함께 참배하는 가족을 확인하는 중입니다…</div>';
    const target=$('#meetingRoom'), id=roomId;
    const refresh=async()=>{try{const r=await api(`${base}/events/${id}/presence`,{method:'POST'});if(!target.isConnected)return;target.innerHTML=`<h2>${esc(r.event.title)}</h2><p>${dateText(`${r.event.year}-${String(r.event.month).padStart(2,'0')}-${String(r.event.day).padStart(2,'0')}T${String(r.event.hour).padStart(2,'0')}:${String(r.event.minute).padStart(2,'0')}:00+09:00`)}</p><p class="muted">현재 함께하는 가족 · ${r.members.filter(m=>m.present).map(m=>esc(m.name)).join(', ')||'접속 확인 중'}</p><p class="muted">참석 예정: ${r.members.filter(m=>m.response==='yes').map(m=>esc(m.name)).join(', ')||'없음'}</p><button id="meetingVisit">봉안함을 뵈며 참배하기</button><button class="secondary" id="meetingComfort">마음 남기기</button><p class="muted">가족 간 영상 통화가 아닌 공동 참배 공간입니다. 화면을 나가면 45초 안에 접속 표시가 사라집니다.</p>`;$('#meetingVisit').onclick=()=>go('visit');$('#meetingComfort').onclick=()=>go('comfort');}catch(e){if(target.isConnected)target.textContent=e.message;}};
    await refresh();if(target.isConnected)every(refresh,15000);
  }
  const traditions={classic:['일반','헌화','잠시 묵념','마음 전하기'],buddhist:['불교','연꽃 올리기','합장하며 추모','마음 전하기'],catholic:['천주교','촛불 밝히기','기도하며 추모','마음 전하기'],christian:['기독교','조용히 머물기','기도하며 추모','마음 전하기']};
  async function comfort(){
    const d=selectedPerson();if(!d){view.innerHTML='<div class="card empty-state"><h2>아직 등록된 고인 정보가 없습니다</h2><p>시설에서 고인 정보를 등록하면 마음을 전할 수 있습니다. 시설 담당자에게 문의해 주세요.</p></div>';return;}
    view.innerHTML=heading('마음 전하기','잠시, 그리운 분 곁에','서두르지 않아도 괜찮습니다. 편안한 만큼 머물러 주세요.')+personPicker()+'<div id="comfortContent" aria-live="polite">추모 순서를 불러오는 중입니다…</div>';onPerson(comfort);const target=$('#comfortContent');
    try{const [guide,tributes]=await Promise.all([api(`${base}/guides/${d.id}`),api(`${base}/tributes/${d.id}`)]);if(!target.isConnected)return;const tradition=traditions[guide.tradition]||traditions.classic;
      target.innerHTML=`<div class="card comfort-card"><span class="eyebrow">${tradition[0]} · 가족의 추모 순서</span><ol class="remembrance-steps">${tradition.slice(1).map(t=>`<li>${t}</li>`).join('')}</ol>${guide.text?`<div class="approved-prayer preserve">${esc(guide.text)}</div><p class="muted">가족이 직접 정한 추모문</p>`:'<p class="muted">편안히 고인을 기억해 주세요. 정해진 문구를 읽지 않아도 좋습니다.</p>'}<button id="leaveTribute">${tradition[1]} · 마음 남기기</button>${manage()?'<button class="ghost" id="editGuide">가족의 추모 순서·문구 정하기</button>':''}</div><div class="card"><h2>가족이 전한 마음</h2>${tributes.map(t=>`<div class="tribute-entry"><b>${esc(t.author)}</b><small class="muted"> ${dateText(t.created_at)}</small><p class="preserve">${esc(t.message)||({flower:'꽃을 올렸습니다.',candle:'촛불을 밝혔습니다.',bow:'합장하며 추모했습니다.',letter:'마음을 전했습니다.'}[t.kind])}</p></div>`).join('')||'<p class="muted">첫 마음을 전해 주세요.</p>'}</div>`;
      $('#leaveTribute').onclick=()=>form(`<h2>${esc(d.name)} 님께</h2><label class="field">마음 (선택)<textarea name="message" maxlength="1000" rows="4"></textarea><small class="muted">예: 오늘도 기억하고 있습니다.</small></label>`,'마음 전하기',async(fd,box)=>{await api(`${base}/tributes/${d.id}`,{method:'POST',body:{kind:{classic:'flower',buddhist:'bow',catholic:'candle',christian:'letter'}[guide.tradition]||'flower',message:fd.get('message')}});box.remove();await comfort();toast('마음을 전했습니다.');});
      if($('#editGuide'))$('#editGuide').onclick=()=>form(`<h2>가족의 추모 방식</h2><label class="field">전통<select name="tradition">${Object.entries(traditions).map(([k,v])=>`<option value="${k}" ${guide.tradition===k?'selected':''}>${v[0]}</option>`).join('')}</select></label><label class="field">가족이 정한 추모문·기도문 (선택)<textarea name="text" maxlength="3000" rows="6">${esc(guide.text)}</textarea></label><p class="muted">가족이 함께 읽기로 정한 문구를 직접 적어 주세요.</p>`,'저장',async(fd,box)=>{await api(`${base}/guides/${d.id}`,{method:'PUT',body:Object.fromEntries(fd)});box.remove();await comfort();});
    }catch(e){if(target.isConnected)target.textContent=e.message;}
  }
  async function preferencesForm(){
    const p=await api(`${base}/notification-preferences`);
    form(`<h2>알림을 받는 방법</h2>${check('enabled','가족 일정 알림 받기',!!p.enabled)}<fieldset><legend>언제 알려드릴까요?</legend>${[7,1,0].map(n=>check('offsets',n?`${n}일 전`:'당일',p.offsets.includes(n),n)).join('')}</fieldset><fieldset><legend>기억할 일정</legend>${Object.entries(eventKinds).map(([k,v])=>check('kinds',v,p.kinds.includes(k),k)).join('')}</fieldset>${field('이 날짜까지 알림 쉬기 (선택)','paused_until','date',p.paused_until)}<hr>${check('kakao','카카오 알림톡으로도 받기',!!p.kakao)}${field('알림 받을 휴대폰 번호 (숫자만)','phone','tel',p.phone,'autocomplete="tel" inputmode="numeric"')}${check('consent','가족 일정 알림톡 발송을 위한 휴대폰 번호 이용과 수신에 동의합니다.',!!p.consent_at)}<p class="muted">저장한 뒤에도 언제든 해제할 수 있습니다. ${p.provider.ready?'알림톡 발송 서비스가 연결되어 있습니다.':'알림톡은 서비스 연결을 준비하고 있습니다. 앱 안 알림은 지금도 받을 수 있습니다.'}</p>`,'알림 설정 저장',async(fd,box)=>{await api(`${base}/notification-preferences`,{method:'PUT',body:{enabled:fd.has('enabled'),offsets:fd.getAll('offsets').map(Number),kinds:fd.getAll('kinds'),paused_until:fd.get('paused_until'),phone:fd.get('phone'),kakao:fd.has('kakao'),consent:fd.has('consent')}});box.remove();toast('알림 설정을 저장했습니다.');});
  }
  async function inbox(){
    const rows=await api(`${base}/notifications`);
    const box=modal(`<h2>가족 알림</h2><button class="secondary small" id="notificationPrefs">알림 설정</button>${rows.map(r=>`<div class="tribute-entry"><b>${esc(r.title)}</b>${!r.read_at?'<span class="pill">새 알림</span>':''}<p>${esc(r.body)}</p><button class="small secondary" data-read="${r.id}">일정 보기</button></div>`).join('')||'<p class="muted">아직 새 알림이 없습니다. 알림 설정에서 기일·약속 알림을 받을 날을 정할 수 있습니다.</p>'}`);
    bind(box,'#notificationPrefs',preferencesForm);
    bind(box,'[data-read]',async b=>{await api(`${base}/notifications/${b.dataset.read}/read`,{method:'POST'});box.remove();go('calendar');});
  }
  async function access(){
    view.innerHTML=heading('가족 초대 관리','안심하고 나누는 공간','초대의 유효기간과 가족별 이용 권한을 관리합니다.')+'<div id="accessList" aria-live="polite">가족 초대 현황을 불러오는 중입니다…</div>';
    const target=$('#accessList');try{const members=await api(`${base}/access`);if(!target.isConnected)return;target.innerHTML=members.map(m=>`<div class="card"><h2>${esc(m.name)}</h2><p class="muted">${esc(m.relation)} · ${m.role==='manage'?'계약자':m.role==='chat'?'보기·대화':'보기'} · ${m.revoked_at?'접속 해제됨':m.invite_expires_at?`유효기간 ${dateText(m.invite_expires_at)}`:'유효기간 없음'}</p>${m.role!=='manage'?`<div class="community-actions"><button class="small secondary" data-rotate="${m.id}">새 초대 링크</button><button class="small ghost" data-role="${m.id}" data-value="${m.role==='view'?'chat':'view'}">${m.role==='view'?'대화도 허용':'보기만 허용'}</button>${!m.revoked_at?`<button class="small ghost" data-revoke="${m.id}">접속 해제</button>`:''}</div>`:''}</div>`).join('');
      bind(target,'[data-role]',async b=>{await api(`${base}/access/${b.dataset.role}`,{method:'POST',body:{action:'role',role:b.dataset.value}});await access();});
      bind(target,'[data-revoke]',b=>confirmAction('가족의 접속을 해제할까요?','접속을 해제하면 지금 초대 링크로는 더 이상 들어올 수 없습니다. 다시 들어오려면 새 초대 링크가 필요합니다.',async()=>{await api(`${base}/access/${b.dataset.revoke}`,{method:'POST',body:{action:'revoke'}});await access();toast('접속을 해제했습니다.');},'접속 해제'));
      bind(target,'[data-rotate]',b=>form(`<h2>새 초대 링크 만들기</h2><p>새 링크를 만들면 이전 링크는 바로 쓸 수 없게 되며, 되돌릴 수 없습니다. 새 링크를 가족에게 직접 전해 주세요.</p>${field('유효기간 (일)','days','number',30,'required min="1" max="365"')}`,'링크 새로 만들기',async(fd,box)=>{const r=await api(`${base}/access/${b.dataset.rotate}`,{method:'POST',body:{action:'rotate',days:+fd.get('days')}});box.remove();await access();const info=modal(`<h2>새 초대 링크</h2><p>${dateText(r.expires_at)}까지 유효합니다.</p><label class="field">가족에게 전달할 링크<input readonly value="${esc(r.link)}"></label><button id="copyInvite">링크 복사</button>`);bind(info,'#copyInvite',async()=>{await navigator.clipboard.writeText(r.link);toast('복사했습니다.');});}));
    }catch(e){if(target.isConnected)target.textContent=e.message;}
  }
  async function download(path,name,button){
    await busy(button,async()=>{const response=await fetch(withToken(base+path));if(!response.ok){let message='자료를 내려받지 못했습니다.';try{message=(await response.json()).detail||message;}catch{}throw new Error(message);}const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);toast('자료를 준비했습니다. 다운로드를 확인해 주세요.');});
  }
  function setEasy(on){localStorage.setItem('memorial_easy',''+on);document.documentElement.dataset.easy=on?'true':'false';$('#easyMode').textContent=on?'전체 화면':'쉬운 화면';$('#easyMode').setAttribute('aria-pressed',String(on));}
  function hub(){view.innerHTML=heading('편안하게 함께','무엇을 하고 싶으세요?','아래에서 하나를 눌러 주세요.')+`<div class="easy-choices"><button data-route="visit"><span aria-hidden="true">◯</span>참배하기<small>그리운 분을 뵙습니다</small></button><button data-route="album"><span aria-hidden="true">▧</span>사진 보기<small>가족의 추억을 봅니다</small></button><button data-route="comfort"><span aria-hidden="true">♡</span>마음 남기기<small>짧은 인사를 전합니다</small></button></div><button class="ghost" data-route="settings">설정과 가족 관리</button>`;routes(view);}
  function routes(root){root.querySelectorAll('[data-route]').forEach(b=>b.onclick=()=>go(b.dataset.route));}
  function mount(tab){
    if(roomId && ['visit','comfort'].includes(tab)){
      const presence=document.createElement('div');presence.className='card shared-presence';presence.innerHTML='<p aria-live="polite">함께 참배하는 가족을 확인합니다…</p><button class="small ghost" data-leave-room>함께 참배 나가기</button>';view.prepend(presence);
      const id=roomId;
      const heartbeat=async()=>{try{const r=await api(`${base}/events/${id}/presence`,{method:'POST'});if(presence.isConnected)$('p',presence).textContent='함께하는 가족: '+r.members.filter(m=>m.present).map(m=>m.name).join(', ');}catch(e){if(presence.isConnected)$('p',presence).textContent=e.message;}};
      heartbeat();every(()=>{if(presence.isConnected && roomId===id)heartbeat();},15000);
      $('[data-leave-room]',presence).onclick=()=>{roomId=null;presence.remove();toast('함께 참배를 마쳤습니다.');};
    } else if(tab!=='together') roomId=null;
    const links={memorial:[['album','가족 앨범'],['comfort','마음 남기기']],ritual:[['calendar','기일·가족 약속']],chat:[['album','대화에 쓰는 가족 기록']]};
    if(links[tab]){const el=document.createElement('div');el.className='community-actions section-shortcuts';el.innerHTML=links[tab].map(([route,text])=>`<button class="secondary" data-route="${route}">${text}</button>`).join('');const anchor=view.querySelector(".visit-actions")||view.querySelector(".page-heading, .welcome-garden, .memorial-garden");if(anchor)anchor.after(el);else view.prepend(el);routes(el);}
    if(tab==='settings'){
      const el=document.createElement('section');el.className='card';el.innerHTML=`<h2>가족의 기록과 알림</h2><p class="muted">기억을 나누고, 각자의 속도로 추모합니다.</p><div class="settings-actions"><button class="secondary" data-route="album">가족 앨범</button><button class="secondary" data-route="calendar">기일·함께 참배 약속</button><button class="secondary" id="openPrefs">알림·카카오 알림톡</button>${manage()?'<button class="secondary" data-route="access">초대 유효기간·권한 관리</button>':''}</div><details class="archive-details"><summary>추모 자료 내려받기</summary><p class="muted">가족 이야기를 언제든 따로 간직하실 수 있습니다. ZIP에는 열람 가능한 자료와 이야기, PDF에는 가족 앨범의 사진·이야기와 방명록이 담깁니다.</p><div class="community-actions"><button class="secondary" id="archiveZip">자료 ZIP 받기</button><button class="secondary" id="archivePdf">추억책 PDF 받기</button></div></details>`;const themeCard=view.querySelector(".theme-settings");if(themeCard)themeCard.after(el);else view.prepend(el);routes(el);bind(el,'#openPrefs',preferencesForm);$('#archiveZip',el).onclick=e=>download('/archive.zip','family-memories.zip',e.currentTarget);$('#archivePdf',el).onclick=e=>download('/archive.pdf','family-memories.pdf',e.currentTarget);
    }
    const active={album:'memorial',comfort:'memorial',calendar:'ritual',together:'ritual',access:'settings',policy:'settings'}[tab];if(active)document.querySelector(`#tabs [data-tab="${active}"]`)?.classList.add('active');
  }
  function init(){
    const toolbar=document.createElement('div');toolbar.className='family-utilities';toolbar.setAttribute('aria-label','화면 도구');toolbar.innerHTML='<button class="ghost small" id="easyMode" aria-pressed="false">쉬운 화면</button><button class="ghost small" id="familyInbox">알림</button><button class="ghost small easy-home" data-route="easy">처음 화면</button>';const slot=document.querySelector('#topTools');if(slot)slot.append(toolbar);else document.querySelector('.top').after(toolbar);routes(toolbar);setEasy(localStorage.getItem('memorial_easy')==='true');$('#easyMode').onclick=()=>{const on=document.documentElement.dataset.easy!=='true';setEasy(on);go(on?'easy':'visit');};bind(toolbar,'#familyInbox',inbox);
  }
  const pages={album,calendar:calendarPage,comfort,together,easy:hub,access};
  return {init,mount,pages};
}
