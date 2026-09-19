// 관리자 콘솔. ?key=관리자키 로 열면 키를 기억한다.
const qs = new URLSearchParams(location.search);
if (qs.get("key")) { sessionStorage.setItem("admin_key", qs.get("key")); history.replaceState(null, "", location.pathname); }
let KEY = sessionStorage.getItem("admin_key") || "";

const $ = (s, el = document) => el.querySelector(s);
const page = $("#page");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (iso) => iso ? iso.replace("T", " ").slice(0, 16) : "";
let timers = [];
const every = (fn, ms) => timers.push(setInterval(fn, ms));

async function api(path, opts = {}) {
  const isForm = opts.body instanceof FormData;
  const r = await fetch(path, { ...opts, headers: { "X-Admin-Key": KEY, ...(opts.body && !isForm ? { "Content-Type": "application/json" } : {}) }, body: opts.body && !isForm ? JSON.stringify(opts.body) : opts.body });
  if (!r.ok) { let msg = r.statusText; try { msg = (await r.json()).detail || msg; } catch {} throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg)); }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r;
}
const toast = (m) => { let el = $(".toast"); if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); } el.textContent = m; el.classList.remove("hidden"); setTimeout(() => el.classList.add("hidden"), 2500); };
const modal = (html) => { const bg = document.createElement("div"); bg.className = "modal-bg"; bg.style.alignItems = "center"; bg.innerHTML = `<div class="modal" style="border-radius:16px;max-width:720px">${html}</div>`; bg.addEventListener("click", (e) => e.target === bg && bg.remove()); document.body.appendChild(bg); return bg; };

async function boot() {
  if (!KEY) { KEY = prompt("관리자 키를 입력하세요") || ""; sessionStorage.setItem("admin_key", KEY); }
  try { await api("/api/admin/overview"); } catch (e) { sessionStorage.removeItem("admin_key"); page.innerHTML = `<div class="card">인증 실패: ${esc(e.message)} <button class="small" onclick="location.reload()">다시</button></div>`; return; }
  document.querySelectorAll("aside button").forEach((b) => b.onclick = () => go(b.dataset.page));
  go("overview");
}
function go(p) {
  timers.forEach(clearInterval); timers = [];
  document.querySelectorAll("aside button").forEach((b) => b.classList.toggle("active", b.dataset.page === p));
  ({ overview, calib, contracts, deceased, rituals, usage, aisettings })[p]();
}

// ---------------- 현황 ----------------
async function overview() {
  const render = async () => {
    const o = await api("/api/admin/overview");
    const c = o.counts;
    page.innerHTML = `<h1>현황</h1><p class="muted">${esc(o.facility?.name || "")}</p>
      <div class="kpi" style="margin:14px 0">
        ${[["계약", c.contracts], ["가족 계정", c.members], ["고인 등록", c.deceased], ["대화 기능 열림", c.ai_enabled], ["대화 세션", c.chat_sessions], ["공양 접수 대기", c.offerings_pending], ["오늘 실시간 보기", c.live_today]].map(([k, v]) => `<div class="card"><div class="muted">${k}</div><div class="n">${v}</div></div>`).join("")}
      </div>
      <div class="card"><h3>카메라</h3><table><tr><th>이름</th><th>종류</th><th>장치</th><th>칸 수</th><th>상태</th><th>참배객</th><th>fps</th><th>마지막 신호</th></tr>
        ${o.cameras.map((cm) => `<tr><td>${esc(cm.name)}<div class="muted">${esc(cm.room_name)}</div></td><td>${cm.kind === "wall" ? "벽면" : "제례"}</td><td>#${cm.device_index}</td><td>${cm.niche_count}</td>
          <td>${cm.online ? '<span class="tag on">연결됨</span>' : '<span class="tag off">끊김</span>'}</td><td>${cm.occupied ? `<span class="tag busy">사람 ${cm.persons}명 · 송출 중단</span>` : '<span class="tag">없음</span>'}</td><td>${cm.fps}</td><td class="muted">${fmt(cm.last_seen_at)}</td></tr>`).join("")}</table>
        <p class="muted" style="margin-top:8px">현장 프로그램이 꺼져 있으면 <span class="mono">python -m edge.agent</span> 로 실행하세요.</p></div>
      <div class="card"><h3>실시간 보기 보호 <span class="muted">(참배객 감지)</span></h3>
        <div class="toolbar"><button class="small ${o.live_protect ? "" : "danger"}" id="liveProtect">${o.live_protect ? "켬 (운용)" : "끔 (시연 모드)"}</button>
          <span class="muted">${o.live_protect ? "현장에 사람이 감지되면 실시간 영상을 멈추고 사진으로 보여 줍니다. 운용 기본값." : "웹캠 앞에 사람이 있어도 실시간 영상을 계속 보냅니다. 노트북 시연용 — 실제 운용 전에 반드시 켜세요."}</span></div>
        <p class="muted" style="font-size:13px">노트북 시연에서는 카메라 앞에 앉은 사람이 '참배객'으로 잡혀 영상이 몇 초마다 멈춥니다. 시연 중에만 끄고, 안치실에 설치하면 켭니다.</p></div>
      <div class="card"><h3>AI 연결 점검 <span class="muted">(시연 전에 한 번 누르세요)</span></h3>
        <div class="toolbar"><button class="small" id="chkAll">지금 점검</button><span class="muted">Claude 키·크레딧, ElevenLabs 키·권한 3개를 한 번에 확인합니다.</span></div>
        <div id="chkOut" class="stack" style="font-size:14px"></div></div>`;
    $("#chkAll").onclick = runAllChecks;
    $("#liveProtect").onclick = async () => { try { await api("/api/admin/settings/live", { method: "PUT", body: { protect: !o.live_protect } }); toast(o.live_protect ? "참배객 보호를 껐습니다(시연 모드)." : "참배객 보호를 켰습니다."); render(); } catch (e) { toast(e.message); } };
    if (overview.lastCheck) $("#chkOut").innerHTML = overview.lastCheck;
  };
  await render(); every(render, 5000);
}
async function runAllChecks() {
  const out = $("#chkOut"); out.innerHTML = '<div class="muted">점검 중…</div>';
  const line = (ok, label, msg) => `<div style="color:${ok ? "#1e7a45" : "var(--danger)"}"><b>${ok ? "✓" : "✗"} ${label}</b> — ${esc(msg)}</div>`;
  let html = "";
  try { const r = await api("/api/admin/settings/ai/test", { method: "POST" }); html += line(true, "Claude 대화", `${r.model} 응답 확인`); }
  catch (e) { html += line(false, "Claude 대화", e.message + " → AI 설정에서 키/크레딧 확인"); }
  try { const r = await api("/api/admin/settings/tts/test", { method: "POST" }); const c = r.checks || {};
    const mk = (k) => c[k] === "ok" ? "✓" : c[k] === "quota" ? "✗(키 크레딧 한도 0)" : "✗";
    html += line(!!r.all_ok, "ElevenLabs 복제 음성", `텍스트 음성 변환 ${mk("text_to_speech")} · 음성 ${mk("voices_read")} · 사용자 ${mk("user_read")}${r.note ? " · " + r.note : ""}${!r.all_ok && c.text_to_speech !== "quota" ? " → 가장 쉬운 해결: ElevenLabs에서 '키 제한'을 끈 새 키를 만들어 AI 설정에 저장" : ""}`); }
  catch (e) { html += line(false, "ElevenLabs 복제 음성", e.message + (e.message.includes("없습니다") ? "" : " → 가장 쉬운 해결: '키 제한'을 끈 새 키")); }
  try { const r = await api("/api/admin/settings/did/test", { method: "POST" }); html += line(true, "D-ID 실시간 아바타(실제 사진)", `연결 성공${r.note ? " · " + r.note : ""}`); }
  catch (e) { html += line(false, "D-ID 실시간 아바타(실제 사진)", e.message.includes("없습니다") ? "키 없음(선택 기능)" : e.message); }
  try { const r = await api("/api/admin/settings/avatar/test", { method: "POST" }); const c = r.checks || {};
    html += line(!!r.all_ok, "Simli 실시간 아바타", `얼굴 목록 ${c.faces_list === "ok" ? "✓" : "✗"} · 세션 토큰 ${c.session_token === "ok" ? "✓" : "✗"} · 등록된 얼굴 ${r.faces}개${r.note ? " · " + r.note : ""}`); }
  catch (e) { html += line(false, "Simli 실시간 아바타", e.message.includes("없습니다") ? "키 없음(선택 기능)" : e.message); }
  overview.lastCheck = html; out.innerHTML = html;
}

// ---------------- 칸 좌표 등록 ----------------
async function calib() {
  const cams = (await api("/api/admin/cameras")).filter((c) => c.kind === "wall");
  const rooms = await api("/api/admin/rooms");
  page.innerHTML = `<h1>칸 좌표 등록</h1><p class="muted">카메라 화면 위에 봉안함 칸을 사각형으로 그리고 번호를 붙입니다. 카메라가 고정이라 한 번만 등록하면 됩니다. 드래그로 칸 하나를 그리거나, 큰 영역을 그린 뒤 '격자로 나누기'를 쓰세요.</p>
    <div class="toolbar">
      <select id="camSel">${cams.map((c) => `<option value="${c.id}">${esc(c.name)} (#${c.device_index})</option>`).join("")}</select>
      <button class="small secondary" id="addCam">카메라 추가</button>
      <button class="small ghost" id="refresh">화면 새로고침</button>
      <span class="muted" id="frameInfo"></span>
    </div>
    <div class="cal">
      <div><div id="canvasWrap"><canvas id="cal"></canvas></div>
        <div class="toolbar" style="margin-top:10px">
          <label style="margin:0">접두어 <input id="prefix" value="A" style="width:60px"></label>
          <label style="margin:0">단(행) <input id="rows" type="number" value="1" min="1" style="width:60px"></label>
          <label style="margin:0">열 <input id="cols" type="number" value="1" min="1" style="width:60px"></label>
          <button class="small secondary" id="gridBtn">마지막 사각형을 격자로 나누기</button>
          <button class="small ghost" id="undoBtn">마지막 취소</button>
          <button class="small ghost" id="clearBtn">모두 지우기</button>
        </div></div>
      <div class="card" style="margin:0"><h3>칸 목록 <span id="cnt"></span></h3><div id="list" style="max-height:520px;overflow:auto"></div><button id="save" style="margin-top:10px">저장</button></div>
    </div>`;
  const canvas = $("#cal"), ctx = canvas.getContext("2d");
  let img = new Image(), niches = [], drag = null, camId = +$("#camSel").value;

  async function loadNiches() { niches = (await api(`/api/admin/cameras/${camId}/niches`)).map((n) => ({ ...n })); list(); draw(); }
  function loadFrame() {
    const im = new Image();
    im.onload = () => { img = im; canvas.width = im.naturalWidth; canvas.height = im.naturalHeight; $("#frameInfo").textContent = `${im.naturalWidth}×${im.naturalHeight}`; draw(); };
    im.onerror = () => { $("#frameInfo").textContent = "카메라 화면 없음 — 현장 프로그램을 실행하세요"; if (!img.naturalWidth) { canvas.width = 1280; canvas.height = 720; draw(); } };
    im.src = `/api/admin/cameras/${camId}/frame.jpg?key=${encodeURIComponent(KEY)}&_=${Date.now()}`;
  }
  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (img.naturalWidth) ctx.drawImage(img, 0, 0, canvas.width, canvas.height); else { ctx.fillStyle = "#222"; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = "#888"; ctx.font = "28px sans-serif"; ctx.fillText("카메라 화면이 없습니다", 40, 60); }
    const W = canvas.width, H = canvas.height;
    ctx.lineWidth = Math.max(2, W / 640); ctx.font = `${Math.max(14, W / 70)}px sans-serif`;
    niches.forEach((n, i) => { ctx.strokeStyle = n.contract ? "#f0b429" : "#3ad07a"; ctx.strokeRect(n.x * W, n.y * H, n.w * W, n.h * H); ctx.fillStyle = "rgba(0,0,0,.55)"; ctx.fillRect(n.x * W, n.y * H, ctx.measureText(n.code).width + 12, W / 60 + 8); ctx.fillStyle = "#fff"; ctx.fillText(n.code, n.x * W + 6, n.y * H + W / 60 + 2); });
    if (drag) { ctx.strokeStyle = "#5bb8ff"; ctx.setLineDash([8, 6]); ctx.strokeRect(drag.x0 * W, drag.y0 * H, (drag.x1 - drag.x0) * W, (drag.y1 - drag.y0) * H); ctx.setLineDash([]); }
  }
  function list() {
    $("#cnt").textContent = `(${niches.length})`;
    $("#list").innerHTML = niches.map((n, i) => `<div class="niche-row"><input value="${esc(n.code)}" data-i="${i}"><span class="muted">${(n.x * 100).toFixed(0)},${(n.y * 100).toFixed(0)} · ${(n.w * 100).toFixed(0)}×${(n.h * 100).toFixed(0)}%</span>${n.contract ? `<span class="tag on">${esc(n.contract.holder_name)}</span>` : ""}<button class="small ghost" data-del="${i}" style="margin-left:auto;min-height:28px;padding:0 8px">✕</button></div>`).join("") || `<p class="muted">아직 칸이 없습니다. 화면에서 드래그하세요.</p>`;
    $("#list").querySelectorAll("input").forEach((inp) => inp.oninput = () => { niches[+inp.dataset.i].code = inp.value; draw(); });
    $("#list").querySelectorAll("[data-del]").forEach((b) => b.onclick = () => { const n = niches[+b.dataset.del]; if (n.contract && !confirm("계약이 연결된 칸입니다. 삭제하면 저장 시 거부됩니다. 계속할까요?")) return; niches.splice(+b.dataset.del, 1); list(); draw(); });
  }
  const pos = (e) => { const r = canvas.getBoundingClientRect(); return { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) }; };
  canvas.onpointerdown = (e) => { const p = pos(e); drag = { x0: p.x, y0: p.y, x1: p.x, y1: p.y }; canvas.setPointerCapture(e.pointerId); };
  canvas.onpointermove = (e) => { if (!drag) return; const p = pos(e); drag.x1 = p.x; drag.y1 = p.y; draw(); };
  canvas.onpointerup = () => {
    if (!drag) return; const x = Math.min(drag.x0, drag.x1), y = Math.min(drag.y0, drag.y1), w = Math.abs(drag.x1 - drag.x0), h = Math.abs(drag.y1 - drag.y0); drag = null;
    if (w < 0.01 || h < 0.01) return draw();
    const rows = +$("#rows").value || 1, cols = +$("#cols").value || 1;
    niches.push({ code: nextCode(), row: rows, col: cols, x, y, w, h }); list(); draw();
  };
  function nextCode() { const p = $("#prefix").value || "A"; let i = 1; const codes = new Set(niches.map((n) => n.code)); while (codes.has(`${p}-${i}`)) i++; return `${p}-${i}`; }
  $("#gridBtn").onclick = () => {
    const last = niches.pop(); if (!last) return toast("먼저 큰 영역을 드래그하세요.");
    const rows = +$("#rows").value || 1, cols = +$("#cols").value || 1, p = $("#prefix").value || "A";
    const codes = new Set(niches.map((n) => n.code));
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) { let code = `${p}-${r + 1}-${c + 1}`; let k = 2; while (codes.has(code)) code = `${p}-${r + 1}-${c + 1}_${k++}`; codes.add(code);
      niches.push({ code, row: r + 1, col: c + 1, x: last.x + c * last.w / cols, y: last.y + r * last.h / rows, w: last.w / cols, h: last.h / rows }); }
    list(); draw();
  };
  $("#undoBtn").onclick = () => { niches.pop(); list(); draw(); };
  $("#clearBtn").onclick = () => { if (confirm("모두 지울까요? (저장 전까지는 반영되지 않습니다)")) { niches = []; list(); draw(); } };
  $("#save").onclick = async () => {
    try { niches = (await api(`/api/admin/cameras/${camId}/niches`, { method: "PUT", body: niches.map((n) => ({ id: n.id || null, code: n.code.trim(), row: n.row || 0, col: n.col || 0, x: n.x, y: n.y, w: n.w, h: n.h })) })).map((n) => ({ ...n })); list(); draw(); toast("저장했습니다. 현장 프로그램이 1초 안에 새 칸을 반영합니다."); }
    catch (e) { toast("저장 실패: " + e.message); }
  };
  $("#camSel").onchange = () => { camId = +$("#camSel").value; img = new Image(); loadFrame(); loadNiches(); };
  $("#refresh").onclick = loadFrame;
  $("#addCam").onclick = () => {
    const m = modal(`<h2>카메라 추가</h2><div class="form-grid">
      <div class="field"><label>이름</label><input id="cName" value="안치실 1 · 벽면 B"></div>
      <div class="field"><label>안치실</label><select id="cRoom">${rooms.map((r) => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select></div>
      <div class="field"><label>종류</label><select id="cKind"><option value="wall">벽면(참배)</option><option value="ritual">제례 공간(중계)</option></select></div>
      <div class="field"><label>장치 번호(웹캠 index)</label><input id="cIdx" type="number" value="0"></div></div>
      <button id="cGo" style="margin-top:12px">추가</button>`);
    $("#cGo", m).onclick = async () => { await api("/api/admin/cameras", { method: "POST", body: { name: $("#cName", m).value, room_id: +$("#cRoom", m).value, kind: $("#cKind", m).value, device_index: +$("#cIdx", m).value } }); m.remove(); calib(); };
  };
  if (cams.length) { loadFrame(); loadNiches(); every(loadFrame, 5000); } else { $("#frameInfo").textContent = "벽면 카메라가 없습니다. 먼저 추가하세요."; }
}

// ---------------- 계약·가족 ----------------
async function contracts() {
  const rows = await api("/api/admin/contracts");
  page.innerHTML = `<h1>계약·가족</h1><div class="toolbar"><button class="small" id="newC">새 계약</button></div>
    <div class="card"><table><tr><th>#</th><th>계약자</th><th>봉안함</th><th>요금제</th><th>가족</th><th>고인</th><th>등록</th><th></th></tr>
      ${rows.map((c) => `<tr><td>${c.id}</td><td><b>${esc(c.holder_name)}</b><div class="muted">${esc(c.holder_phone)}</div></td><td>${esc(c.niche_code || "-")}</td><td>${c.plan === "premium" ? "프리미엄" : "기본"}</td><td>${c.member_count}</td><td>${esc(c.deceased_names || "-")}</td><td class="muted">${fmt(c.created_at)}</td><td><button class="small ghost" data-open="${c.id}">열기</button></td></tr>`).join("")}</table></div>`;
  page.querySelectorAll("[data-open]").forEach((b) => b.onclick = () => contractDetail(+b.dataset.open));
  $("#newC").onclick = async () => {
    const niches = await freeNiches();
    const m = modal(`<h2>새 계약</h2><div class="form-grid">
      <div class="field"><label>계약자 이름</label><input id="hName"></div><div class="field"><label>연락처</label><input id="hPhone"></div>
      <div class="field"><label>봉안함</label><select id="hNiche"><option value="">나중에 연결</option>${niches.map((n) => `<option value="${n.id}">${esc(n.code)}</option>`).join("")}</select></div>
      <div class="field"><label>요금제</label><select id="hPlan"><option value="basic">기본</option><option value="premium">프리미엄</option></select></div></div>
      <button id="hGo" style="margin-top:12px">만들기 (계약자 초대 링크 발급)</button>`);
    $("#hGo", m).onclick = async () => { try { const r = await api("/api/admin/contracts", { method: "POST", body: { holder_name: $("#hName", m).value, holder_phone: $("#hPhone", m).value, niche_id: $("#hNiche", m).value ? +$("#hNiche", m).value : null, plan: $("#hPlan", m).value } }); m.remove(); contractDetail(r.id); } catch (e) { toast(e.message); } };
  };
}
async function freeNiches(includeId) {
  const cams = await api("/api/admin/cameras"); let all = [];
  for (const c of cams.filter((c) => c.kind === "wall")) all = all.concat(await api(`/api/admin/cameras/${c.id}/niches`));
  return all.filter((n) => !n.contract || n.id === includeId);
}
async function contractDetail(id) {
  const d = await api(`/api/admin/contracts/${id}`);
  const c = d.contract; const roleName = { view: "보기", chat: "보기·대화", manage: "관리" };
  page.innerHTML = `<button class="small ghost" id="back">← 목록</button><h1 style="margin-top:8px">${esc(c.holder_name)} 계약 <small class="muted">#${c.id} · 봉안함 ${esc(c.niche_code || "-")}</small></h1>
    <div class="toolbar"><button class="small secondary" id="editC">계약 수정</button><button class="small secondary" id="addM">가족 추가</button><button class="small secondary" id="addD">고인 등록</button></div>
    <div class="card"><h3>가족 계정과 초대 링크 <span class="muted">(카카오톡으로 보내는 링크)</span></h3><table><tr><th>이름</th><th>관계</th><th>권한</th><th>링크</th><th>마지막 접속</th><th></th></tr>
      ${d.members.map((m) => `<tr><td><b>${esc(m.name)}</b>${m.is_minor ? ' <span class="tag">미성년</span>' : ""}</td><td>${esc(m.relation)}</td><td>${roleName[m.role]}</td><td class="mono">${esc(m.link)} <button class="small ghost" data-copy="${esc(m.link)}" style="min-height:26px;padding:0 6px">복사</button></td><td class="muted">${fmt(m.last_seen_at)}</td><td><button class="small ghost" data-delm="${m.id}" style="min-height:26px;padding:0 6px">삭제</button></td></tr>`).join("")}</table></div>
    <div class="card"><h3>고인</h3>${d.deceased.length ? d.deceased.map((x) => `<div class="list-item"><div><b>${esc(x.name)}</b> <span class="muted">${esc(x.honorific)} · ${esc(x.birth_date)} ~ ${esc(x.death_date)}</span>
        <div>${x.ai_enabled ? '<span class="tag on">대화 기능 열림</span>' : '<span class="tag">대화 기능 닫힘</span>'} 동의서 ${x.consents.filter((k) => !k.revoked_at).length}건 · 기억 카드 ${x.memory_card.length}자 · 자료 ${x.media.length}건</div></div>
        <button class="small ghost" data-editd="${x.id}">편집</button></div>`).join("") : `<p class="muted">등록된 고인이 없습니다.</p>`}</div>
    <div class="card"><h3>방명록(최근)</h3>${d.guestbook.map((g) => `<div class="guest"><span class="who">${esc(g.author)}</span><span class="when">${fmt(g.created_at)}</span><div>${esc(g.message)}</div></div>`).join("") || '<p class="muted">없음</p>'}</div>`;
  $("#back").onclick = contracts;
  page.querySelectorAll("[data-copy]").forEach((b) => b.onclick = () => { navigator.clipboard?.writeText(b.dataset.copy); toast("복사했습니다."); });
  page.querySelectorAll("[data-delm]").forEach((b) => b.onclick = async () => { if (confirm("이 가족 계정을 삭제할까요?")) { await api(`/api/admin/members/${b.dataset.delm}`, { method: "DELETE" }); contractDetail(id); } });
  page.querySelectorAll("[data-editd]").forEach((b) => b.onclick = () => deceasedForm(+b.dataset.editd, id));
  $("#addD").onclick = () => deceasedForm(null, id);
  $("#addM").onclick = () => {
    const m = modal(`<h2>가족 추가</h2><div class="form-grid"><div class="field"><label>이름</label><input id="mName"></div><div class="field"><label>관계</label><input id="mRel"></div>
      <div class="field"><label>권한</label><select id="mRole"><option value="view">보기</option><option value="chat">보기·대화</option><option value="manage">관리</option></select></div></div>
      <div class="check"><input type="checkbox" id="mMinor"><label for="mMinor" style="margin:0">미성년자</label></div><button id="mGo">추가</button>`);
    $("#mGo", m).onclick = async () => { await api(`/api/admin/contracts/${id}/members`, { method: "POST", body: { name: $("#mName", m).value, relation: $("#mRel", m).value, role: $("#mRole", m).value, is_minor: $("#mMinor", m).checked } }); m.remove(); contractDetail(id); };
  };
  $("#editC").onclick = async () => {
    const niches = await freeNiches(c.niche_id);
    const m = modal(`<h2>계약 수정</h2><div class="form-grid"><div class="field"><label>계약자</label><input id="hName" value="${esc(c.holder_name)}"></div><div class="field"><label>연락처</label><input id="hPhone" value="${esc(c.holder_phone)}"></div>
      <div class="field"><label>봉안함</label><select id="hNiche"><option value="">연결 안 함</option>${niches.map((n) => `<option value="${n.id}" ${n.id === c.niche_id ? "selected" : ""}>${esc(n.code)}</option>`).join("")}</select></div>
      <div class="field"><label>요금제</label><select id="hPlan"><option value="basic" ${c.plan === "basic" ? "selected" : ""}>기본</option><option value="premium" ${c.plan === "premium" ? "selected" : ""}>프리미엄</option></select></div></div><button id="hGo" style="margin-top:12px">저장</button>`);
    $("#hGo", m).onclick = async () => { try { await api(`/api/admin/contracts/${id}`, { method: "PUT", body: { holder_name: $("#hName", m).value, holder_phone: $("#hPhone", m).value, niche_id: $("#hNiche", m).value ? +$("#hNiche", m).value : null, plan: $("#hPlan", m).value } }); m.remove(); contractDetail(id); } catch (e) { toast(e.message); } };
  };
}

// ---------------- 고인·기억 카드·동의서 ----------------
async function deceased() {
  const rows = await api("/api/admin/contracts");
  page.innerHTML = `<h1>고인·기억 카드·동의서</h1><p class="muted">계약을 선택해 고인을 등록하고, 상담 인터뷰로 정리한 기억 카드(2,000~5,000자)와 직계가족 동의서를 넣습니다. 동의서와 '대화 기능 열림'이 모두 있어야 유족 앱에서 대화가 열립니다.</p>
    <div class="card"><table><tr><th>계약</th><th>봉안함</th><th>고인</th><th></th></tr>${rows.map((c) => `<tr><td>${esc(c.holder_name)}</td><td>${esc(c.niche_code || "-")}</td><td>${esc(c.deceased_names || "-")}</td><td><button class="small ghost" data-open="${c.id}">열기</button></td></tr>`).join("")}</table></div>`;
  page.querySelectorAll("[data-open]").forEach((b) => b.onclick = () => contractDetail(+b.dataset.open));
}
async function deceasedForm(did, contractId) {
  const detail = await api(`/api/admin/contracts/${contractId}`);
  const x = did ? detail.deceased.find((d) => d.id === did) : { contract_id: contractId, name: "", honorific: "", birth_date: "", death_date: "", memory_card: "", voice_note: "", ai_enabled: 0, chat_min_days_after_death: 49, theme: "classic", consents: [], media: [], photo_path: "", face_id: "", face_provider: "" };
  const kindName = { ai_chat: "AI 대화", likeness: "초상 사용", voice: "음성 사용", lifetime_record: "생전 기록" };
  const m = modal(`<h2>${did ? "고인 편집" : "고인 등록"}</h2>
    <div class="form-grid">
      <div class="field"><label>이름</label><input id="dName" value="${esc(x.name)}"></div>
      <div class="field"><label>가족이 부르던 호칭</label><input id="dHon" value="${esc(x.honorific)}" placeholder="어머니"></div>
      <div class="field"><label>생년월일</label><input id="dBirth" type="date" value="${esc(x.birth_date)}"></div>
      <div class="field"><label>별세일</label><input id="dDeath" type="date" value="${esc(x.death_date)}"></div>
      <div class="field"><label>첫 대화 권장 대기일</label><input id="dDays" type="number" value="${x.chat_min_days_after_death}"></div>
      <div class="field"><label>대화 기능</label><select id="dAi"><option value="0" ${!x.ai_enabled ? "selected" : ""}>닫힘</option><option value="1" ${x.ai_enabled ? "selected" : ""}>열림</option></select></div>
      <div class="field"><label>추모 공간 테마(종교)</label><select id="dTheme">${[["classic", "전통 (먹빛과 금)"], ["buddhist", "불교 (연꽃·등불)"], ["catholic", "천주교 (성당의 빛)"], ["christian", "기독교 (새벽 빛·십자가)"]].map(([v, n]) => `<option value="${v}" ${(x.theme || "classic") === v ? "selected" : ""}>${n}</option>`).join("")}</select></div>
    </div>
    <div class="field" style="margin-top:10px"><label>기억 카드 (호칭·말투·입버릇·좋아하던 것·가족·가족만 아는 일화·성격·당부)</label><textarea id="dCard" style="min-height:220px;font-size:14px">${esc(x.memory_card)}</textarea><small class="muted" id="cardLen">${x.memory_card.length}자</small></div>
    <div class="field"><label>음성 자료 메모(출처·품질)</label><input id="dVoice" value="${esc(x.voice_note)}" placeholder="예: 2023년 생일 영상 1분 20초, 통화 녹음 3건(음질 낮음)"></div>
    <button id="dSave">저장</button>
    ${did ? `<hr style="border:0;border-top:1px solid var(--line);margin:16px 0">
    <h3>사진·자료</h3><div class="row" style="flex-wrap:wrap"><label class="btn small secondary" style="width:auto">대표 사진 올리기<input type="file" id="dPhoto" accept="image/*" hidden></label>
      <select id="mKind" style="width:auto"><option value="photo">사진</option><option value="video">영상</option><option value="voice">음성</option><option value="message_video">영상 메시지(AI 제작)</option></select><input id="mCap" placeholder="설명" style="width:200px"><label class="btn small secondary" style="width:auto">자료 올리기<input type="file" id="dMedia" hidden></label></div>
    <div style="margin-top:8px">${x.photo_path ? `<img src="/api/admin/deceased/${did}/photo.jpg?key=${encodeURIComponent(KEY)}&_=${Date.now()}" class="portrait">` : '<span class="muted">대표 사진 없음</span>'}
      ${x.media.map((md) => `<div class="list-item"><span>${md.kind} · ${esc(md.caption)} ${md.ai_generated ? '<span class="ai-tag">AI 제작</span>' : ""}</span><button class="small ghost" data-delmedia="${md.id}" style="min-height:26px">삭제</button></div>`).join("")}</div>
    <h3 style="margin-top:16px">복제 음성 <span class="muted">(음성 자료 + 음성 사용 동의서가 있어야 등록됩니다)</span></h3>
    <div class="row" style="flex-wrap:wrap">${x.voice_id ? `<span class="tag on">등록됨 · ${esc(x.voice_provider)} · <span class="mono">${esc(x.voice_id.slice(0, 8))}…</span></span><button class="small secondary" id="vPreview">미리 듣기</button><button class="small ghost" id="vDelete">음성 삭제</button>` : `<span class="tag">미등록</span><button class="small secondary" id="vRegister">음성 등록 (ElevenLabs)</button>`}<span id="vOut" class="muted"></span></div>
    <audio id="vAudio" controls style="display:none;margin-top:6px;width:100%"></audio>
    <h3 style="margin-top:16px">실시간 아바타 얼굴 <span class="muted">(대표 사진 + 초상 사용 동의서가 있어야 등록됩니다)</span></h3>
    <div class="row" style="flex-wrap:wrap">${x.face_id ? `<span class="tag on">등록됨 · ${esc(x.face_provider)} · <span class="mono">${esc(x.face_id.slice(0, 8))}…</span></span><button class="small ghost" id="fDelete">얼굴 삭제</button>` : `<span class="tag">미등록</span><button class="small secondary" id="fRegister">사진으로 얼굴 만들기</button>`}<span id="fOut" class="muted"></span></div>
    <div class="row" style="margin-top:6px"><select id="fPreset" style="width:auto"><option value="">기본 얼굴 고르기 (무료 플랜)…</option></select><button class="small secondary" id="fPresetGo">기본 얼굴로 설정</button></div>
    <h3 style="margin-top:16px">동의서</h3>
    ${x.consents.map((k) => `<div class="list-item"><span>${kindName[k.kind]} · ${esc(k.signer_name)}(${esc(k.relation)}) · ${fmt(k.signed_at)} ${k.revoked_at ? `<span class="tag off">철회 ${fmt(k.revoked_at)}</span>` : '<span class="tag on">유효</span>'}</span>${!k.revoked_at ? `<button class="small ghost" data-revoke="${k.id}" style="min-height:26px">철회</button>` : ""}</div>`).join("") || '<p class="muted">동의서 없음 — AI 대화 동의서가 없으면 대화가 열리지 않습니다.</p>'}
    <div class="row" style="margin-top:8px;flex-wrap:wrap"><input id="cSigner" placeholder="서명자" style="width:120px"><input id="cRel" placeholder="관계" style="width:100px"><select id="cKind" style="width:auto"><option value="ai_chat">AI 대화</option><option value="likeness">초상 사용</option><option value="voice">음성 사용</option><option value="lifetime_record">생전 기록</option></select><button class="small secondary" id="cAdd">동의서 등록</button></div>
    <p class="muted" style="font-size:12px">가족 한 명이라도 이의를 제기하면 철회하고 대화 기능을 닫습니다(계획서 7장).</p>` : ""}`);
  $("#dCard", m).oninput = () => $("#cardLen", m).textContent = `${$("#dCard", m).value.length}자`;
  const body = () => ({ contract_id: contractId, name: $("#dName", m).value, honorific: $("#dHon", m).value, birth_date: $("#dBirth", m).value, death_date: $("#dDeath", m).value, memory_card: $("#dCard", m).value, voice_note: $("#dVoice", m).value, ai_enabled: $("#dAi", m).value === "1", chat_min_days_after_death: +$("#dDays", m).value || 49, theme: $("#dTheme", m).value });
  $("#dSave", m).onclick = async () => { try { if (did) await api(`/api/admin/deceased/${did}`, { method: "PUT", body: body() }); else { const r = await api("/api/admin/deceased", { method: "POST", body: body() }); did = r.id; } m.remove(); toast("저장했습니다."); contractDetail(contractId); } catch (e) { toast(e.message); } };
  if (did) {
    $("#dPhoto", m).onchange = async (e) => { const fd = new FormData(); fd.append("file", e.target.files[0]); await api(`/api/admin/deceased/${did}/photo`, { method: "POST", body: fd }); m.remove(); deceasedForm(did, contractId); };
    $("#dMedia", m).onchange = async (e) => { const fd = new FormData(); fd.append("file", e.target.files[0]); await api(`/api/admin/deceased/${did}/media?kind=${$("#mKind", m).value}&caption=${encodeURIComponent($("#mCap", m).value)}`, { method: "POST", body: fd }); m.remove(); deceasedForm(did, contractId); };
    m.querySelectorAll("[data-delmedia]").forEach((b) => b.onclick = async () => { await api(`/api/admin/media/${b.dataset.delmedia}`, { method: "DELETE" }); m.remove(); deceasedForm(did, contractId); });
    m.querySelectorAll("[data-revoke]").forEach((b) => b.onclick = async () => { if (confirm("철회할까요?")) { await api(`/api/admin/consents/${b.dataset.revoke}/revoke`, { method: "POST" }); m.remove(); deceasedForm(did, contractId); } });
    const vOut = (msg, ok) => { const el = $("#vOut", m); el.textContent = msg; el.style.color = ok ? "#1e7a45" : "var(--danger)"; };
    if ($("#vRegister", m)) $("#vRegister", m).onclick = async () => { vOut("등록 중… (1분 안팎)", true); $("#vRegister", m).disabled = true; try { const r = await api(`/api/admin/deceased/${did}/voice/register`, { method: "POST" }); toast(`음성을 등록했습니다 (${r.files}개 파일)`); m.remove(); deceasedForm(did, contractId); } catch (e) { vOut("실패: " + e.message, false); $("#vRegister", m).disabled = false; } };
    if ($("#vDelete", m)) $("#vDelete", m).onclick = async () => { if (confirm("복제 음성을 삭제할까요? 공급자 쪽 데이터도 지웁니다.")) { await api(`/api/admin/deceased/${did}/voice`, { method: "DELETE" }); m.remove(); deceasedForm(did, contractId); } };
    if ($("#vPreview", m)) $("#vPreview", m).onclick = async () => { vOut("합성 중…", true); try { const r = await fetch(`/api/admin/deceased/${did}/voice/preview`, { method: "POST", headers: { "X-Admin-Key": KEY } }); if (!r.ok) throw new Error((await r.json()).detail); const a = $("#vAudio", m); a.src = URL.createObjectURL(await r.blob()); a.style.display = "block"; a.play(); vOut("", true); } catch (e) { vOut("실패: " + e.message, false); } };
    const fOut = (msg, ok) => { const el = $("#fOut", m); el.textContent = msg; el.style.color = ok ? "#1e7a45" : "var(--danger)"; };
    if ($("#fRegister", m)) $("#fRegister", m).onclick = async () => { fOut("얼굴 생성 중… (1~3분)", true); $("#fRegister", m).disabled = true; try { await api(`/api/admin/deceased/${did}/face/register`, { method: "POST" }); toast("얼굴을 등록했습니다."); m.remove(); deceasedForm(did, contractId); } catch (e) { fOut("실패: " + e.message, false); $("#fRegister", m).disabled = false; } };
    if ($("#fDelete", m)) $("#fDelete", m).onclick = async () => { await api(`/api/admin/deceased/${did}/face`, { method: "DELETE" }); m.remove(); deceasedForm(did, contractId); };
    api("/api/admin/avatar/presets").then((list) => { const sel = $("#fPreset", m); list.forEach((pf) => { const o = document.createElement("option"); o.value = pf.id; o.textContent = pf.label; if (pf.id === x.face_id) o.selected = true; sel.appendChild(o); }); }).catch(() => {});
    $("#fPresetGo", m).onclick = async () => { const v = $("#fPreset", m).value; if (!v) return fOut("기본 얼굴을 고르세요.", false); try { await api(`/api/admin/deceased/${did}/face/preset`, { method: "POST", body: { face_id: v } }); toast("기본 얼굴로 설정했습니다."); m.remove(); deceasedForm(did, contractId); } catch (e) { fOut("실패: " + e.message, false); } };
    $("#cAdd", m).onclick = async () => { try { await api(`/api/admin/deceased/${did}/consents`, { method: "POST", body: { signer_name: $("#cSigner", m).value, relation: $("#cRel", m).value, kind: $("#cKind", m).value } }); m.remove(); deceasedForm(did, contractId); } catch (e) { toast(e.message); } };
  }
}

// ---------------- 의례 일정·중계 ----------------
async function rituals() {
  const [rows, cams, cons] = await Promise.all([api("/api/admin/rituals"), api("/api/admin/cameras"), api("/api/admin/contracts")]);
  const kindName = { memorial: "기일", holiday: "명절", event: "행사" };
  page.innerHTML = `<h1>의례 일정·중계</h1><div class="toolbar"><button class="small" id="newR">일정 추가</button></div>
    <div class="card"><table><tr><th>일시</th><th>종류</th><th>제목</th><th>대상</th><th>중계</th><th>다시 보기</th><th></th></tr>
      ${rows.map((r) => `<tr><td>${fmt(r.scheduled_at)}</td><td>${kindName[r.kind]}</td><td><b>${esc(r.title)}</b><div class="muted">${esc(r.note)}</div></td><td>${r.contract_id ? esc(r.holder_name) + " 가족" : "시설 공통"}</td><td>${r.camera_id ? "현장 카메라 #" + r.camera_id : r.stream_url ? '<a href="' + esc(r.stream_url) + '" target="_blank">링크</a>' : "-"}</td><td>${r.replay_url ? '<a href="' + esc(r.replay_url) + '" target="_blank">링크</a>' : "-"}</td><td><button class="small ghost" data-edit="${r.id}">편집</button> <button class="small ghost" data-del="${r.id}">삭제</button></td></tr>`).join("")}</table></div>`;
  const form = (r) => {
    const m = modal(`<h2>${r ? "일정 편집" : "일정 추가"}</h2><div class="form-grid">
      <div class="field"><label>제목</label><input id="rTitle" value="${esc(r?.title || "")}"></div>
      <div class="field"><label>종류</label><select id="rKind">${Object.entries(kindName).map(([k, v]) => `<option value="${k}" ${r?.kind === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <div class="field"><label>일시</label><input id="rAt" type="datetime-local" value="${esc((r?.scheduled_at || "").slice(0, 16))}"></div>
      <div class="field"><label>대상</label><select id="rCon"><option value="">시설 공통</option>${cons.map((c) => `<option value="${c.id}" ${r?.contract_id === c.id ? "selected" : ""}>${esc(c.holder_name)} 가족</option>`).join("")}</select></div>
      <div class="field"><label>현장 카메라</label><select id="rCam"><option value="">없음</option>${cams.map((c) => `<option value="${c.id}" ${r?.camera_id === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>
      <div class="field"><label>중계 링크(유튜브 등)</label><input id="rUrl" value="${esc(r?.stream_url || "")}"></div>
      <div class="field"><label>다시 보기 링크</label><input id="rReplay" value="${esc(r?.replay_url || "")}"></div>
      <div class="field"><label>메모</label><input id="rNote" value="${esc(r?.note || "")}"></div></div><button id="rGo" style="margin-top:12px">저장</button>`);
    $("#rGo", m).onclick = async () => {
      const body = { title: $("#rTitle", m).value, kind: $("#rKind", m).value, scheduled_at: $("#rAt", m).value, contract_id: $("#rCon", m).value ? +$("#rCon", m).value : null, camera_id: $("#rCam", m).value ? +$("#rCam", m).value : null, stream_url: $("#rUrl", m).value, replay_url: $("#rReplay", m).value, note: $("#rNote", m).value };
      try { await api(r ? `/api/admin/rituals/${r.id}` : "/api/admin/rituals", { method: r ? "PUT" : "POST", body }); m.remove(); rituals(); } catch (e) { toast(e.message); }
    };
  };
  $("#newR").onclick = () => form(null);
  page.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => form(rows.find((r) => r.id === +b.dataset.edit)));
  page.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => { if (confirm("삭제할까요?")) { await api(`/api/admin/rituals/${b.dataset.del}`, { method: "DELETE" }); rituals(); } });
}

// ---------------- 공양 접수·이용 현황 ----------------
async function usage() {
  const [offs, u] = await Promise.all([api("/api/admin/offerings"), api("/api/admin/usage")]);
  const kindLabel = { offering: "공양", flower: "헌화", prayer: "기도" };
  const statuses = { requested: "접수 대기", accepted: "접수됨", done: "봉행 완료", cancelled: "취소" };
  page.innerHTML = `<h1>공양 접수·이용 현황</h1>
    <div class="card"><h3>공양·헌화·기도 신청</h3><table><tr><th>일시</th><th>가족</th><th>종류</th><th>일정</th><th>금액</th><th>전할 말</th><th>상태</th></tr>
      ${offs.map((o) => `<tr><td>${fmt(o.created_at)}</td><td>${esc(o.member_name || o.holder_name)}<div class="muted">${esc(o.holder_name)} 계약</div></td><td>${kindLabel[o.kind]}</td><td>${esc(o.ritual_title || "-")}</td><td>${(o.amount || 0).toLocaleString()}원</td><td>${esc(o.note)}</td>
        <td><select data-status="${o.id}">${Object.entries(statuses).map(([k, v]) => `<option value="${k}" ${o.status === k ? "selected" : ""}>${v}</option>`).join("")}</select></td></tr>`).join("") || '<tr><td colspan="7" class="muted">신청 없음</td></tr>'}</table></div>
    <div class="card"><h3>대화 세션 <span class="muted">(원문은 저장하지 않으며 요약만 남습니다 · 안전 점검 발동 ${u.safety_events}건)</span></h3><table><tr><th>시작</th><th>가족</th><th>고인</th><th>왕복</th><th>공급자</th><th>안전 점검</th><th>요약</th></tr>
      ${u.chat_sessions.map((s) => `<tr><td>${fmt(s.started_at)}</td><td>${esc(s.member_name)}</td><td>${esc(s.deceased_name)}</td><td>${s.turns}</td><td>${esc(s.provider)}</td><td>${s.safety_events && s.safety_events !== "[]" ? `<span class="tag busy">${esc(s.safety_events)}</span>` : "-"}</td><td class="muted">${esc(s.summary)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">없음</td></tr>'}</table></div>
    <div class="card"><h3>실시간 보기</h3><table><tr><th>시작</th><th>가족</th><th>봉안함</th><th>종료</th></tr>${u.live_sessions.map((l) => `<tr><td>${fmt(l.started_at)}</td><td>${esc(l.member_name)}</td><td>${esc(l.code)}</td><td>${fmt(l.expires_at)}</td></tr>`).join("") || '<tr><td colspan="4" class="muted">없음</td></tr>'}</table></div>
    <div class="card"><h3>접근 기록(관리자 열람 포함)</h3><table>${u.audit.map((a) => `<tr><td class="muted">${fmt(a.created_at)}</td><td>${esc(a.actor)}</td><td>${esc(a.action)}</td><td>${esc(a.target)}</td><td class="muted">${esc(a.detail)}</td></tr>`).join("")}</table></div>`;
  page.querySelectorAll("[data-status]").forEach((s) => s.onchange = async () => { await api(`/api/admin/offerings/${s.dataset.status}/status`, { method: "POST", body: { status: s.value } }); toast("상태를 바꿨습니다."); });
}

// ---------------- AI 설정 (API 키) ----------------
async function aisettings() {
  const s = await api("/api/admin/settings/ai");
  const provName = { anthropic: "Anthropic Claude (실제 AI)", mock: "Mock (규칙 기반, 비용 없음)" };
  const srcName = { console: "관리자 콘솔에서 입력", env: ".env 파일", none: "없음" };
  page.innerHTML = `<h1>AI 설정</h1><p class="muted">기념일 대화에 쓰는 언어 모델 설정입니다. API 키는 여기서 입력하며 서버 DB에만 저장되고 유족 앱에는 절대 노출되지 않습니다.</p>
    <div class="kpi" style="margin:14px 0;max-width:720px">
      <div class="card"><div class="muted">지금 동작 중인 공급자</div><div class="n" style="font-size:20px">${provName[s.active_provider] || s.active_provider}</div></div>
      <div class="card"><div class="muted">API 키</div><div class="n" style="font-size:20px">${s.api_key_masked ? `<span class="mono">${esc(s.api_key_masked)}</span>` : (s.api_key_source === "env" ? ".env에서 읽음" : '<span class="tag off">없음</span>')}</div><div class="muted" style="font-size:12px">출처: ${srcName[s.api_key_source]}${s.updated_at ? " · " + fmt(s.updated_at) : ""}</div></div>
    </div>
    <div class="card" style="max-width:720px">
      <div class="field"><label>Anthropic API 키 <span class="muted">(sk-ant-… · 비워 두면 기존 키 유지)</span></label>
        <div class="row"><input id="aiKey" type="password" placeholder="${s.api_key_masked ? "기존 키 유지" : "sk-ant-api03-…"}" autocomplete="off" spellcheck="false"><button class="small ghost" id="aiEye" style="min-height:40px">보기</button></div></div>
      <div class="form-grid">
        <div class="field"><label>공급자</label><select id="aiProv">
          <option value="auto" ${s.provider === "auto" ? "selected" : ""}>자동 (키가 있으면 Claude, 없으면 Mock)</option>
          <option value="anthropic" ${s.provider === "anthropic" ? "selected" : ""}>Anthropic Claude</option>
          <option value="mock" ${s.provider === "mock" ? "selected" : ""}>Mock (규칙 기반)</option></select></div>
        <div class="field"><label>모델</label><select id="aiModel">${s.models.map((m) => `<option value="${m}" ${m === s.model ? "selected" : ""}>${m}${m === "claude-opus-5" ? " (권장)" : ""}</option>`).join("")}</select></div>
      </div>
      <div class="toolbar" style="margin-top:10px"><button class="small" id="aiSave">저장</button><button class="small secondary" id="aiTest">연결 테스트</button>${s.api_key_masked ? `<button class="small ghost" id="aiClear">키 삭제</button>` : ""}<span id="aiOut" class="muted"></span></div>
      <p class="muted" style="font-size:13px;margin-top:12px">키는 <a href="https://console.anthropic.com/settings/keys" target="_blank">console.anthropic.com → API Keys</a>에서 발급합니다. 대화 1회(10분, 20회 왕복) 기준 원가는 계획서 6장 추정으로 15~30원 수준이며, 연결 테스트 1회는 그보다 훨씬 적습니다.</p>
    </div>
    <h2 style="margin-top:20px">음성 복제 (ElevenLabs)</h2>
    <p class="muted">고인별로 음성 자료를 올리고 '음성 등록'을 누르면 그 목소리로 대화가 재생됩니다(B등급). 키가 없으면 브라우저 기본 음성을 씁니다.</p>
    <div class="kpi" style="margin:14px 0;max-width:720px">
      <div class="card"><div class="muted">지금 동작 중인 음성</div><div class="n" style="font-size:20px">${s.active_tts === "elevenlabs" ? "ElevenLabs 복제 음성" : "브라우저 기본 음성"}</div><div class="muted" style="font-size:12px">등록된 고인 음성 ${s.voices_registered}건</div></div>
      <div class="card"><div class="muted">ElevenLabs 키</div><div class="n" style="font-size:20px">${s.elevenlabs_key_masked ? `<span class="mono">${esc(s.elevenlabs_key_masked)}</span>` : (s.elevenlabs_key_source === "env" ? ".env에서 읽음" : '<span class="tag off">없음</span>')}</div></div>
    </div>
    <div class="card" style="max-width:720px">
      <div class="field"><label>ElevenLabs API 키 <span class="muted">(비워 두면 기존 키 유지)</span></label>
        <div class="row"><input id="elKey" type="password" placeholder="${s.elevenlabs_key_masked ? "기존 키 유지" : "xi-…"}" autocomplete="off" spellcheck="false"><button class="small ghost" id="elEye" style="min-height:40px">보기</button></div></div>
      <div class="form-grid">
        <div class="field"><label>음성 공급자</label><select id="ttsProv">
          <option value="auto" ${s.tts_provider === "auto" ? "selected" : ""}>자동 (키가 있으면 ElevenLabs)</option>
          <option value="elevenlabs" ${s.tts_provider === "elevenlabs" ? "selected" : ""}>ElevenLabs</option>
          <option value="browser" ${s.tts_provider === "browser" ? "selected" : ""}>브라우저 기본 음성만 (복제 음성 끔)</option></select></div>
        <div class="field"><label>음성 모델</label><select id="ttsModel">${s.tts_models.map((m) => `<option value="${m}" ${m === s.tts_model ? "selected" : ""}>${m}${({ eleven_multilingual_v2: " (안정적 · 한국어 기본)", eleven_v3: " (가장 자연스러움 · 감정 표현 · 답 2~4초 느림)", eleven_v3_conversational: " (v3 실시간형 · 빠름)", eleven_flash_v2_5: " (가장 빠름·저렴 · 품질 낮음)" })[m] || ""}</option>`).join("")}</select></div>
      </div>
      <details style="margin-top:6px" open><summary style="cursor:pointer;font-weight:700">음성 세부 설정 — 봇 느낌 줄이기 (저장 전에 미리 들어 보세요)</summary>
        <div class="form-grid" style="margin-top:8px">
          <div class="field"><label>안정감 <b id="vsStabV"></b> <span class="muted">낮을수록 억양·감정 기복이 커짐</span></label><input type="range" id="vsStab" min="0" max="1" step="0.05" value="${s.tts_voice_settings.stability}"></div>
          <div class="field"><label>목소리 유사도 <b id="vsSimV"></b> <span class="muted">원본과 닮은 정도</span></label><input type="range" id="vsSim" min="0" max="1" step="0.05" value="${s.tts_voice_settings.similarity_boost}"></div>
          <div class="field"><label>표현력 <b id="vsStyleV"></b> <span class="muted">높을수록 풍부, 너무 높으면 흔들림</span></label><input type="range" id="vsStyle" min="0" max="1" step="0.05" value="${s.tts_voice_settings.style}"></div>
          <div class="field"><label>말 빠르기 <b id="vsSpeedV"></b> <span class="muted">어르신 말투는 0.9~0.95 · v3 계열은 미적용</span></label><input type="range" id="vsSpeed" min="0.7" max="1.2" step="0.05" value="${s.tts_voice_settings.speed}"></div>
        </div>
        <div class="field"><label>미리 듣기 문장</label><input id="vsText" value="아이고, 우리 강아지 왔냐. 밥은 묵었냐? 요즘 날이 쌀쌀헌디 옷 따숩게 입고 댕겨라."></div>
        <div class="toolbar"><button class="small secondary" id="vsPreview">이 설정으로 미리 듣기</button><button class="small ghost" id="vsReset">권장값으로</button><span id="vsOut" class="muted"></span></div>
        <audio id="vsAudio" controls style="display:none;width:100%;max-width:520px;margin-top:6px"></audio>
        <div class="notice" style="margin-top:10px;font-size:13px"><b>더 자연스럽게 만드는 순서 (효과가 큰 것부터)</b><br>
          1) <b>녹음 원본이 90%</b>: 또박또박 읽은 목소리는 봇처럼 나옵니다. 조용한 방에서 <b>평소 대화하듯 웃고 쉬어 가며 3분 이상</b> 녹음한 파일로 다시 등록하세요. 여러 파일(총 5분 안팎)을 함께 올리면 더 좋습니다.<br>
          2) 위 슬라이더: 안정감 0.35~0.45 · 표현력 0.3~0.45 · 속도 0.9~0.95 → "미리 듣기"로 비교 후 저장<br>
          3) 모델을 <b>eleven_v3</b>로 바꿔 보기(감정·억양이 가장 자연스럽지만 답이 2~4초 늦고 실시간 아바타와는 쓰지 못할 수 있음). 실시간이 필요하면 <b>eleven_v3_conversational</b><br>
          4) <b>Professional Voice Clone(PVC)</b>: Creator 요금제(월 $11~)부터. 깨끗한 음성 30분 이상(3시간이 최적)이면 원본과 거의 구분되지 않습니다. 생전 기록 자원자에게 가장 권합니다.<br>
          5) 다른 API(2026-09 조사): <b>Fish Audio S2.1 Pro</b>(한·중·일에 강함, TTS-Arena 상위, 15초~3분 샘플 복제, 저렴) · <b>Cartesia Sonic 3.6</b>(한국어 지원, 40~90ms 초저지연, 실시간 아바타용) · <b>MiniMax Speech-02</b>(다국어·저비용). 국내 <b>Supertone</b>은 검색 결과에 "2026-08-31 API 종료" 공지가 보이나 페이지 접근이 막혀 직접 확인하지 못했습니다. 연동은 tts.py에 공급자 클래스 하나 추가로 가능하며, 비교 청취 후 결정하는 것을 권합니다.</div>
      </details>
      ${s.elevenlabs_key_masked && s.tts_provider === "browser" ? '<div class="notice" style="margin-top:8px">키는 있지만 공급자가 "브라우저 기본 음성만"이라 복제 음성이 꺼져 있습니다. "자동"으로 바꾸고 저장하세요.</div>' : ""}
      <div class="toolbar" style="margin-top:10px"><button class="small" id="elSave">저장</button><button class="small secondary" id="elTest">연결 테스트</button>${s.elevenlabs_key_masked ? `<button class="small ghost" id="elClear">키 삭제</button>` : ""}<span id="elOut" class="muted"></span></div>
      <div class="notice" style="margin-top:12px;font-size:13px"><b>ElevenLabs 키 만드는 법 (그대로 따라 하세요)</b><br>
        1) <a href="https://elevenlabs.io/app/settings/api-keys" target="_blank">elevenlabs.io/app/settings/api-keys</a> → <b>Create API Key</b><br>
        2) 이름 아무거나 · 만료 기간 <b>90일 이상</b> · <b>"사용 제한 (크레딧)"의 '크레딧 갱신 주기당' 칸은 비워 두기</b>(0을 넣으면 모든 합성이 막힘)<br>
        3) <b>키 제한 토글을 끄기(OFF)</b> ← 가장 확실. 끄면 아래 4)는 건너뜀<br>
        4) 제한을 켜야 한다면 딱 세 개만: <b>텍스트 음성 변환 = 접근</b> · <b>음성(Voices) = 쓰기</b> · <b>사용자(User) = 읽기</b> (나머지 전부 접근 불가. "음성 변환"은 다른 기능이니 건드리지 않음)<br>
        5) 키 생성 → 화면에 한 번만 보이는 키를 복사 → 위 칸에 붙여 넣기 → 저장 → 연결 테스트에서 ✓ 세 개 확인<br>
        ※ 옛 키를 지우거나 새로 만들면 여기 저장된 키도 반드시 새 것으로 바꿔야 합니다("기존 키 유지"는 옛 키를 그대로 쓴다는 뜻).<br>
        ※ 키를 만든 <b>직후 한 번만 보이는 sk_… 전체 값</b>을 복사합니다. 키 목록의 짧은 요약본은 쓸 수 없습니다.
        <details style="margin-top:8px"><summary style="cursor:pointer;font-weight:700">"키 제한"을 켠 경우 — ElevenLabs 편집창 항목별 선택값 (전체)</summary>
        <table style="margin-top:6px;font-size:12px"><tr><th>항목</th><th>선택</th></tr>
          <tr><td>이름</td><td>아무거나</td></tr><tr><td>만료 기간</td><td>90일 이상 (편집 중이면 "현재 값 유지")</td></tr>
          <tr><td>사용 제한(크레딧) · 크레딧 갱신 주기당</td><td>비움(무제한) 또는 10000</td></tr>
          <tr><td colspan="2" style="background:#f4f1ea"><b>엔드포인트</b></td></tr>
          <tr><td><b>텍스트 음성 변환</b></td><td><b>접근</b></td></tr>
          <tr><td>음성 변환</td><td>접근 불가</td></tr><tr><td>음성 텍스트 변환</td><td>접근 불가</td></tr><tr><td>효과음</td><td>접근 불가</td></tr>
          <tr><td>오디오 아이솔레이션</td><td>접근 불가</td></tr><tr><td>뮤직 생성</td><td>접근 불가</td></tr><tr><td>이미지 및 동영상 생성</td><td>접근 불가</td></tr>
          <tr><td>더빙</td><td>접근 불가</td></tr><tr><td>ElevenAgents</td><td>접근 불가</td></tr><tr><td>프로젝트</td><td>접근 불가</td></tr><tr><td>오디오 네이티브</td><td>접근 불가</td></tr>
          <tr><td><b>음성</b></td><td><b>작성</b></td></tr>
          <tr><td>음성 생성</td><td>접근 불가</td></tr><tr><td>강제 정렬</td><td>접근 불가</td></tr><tr><td>Ads 엔진</td><td>접근 불가</td></tr>
          <tr><td colspan="2" style="background:#f4f1ea"><b>관리</b></td></tr>
          <tr><td>기록</td><td>접근 불가</td></tr><tr><td>모델들</td><td>접근 불가</td></tr><tr><td>발음 사전</td><td>접근 불가</td></tr>
          <tr><td><b>사용자</b></td><td><b>접근</b></td></tr>
          <tr><td>워크스페이스</td><td>접근 불가</td></tr><tr><td>워크스페이스 분석</td><td>접근 불가</td></tr><tr><td>웹훅</td><td>접근 불가</td></tr><tr><td>서비스 계정</td><td>접근 불가</td></tr>
          <tr><td>그룹 멤버</td><td>접근 불가</td></tr><tr><td>워크스페이스 멤버 읽기 / 초대 / 제거</td><td>접근 불가</td></tr><tr><td>서비스 약관 동의</td><td>접근 불가</td></tr>
          <tr><td colspan="2" style="background:#f4f1ea"><b>그 밖</b></td></tr>
          <tr><td>IP 주소로 제한</td><td>비움 (노트북·휴대폰·배포 서버 IP가 바뀜)</td></tr><tr><td>유출 시 자동 비활성화</td><td>켬(기본값 유지)</td></tr>
        </table>
        <p style="margin:6px 0 0">요약: <b>접근/작성으로 켜는 건 딱 3개 — 텍스트 음성 변환·음성·사용자.</b> 나머지 전부 접근 불가.</p></details></div>
      <p class="muted" style="font-size:13px;margin-top:12px">Instant Voice Clone은 Starter 요금제(월 $6, 30,000크레딧)부터 가능합니다. 답변 1회 60자 ≈ 60크레딧이므로 10분 대화(20회 왕복) ≈ 1,200크레딧, Starter로 월 25회 정도입니다. <b>약관상 본인 동의가 전제</b>이므로 시연은 생전 기록 자원자(본인 목소리)로, 고인 적용은 법률 자문 뒤에 합니다.</p>
    </div>
    <h2 style="margin-top:20px">실시간 아바타 (D-ID · Simli)</h2>
    <p class="muted">고인의 정면 사진으로 대화 중 복제 음성에 입을 맞춘 영상을 실시간으로 보여 줍니다(A등급). 복제 음성(ElevenLabs)이 있어야 동작하며, 없으면 사진 아바타로 자동 복귀합니다.<br>
      <b>D-ID</b>는 올린 사진 그대로를 움직여 <b>얼굴이 실제와 같고</b>(권장), <b>Simli</b>는 사진으로 3D 얼굴을 새로 만듭니다(유료 플랜 필요, 무료는 기본 얼굴만).</p>
    <div class="kpi" style="margin:14px 0;max-width:720px">
      <div class="card"><div class="muted">지금 동작 중인 아바타</div><div class="n" style="font-size:20px">${s.active_avatar === "did" ? "D-ID 실시간 아바타" : s.active_avatar === "simli" ? "Simli 실시간 아바타" : "사진 아바타(기본)"}</div><div class="muted" style="font-size:12px">등록된 얼굴 ${s.faces_registered}건</div></div>
      <div class="card"><div class="muted">D-ID 키</div><div class="n" style="font-size:20px">${s.did_key_masked ? `<span class="mono">${esc(s.did_key_masked)}</span>` : (s.did_key_source === "env" ? ".env에서 읽음" : '<span class="tag off">없음</span>')}</div></div>
      <div class="card"><div class="muted">Simli 키</div><div class="n" style="font-size:20px">${s.simli_key_masked ? `<span class="mono">${esc(s.simli_key_masked)}</span>` : (s.simli_key_source === "env" ? ".env에서 읽음" : '<span class="tag off">없음</span>')}</div></div>
    </div>
    <div class="card" style="max-width:720px">
      <div class="field"><label>D-ID API 키 <span class="muted">(비워 두면 기존 키 유지 · 'API_USER:API_PASSWORD' 형태 그대로)</span></label>
        <div class="row"><input id="ddKey" type="password" placeholder="${s.did_key_masked ? "기존 키 유지" : "studio.d-id.com → Account settings 에서 발급"}" autocomplete="off" spellcheck="false"><button class="small ghost" id="ddEye" style="min-height:40px">보기</button></div></div>
      <div class="field"><label>Simli API 키 <span class="muted">(비워 두면 기존 키 유지)</span></label>
        <div class="row"><input id="smKey" type="password" placeholder="${s.simli_key_masked ? "기존 키 유지" : "app.simli.com 에서 발급한 키"}" autocomplete="off" spellcheck="false"><button class="small ghost" id="smEye" style="min-height:40px">보기</button></div></div>
      <div class="field"><label>아바타 공급자</label><select id="avProv">
        <option value="auto" ${s.avatar_provider === "auto" ? "selected" : ""}>자동 (D-ID 키가 있으면 D-ID, 아니면 Simli)</option>
        <option value="did" ${s.avatar_provider === "did" ? "selected" : ""}>D-ID (실제 사진)</option>
        <option value="simli" ${s.avatar_provider === "simli" ? "selected" : ""}>Simli</option>
        <option value="off" ${s.avatar_provider === "off" ? "selected" : ""}>끔 (사진 아바타만)</option></select></div>
      ${(s.simli_key_masked || s.did_key_masked) && s.avatar_provider === "off" ? '<div class="notice" style="margin-top:8px">키는 있지만 공급자가 "끔"이라 실시간 아바타가 꺼져 있습니다. "자동"으로 바꾸고 저장하세요.</div>' : ""}
      <div class="toolbar" style="margin-top:10px"><button class="small" id="smSave">저장</button><button class="small secondary" id="ddTest">D-ID 연결 테스트</button><button class="small secondary" id="smTest">Simli 연결 테스트</button>${s.did_key_masked ? `<button class="small ghost" id="ddClear">D-ID 키 삭제</button>` : ""}${s.simli_key_masked ? `<button class="small ghost" id="smClear">Simli 키 삭제</button>` : ""}<span id="smOut" class="muted"></span></div>
      <div class="notice" style="margin-top:12px;font-size:13px"><b>D-ID 키 만드는 법 (2026-09-19 공식 문서 기준)</b><br>
        1) <a href="https://studio.d-id.com" target="_blank">studio.d-id.com</a> 로그인 (14일 무료 체험: 영상 3분)<br>
        2) <b>Account settings</b>(계정 설정) → <b>Generate API key</b>(API 키 생성) — 키는 <b>한 번만</b> 보입니다<br>
        3) 표시된 값 전체(예: <span class="mono">bGVl…==:abcd1234</span>, 가운데 콜론 포함)를 복사 → 위 D-ID 칸에 붙여 넣고 저장 → 자동 연결 테스트<br>
        ※ 실제 인물 사진은 D-ID 자동 검열에 걸릴 수 있습니다. 거부되면 다른 사진으로 다시 시도하거나 D-ID 지원팀에 수동 심사를 요청합니다.</div>
      <div class="notice" style="margin-top:12px;font-size:13px"><b>Simli 키 만드는 법 (2026-09-19 문서 기준)</b><br>
        1) <a href="https://app.simli.com" target="_blank">app.simli.com</a> 가입 → 무료로 $10 + 매월 50분이 들어옵니다<br>
        2) 대시보드에서 API 키를 만들어 복사 → 위 칸에 붙여 넣고 저장 → 연결 테스트<br>
        ※ 키 발급 화면의 정확한 메뉴 이름은 로그인이 필요해 확인하지 못했습니다. 화면 문구를 알려 주시면 이 안내에 그대로 넣겠습니다.<br>
        ※ 사진 조건: JPEG/PNG/WEBP, 5MB 이하, 512×512 이상, 정면, 머리가 화면 높이의 15% 이상. 얼굴 생성은 수 분 걸릴 수 있습니다.</div>
    </div>`;
  const out = (msg, ok) => { const el = $("#aiOut"); el.textContent = msg; el.style.color = ok ? "#1e7a45" : "var(--danger)"; };
  const outSm = (msg, ok) => { const el = $("#smOut"); el.textContent = msg; el.style.color = ok ? "#1e7a45" : "var(--danger)"; };
  $("#aiEye").onclick = () => { const i = $("#aiKey"); i.type = i.type === "password" ? "text" : "password"; $("#aiEye").textContent = i.type === "password" ? "보기" : "숨기기"; };
  const outEl = (msg, ok) => { const el = $("#elOut"); el.textContent = msg; el.style.color = ok ? "#1e7a45" : "var(--danger)"; };
  const voiceSettings = () => ({ stability: +$("#vsStab").value, similarity_boost: +$("#vsSim").value, style: +$("#vsStyle").value, speed: +$("#vsSpeed").value });
  const showVs = () => { $("#vsStabV").textContent = (+$("#vsStab").value).toFixed(2); $("#vsSimV").textContent = (+$("#vsSim").value).toFixed(2); $("#vsStyleV").textContent = (+$("#vsStyle").value).toFixed(2); $("#vsSpeedV").textContent = (+$("#vsSpeed").value).toFixed(2); };
  ["#vsStab", "#vsSim", "#vsStyle", "#vsSpeed"].forEach((id) => $(id).oninput = showVs); showVs();
  $("#vsReset").onclick = () => { const d = s.tts_voice_defaults; $("#vsStab").value = d.stability; $("#vsSim").value = d.similarity_boost; $("#vsStyle").value = d.style; $("#vsSpeed").value = d.speed; showVs(); };
  $("#vsPreview").onclick = async () => {
    const o = $("#vsOut"); o.textContent = "합성 중… (2~6초)"; o.style.color = ""; $("#vsPreview").disabled = true;
    try {
      const r = await fetch("/api/admin/settings/tts/preview", { method: "POST", headers: { "X-Admin-Key": KEY, "Content-Type": "application/json" }, body: JSON.stringify({ text: $("#vsText").value, model: $("#ttsModel").value, settings: voiceSettings() }) });
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      const a = $("#vsAudio"); a.src = URL.createObjectURL(await r.blob()); a.style.display = "block"; await a.play(); o.textContent = "마음에 들면 '저장'을 누르세요. 다음 대화부터 적용됩니다.";
    } catch (e) { o.textContent = "실패: " + e.message; o.style.color = "var(--danger)"; }
    $("#vsPreview").disabled = false;
  };
  const body = (o = {}) => ({ api_key: $("#aiKey").value.trim() || null, provider: $("#aiProv").value, model: $("#aiModel").value,
    elevenlabs_api_key: $("#elKey").value.trim() || null, tts_provider: $("#ttsProv").value, tts_model: $("#ttsModel").value, tts_voice_settings: voiceSettings(),
    simli_api_key: $("#smKey").value.trim() || null, did_api_key: $("#ddKey").value.trim() || null, avatar_provider: $("#avProv").value, ...o });
  $("#ddEye").onclick = () => { const i = $("#ddKey"); i.type = i.type === "password" ? "text" : "password"; $("#ddEye").textContent = i.type === "password" ? "보기" : "숨기기"; };
  async function runDdTest() {
    outSm("D-ID 확인 중…", true); $("#ddTest").disabled = true;
    try { const r = await api("/api/admin/settings/did/test", { method: "POST" }); outSm(`D-ID 연결 성공${r.note ? " · " + r.note : ""}`, true); }
    catch (e) { outSm("D-ID 실패: " + e.message, false); }
    $("#ddTest").disabled = false;
  }
  $("#ddTest").onclick = async () => { if ($("#ddKey").value.trim()) { try { await api("/api/admin/settings/ai", { method: "PUT", body: body() }); } catch (e) { return outSm(e.message, false); } } await runDdTest(); };
  if ($("#ddClear")) $("#ddClear").onclick = async () => { const b = $("#ddClear"); if (b.dataset.armed !== "1") { b.dataset.armed = "1"; b.textContent = "정말 삭제 (다시 누르기)"; b.style.color = "var(--danger)"; setTimeout(() => { b.dataset.armed = ""; b.textContent = "D-ID 키 삭제"; b.style.color = ""; }, 5000); return; } try { await api("/api/admin/settings/ai", { method: "PUT", body: body({ did_api_key: "" }) }); toast("D-ID 키를 삭제했습니다."); aisettings(); } catch (e) { outSm(e.message, false); } };
  $("#smEye").onclick = () => { const i = $("#smKey"); i.type = i.type === "password" ? "text" : "password"; $("#smEye").textContent = i.type === "password" ? "보기" : "숨기기"; };
  async function runSmTest() {
    outSm("확인 중…", true); $("#smTest").disabled = true;
    try { const r = await api("/api/admin/settings/avatar/test", { method: "POST" }); const c = r.checks || {};
      outSm(`${r.all_ok ? "연결 성공" : "키는 유효하지만 세션 실패"} · 얼굴 목록 ${c.faces_list === "ok" ? "✓" : "✗"} · 세션 토큰 ${c.session_token === "ok" ? "✓" : "✗"} · 등록된 얼굴 ${r.faces}개${r.note ? " · " + r.note : ""}`, !!r.all_ok); }
    catch (e) { outSm("실패: " + e.message, false); }
    $("#smTest").disabled = false;
  }
  $("#smSave").onclick = async () => { const typedSm = $("#smKey").value.trim(), typedDd = $("#ddKey").value.trim(); try { await api("/api/admin/settings/ai", { method: "PUT", body: body() }); } catch (e) { return outSm(e.message, false); } if (typedDd) { outSm("저장됨 · 연결 확인 중…", true); await runDdTest(); } else if (typedSm) { outSm("저장됨 · 연결 확인 중…", true); await runSmTest(); } else { toast("저장했습니다."); aisettings(); } };
  $("#smTest").onclick = async () => { if ($("#smKey").value.trim()) { try { await api("/api/admin/settings/ai", { method: "PUT", body: body() }); } catch (e) { return outSm(e.message, false); } } await runSmTest(); };
  if ($("#smClear")) $("#smClear").onclick = async () => { const b = $("#smClear"); if (b.dataset.armed !== "1") { b.dataset.armed = "1"; b.textContent = "정말 삭제 (다시 누르기)"; b.style.color = "var(--danger)"; setTimeout(() => { b.dataset.armed = ""; b.textContent = "키 삭제"; b.style.color = ""; }, 5000); return; } try { await api("/api/admin/settings/ai", { method: "PUT", body: body({ simli_api_key: "" }) }); toast("Simli 키를 삭제했습니다."); aisettings(); } catch (e) { outSm(e.message, false); } };
  const save = async (keyOverride) => {
    try { await api("/api/admin/settings/ai", { method: "PUT", body: body(keyOverride !== undefined ? { api_key: keyOverride } : {}) }); toast("저장했습니다. 다음 대화부터 적용됩니다."); aisettings(); }
    catch (e) { out(e.message, false); }
  };
  $("#elEye").onclick = () => { const i = $("#elKey"); i.type = i.type === "password" ? "text" : "password"; $("#elEye").textContent = i.type === "password" ? "보기" : "숨기기"; };
  // 확인창(confirm)은 일부 환경에서 자동으로 취소되므로, 화면 안에서 두 번 누르는 방식으로 삭제한다.
  if ($("#elClear")) $("#elClear").onclick = async () => {
    const b = $("#elClear");
    if (b.dataset.armed !== "1") { b.dataset.armed = "1"; b.textContent = "정말 삭제 (다시 누르기)"; b.style.color = "var(--danger)"; setTimeout(() => { b.dataset.armed = ""; b.textContent = "키 삭제"; b.style.color = ""; }, 5000); return; }
    try { await api("/api/admin/settings/ai", { method: "PUT", body: body({ elevenlabs_api_key: "" }) }); toast("ElevenLabs 키를 삭제했습니다."); aisettings(); } catch (e) { outEl(e.message, false); }
  };
  if ($("#aiClear")) $("#aiClear").onclick = async () => {
    const b = $("#aiClear");
    if (b.dataset.armed !== "1") { b.dataset.armed = "1"; b.textContent = "정말 삭제 (다시 누르기)"; b.style.color = "var(--danger)"; setTimeout(() => { b.dataset.armed = ""; b.textContent = "키 삭제"; b.style.color = ""; }, 5000); return; }
    save("");
  };
  $("#elSave").onclick = async () => {
    const typed = $("#elKey").value.trim();
    try { await api("/api/admin/settings/ai", { method: "PUT", body: body() }); } catch (e) { return outEl(e.message, false); }
    if (typed) { outEl("저장됨 · 연결 확인 중…", true); await runElTest(); } else { toast("저장했습니다."); aisettings(); }
  };
  async function runElTest() {
    outEl("확인 중…", true); $("#elTest").disabled = true;
    try { const r = await api("/api/admin/settings/tts/test", { method: "POST" });
      const c = r.checks || {}; const mark = (k) => c[k] === "ok" ? "✓" : c[k] === "quota" ? "✗(키 크레딧 한도)" : "✗";
      const list = `권한 확인 — 텍스트 음성 변환 ${mark("text_to_speech")} · 음성(Voices) ${mark("voices_read")} · 사용자 읽기 ${mark("user_read")}`;
      outEl(`${r.all_ok ? "연결 성공" : "키는 유효하지만 권한 부족"} · ${list}${r.tier ? ` · 요금제 ${r.tier} · ${r.used ?? "-"}/${r.limit ?? "-"} 크레딧` : ""}${r.note ? " · " + r.note : ""}`, !!r.all_ok); }
    catch (e) { outEl("실패: " + e.message, false); }
    $("#elTest").disabled = false;
  }
  $("#elTest").onclick = async () => {
    if ($("#elKey").value.trim()) { try { await api("/api/admin/settings/ai", { method: "PUT", body: body() }); } catch (e) { return outEl(e.message, false); } }
    await runElTest();
  };
  $("#aiSave").onclick = () => save();
  $("#aiTest").onclick = async () => {
    if ($("#aiKey").value.trim()) { await save(); }
    out("확인 중…", true); $("#aiTest").disabled = true;
    try { const r = await api("/api/admin/settings/ai/test", { method: "POST" }); out(`연결 성공 · ${r.model} 응답: "${r.reply}"`, true); }
    catch (e) { out("실패: " + e.message, false); }
    $("#aiTest").disabled = false;
  };
}

boot();
