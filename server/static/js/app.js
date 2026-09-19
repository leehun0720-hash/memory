// 유족 웹앱. 초대 링크(/?t=토큰)로 열리며 설치가 필요 없다.
const qs = new URLSearchParams(location.search);
const TOKEN = qs.get("t") || localStorage.getItem("family_token");
if (qs.get("t")) { localStorage.setItem("family_token", qs.get("t")); history.replaceState(null, "", location.pathname); }

const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDT = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : `${d.getMonth() + 1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const fmtD = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`; };
const ago = (iso) => { if (!iso) return "아직 없음"; const s = Math.max(0, (Date.now() - new Date(iso)) / 1000); return s < 60 ? `${Math.round(s)}초 전` : s < 3600 ? `${Math.round(s / 60)}분 전` : `${Math.round(s / 3600)}시간 전`; };

async function api(path, opts = {}) {
  const headers = { "X-Family-Token": TOKEN || "", ...(opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}) };
  const r = await fetch(path, { ...opts, headers, body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body });
  if (!r.ok) { let msg = r.statusText; try { msg = (await r.json()).detail || msg; } catch {} throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg)); }
  if (r.status === 204) return null;
  return r.json();
}
const withToken = (url) => url + (url.includes("?") ? "&" : "?") + "t=" + encodeURIComponent(TOKEN);

let toastT;
function toast(msg, ms = 2600) {
  let el = $(".toast"); if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.textContent = msg; el.classList.remove("hidden"); clearTimeout(toastT); toastT = setTimeout(() => el.classList.add("hidden"), ms);
}
function modal(html) {
  const bg = document.createElement("div"); bg.className = "modal-bg"; bg.innerHTML = `<div class="modal">${html}</div>`;
  bg.addEventListener("click", (e) => { if (e.target === bg) bg.remove(); });
  document.body.appendChild(bg); return bg;
}

const state = { me: null, tab: "visit", timers: [] };
function clearTimers() { state.timers.forEach(clearInterval); state.timers = []; }
function every(fn, ms) { const id = setInterval(fn, ms); state.timers.push(id); return id; }

// ---------------- 테마(전통·불교·천주교·기독교) ----------------
const THEMES = [
  ["classic", "전통", "먹빛과 금, 한지의 결"],
  ["buddhist", "불교", "연꽃과 등불의 붉은 빛"],
  ["catholic", "천주교", "성당 창의 푸른 빛"],
  ["christian", "기독교", "새벽 빛과 십자가"],
];
const THEME_META = { classic: "#0f1216", buddhist: "#15090d", catholic: "#0b0e1e", christian: "#0a171c" };
function applyTheme(t) {
  if (!THEME_META[t]) t = "classic";
  document.documentElement.dataset.theme = t;
  const meta = document.querySelector('meta[name="theme-color"]'); if (meta) meta.content = THEME_META[t];
  state.theme = t;
}
function currentTheme() { return localStorage.getItem("theme_local") || state.me?.deceased?.[0]?.theme || "classic"; }
function motionReduced() { return localStorage.getItem("motion") === "reduce"; }
function applyMotion() { document.documentElement.dataset.motion = motionReduced() ? "reduce" : ""; }

// ---------------- 종소리(범종 느낌, 외부 파일 없이 합성) ----------------
function chimeEnabled() { return localStorage.getItem("chime") !== "0"; }
function chime() {
  if (!chimeEnabled()) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const now = ctx.currentTime;
    const master = ctx.createGain(); master.gain.setValueAtTime(0.0001, now); master.connect(ctx.destination);
    master.gain.exponentialRampToValueAtTime(0.45, now + 0.03);
    master.gain.exponentialRampToValueAtTime(0.0001, now + 5.5);
    [[110, .8, 0], [110.6, .5, 0], [220, .45, .2], [331, .3, .4], [442, .18, .6], [660, .08, .8]].forEach(([f, g, decay]) => {
      const o = ctx.createOscillator(); const gn = ctx.createGain();
      o.type = "sine"; o.frequency.value = f; gn.gain.setValueAtTime(g, now);
      gn.gain.exponentialRampToValueAtTime(0.0001, now + 5.4 - decay * 3);
      o.connect(gn); gn.connect(master); o.start(now); o.stop(now + 5.6);
    });
    setTimeout(() => { try { ctx.close(); } catch {} }, 6000);
  } catch {}
}

// ---------------- 부팅 ----------------
async function boot() {
  applyTheme(localStorage.getItem("theme_local") || "classic"); applyMotion();
  if (!TOKEN) {
    $("#tabs").classList.add("hidden");
    if (await renderLauncher()) return;
    view.innerHTML = `<div class="card hero"><div class="orn"><i>✦ ✦ ✦</i></div><h2>초대 링크로 열어 주세요</h2><p class="muted">계약자에게 받은 카카오톡 링크를 눌러 접속합니다. 링크가 없으면 봉안당 사무실로 문의해 주세요.</p></div>`;
    return;
  }
  try { state.me = await api("/api/family/me"); }
  catch (e) { view.innerHTML = `<div class="card"><h2>접속할 수 없습니다</h2><p class="muted">${esc(e.message)}</p></div>`; $("#tabs").classList.add("hidden"); return; }
  applyTheme(currentTheme());
  $("#who").textContent = `${state.me.member.name} 님`;
  $("#tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) go(b.dataset.tab); });
  const want = location.hash.slice(1);   // /?t=…#ritual 처럼 탭을 지정해 열 수 있다
  go(["visit", "memorial", "chat", "ritual", "settings"].includes(want) ? want : "visit");
}
function go(tab) {
  clearTimers(); stopSpeech(); state.tab = tab; history.replaceState(null, "", location.pathname + (tab === "visit" ? "" : "#" + tab));
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  ({ visit: renderVisit, memorial: renderMemorial, chat: renderChat, ritual: renderRitual, settings: renderSettings })[tab]();
  window.scrollTo(0, 0);
}

// ---------------- 로컬 시작 화면 (서버를 켠 컴퓨터에서 초대 링크 없이 열었을 때) ----------------
async function renderLauncher() {
  let L;
  try { const r = await fetch("/api/launcher"); if (!r.ok) return false; L = await r.json(); } catch { return false; }
  const roleName = { view: "보기", chat: "보기·대화", manage: "계약자(관리)" };
  view.innerHTML = `<div class="launch">
    <div class="card hero"><div class="orn"><i>✦ ✦ ✦</i></div><h1>${esc(L.facility || "봉안당")} · 시연 시작</h1>
      <p class="muted">이 화면은 서버를 켠 컴퓨터에서 초대 링크 없이 열었을 때만 보입니다. 아래에서 열고 싶은 화면을 누르세요.</p></div>
    <div class="card"><h3>관리자</h3><a class="btn" href="${esc(L.admin_url)}" target="_blank">관리자 콘솔 열기 (새 창)</a>
      <p class="muted" style="font-size:14px;margin-top:10px">시연 전에 <b>현황 → AI 연결 점검</b>에서 Claude·ElevenLabs·D-ID가 모두 ✓인지 확인하세요.</p></div>
    <div class="card"><h3>유족 앱 · 시연 계정</h3>
      ${L.members.map((m) => `<div class="who-row"><div><b>${esc(m.name)}</b> <span class="muted">${esc(m.relation)} · ${roleName[m.role] || m.role}</span>
        <div class="muted" style="font-size:13px">${esc(m.deceased_names || "고인 미등록")} · 봉안함 ${esc(m.niche_code || "-")} · ${m.plan === "premium" ? "프리미엄" : "기본"}</div></div>
        <div class="row" style="gap:6px"><a class="btn" href="${esc(m.url)}">열기</a><a class="btn secondary" href="${esc(m.url)}" target="_blank">새 창</a></div></div>`).join("") || '<p class="muted">시연 계정이 없습니다. 관리자 콘솔에서 계약·가족을 만들거나 python -m server.seed 를 실행하세요.</p>'}
    </div>
    <div class="card"><h3>다음부터 여는 법</h3><p class="muted" style="font-size:14px">바탕화면의 <b>봉안당 시연 시작</b> 바로가기(또는 프로젝트 폴더의 <b>시작.bat</b>)를 두 번 누르면 서버와 웹캠 프로그램이 켜지고 이 화면이 열립니다.</p></div>
  </div>`;
  return true;
}

// ---------------- 1. 원격 참배 ----------------
async function renderVisit() {
  const me = state.me;
  if (!me.niche) { view.innerHTML = `<div class="card"><h2>연결된 봉안함이 없습니다</h2><p class="muted">봉안당 사무실에서 봉안함 번호를 연결해 드립니다.</p></div>`; return; }
  const d = me.deceased[0];
  const liveLabel = `<svg viewBox="0 0 24 24" width="22" height="22" style="stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round"><path d="M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/></svg> 실시간으로 뵙기 <small style="opacity:.7;font-weight:600;color:inherit">(${me.live_seconds}초)</small>`;
  view.innerHTML = `
    <div class="card tight">
      <div class="row between" style="margin-bottom:10px"><h2 style="margin:0">${esc(d ? d.name + " 님" : "내 가족")} <small class="muted" style="font-family:var(--font-sans)">봉안함 ${esc(me.niche.code)}</small></h2></div>
      <div class="viewer" id="viewer">
        <div class="snapshot" id="snap"><div class="placeholder">사진을 불러오는 중…</div></div>
        <div class="veil"><div class="pane l"></div><div class="pane r"></div></div>
        <div class="candle l"></div><div class="candle r"></div><div class="smoke"></div>
        <div class="title-card">${esc(d ? d.name + " 님을 뵙습니다" : "가족을 뵙습니다")}</div>
      </div>
      <div class="status-line"><span id="camStatus"><span class="dot"></span>확인 중</span><span class="row" style="gap:8px"><span id="snapAt"></span><button class="chime-toggle ${chimeEnabled() ? "on" : ""}" id="chimeBtn">🔔 종소리 ${chimeEnabled() ? "켬" : "끔"}</button></span></div>
    </div>
    <div class="stack">
      <button id="liveBtn">${liveLabel}</button>
      <button class="secondary" id="toMemorial">추모 공간 열기</button>
    </div>
    <p class="muted center" style="margin-top:12px;font-size:14px">사진은 10초마다 새로 찍힙니다. 현장에 다른 참배객이 계시면 실시간 영상은 잠시 멈추고 사진으로 보여 드립니다.</p>`;
  $("#toMemorial").onclick = () => go("memorial");
  $("#snap").onclick = () => { if (!live.on) go("memorial"); };   // 화면 속 봉안함을 누르면 추모 공간
  $("#chimeBtn").onclick = () => { localStorage.setItem("chime", chimeEnabled() ? "0" : "1"); const on = chimeEnabled(); $("#chimeBtn").classList.toggle("on", on); $("#chimeBtn").textContent = `🔔 종소리 ${on ? "켬" : "끔"}`; if (on) chime(); };
  const live = { on: false, timer: null };
  let firstShown = false;

  const snap = $("#snap"), viewer = $("#viewer");
  async function refreshStatus() {
    try {
      const s = await api("/api/family/niche/status");
      const demo = s.live_protect === false;   // 관리자 콘솔에서 참배객 보호를 끈 시연 모드
      $("#camStatus").innerHTML = (s.camera_online
        ? (s.occupied && !demo ? `<span class="dot busy"></span>현장에 참배객이 계십니다` : `<span class="dot on"></span>카메라 연결됨`)
        : `<span class="dot"></span>카메라 연결 안 됨`) + (demo ? ' <span class="pill" title="참배객 감지를 꺼 둔 상태">시연 모드</span>' : "");
      $("#snapAt").textContent = s.last_snapshot_at ? `사진 ${ago(s.last_snapshot_at)}` : "사진 없음";
      if (live.on && s.occupied && !demo) endLive("현장에 참배객이 계셔서 사진 화면으로 바꿨습니다.");
    } catch {}
  }
  function showSnapshot() {
    const img = new Image();
    img.onload = () => { snap.innerHTML = ""; snap.classList.remove("live"); snap.classList.toggle("reveal", !firstShown); firstShown = true; snap.appendChild(img); snap.insertAdjacentHTML("beforeend", `<span class="badge">방금 찍은 사진</span><span class="tap-hint">눌러서 추모 공간 열기</span>`); };
    img.onerror = () => { if (!snap.querySelector("img")) snap.innerHTML = `<div class="placeholder">아직 사진이 없습니다.<br><small>현장 카메라가 켜지면 자동으로 나타납니다.</small></div>`; };
    img.src = withToken("/api/family/niche/snapshot.jpg") + "&_=" + Date.now();
  }
  function endLive(msg) {
    if (!live.on) return; live.on = false; clearInterval(live.timer);
    viewer.classList.remove("live", "open", "curtain");
    $("#liveBtn").disabled = false; $("#liveBtn").innerHTML = liveLabel;
    showSnapshot(); if (msg) toast(msg);
  }
  $("#liveBtn").onclick = async () => {
    try {
      const r = await api("/api/family/live/start", { method: "POST" });
      live.on = true; let left = r.seconds;
      // 극적 연출: 막이 내린 상태에서 종소리와 함께 막이 열리고, 영상이 안개 속에서 또렷해지며 촛불·향이 켜진다.
      viewer.classList.remove("open", "live"); viewer.classList.add("curtain");
      const img = new Image();
      img.onerror = () => endLive("실시간 영상이 끊겼습니다. 사진으로 보여 드립니다.");
      snap.innerHTML = ""; snap.classList.remove("reveal"); snap.classList.add("live"); snap.appendChild(img); snap.insertAdjacentHTML("beforeend", `<span class="badge live">● 실시간</span>`);
      img.src = withToken(`/api/family/live/stream?sid=${r.session_id}`);
      chime();
      void viewer.offsetWidth;   // 막(display:none→block)의 초기 위치를 먼저 그리게 해서 열리는 전환이 실제로 보이게 한다
      setTimeout(() => { if (live.on) viewer.classList.add("open", "live"); }, 500);
      setTimeout(() => { if (live.on) viewer.classList.remove("curtain"); }, 4200);
      $("#liveBtn").disabled = true; $("#liveBtn").textContent = `실시간으로 뵙는 중 ${left}초`;
      live.timer = every(() => { const b = $("#liveBtn"); if (!b) { clearInterval(live.timer); return; } left--; if (left <= 0) endLive("실시간 보기가 끝났습니다."); else b.textContent = `실시간으로 뵙는 중 ${left}초`; }, 1000);
    } catch (e) { toast(e.message, 3500); }
  };
  showSnapshot(); refreshStatus();
  every(() => { if (!live.on) showSnapshot(); }, 10000);
  every(refreshStatus, 3000);
}

// ---------------- 2. 추모 공간 ----------------
async function renderMemorial() {
  let data; try { data = await api("/api/family/memorial"); } catch (e) { view.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  const cards = data.deceased.map((d) => `
    <div class="card hero">
      ${d.has_photo ? `<img class="portrait big" src="${withToken(`/api/family/deceased/${d.id}/photo.jpg`)}" alt="">` : `<div class="portrait big" style="display:inline-block"></div>`}
      <h2 style="margin-top:12px">${esc(d.name)} 님 <small class="muted" style="font-family:var(--font-sans)">${esc(d.honorific)}</small></h2>
      <div class="dates">${esc(fmtD(d.birth_date))} ~ ${esc(fmtD(d.death_date))}</div>
      <div class="orn"><i>✦</i></div>
      ${d.media.length ? `<div class="media-grid" style="margin-top:6px">${d.media.slice(0, 9).map((m) => m.kind === "video" || m.kind === "message_video"
        ? `<div><video src="${withToken(`/api/family/media/${m.id}`)}" controls playsinline></video><div class="cap">${esc(m.caption)}${m.ai_generated ? '<span class="ai-tag">AI 제작</span>' : ""}</div></div>`
        : m.kind === "voice" ? `<div><audio src="${withToken(`/api/family/media/${m.id}`)}" controls style="width:100%"></audio><div class="cap">${esc(m.caption)}</div></div>`
        : `<div><img src="${withToken(`/api/family/media/${m.id}`)}" alt=""><div class="cap">${esc(m.caption)}</div></div>`).join("")}</div>` : `<p class="muted">등록된 사진·영상이 없습니다. 봉안당 사무실에서 등록해 드립니다.</p>`}
    </div>`).join("");
  const upcoming = data.upcoming.length ? data.upcoming.map((r) => `<div class="ritual"><span class="when">${esc(fmtDT(r.scheduled_at))}</span> ${esc(r.title)}</div>`).join("") : `<p class="muted">예정된 일정이 없습니다.</p>`;
  const guest = data.guestbook.length ? data.guestbook.map((g) => `<div class="guest"><span class="who">${esc(g.author)}</span><span class="when">${esc(fmtDT(g.created_at))}</span><div>${esc(g.message)}</div></div>`).join("") : `<p class="muted">첫 글을 남겨 주세요.</p>`;
  view.innerHTML = `${cards}
    <div class="card"><h3>다가오는 기일·제사</h3>${upcoming}<button class="ghost small" style="margin-top:8px" id="toRitual">일정 전체 보기</button></div>
    <div class="card"><h3>가족 방명록</h3>
      <div class="field"><textarea id="gbMsg" placeholder="가족에게, 그리고 ${esc(data.deceased[0]?.name || "고인")} 님께 한마디"></textarea></div>
      <button id="gbSend">글 남기기</button>
      <div style="margin-top:12px">${guest}</div></div>`;
  $("#toRitual").onclick = () => go("ritual");
  $("#gbSend").onclick = async () => { const t = $("#gbMsg").value.trim(); if (!t) return; try { await api("/api/family/guestbook", { method: "POST", body: { message: t } }); toast("남겼습니다."); renderMemorial(); } catch (e) { toast(e.message); } };
}

// ---------------- 3. 기념일 대화 ----------------
let speech = { rec: null, listening: false, audio: null };
function stopSpeech() {
  try { window.speechSynthesis?.cancel(); speech.rec?.stop(); if (speech.audio) { speech.audio.pause(); speech.audio.src = ""; speech.audio = null; } } catch {}
  try { window.__avatarStop?.(); window.__avatarStop = null; } catch {}
  speech.listening = false;
}
// 브라우저 내장 한국어 음성 고르기. 엣지는 'Natural' 신경망 음성(SunHi·InJoon 등)이 있어 품질이 가장 좋다.
function pickVoice(hint) {
  const ko = (window.speechSynthesis?.getVoices() || []).filter((v) => /^ko/i.test(v.lang));
  if (!ko.length) return null;
  const female = /SunHi|Heami|Yuna|JiMin|SeoHyeon|Female|여성/i, male = /InJoon|Hyunsu|BongJin|GookMin|Male|남성/i;
  const score = (v) => (/Natural|Online|Neural/i.test(v.name) ? 10 : 0) + (/Google/i.test(v.name) ? 3 : 0)
    + (hint === "female" && female.test(v.name) ? 5 : 0) + (hint === "male" && male.test(v.name) ? 5 : 0);
  return ko.sort((a, b) => score(b) - score(a))[0];
}
function speak(text, onend, hint = "any") {
  if (!("speechSynthesis" in window)) { onend?.(); return; }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text); u.lang = "ko-KR"; u.rate = 0.92; u.pitch = hint === "male" ? 0.85 : 0.95;
  const v = pickVoice(hint); if (v) u.voice = v;
  u.onend = () => onend?.(); u.onerror = () => onend?.();
  window.speechSynthesis.speak(u);
}
// ---------------- 실시간 립싱크 아바타 (Simli WebRTC, SDK 없이) ----------------
// 서버가 세션 토큰을 주면 브라우저가 WebRTC로 연결하고, 우리가 만든 음성(PCM16 16kHz)을 웹소켓으로 보내면 입을 맞춘 영상이 돌아온다.
class LiveAvatar {
  constructor(videoEl) { this.video = videoEl; this.pc = null; this.ws = null; this.ready = false; this.onstate = () => {}; }
  async connect(sess) {
    const cfg = await api("/api/family/chat/avatar-session", { method: "POST", body: { session_id: sess.session_id } });
    this.pc = new RTCPeerConnection({ iceServers: cfg.ice_servers || [{ urls: ["stun:stun.l.google.com:19302"] }] });
    this.pc.addTransceiver("audio", { direction: "recvonly" }); this.pc.addTransceiver("video", { direction: "recvonly" });
    this.pc.ontrack = (e) => { if (e.streams[0] && this.video.srcObject !== e.streams[0]) { this.video.srcObject = e.streams[0]; this.video.play().catch(() => {}); } };
    this.pc.onconnectionstatechange = () => { if (["failed", "disconnected", "closed"].includes(this.pc.connectionState)) this.stop("연결 끊김"); };
    const offer = await this.pc.createOffer(); await this.pc.setLocalDescription(offer);
    await new Promise((res) => { if (this.pc.iceGatheringState === "complete") return res(); const t = setTimeout(res, 1500); this.pc.onicegatheringstatechange = () => { if (this.pc.iceGatheringState === "complete") { clearTimeout(t); res(); } }; });
    await new Promise((resolve, reject) => {
      const ws = new WebSocket(`${cfg.ws_url}?session_token=${encodeURIComponent(cfg.session_token)}&enableSFU=false`);
      ws.binaryType = "arraybuffer"; this.ws = ws;
      const timeout = setTimeout(() => reject(new Error("아바타 연결 시간 초과")), 12000);
      ws.onopen = () => ws.send(JSON.stringify({ sdp: this.pc.localDescription.sdp, type: "offer" }));
      ws.onmessage = async (ev) => {
        if (typeof ev.data !== "string") return;
        if (ev.data.startsWith("{")) { try { const m = JSON.parse(ev.data); if (m.type === "answer") await this.pc.setRemoteDescription(m); } catch (e) { clearTimeout(timeout); reject(e); } return; }
        if (ev.data === "START") { this.ready = true; ws.send(new Uint8Array(64000)); clearTimeout(timeout); this.onstate("live"); resolve(); }
        else if (ev.data === "STOP") this.stop("세션 종료");
      };
      ws.onerror = () => { clearTimeout(timeout); reject(new Error("아바타 웹소켓 오류")); };
      ws.onclose = () => { if (this.ready) this.stop("연결 종료"); };
    });
  }
  // mp3 → PCM16 16kHz 모노 → 6000바이트씩 전송. 반환값은 재생 길이(초).
  async speak(mp3Blob) {
    if (!this.ready || !this.ws || this.ws.readyState !== 1) throw new Error("아바타 미연결");
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const decoded = await ctx.decodeAudioData(await mp3Blob.arrayBuffer());
    const off = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
    const src = off.createBufferSource(); src.buffer = decoded; src.connect(off.destination); src.start();
    const rendered = await off.startRendering(); ctx.close();
    const f32 = rendered.getChannelData(0); const pcm = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) { const v = Math.max(-1, Math.min(1, f32[i])); pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff; }
    const bytes = new Uint8Array(pcm.buffer);
    for (let i = 0; i < bytes.length; i += 6000) this.ws.send(bytes.subarray(i, i + 6000));
    return decoded.duration;
  }
  interrupt() { try { this.ws?.send(new TextEncoder().encode("SKIP")); } catch {} }
  stop(reason) {
    if (!this.pc && !this.ws) return;
    try { this.ws?.send(new TextEncoder().encode("DONE")); } catch {}
    try { this.ws?.close(); } catch {} try { this.pc?.close(); } catch {}
    this.ws = null; this.pc = null; this.ready = false; this.video.srcObject = null; this.onstate("off", reason);
  }
}

// ---------------- D-ID 사진 아바타 (공식 Agents SDK, CDN ESM) ----------------
// 실제 사진 그대로를 움직인다. 서버가 세션마다 짧은 클라이언트 키를 발급하고, 음성은 서버가 합성해 D-ID에 올린 URL로 말하게 한다.
class DIDAvatar {
  constructor(videoEl) { this.video = videoEl; this.mgr = null; this.ready = false; this.onstate = () => {}; this._resolveStop = null; this.sess = null; }
  async connect(sess) {
    this.sess = sess;
    const cfg = await api("/api/family/chat/avatar-session", { method: "POST", body: { session_id: sess.session_id } });
    const sdk = await import(cfg.sdk_url);
    await new Promise(async (resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("아바타 연결 시간 초과")), 20000);
      try {
        this.mgr = await sdk.createAgentManager(cfg.agent_id, {
          auth: { type: "key", clientKey: cfg.client_key },
          streamOptions: { compatibilityMode: "auto", streamWarmup: true },
          callbacks: {
            onSrcObjectReady: (stream) => { this.video.srcObject = stream; this.video.muted = false; this.video.play().catch(() => {}); return stream; },
            onConnectionStateChange: (st) => { if (st === "connected") { this.ready = true; clearTimeout(timeout); this.onstate("live"); resolve(); } else if (["disconnected", "closed", "fail", "failed"].includes(String(st).toLowerCase()) && this.ready) { this.stop("연결 끊김"); } },
            onVideoStateChange: (st) => { if (st === "START") this.onstate("speaking"); else if (st === "STOP") { this.onstate("silent"); if (this._resolveStop) { const r = this._resolveStop; this._resolveStop = null; r(); } } },
            onError: (err, data) => { console.warn("D-ID error", err, data); if (!this.ready) { clearTimeout(timeout); reject(new Error(String(err?.message || err || "아바타 오류"))); } },
          },
        });
        await this.mgr.connect();
      } catch (e) { clearTimeout(timeout); reject(e); }
    });
  }
  // 서버가 복제 음성으로 합성해 D-ID에 올린 URL로 말하게 하고, 말이 끝나면(STOP) 돌아온다.
  async speak(text) {
    if (!this.ready || !this.mgr) throw new Error("아바타 미연결");
    const r = await api("/api/family/chat/avatar-speak", { method: "POST", body: { session_id: this.sess.session_id, text } });
    const done = new Promise((res) => { this._resolveStop = res; setTimeout(res, 45000); });
    await this.mgr.speak({ type: "audio", audio_url: r.audio_url });
    await done;
  }
  interrupt() { try { this.mgr?.interrupt?.({ type: "click" }); } catch {} }
  stop(reason) {
    if (!this.mgr) return;
    try { this.mgr.disconnect(); } catch {}
    this.mgr = null; this.ready = false; this.video.srcObject = null; this.onstate("off", reason);
  }
}

// 복제 음성이 등록된 고인이면 서버(ElevenLabs 등)에서 오디오를 받아 재생하고, 실패하면 브라우저 음성으로 내려간다.
// 실시간 아바타가 연결돼 있으면 오디오를 아바타로 보내고(아바타 영상에 소리가 실려 옴) 로컬에서는 재생하지 않는다.
async function speakAs(sess, text, onend, onstart) {
  if (sess._avatar?.ready && sess._avatar instanceof DIDAvatar) {
    try { onstart?.(); await sess._avatar.speak(text); onend?.(); return; }
    catch (e) { console.warn("D-ID speak failed → local audio", e); }
  }
  if (sess.voice_available) {
    try {
      const r = await fetch(withToken(`/api/family/chat/tts?session_id=${encodeURIComponent(sess.session_id)}&text=${encodeURIComponent(text)}`));
      if (r.status === 200) {
        const blob = await r.blob();
        if (sess._avatar?.ready) {
          try { const secs = await sess._avatar.speak(blob); onstart?.(); setTimeout(() => onend?.(), secs * 1000 + 600); return; }
          catch (e) { console.warn("avatar speak failed → local audio", e); }
        }
        const url = URL.createObjectURL(blob);
        const a = new Audio(url); speech.audio = a;
        a.onplay = () => onstart?.();
        a.onended = () => { URL.revokeObjectURL(url); speech.audio = null; onend?.(); };
        a.onerror = () => { URL.revokeObjectURL(url); speech.audio = null; onend?.(); };
        await a.play(); return;
      }
    } catch {}
  }
  onstart?.(); speak(text, onend, sess.voice_hint);
}

async function renderChat() {
  const me = state.me; const list = me.deceased;
  const eligible = list.filter((d) => d.chat_available);
  if (me.member.role === "view") { view.innerHTML = `<div class="card"><h2>기념일 대화</h2><p class="muted">대화 기능은 계약자가 권한을 준 가족만 이용할 수 있습니다. 설정 화면에서 계약자에게 요청해 주세요.</p></div>`; return; }
  if (!eligible.length) { view.innerHTML = `<div class="card"><h2>기념일 대화</h2><p class="muted">아직 대화 기능이 열려 있지 않습니다.</p><p class="muted">봉안당 상담 직원과 30분가량 인터뷰로 <b>기억 카드</b>를 만들고 직계가족 동의서를 등록하면 열립니다. 대화 기능은 선택 사항이며, 언제든 닫을 수 있습니다.</p></div>`; return; }
  const options = eligible.map((d) => `<option value="${d.id}">${esc(d.name)} 님${d.honorific ? ` (${esc(d.honorific)})` : ""}</option>`).join("");
  const first = eligible[0];
  view.innerHTML = `
    <div class="notice ai" style="font-size:14px;padding:8px 12px">🔈 이 화면의 목소리와 답변은 AI가 만든 것입니다. 실제 고인이 아닙니다.</div>
    <div class="card hero" style="margin-top:12px;text-align:left">
      <div class="orn"><i>✦ ✦ ✦</i></div>
      <h2>기념일 대화</h2>
      <p class="muted">기일·명절·생신처럼 특별한 날에, 가족이 남긴 기억과 말투로 만든 AI와 짧게 이야기합니다. 1회 ${me.chat_max_minutes}분.</p>
      <p class="muted" style="font-size:14px">${first.has_voice ? "🎙️ 가족이 등록한 목소리로 만든 AI 음성으로 답합니다." : `🔈 기본 AI 음성으로 답합니다. ${me.member.role === "manage" ? '<a href="#" id="toVoice">목소리 등록하기 →</a>' : "계약자가 목소리를 등록하면 그 음성으로 바뀝니다."}`}
      ${first.has_face && first.has_voice ? " · 🎬 등록한 얼굴로 실시간 아바타가 나옵니다." : first.has_face ? " · 실시간 아바타는 목소리 등록 뒤에 켜집니다." : ""}</p>
      <div class="field"><label>누구와 이야기할까요</label><select id="chatWho">${options}</select></div>
      <div class="field"><label>오늘의 자리</label><select id="occ"><option value="">평소</option><option>기일</option><option>명절</option><option>생신</option><option>49재</option></select></div>
      ${first.days_since_death !== null && first.days_since_death < 49 ? `<div class="notice">첫 대화는 49재 이후를 권장합니다. (별세 후 ${first.days_since_death}일)</div>` : ""}
      <div class="check"><input type="checkbox" id="ack"><label for="ack" style="margin:0;color:var(--ink)">이 대화가 AI가 만든 음성·답변이며, 실제 고인이 아님을 이해했습니다.</label></div>
      ${me.member.is_minor ? `<div class="check"><input type="checkbox" id="guardian"><label for="guardian" style="margin:0;color:var(--ink)">보호자가 함께 있습니다.</label></div>` : ""}
      <button id="startChat" style="margin-top:8px">대화 시작하기</button>
      <p class="muted center" style="margin-top:10px;font-size:14px">마음이 많이 힘드시면 자살예방 상담전화 <b>109</b>로 먼저 연락해 주세요.</p>
    </div>`;
  if ($("#toVoice")) $("#toVoice").onclick = (e) => { e.preventDefault(); go("settings"); setTimeout(() => $("#voiceCard")?.scrollIntoView({ behavior: "smooth" }), 300); };
  $("#startChat").onclick = async () => {
    if (!$("#ack").checked) return toast("AI 고지를 확인해 주세요.");
    try {
      const r = await api("/api/family/chat/start", { method: "POST", body: { deceased_id: +$("#chatWho").value, occasion: $("#occ").value, acknowledged_ai: true, guardian_present: !!$("#guardian")?.checked } });
      runChat(r, eligible.find((d) => d.id === +$("#chatWho").value));
    } catch (e) { toast(e.message, 4000); }
  };
}

function runChat(sess, d) {
  clearTimers();
  let left = sess.max_seconds, ended = false, busy = false;
  view.innerHTML = `
    <div class="notice ai" style="font-size:13px;padding:6px 12px;text-align:center">🔈 AI가 만든 음성·영상입니다 · 실제 고인이 아닙니다</div>
    <div class="chat-wrap">
      <div class="shrine" id="stage">
        <div class="shrine-halo"></div>
        <div class="shrine-frame"><div class="shrine-inner">
          <div class="backdrop"></div>
          ${sess.photo_url ? `<img src="${withToken(sess.photo_url)}" alt="">` : `<div class="no-photo">🕊️</div>`}
          <video id="avatarVideo" autoplay playsinline></video>
          <div class="rays"></div><div class="mist"></div>
        </div></div>
        <div class="shrine-particles"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
        <div class="shrine-caption"><span class="live-badge" id="liveBadge">AI 사진 아바타</span>
          <div class="voice-bars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
          <div class="voice-tag" id="voiceTag">${sess.voice_available ? "가족이 등록한 목소리로 만든 AI 음성" : "기본 AI 음성"}${sess.avatar_available ? " · 실시간 아바타 연결 중…" : ""}</div></div>
      </div>
      <div class="chat-head" style="margin:6px 0 4px">
        <div><h2 style="margin:0">${esc(d.name)} 님</h2><div class="timer" id="timer"></div></div>
        <button class="ghost small" id="endBtn" style="margin-left:auto">마치기</button>
      </div>
      ${sess.notices.map((n) => `<div class="notice" style="margin-bottom:6px">${esc(n)}</div>`).join("")}
      <div class="chat-log" id="log"></div>
      <div class="chat-input">
        <button class="mic" id="mic" title="말하기">🎤</button>
        <input id="txt" placeholder="말하거나 글로 적어 주세요" autocomplete="off">
        <button class="small" id="send" style="min-height:48px">보내기</button>
      </div>
      <p class="muted center" style="margin:6px 0 0;font-size:12px">대화: ${esc(sess.provider)} · 음성: ${esc(sess.voice_provider || "browser")} · 내 목소리 원본은 저장하지 않습니다</p>
    </div>`;
  const log = $("#log");
  const add = (cls, text) => { const b = document.createElement("div"); b.className = `bubble ${cls}`; b.textContent = text; log.appendChild(b); log.scrollTop = log.scrollHeight; return b; };
  const tick = () => { $("#timer").textContent = `남은 시간 ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`; };
  tick(); every(() => { if (!ended && left > 0) { left--; tick(); if (left === 60) add("sys", "1분 뒤에 인사하고 마칩니다."); } }, 1000);

  const stage = $("#stage");
  const say = (text, onend) => speakAs(sess, text, () => { stage.classList.remove("speaking"); onend?.(); }, () => stage.classList.add("speaking"));
  // 첫 인사는 초상이 안개 속에서 나타난 뒤에 시작한다(등장 연출과 겹치지 않게).
  const greet = () => setTimeout(() => { add("them", sess.greeting); say(sess.greeting); }, 2600);
  // 실시간 아바타(A등급): 연결되면 사진 대신 영상. 실패하면 조용히 사진 아바타로.
  if (sess.avatar_available) {
    const av = sess.avatar_provider === "did" ? new DIDAvatar($("#avatarVideo")) : new LiveAvatar($("#avatarVideo")); sess._avatar = av;
    av.onstate = (st, reason) => {
      if (st === "speaking") { stage.classList.add("speaking"); return; }
      if (st === "silent") { stage.classList.remove("speaking"); return; }
      stage.classList.toggle("live", st === "live");
      $("#liveBadge").textContent = st === "live" ? "AI 실시간 영상" : "AI 사진 아바타";
      $("#voiceTag").textContent = st === "live" ? `가족이 등록한 목소리와 사진으로 만든 AI · 실시간 아바타(${sess.avatar_provider === "did" ? "D-ID" : "Simli"})` : `가족이 등록한 목소리로 만든 AI 음성 · 사진 아바타${reason ? ` (${reason})` : ""}`;
    };
    av.connect(sess).then(greet).catch((e) => { console.warn("avatar connect failed", e); av.stop(e.message); greet(); });
    window.__avatarStop = () => av.stop();   // 화면을 떠날 때 아바타도 끊는다
  } else {
    greet();
  }

  async function sendText(text) {
    text = text.trim(); if (!text || busy || ended) return;
    busy = true; add("me", text); $("#txt").value = "";
    const thinking = add("them", "…");
    try {
      const r = await api("/api/family/chat/turn", { method: "POST", body: { session_id: sess.session_id, text } });
      thinking.remove();
      if (r.safety?.kind === "crisis") { add("danger", r.reply); speak(r.reply, null, "any"); finish(true); return; }   // 위기 안내는 고인 목소리가 아닌 기본 음성으로
      add("them", r.reply); left = Math.min(left, r.remaining_seconds); say(r.reply, () => { if (!ended && speech.autoListen) listen(); });
      if (r.ended) finish(true);
    } catch (e) { thinking.textContent = e.message; thinking.classList.add("sys"); }
    busy = false;
  }
  async function finish(silent) {
    if (ended) return; ended = true; clearTimers();
    try {
      const r = await api("/api/family/chat/end", { method: "POST", body: { session_id: sess.session_id } });
      if (!silent && r.closing) { add("them", r.closing); say(r.closing); }
      add("sys", `오늘의 대화 요약: ${r.summary || "(요약 없음)"}`);
    } catch {}
    $("#mic").disabled = $("#send").disabled = $("#txt").disabled = true;
    setTimeout(() => { try { sess._avatar?.stop("대화 종료"); } catch {} }, 8000);   // 마지막 인사가 끝난 뒤 아바타 종료
    $("#endBtn").textContent = "처음으로"; $("#endBtn").onclick = () => go("chat");
  }
  $("#send").onclick = () => sendText($("#txt").value);
  $("#txt").addEventListener("keydown", (e) => { if (e.key === "Enter") sendText($("#txt").value); });
  $("#endBtn").onclick = () => finish(false);

  // 브라우저 음성 인식(Web Speech API). 크롬·삼성 인터넷·엣지에서 동작.
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  function listen() {
    if (!SR) return toast("이 브라우저는 음성 인식을 지원하지 않습니다. 글로 적어 주세요.");
    if (speech.listening) { speech.rec?.stop(); return; }
    window.speechSynthesis?.cancel(); if (speech.audio) { speech.audio.pause(); speech.audio = null; } sess._avatar?.interrupt(); stage.classList.remove("speaking");
    const rec = new SR(); rec.lang = "ko-KR"; rec.interimResults = true; rec.maxAlternatives = 1;
    speech.rec = rec; speech.listening = true; $("#mic").classList.add("listening"); stage.classList.add("listening");
    let final = "";
    rec.onresult = (e) => { let interim = ""; for (const res of e.results) { if (res.isFinal) final += res[0].transcript; else interim += res[0].transcript; } $("#txt").value = final || interim; };
    rec.onend = () => { speech.listening = false; $("#mic").classList.remove("listening"); stage.classList.remove("listening"); if (final.trim()) sendText(final); };
    rec.onerror = (e) => { speech.listening = false; $("#mic").classList.remove("listening"); stage.classList.remove("listening"); if (e.error !== "no-speech" && e.error !== "aborted") toast("음성 인식 오류: " + e.error); };
    rec.start();
  }
  speech.autoListen = false;
  $("#mic").onclick = () => { speech.autoListen = true; listen(); };
}

// ---------------- 4. 제사 일정·중계·공양 ----------------
async function renderRitual() {
  let rituals, offerings;
  try { [rituals, offerings] = await Promise.all([api("/api/family/rituals"), api("/api/family/offerings")]); } catch (e) { view.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  const me = state.me;
  const kindName = { memorial: "기일", holiday: "명절", event: "행사" };
  const pStatus = { requested: "신청됨", accepted: "확정", rejected: "반려" };
  const items = rituals.filter((r) => !r.is_past).map((r) => `
    <div class="ritual">
      <div><span class="when">${esc(fmtDT(r.scheduled_at))}</span><span class="pill">${kindName[r.kind] || r.kind}</span><span class="pill">${r.access === "applied" ? "신청 가족만" : "누구나"}</span>${r.is_live_window && (r.has_camera || r.stream_url) ? '<span class="pill live">● 중계 중</span>' : ""}${r.viewer_count ? `<span class="pill">👁 ${r.viewer_count}</span>` : ""}</div>
      <div style="font-weight:700">${esc(r.title)}</div>
      ${r.note ? `<div class="muted">${esc(r.note)}</div>` : ""}
      ${r.my_participation ? `<div class="muted" style="font-size:14px">우리 가족: ${esc(r.my_participation.deceased_name)} 님 · 상주 ${esc(r.my_participation.mourner_name || "-")} · ${pStatus[r.my_participation.status] || r.my_participation.status}${r.my_participation.order_no ? ` · 순서 ${r.my_participation.order_no}번` : ""}</div>` : ""}
      ${r.participants.length ? `<div class="muted" style="font-size:13px">봉행 순서: ${r.participants.map((x) => `${x.order_no || "-"}. ${esc(x.deceased_name)}${x.is_mine ? " (우리)" : ""}`).join(" · ")}</div>` : ""}
      <div class="row" style="margin-top:8px;flex-wrap:wrap">
        ${r.is_live_window && r.has_camera && r.can_watch ? `<button class="small" data-live="${r.id}">▶ 라이브 보기</button>` : ""}
        ${r.is_live_window && r.has_camera && !r.can_watch ? `<span class="muted" style="font-size:14px">신청한 가족만 볼 수 있습니다</span>` : ""}
        ${r.access === "applied" && !r.my_participation && me.member.role !== "view" ? `<button class="small secondary" data-join="${r.id}">제사 참여 신청</button>` : ""}
        ${r.is_live_window && r.stream_url ? `<a class="btn small" style="width:auto;min-height:40px;font-size:15px;text-decoration:none" href="${esc(r.stream_url)}" target="_blank">중계 링크</a>` : ""}
        ${r.replay_url ? `<a class="btn small secondary" style="width:auto;min-height:40px;font-size:15px;text-decoration:none" href="${esc(r.replay_url)}" target="_blank">다시 보기</a>` : ""}
        <button class="small ghost" data-offer="${r.id}">공양·헌화 신청</button>
      </div>
    </div>`).join("") || `<p class="muted">예정된 일정이 없습니다.</p>`;
  const past = rituals.filter((r) => r.is_past).slice(-5).reverse().map((r) => `<div class="ritual"><span class="muted">${esc(fmtDT(r.scheduled_at))}</span> ${esc(r.title)} ${r.replay_url ? `<a href="${esc(r.replay_url)}" target="_blank">다시 보기</a>` : ""}</div>`).join("");
  const kindLabel = { offering: "공양", flower: "헌화", prayer: "기도" };
  const statusLabel = { requested: "접수 대기", accepted: "접수됨", done: "봉행 완료", cancelled: "취소" };
  const myOff = offerings.length ? offerings.map((o) => `<div class="list-item"><div><b>${kindLabel[o.kind]}</b> ${o.ritual_title ? `· ${esc(o.ritual_title)}` : ""}<div class="muted" style="font-size:13px">${esc(fmtDT(o.created_at))}${o.amount ? ` · ${o.amount.toLocaleString()}원` : ""}</div></div><span class="pill">${statusLabel[o.status] || o.status}</span></div>`).join("") : `<p class="muted">신청 내역이 없습니다.</p>`;
  view.innerHTML = `
    <div class="card"><h2>제사 일정과 생중계</h2><p class="muted">법회·행사는 누구나, 제사는 참여를 신청한 가족만 생중계를 봅니다. 중계는 봉행 30분 전부터 열리고, 화면에서 현장에 한마디를 남기거나 합장·헌화 반응을 보낼 수 있습니다.</p>${items}</div>
    ${past ? `<div class="card"><h3>지난 일정</h3>${past}</div>` : ""}
    <div class="card"><h3>내 공양·헌화 신청</h3>${myOff}<button class="secondary" style="margin-top:10px" id="offerAny">공양·헌화·기도 신청</button></div>`;
  view.querySelectorAll("[data-live]").forEach((b) => b.onclick = () => openRitualLive(rituals.find((r) => r.id === +b.dataset.live)));
  view.querySelectorAll("[data-join]").forEach((b) => b.onclick = () => {
    const r = rituals.find((x) => x.id === +b.dataset.join);
    const m = modal(`<h2>${esc(r.title)} 참여 신청</h2><p class="muted">신청한 가족만 생중계를 볼 수 있고, 봉행 순서에 우리 가족 고인이 올라갑니다. 순서는 사찰에서 정해 알려 드립니다.</p>
      <div class="field"><label>고인</label><select id="jDec">${me.deceased.map((d) => `<option value="${d.id}">${esc(d.name)} 님${d.honorific ? ` (${esc(d.honorific)})` : ""}</option>`).join("")}</select></div>
      <div class="field"><label>상주(대표 가족) 이름</label><input id="jMourner" value="${esc(me.contract.holder_name)}"></div>
      <div class="field"><label>전할 말(선택)</label><input id="jNote" placeholder="예: 가족 6명이 함께 봅니다"></div>
      <button id="jGo">참여 신청</button>`);
    $("#jGo", m).onclick = async () => {
      try { await api(`/api/family/rituals/${r.id}/join`, { method: "POST", body: { deceased_id: +$("#jDec", m).value, mourner_name: $("#jMourner", m).value, note: $("#jNote", m).value } }); m.remove(); toast("참여를 신청했습니다. 사찰에서 순서를 정해 알려 드립니다.", 4000); renderRitual(); }
      catch (e) { toast(e.message, 4000); }
    };
  });
  const openOffer = (ritualId) => {
    const m = modal(`<h2>공양·헌화·기도 신청</h2><p class="muted">사찰에서 접수 후 봉행합니다. 결제는 파일럿에서 연결됩니다(현재는 신청만).</p>
      <div class="field"><label>종류</label><select id="ofKind"><option value="offering">공양</option><option value="flower">헌화</option><option value="prayer">기도</option></select></div>
      <div class="field"><label>일정</label><select id="ofRitual"><option value="">특정 일정 없음</option>${rituals.filter((r) => !r.is_past).map((r) => `<option value="${r.id}" ${r.id == ritualId ? "selected" : ""}>${esc(fmtDT(r.scheduled_at))} ${esc(r.title)}</option>`).join("")}</select></div>
      <div class="field"><label>금액(원)</label><input id="ofAmount" type="number" inputmode="numeric" value="30000" min="0" step="1000"></div>
      <div class="field"><label>전할 말(선택)</label><input id="ofNote" placeholder="예: 어머니 기일에 흰 국화로 부탁드립니다"></div>
      <button id="ofSend">신청하기</button>`);
    $("#ofSend", m).onclick = async () => {
      try { await api("/api/family/offerings", { method: "POST", body: { kind: $("#ofKind", m).value, ritual_id: $("#ofRitual", m).value ? +$("#ofRitual", m).value : null, amount: +$("#ofAmount", m).value || 0, note: $("#ofNote", m).value } }); m.remove(); toast("신청했습니다. 사찰에서 확인 후 연락드립니다."); renderRitual(); }
      catch (e) { toast(e.message); }
    };
  };
  view.querySelectorAll("[data-offer]").forEach((b) => b.onclick = () => openOffer(+b.dataset.offer));
  $("#offerAny").onclick = () => openOffer(null);
}

// 틱톡 라이브처럼: 전체 화면 영상 + 지금 봉행 중인 고인 정보 + 가족 메시지가 아래에서 올라오고 + 합장·촛불·헌화 반응이 떠오른다.
function openRitualLive(r) {
  clearTimers(); stopSpeech();
  const el = document.createElement("div"); el.className = "live-view";
  const src = () => withToken(`/api/family/rituals/${r.id}/stream`) + "&_=" + Date.now();
  el.innerHTML = `
    <canvas class="live-bg" id="lvBg"></canvas>
    <img class="live-video" id="lvVideo" alt="">
    <div class="live-shade"></div>
    <div class="live-top"><span class="live-badge-red">● LIVE</span><span class="live-title">${esc(r.title)}</span><span class="live-viewers" id="lvViewers">👁 1</span><button class="live-close" id="lvClose" title="닫기">✕</button></div>
    <div class="live-now" id="lvNow"></div>
    <div class="live-fx" id="lvFx"></div>
    <div class="live-msgs" id="lvMsgs"></div>
    <div class="live-bar"><input id="lvInput" placeholder="현장에 한마디…" maxlength="200" autocomplete="off"><button class="live-send" id="lvSend">보내기</button></div>
    <div class="live-react"><button class="live-orderbtn" id="lvOrder">봉행 순서</button>${["🙏", "🕯️", "🌸", "💛"].map((e) => `<button data-react="${e}" title="반응 보내기">${e}</button>`).join("")}</div>
    <div class="live-drawer hidden" id="lvDrawer"><div class="live-drawer-in"><h3>봉행 순서</h3><div id="lvOrderList"></div><button class="small ghost" id="lvDrawerClose" style="margin-top:10px">닫기</button></div></div>`;
  document.body.appendChild(el); document.body.classList.add("noscroll");
  const video = $("#lvVideo", el), bg = $("#lvBg", el), msgs = $("#lvMsgs", el), fx = $("#lvFx", el);
  video.src = src();
  video.onerror = () => setTimeout(() => { if (el.isConnected) video.src = src(); }, 3000);
  // 가로 영상 뒤에 같은 영상을 흐리게 깔아 세로 화면을 채운다(틱톡의 가로 영상 처리와 같음). 별도 연결 없이 캔버스로 복사.
  const paintBg = () => { try { if (video.naturalWidth) { bg.width = 64; bg.height = Math.max(1, Math.round(64 * video.naturalHeight / video.naturalWidth)); bg.getContext("2d").drawImage(video, 0, 0, bg.width, bg.height); } } catch {} };
  let since = 0, rseq = -1, ended = false;
  const addMsg = (m) => { const d = document.createElement("div"); d.className = `live-msg ${m.sender === "site" ? "site" : ""} ${m.kind === "notice" ? "notice" : ""}`; d.innerHTML = `<b>${esc(m.author)}</b>${esc(m.message)}`; msgs.appendChild(d); while (msgs.children.length > 8) msgs.firstChild.remove(); };
  const float = (emoji) => { const i = document.createElement("i"); i.textContent = emoji; i.style.left = (10 + Math.random() * 70) + "%"; i.style.setProperty("--dx", (Math.random() * 60 - 30) + "px"); fx.appendChild(i); setTimeout(() => i.remove(), 2600); };
  async function poll() {
    if (!el.isConnected) return;
    let d; try { d = await api(`/api/family/rituals/${r.id}/live?since=${since}&rseq=${rseq}`); } catch (e) { return; }
    $("#lvViewers", el).textContent = `👁 ${d.viewer_count}`;
    d.messages.forEach((m) => { since = Math.max(since, m.id); addMsg(m); });
    d.reactions.forEach((x) => { if (x.seq > rseq) { rseq = x.seq; float(x.emoji); } });
    if (d.rseq > rseq) rseq = d.rseq;
    const now = d.current;
    $("#lvNow", el).innerHTML = now
      ? `<div class="live-now-in"><span class="live-now-k">지금 ${d.current_order}/${d.order.length}</span><b>${esc(now.deceased_name)} 님</b><span>${esc(fmtD(now.birth_date))} ~ ${esc(fmtD(now.death_date))}</span><span>상주 ${esc(now.mourner_name || "-")}</span>${now.is_mine ? '<span class="live-mine">우리 가족 차례</span>' : ""}</div>`
      : (d.order.length ? `<div class="live-now-in"><span class="live-now-k">봉행 순서 ${d.order.length}가족</span><span>${d.current_order === 0 ? "곧 시작합니다" : "봉행을 마쳤습니다"}</span></div>` : "");
    $("#lvOrderList", el).innerHTML = d.order.map((x) => `<div class="live-order-row ${x.order_no === d.current_order ? "now" : ""} ${x.is_mine ? "mine" : ""}"><span class="no">${x.order_no || "-"}</span><div><b>${esc(x.deceased_name)} 님</b> <span class="muted">${esc(fmtD(x.birth_date))} ~ ${esc(fmtD(x.death_date))}</span><div class="muted" style="font-size:13px">상주 ${esc(x.mourner_name || "-")}${x.is_mine ? " · 우리 가족" : ""}</div></div></div>`).join("") || '<p class="muted">순서가 아직 정해지지 않았습니다.</p>';
    if (!d.live && !ended) { ended = true; el.insertAdjacentHTML("beforeend", `<div class="live-ended">중계가 끝났습니다</div>`); }
    paintBg();
  }
  poll(); const t = setInterval(poll, 2000); const tb = setInterval(paintBg, 700);
  const close = () => { clearInterval(t); clearInterval(tb); video.src = ""; el.remove(); document.body.classList.remove("noscroll"); renderRitual(); };
  $("#lvClose", el).onclick = close;
  $("#lvOrder", el).onclick = () => $("#lvDrawer", el).classList.remove("hidden");
  $("#lvDrawerClose", el).onclick = () => $("#lvDrawer", el).classList.add("hidden");
  $("#lvDrawer", el).onclick = (e) => { if (e.target === $("#lvDrawer", el)) $("#lvDrawer", el).classList.add("hidden"); };
  const send = async () => { const txt = $("#lvInput", el).value.trim(); if (!txt) return; $("#lvSend", el).disabled = true; try { await api(`/api/family/rituals/${r.id}/messages`, { method: "POST", body: { message: txt } }); $("#lvInput", el).value = ""; poll(); } catch (e) { toast(e.message, 3000); } $("#lvSend", el).disabled = false; };
  $("#lvSend", el).onclick = send;
  $("#lvInput", el).addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
  el.querySelectorAll("[data-react]").forEach((b) => b.onclick = () => { float(b.dataset.react); api(`/api/family/rituals/${r.id}/reactions`, { method: "POST", body: { emoji: b.dataset.react } }).then((x) => { if (x?.seq) rseq = Math.max(rseq, x.seq); }).catch(() => {}); });
}

// ---------------- 5. 가족 초대·설정(작별 포함) ----------------
async function renderSettings() {
  const me = state.me; let members, history;
  try { [members, history] = await Promise.all([api("/api/family/members"), api("/api/family/chat/history")]); } catch (e) { view.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  const roleName = { view: "보기", chat: "보기·대화", manage: "관리" };
  const canManage = me.member.role === "manage";
  const cur = currentTheme();
  view.innerHTML = `
    <div class="card"><h3>추모 공간 분위기</h3><p class="muted" style="font-size:14px;margin-top:0">${canManage ? "가족 모두의 화면에 함께 적용됩니다." : "이 기기에서만 바뀝니다. 가족 전체는 계약자가 정합니다."}</p>
      <div class="theme-grid">${THEMES.map(([id, name, desc]) => `<button class="tile ${cur === id ? "active" : ""}" data-theme="${id}"><span class="sw">${id === "buddhist" ? "❁" : id === "classic" ? "✦" : "✝"}</span><span>${name}<small>${desc}</small></span></button>`).join("")}</div>
      <div class="row between" style="margin-top:12px"><span class="muted" style="font-size:14px">등장·막·촛불 같은 움직이는 연출</span><button class="small ${motionReduced() ? "ghost" : "secondary"}" id="motionBtn">${motionReduced() ? "연출 줄임 (누르면 켬)" : "연출 켬 (누르면 줄임)"}</button></div></div>
    <div class="card"><h2>가족</h2>
      ${members.map((m) => `<div class="list-item"><div><b>${esc(m.name)}</b> <span class="muted">${esc(m.relation)}</span>${m.is_minor ? '<span class="pill">미성년</span>' : ""}</div><span class="pill">${roleName[m.role]}</span></div>`).join("")}
      ${canManage ? `<button class="secondary" style="margin-top:12px" id="inviteBtn">가족 초대 링크 만들기</button>` : `<p class="muted" style="margin-top:8px">가족 초대는 계약자(${esc(me.contract.holder_name)})가 할 수 있습니다.</p>`}
    </div>
    <div class="card"><h3>지난 대화 요약</h3>${history.length ? history.map((h) => `<div class="guest"><span class="who">${esc(h.deceased_name)} 님</span><span class="when">${esc(fmtDT(h.started_at))} · ${h.turns}회</span><div class="muted">${esc(h.summary || "(요약 없음)")}</div></div>`).join("") : `<p class="muted">아직 대화 기록이 없습니다. 대화 원문은 저장하지 않고 요약만 남깁니다.</p>`}</div>
    <div class="card" id="voiceCard"><h3>목소리 등록</h3><div id="voiceBody"><p class="muted">불러오는 중…</p></div></div>
    <div class="card" id="faceCard"><h3>얼굴 등록 <span class="muted">(실시간 아바타)</span></h3><div id="faceBody"><p class="muted">불러오는 중…</p></div></div>
    ${canManage && me.deceased.some((d) => d.ai_enabled) ? `<div class="card"><h3>대화 기능 작별</h3><p class="muted">대화 기능은 가족이 원하면 언제든 닫을 수 있습니다. 닫을 때 등록한 기억 카드와 음성 자료를 돌려받거나 삭제합니다.</p><button class="ghost" id="farewellBtn">작별 절차 시작</button></div>` : ""}
    <div class="card"><h3>내 정보</h3><p>${esc(me.member.name)} · ${esc(me.member.relation)} · ${roleName[me.member.role]}</p><p class="muted">계약자 ${esc(me.contract.holder_name)} · 봉안함 ${esc(me.niche?.code || "-")} · ${me.contract.plan === "premium" ? "프리미엄" : "기본"}</p>
      <button class="ghost small" id="logout">이 기기에서 나가기</button></div>`;
  $("#motionBtn").onclick = () => { localStorage.setItem("motion", motionReduced() ? "" : "reduce"); applyMotion(); renderSettings(); };
  view.querySelectorAll(".tile").forEach((t) => t.onclick = async () => {
    const id = t.dataset.theme; applyTheme(id);
    view.querySelectorAll(".tile").forEach((x) => x.classList.toggle("active", x === t));
    if (canManage && me.deceased[0]) {
      try { await api("/api/family/theme", { method: "POST", body: { deceased_id: me.deceased[0].id, theme: id } }); localStorage.removeItem("theme_local"); me.deceased[0].theme = id; toast("가족 모두의 화면에 적용했습니다."); }
      catch (e) { localStorage.setItem("theme_local", id); toast(e.message); }
    } else { localStorage.setItem("theme_local", id); }
  });
  $("#logout").onclick = () => { localStorage.removeItem("family_token"); location.href = "/"; };
  renderVoiceCard(); renderFaceCard();
  $("#inviteBtn") && ($("#inviteBtn").onclick = () => {
    const m = modal(`<h2>가족 초대</h2><p class="muted">만들어진 링크를 카카오톡으로 보내 주세요. 링크를 누르면 바로 열립니다.</p>
      <div class="field"><label>이름</label><input id="ivName"></div>
      <div class="field"><label>관계</label><input id="ivRel" placeholder="예: 둘째 아들"></div>
      <div class="field"><label>권한</label><select id="ivRole"><option value="view">보기만</option><option value="chat">보기·대화</option></select></div>
      <div class="check"><input type="checkbox" id="ivMinor"><label for="ivMinor" style="margin:0;color:var(--ink)">미성년자 (보호자 동반 필요)</label></div>
      <button id="ivGo">링크 만들기</button><div id="ivOut" style="margin-top:12px"></div>`);
    $("#ivGo", m).onclick = async () => {
      try {
        const r = await api("/api/family/invite", { method: "POST", body: { name: $("#ivName", m).value, relation: $("#ivRel", m).value, role: $("#ivRole", m).value, is_minor: $("#ivMinor", m).checked } });
        $("#ivOut", m).innerHTML = `<div class="link-box">${esc(r.link)}</div><button class="small" style="margin-top:8px" id="ivCopy">복사</button>`;
        $("#ivCopy", m).onclick = () => { navigator.clipboard?.writeText(r.link); toast("복사했습니다. 카카오톡에 붙여 넣어 보내세요."); };
      } catch (e) { toast(e.message); }
    };
  });
  $("#farewellBtn") && ($("#farewellBtn").onclick = () => {
    const d = me.deceased.find((x) => x.ai_enabled);
    const m = modal(`<h2>${esc(d.name)} 님과 작별</h2><p class="muted">대화 기능을 닫습니다. 이 절차는 되돌릴 수 없으며, 다시 열려면 봉안당에서 새로 등록해야 합니다.</p>
      <div class="field"><label>마지막 인사(방명록에 남습니다)</label><textarea id="fwWords" placeholder="고마웠어요. 이제 마음속에서 뵐게요."></textarea></div>
      <div class="field"><label>등록 자료 처리</label><select id="fwAct"><option value="return">돌려받기(화면에 표시)</option><option value="delete">삭제</option></select></div>
      <button class="danger" id="fwGo">작별하고 대화 기능 닫기</button>`);
    $("#fwGo", m).onclick = async () => {
      if (!confirm("정말 닫을까요?")) return;
      try {
        const r = await api("/api/family/farewell", { method: "POST", body: { deceased_id: d.id, action: $("#fwAct", m).value, last_words: $("#fwWords", m).value } });
        m.remove(); state.me = await api("/api/family/me");
        if (r.exported) modal(`<h2>돌려받은 자료</h2><p class="muted">아래 내용을 보관해 주세요. 서버에서는 지워졌습니다.</p><pre style="white-space:pre-wrap;font-size:14px">${esc(r.exported.memory_card || "(기억 카드 없음)")}</pre>`);
        else toast("작별 절차를 마쳤습니다.");
        renderSettings();
      } catch (e) { toast(e.message); }
    };
  });
}

// ---------------- 목소리 등록 (앱에서 직접 녹음 · 생전 기록) ----------------
const VOICE_SCRIPT = `<b>1분 정도, 평소 말투로 편하게</b> 이야기해 주세요. 조용한 곳에서, 휴대폰을 입에서 한 뼘쯤 떨어뜨리고요.<br>
예를 들면 — 가족 이름을 부르며 안부 묻기 · 요즘 지내는 이야기 · 좋아하는 음식이나 장소 · 가족에게 꼭 하고 싶은 말 · 자주 하시던 말씀<br>
<small>또박또박 읽는 말투보다 <b>평소 대화하듯 웃고 쉬어 가며</b> 말할수록 AI 목소리가 자연스러워집니다. 3분 가까이 길게 남기면 더 좋습니다.</small>`;

async function renderVoiceCard() {
  const box = $("#voiceBody"); if (!box) return;
  let v; try { v = await api("/api/family/voice"); } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  if (!v.provider_ready) { box.innerHTML = `<p class="muted">봉안당에서 아직 음성 복제 기능을 켜지 않았습니다. 사무실에 문의해 주세요.</p>`; return; }
  const rows = v.deceased.map((d) => `
    <div class="list-item" style="align-items:flex-start;flex-direction:column;gap:6px">
      <div class="row between" style="width:100%"><div><b>${esc(d.name)} 님</b> <span class="muted">${esc(d.honorific)}</span></div>
        ${d.has_voice ? '<span class="pill ok">목소리 등록됨</span>' : '<span class="pill">미등록</span>'}</div>
      <div class="muted" style="font-size:14px">${d.has_voice ? `이 목소리로 대화가 재생됩니다.` : `자료 ${d.samples}개`}${d.consent ? ` · 동의: ${esc(d.consent.signer_name)} (${d.consent.kind === "lifetime_record" ? "생전 기록" : "음성 사용"})` : ""}</div>
      <div class="row" style="flex-wrap:wrap">
        ${d.has_voice ? `<button class="small secondary" data-vprev="${d.id}">미리 듣기</button>` : ""}
        ${v.can_manage ? `<button class="small ${d.has_voice ? "ghost" : ""}" data-vrec="${d.id}">${d.has_voice ? "다시 등록" : "🎙️ 목소리 등록"}</button>` : ""}
        ${v.can_manage && d.has_voice ? `<button class="small ghost" data-vdel="${d.id}">삭제</button>` : ""}
      </div>
      <audio data-vaudio="${d.id}" controls style="display:none;width:100%"></audio>
    </div>`).join("");
  box.innerHTML = `<p class="muted" style="font-size:14px">살아 계실 때 직접 남기는 <b>생전 기록</b>이 가장 좋습니다. 고인의 음성 자료(휴대폰 영상·음성 메시지)도 가족 동의로 올릴 수 있습니다. 목소리는 대화에만 쓰이고, 작별하면 함께 지워집니다.</p>${rows}
    ${!v.can_manage ? '<p class="muted" style="font-size:14px">등록은 계약자만 할 수 있습니다.</p>' : ""}`;
  box.querySelectorAll("[data-vprev]").forEach((b) => b.onclick = async () => {
    b.disabled = true; b.textContent = "만드는 중…";
    try { const r = await fetch(withToken("/api/family/voice/preview"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ deceased_id: +b.dataset.vprev }) });
      if (!r.ok) throw new Error((await r.json()).detail); const a = box.querySelector(`[data-vaudio="${b.dataset.vprev}"]`); a.src = URL.createObjectURL(await r.blob()); a.style.display = "block"; a.play(); }
    catch (e) { toast(e.message, 4000); }
    b.disabled = false; b.textContent = "미리 듣기";
  });
  box.querySelectorAll("[data-vdel]").forEach((b) => b.onclick = async () => { if (confirm("등록된 목소리를 지울까요? 대화는 기본 음성으로 돌아갑니다.")) { await api(`/api/family/voice/${b.dataset.vdel}`, { method: "DELETE" }); renderVoiceCard(); } });
  box.querySelectorAll("[data-vrec]").forEach((b) => b.onclick = () => openRecorder(v.deceased.find((d) => d.id === +b.dataset.vrec), v.min_seconds));
}

function openRecorder(d, minSeconds) {
  const canRecord = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  const m = modal(`<h2>${esc(d.name)} 님 목소리 등록</h2>
    <div class="seg" style="margin-bottom:12px"><button class="active" data-kind="lifetime_record">본인이 직접 녹음<br><small>생전 기록</small></button><button data-kind="voice">고인의 음성 자료<br><small>가족 동의</small></button></div>
    <div class="script" id="script">${VOICE_SCRIPT}</div>
    <div id="recArea" style="margin-top:12px">
      ${canRecord ? `<div class="rec-time" id="recTime">0:00</div><button class="rec-btn" id="recBtn">🎙️</button><p class="muted center" style="font-size:14px" id="recHint">눌러서 녹음 시작</p>`
                  : `<div class="notice">이 브라우저에서는 마이크 녹음을 할 수 없습니다(https 또는 노트북에서 열면 됩니다). 아래에서 파일을 올려 주세요.</div>`}
      <audio id="recPlay" controls style="display:none;width:100%;margin-top:8px"></audio>
      <label class="btn secondary" style="margin-top:10px;cursor:pointer">📁 파일로 올리기 (mp3·m4a·wav·영상)<input type="file" id="recFile" accept="audio/*,video/*" hidden></label>
    </div>
    <div class="check" style="margin-top:12px"><input type="checkbox" id="vAgree"><label for="vAgree" style="margin:0;color:var(--ink)" id="vAgreeText">이 목소리가 AI 대화에만 쓰이는 것에 본인으로서 동의합니다. 언제든 삭제할 수 있습니다.</label></div>
    <div class="field"><input id="vNote" placeholder="메모(선택) 예: 2026년 추석에 녹음"></div>
    <button id="vGo" disabled>이 목소리로 등록</button><p class="muted center" id="vOut" style="margin-top:8px;font-size:14px"></p>`);
  let kind = "lifetime_record", blob = null, filename = "recording.webm", rec = null, stream = null, t0 = 0, timer = null;
  const out = (msg) => { $("#vOut", m).textContent = msg; };
  const ready = () => { $("#vGo", m).disabled = !(blob && $("#vAgree", m).checked); };
  m.querySelectorAll("[data-kind]").forEach((b) => b.onclick = () => { m.querySelectorAll("[data-kind]").forEach((x) => x.classList.remove("active")); b.classList.add("active"); kind = b.dataset.kind;
    $("#vAgreeText", m).textContent = kind === "lifetime_record" ? "이 목소리가 AI 대화에만 쓰이는 것에 본인으로서 동의합니다. 언제든 삭제할 수 있습니다." : "가족 대표로서 고인의 음성을 AI 대화에만 쓰는 것에 동의합니다. 다른 가족이 반대하면 즉시 삭제하겠습니다.";
    $("#script", m).innerHTML = kind === "lifetime_record" ? VOICE_SCRIPT : "휴대폰 영상, 음성 메시지, 통화 녹음 등 <b>고인의 목소리가 또렷하게 1분 이상</b> 담긴 파일을 올려 주세요. 여러 사람이 함께 말하는 파일은 품질이 떨어집니다."; });
  $("#vAgree", m).onchange = ready;
  const setBlob = (b, name) => { blob = b; filename = name; const a = $("#recPlay", m); a.src = URL.createObjectURL(b); a.style.display = "block"; ready(); };
  $("#recFile", m).onchange = (e) => { const f = e.target.files[0]; if (f) { setBlob(f, f.name); out(`${f.name} (${(f.size / 1024 / 1024).toFixed(1)}MB)`); } };
  if (canRecord) {
    const btn = $("#recBtn", m), time = $("#recTime", m), hint = $("#recHint", m);
    btn.onclick = async () => {
      if (rec && rec.state === "recording") { rec.stop(); return; }
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
      catch { return toast("마이크 권한이 필요합니다. 브라우저 주소창의 마이크 아이콘을 확인해 주세요.", 4000); }
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
      const chunks = []; rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      rec.onstop = () => { stream.getTracks().forEach((t) => t.stop()); clearInterval(timer); btn.classList.remove("on"); btn.textContent = "🎙️";
        const secs = (Date.now() - t0) / 1000; const b = new Blob(chunks, { type: rec.mimeType || mime });
        const ext = (rec.mimeType || mime).includes("mp4") ? "m4a" : (rec.mimeType || mime).includes("ogg") ? "ogg" : "webm";
        setBlob(b, `recording.${ext}`); hint.textContent = secs < minSeconds ? `${Math.round(secs)}초 — 너무 짧습니다. ${minSeconds}초 이상 다시 녹음해 주세요.` : `${Math.round(secs)}초 녹음됨 · 들어 보고 마음에 들면 아래 '등록'`; if (secs < minSeconds) { blob = null; ready(); } };
      rec.start(250); t0 = Date.now(); btn.classList.add("on"); btn.textContent = "■"; hint.textContent = "녹음 중… 다 말했으면 눌러서 마치기";
      timer = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); time.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; time.classList.toggle("short", s < minSeconds); if (s >= 180) rec.stop(); }, 250);
    };
  }
  $("#vGo", m).onclick = async () => {
    if (!blob) return; $("#vGo", m).disabled = true; out("올리는 중… 목소리를 만드는 데 1분쯤 걸립니다.");
    const fd = new FormData(); fd.append("deceased_id", d.id); fd.append("kind", kind); fd.append("agree", "true"); fd.append("note", $("#vNote", m).value); fd.append("file", blob, filename);
    try { const r = await api("/api/family/voice/register", { method: "POST", body: fd }); m.remove(); toast(`목소리를 등록했습니다${r.seconds ? ` (${Math.round(r.seconds)}초)` : ""}. 대화에서 바로 쓰입니다.`, 4000); renderVoiceCard(); state.me = await api("/api/family/me"); }
    catch (e) { out("실패: " + e.message); $("#vGo", m).disabled = false; }
  };
}

// ---------------- 얼굴 등록 (실시간 아바타) ----------------
async function renderFaceCard() {
  const box = $("#faceBody"); if (!box) return;
  let v; try { v = await api("/api/family/avatar"); } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  if (!v.provider_ready) { box.innerHTML = `<p class="muted">봉안당에서 아직 실시간 아바타 기능을 켜지 않았습니다. 지금은 사진 아바타로 대화합니다.</p>`; return; }
  const isDid = v.provider === "did";
  box.innerHTML = `<p class="muted" style="font-size:14px">말할 때 입이 움직이는 아바타입니다. <b>목소리 등록이 먼저</b> 되어 있어야 대화에서 쓰입니다. 화면에는 항상 'AI 실시간 영상' 표시가 붙습니다.<br>
    ${isDid ? "<b>D-ID</b>: 올린 정면 사진 <b>그대로</b>를 움직이므로 얼굴이 실제와 같습니다." : "<b>Simli</b>: 기본 얼굴은 무료 플랜에서 바로 되고, 사진으로 만든 얼굴은 유료 플랜이 필요합니다."}</p>` +
    v.deceased.map((d) => `<div class="list-item" style="align-items:flex-start;flex-direction:column;gap:6px">
      <div class="row between" style="width:100%"><div><b>${esc(d.name)} 님</b> <span class="muted">${esc(d.honorific)}</span></div>
        ${d.has_face ? `<span class="pill ok">${esc(d.face_label || "얼굴 등록됨")}</span>` : '<span class="pill">미등록</span>'}</div>
      <div class="muted" style="font-size:14px">사진 ${d.has_photo ? "있음" : "없음"} · 목소리 ${d.has_voice ? "있음" : "없음"}${d.consent ? ` · 동의: ${esc(d.consent.signer_name)}` : ""}</div>
      ${v.can_manage && v.presets.length ? `<div class="row" style="width:100%"><select data-fpreset="${d.id}" style="flex:1"><option value="">기본 얼굴 고르기…</option>${v.presets.map((pf) => `<option value="${pf.id}">${esc(pf.label)}</option>`).join("")}</select><button class="small secondary" data-fpresetgo="${d.id}" style="min-height:44px">기본 얼굴로 시연</button></div>` : ""}
      <div class="row" style="flex-wrap:wrap">
        ${v.can_manage ? `<label class="btn small secondary" style="width:auto;cursor:pointer">📷 정면 사진 올리기<input type="file" accept="image/*" data-fphoto="${d.id}" hidden></label>` : ""}
        ${v.can_manage && d.has_photo ? `<button class="small" data-freg="${d.id}">🎬 ${d.has_face ? "사진으로 다시 만들기" : "사진으로 얼굴 만들기"}${isDid ? "" : " (유료)"}</button>` : ""}
        ${v.can_manage && d.has_face ? `<button class="small ghost" data-fdel="${d.id}">삭제</button>` : ""}
      </div><div class="muted" style="font-size:13px" data-fout="${d.id}"></div></div>`).join("");
  box.querySelectorAll("[data-fpresetgo]").forEach((b) => b.onclick = async () => {
    const id = b.dataset.fpresetgo; const sel = box.querySelector(`[data-fpreset="${id}"]`); if (!sel.value) return toast("기본 얼굴을 먼저 고르세요.");
    try { await api("/api/family/avatar/preset", { method: "POST", body: { deceased_id: +id, face_id: sel.value } }); toast("기본 얼굴을 설정했습니다. 다음 대화부터 실시간 아바타가 나옵니다.", 4000); renderFaceCard(); state.me = await api("/api/family/me"); }
    catch (e) { toast(e.message, 5000); }
  });
  box.querySelectorAll("[data-fphoto]").forEach((inp) => inp.onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return; const fd = new FormData(); fd.append("deceased_id", inp.dataset.fphoto); fd.append("file", f);
    try { await api("/api/family/avatar/photo", { method: "POST", body: fd }); toast("사진을 올렸습니다."); renderFaceCard(); } catch (err) { toast(err.message, 4000); }
  });
  box.querySelectorAll("[data-freg]").forEach((b) => b.onclick = () => {
    const d = v.deceased.find((x) => x.id === +b.dataset.freg);
    const m = modal(`<h2>${esc(d.name)} 님 얼굴 등록</h2><p class="muted">정면을 보는 사진이 가장 좋습니다(옆모습·모자·선글라스는 실패할 수 있음). 사진은 아바타 공급자(${isDid ? "D-ID" : "Simli"})로 전송됩니다.${isDid ? " D-ID의 자동 검열이 사진을 거부하면 다른 사진으로 다시 시도해 주세요." : ""}</p>
      <div class="seg" style="margin-bottom:12px"><button class="active" data-kind="likeness">고인의 사진<br><small>가족 동의</small></button><button data-kind="lifetime_record">본인 사진<br><small>생전 기록</small></button></div>
      <div class="check"><input type="checkbox" id="fAgree"><label for="fAgree" style="margin:0;color:var(--ink)">이 사진을 AI 대화의 얼굴로만 쓰는 것에 동의합니다. 다른 가족이 반대하면 즉시 삭제하겠습니다.</label></div>
      <button id="fGo" disabled>얼굴 만들기</button><p class="muted center" id="fOut" style="margin-top:8px;font-size:14px"></p>`);
    let kind = "likeness";
    m.querySelectorAll("[data-kind]").forEach((k) => k.onclick = () => { m.querySelectorAll("[data-kind]").forEach((x) => x.classList.remove("active")); k.classList.add("active"); kind = k.dataset.kind; });
    $("#fAgree", m).onchange = () => { $("#fGo", m).disabled = !$("#fAgree", m).checked; };
    $("#fGo", m).onclick = async () => {
      $("#fGo", m).disabled = true; $("#fOut", m).textContent = "얼굴을 만드는 중… 1~3분 걸릴 수 있습니다.";
      try { await api("/api/family/avatar/register", { method: "POST", body: { deceased_id: d.id, agree: true, kind } }); m.remove(); toast("얼굴을 등록했습니다. 다음 대화부터 실시간 아바타가 나옵니다.", 4000); renderFaceCard(); state.me = await api("/api/family/me"); }
      catch (e) { $("#fOut", m).textContent = "실패: " + e.message; $("#fGo", m).disabled = false; }
    };
  });
  box.querySelectorAll("[data-fdel]").forEach((b) => b.onclick = async () => {
    if (b.dataset.armed !== "1") { b.dataset.armed = "1"; b.textContent = "정말 삭제 (다시 누르기)"; setTimeout(() => { b.dataset.armed = ""; b.textContent = "삭제"; }, 5000); return; }
    await api(`/api/family/avatar/${b.dataset.fdel}`, { method: "DELETE" }); renderFaceCard();
  });
}

if ("speechSynthesis" in window) window.speechSynthesis.onvoiceschanged = () => {};
boot();
