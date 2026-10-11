// 유족 웹앱. 초대 링크(/?t=토큰)로 열리며 설치가 필요 없다.
import {createCommunity} from './community.js?v=20261011-brand';
import {mountArt, destroyArt} from './brand.js?v=20261011';
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
  el.setAttribute("role", "status"); el.textContent = msg; el.classList.remove("hidden"); clearTimeout(toastT); toastT = setTimeout(() => el.classList.add("hidden"), ms);
}
function modal(html) {
  const previous = document.activeElement;
  const bg = document.createElement("div"); bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-label="상세 안내" tabindex="-1"><button class="small ghost modal-close" type="button" aria-label="팝업 닫기">닫기 ×</button>${html}</div>`;
  const close = () => { bg.remove(); if (previous?.isConnected) previous.focus(); };
  bg.querySelector(".modal-close").onclick = close;
  bg.addEventListener("click", (e) => { if (e.target === bg) close(); });
  bg.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    if (e.key !== "Tab") return;
    const items = [...bg.querySelectorAll('button, a[href], input, select, textarea, [tabindex="0"]')].filter(el => !el.disabled && el.getClientRects().length);
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  document.body.appendChild(bg); bg.querySelector(".modal-close").focus(); return bg;
}

const state = { me: null, tab: "visit", timers: [] };
// 오류 안내: 무엇이 안 됐는지 + 이유 + 다음 행동(다시 불러오기)
function failCard(what, e, tab) {
  view.innerHTML = `<div class="card" role="alert"><h2>${esc(what)} 불러오지 못했습니다</h2><p class="muted">${esc(e?.message || "")}</p><p class="muted">연결을 확인한 뒤 다시 불러와 주세요.</p><button class="secondary" type="button" id="failRetry">다시 불러오기</button></div>`;
  $("#failRetry").onclick = () => go(tab || state.tab);
}
function clearTimers() { state.timers.forEach(clearInterval); state.timers = []; }
function every(fn, ms) { const id = setInterval(fn, ms); state.timers.push(id); return id; }

// ---------------- 테마(전통·불교·천주교·기독교) ----------------
const THEMES = [
  ["classic", "일반", "종교 상징 없이 선과 여백"],
  ["buddhist", "불교", "연꽃 · 단청"],
  ["catholic", "천주교", "아치 창과 십자 선"],
  ["christian", "기독교", "십자 선"],
];
// 테마마다 바뀌는 것은 상징과 강조색뿐이고, 먹·한지 바탕과 명조 제목은 같다.
const THEME_FONTS = { classic: "종교 상징 없음 · 창살 선 · 먹 올리브 강조색", buddhist: "연꽃 · 단청 띠 · 주홍 강조색", catholic: "아치 창 십자 선 · 청회색 강조색", christian: "십자 선 · 짙은 청록 강조색" };
const THEME_META = { classic: "#121410", buddhist: "#121410", catholic: "#121410", christian: "#121410" };
function applyTheme(t) {
  if (!THEME_META[t]) t = "classic";
  document.documentElement.dataset.theme = t;
  const meta = document.querySelector('meta[name="theme-color"]'); if (meta) meta.content = THEME_META[t];
  state.theme = t;
}
function currentTheme() { return (state.me?.member.role === "manage" ? null : localStorage.getItem("theme_local")) || state.me?.deceased?.[0]?.theme || "classic"; }
function motionReduced() { return localStorage.getItem("motion") === "reduce" || window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
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
    view.innerHTML = `<section class="memorial-hero entry-hero"><div class="memorial-hero-copy"><span class="eyebrow">가족 추모 공간</span><h1>초대 링크로<br>들어와 주세요.</h1><p>계약하신 가족에게 받은 카카오톡 초대 링크를 누르면 바로 열립니다. 링크가 없으면 시설 담당자에게 초대를 요청해 주세요.</p></div><div class="hero-art" id="heroArt"></div></section>`;
    mountArt($("#heroArt"), state.theme, motionReduced());
    return;
  }
  try { state.me = await api("/api/family/me"); }
  catch (e) {
    view.innerHTML = `<section class="memorial-hero entry-hero"><div class="memorial-hero-copy"><span class="eyebrow">가족 추모 공간</span><h1>추모 공간을<br>열지 못했습니다.</h1><p>${esc(e.message)}</p><p>초대 링크가 바뀌었을 수 있습니다. 계약하신 가족이나 시설 담당자에게 새 초대 링크를 요청해 주세요.</p><button class="secondary" type="button" id="retryBoot">다시 열기</button></div><div class="hero-art" id="heroArt"></div></section>`;
    $("#tabs").classList.add("hidden"); $("#retryBoot").onclick = () => location.reload(); mountArt($("#heroArt"), state.theme, motionReduced()); return;
  }
  applyTheme(currentTheme());
  $("#who").textContent = `${state.me.member.name} 님`;
  community.init();
  $("#tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) go(b.dataset.tab); });
  const want = location.hash.slice(1);   // /?t=…#ritual 처럼 탭을 지정해 열 수 있다
  go(["visit", "memorial", "chat", "ritual", "settings", ...Object.keys(community.pages)].includes(want) ? want : localStorage.getItem('memorial_easy')==='true'?'easy':'visit');
}
function go(tab) {
  clearTimers(); stopSpeech(); destroyArt(); state.tab = tab; history.replaceState(null, "", location.pathname + (tab === "visit" ? "" : "#" + tab));
  document.querySelectorAll("#tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
    if (b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  view.dataset.page = tab;
  view.innerHTML = `<div class="card center"><p class="muted" role="status">화면을 불러오는 중입니다…</p></div>`;
  const render = ({ visit: renderVisit, memorial: renderMemorial, chat: renderChat, ritual: renderRitual, settings: renderSettings, ...community.pages })[tab];
  Promise.resolve(render()).then(() => {if(state.tab===tab)community.mount(tab);}).catch(e=>failCard("화면을", e, tab));
  window.scrollTo(0, 0);
}

// ---------------- 로컬 시작 화면 (서버를 켠 컴퓨터에서 초대 링크 없이 열었을 때) ----------------
async function renderLauncher() {
  let L;
  try { const r = await fetch("/api/launcher"); if (!r.ok) return false; L = await r.json(); } catch { return false; }
  const roleName = { view: "보기", chat: "보기·대화", manage: "계약자(관리)" };
  view.innerHTML = `<div class="launch">
    <section class="memorial-hero launch-intro"><div class="memorial-hero-copy"><span class="eyebrow">가족 추모 공간 · 원격 추도식</span><h1>그리운 마음을,<br>가까이 전합니다.</h1>
      <p>${esc(L.facility || "봉안당")}의 가족 추모 공간입니다. 아래에서 가족 계정을 골라 들어가 주세요.</p></div><div class="hero-art" id="heroArt"></div></section>
    <div class="card"><div class="row between"><h2>가족 계정으로 들어가기</h2><span class="pill">시연 계정</span></div>
      ${L.members.map((m) => `<div class="who-row"><div><b>${esc(m.name)}</b> <span class="muted">${esc(m.relation)} · ${roleName[m.role] || m.role}</span>
        <div class="muted meta">${esc(m.deceased_names || "고인 정보 등록 전")} · 봉안함 ${esc(m.niche_code || "-")} · ${m.plan === "premium" ? "프리미엄" : "기본"}</div></div>
        <div class="row" style="gap:6px"><a class="btn" href="${esc(m.url)}">들어가기</a><a class="btn secondary" href="${esc(m.url)}" target="_blank" rel="noopener">새 창으로</a></div></div>`).join("") || '<p class="muted">아직 시연 계정이 없습니다. 관리자 콘솔에서 계약·가족을 만들거나, 명령 창에서 python -m server.seed 를 실행해 주세요.</p>'}
    </div>
    <div class="card"><div class="row between"><div><h2>추모 운영</h2><p class="muted">직원이 가족·일정·서비스 설정을 관리합니다.</p></div><a class="btn small secondary" href="${esc(L.admin_url)}" target="_blank" rel="noopener">관리자 콘솔 열기 (새 창)</a></div></div>
    <details class="launch-help card"><summary>시작 화면 이용 안내</summary><p>이 화면은 서버를 실행한 컴퓨터에서만 보입니다. 가족에게는 초대 링크를 보내 주세요.</p><p>다음에 이용할 때는 바탕화면의 <b>봉안당 시연 시작</b> 또는 <b>시작.bat</b>을 열어 주세요.</p></details>
  </div>`;
  mountArt($("#heroArt"), state.theme, motionReduced());
  return true;
}

// ---------------- 1. 원격 참배 ----------------
async function renderVisit() {
  const me = state.me;
  if (!me.niche) { view.innerHTML = `<div class="card empty-state"><h2>아직 연결된 봉안함이 없습니다</h2><p class="muted">시설에서 봉안함 번호를 연결하면 이 화면에서 참배하실 수 있습니다. 시설 담당자에게 연결을 요청해 주세요.</p><button class="secondary" type="button" id="toMemorial">추모 공간 열기</button></div>`; $("#toMemorial").onclick = () => go("memorial"); return; }
  const d = me.deceased[0];
  const liveLabel = `<svg viewBox="0 0 24 24" width="22" height="22" style="stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round"><path d="M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/></svg> 실시간으로 뵙기 <small class="btn-note">${me.live_seconds}초</small>`;
  view.innerHTML = `
    <section class="welcome-garden memorial-hero" aria-labelledby="heroTitle"><div class="memorial-hero-copy"><span class="eyebrow">원격 참배</span><h1 id="heroTitle">그리운 마음에,<br>따뜻한 안부를.</h1><p>${esc(d ? d.name + " 님" : "소중한 분")}의 봉안함을 사진과 실시간 영상으로 뵙습니다.</p></div><div class="hero-art" id="heroArt"></div></section>
    <div class="card tight visit-card">
      <div class="row between" style="margin-bottom:10px"><h2 style="margin:0">${esc(d ? d.name + " 님" : "우리 가족")} <small class="muted niche-code">봉안함 ${esc(me.niche.code)}</small></h2></div>
      <div class="viewer" id="viewer">
        <div class="snapshot" id="snap"><div class="placeholder">사진을 불러오는 중…</div></div>
        <div class="veil"><div class="pane l"></div><div class="pane r"></div></div>
        <div class="candle l"></div><div class="candle r"></div><div class="smoke"></div>
        <div class="title-card">${esc(d ? d.name + " 님을 뵙습니다" : "가족을 뵙습니다")}</div>
      </div>
      <div class="status-line"><span id="camStatus" role="status"><span class="dot"></span>카메라 상태를 확인하는 중입니다…</span><span class="row" style="gap:8px"><span id="snapAt"></span><button class="chime-toggle ${chimeEnabled() ? "on" : ""}" id="chimeBtn">종소리 ${chimeEnabled() ? "켬" : "끔"}</button></span></div>
    </div>
    <div class="visit-actions">
      <button id="liveBtn">${liveLabel}</button>
      <button class="secondary" id="toMemorial">추모 공간 열기</button>
    </div>
    <details class="visit-help"><summary>참배 화면 이용 안내</summary><p>사진은 10초마다 새로 찍힙니다. 현장에 다른 참배객이 계시면 실시간 영상은 잠시 멈추고 사진으로 보여 드립니다.</p></details>`;
  mountArt($("#heroArt"), state.theme, motionReduced());
  $("#toMemorial").onclick = () => go("memorial");
  $("#snap").onclick = () => { if (!live.on) go("memorial"); };   // 화면 속 봉안함을 누르면 추모 공간
  $("#chimeBtn").onclick = () => { localStorage.setItem("chime", chimeEnabled() ? "0" : "1"); const on = chimeEnabled(); $("#chimeBtn").classList.toggle("on", on); $("#chimeBtn").textContent = `종소리 ${on ? "켬" : "끔"}`; if (on) chime(); };
  const live = { on: false, timer: null };
  let firstShown = false;

  const snap = $("#snap"), viewer = $("#viewer");
  async function refreshStatus() {
    try {
      const s = await api("/api/family/niche/status");
      const demo = s.live_protect === false;   // 관리자 콘솔에서 참배객 보호를 끈 시연 모드
      $("#camStatus").innerHTML = (s.camera_online
        ? (s.occupied && !demo ? `<span class="dot busy"></span>현장에 참배객이 계십니다` : `<span class="dot on"></span>카메라 연결됨`)
        : `<span class="dot"></span>현장 카메라가 꺼져 있습니다`) + (demo ? ' <span class="pill" title="참배객 감지를 꺼 둔 상태">시연 모드</span>' : "")
        + (s.blurry ? ' <span class="pill" style="color:var(--danger)" title="윈도우 설정 → 카메라 → Windows 스튜디오 효과 → 배경 효과 끄기">카메라 영상 흐림</span>' : "");
      $("#snapAt").textContent = s.last_snapshot_at ? `사진 ${ago(s.last_snapshot_at)}` : "사진 없음";
      if (live.on && s.occupied && !demo) endLive("현장에 참배객이 계셔서 사진 화면으로 바꿨습니다.");
    } catch {}
  }
  function showSnapshot() {
    const img = new Image();
    img.onload = () => { if (img.naturalWidth) snap.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`; snap.innerHTML = ""; snap.classList.remove("live"); snap.classList.toggle("reveal", !firstShown); firstShown = true; snap.appendChild(img); snap.insertAdjacentHTML("beforeend", `<span class="badge">방금 찍은 사진</span><span class="tap-hint">누르면 추모 공간이 열립니다</span>`); };
    img.onerror = () => { if (!snap.querySelector("img")) snap.innerHTML = `<div class="placeholder">아직 봉안함 사진이 없습니다.<br><small>현장 카메라가 켜지면 자동으로 나타납니다. 그동안 추모 공간에서 마음을 남기실 수 있습니다.</small></div>`; };
    img.src = withToken("/api/family/niche/snapshot.jpg") + "&_=" + Date.now();
  }
  function endLive(msg) {
    if (!live.on) return; live.on = false; clearInterval(live.timer);
    viewer.classList.remove("live", "open", "curtain");
    $("#liveBtn").disabled = false; $("#liveBtn").innerHTML = liveLabel;
    showSnapshot(); if (msg) toast(msg);
  }
  $("#liveBtn").onclick = async () => {
    if ($("#liveBtn").disabled) return;
    $("#liveBtn").disabled = true; $("#liveBtn").textContent = "실시간 영상을 여는 중입니다…";
    try {
      const r = await api("/api/family/live/start", { method: "POST" });
      live.on = true; let left = r.seconds;
      // 극적 연출: 막이 내린 상태에서 종소리와 함께 막이 열리고, 영상이 안개 속에서 또렷해지며 촛불·향이 켜진다.
      viewer.classList.remove("open", "live"); viewer.classList.add("curtain");
      const img = new Image();
      img.onerror = () => endLive("실시간 영상이 끊겼습니다. 사진으로 보여 드립니다.");
      img.onload = () => { if (img.naturalWidth) snap.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`; };
      snap.innerHTML = ""; snap.classList.remove("reveal"); snap.classList.add("live"); snap.appendChild(img); snap.insertAdjacentHTML("beforeend", `<span class="badge live">실시간</span>`);
      img.src = withToken(`/api/family/live/stream?sid=${r.session_id}`);
      chime();
      void viewer.offsetWidth;   // 막(display:none→block)의 초기 위치를 먼저 그리게 해서 열리는 전환이 실제로 보이게 한다
      setTimeout(() => { if (live.on) viewer.classList.add("open", "live"); }, 500);
      setTimeout(() => { if (live.on) viewer.classList.remove("curtain"); }, 4200);
      $("#liveBtn").disabled = true; $("#liveBtn").textContent = `실시간으로 뵙는 중입니다 · ${left}초 남음`;
      live.timer = every(() => { const b = $("#liveBtn"); if (!b) { clearInterval(live.timer); return; } left--; if (left <= 0) endLive("실시간 보기가 끝났습니다."); else b.textContent = `실시간으로 뵙는 중입니다 · ${left}초 남음`; }, 1000);
    } catch (e) { $("#liveBtn").disabled = false; $("#liveBtn").innerHTML = liveLabel; toast(`실시간 영상을 열지 못했습니다. ${e.message}`, 4500); }
  };
  showSnapshot(); refreshStatus();
  every(() => { if (!live.on) showSnapshot(); }, 10000);
  every(refreshStatus, 3000);
}

// ---------------- 2. 추모 공간 ----------------
async function renderMemorial() {
  let data; try { data = await api("/api/family/memorial"); } catch (e) { failCard("추모 공간을", e, "memorial"); return; }
  const cards = data.deceased.map((d) => `
    <article class="card hero memorial-garden" data-memorial-theme="${esc(state.theme || d.theme || 'classic')}">
      <div class="memorial-cover" aria-hidden="true"></div>
      <div class="memorial-dedication">
        <div class="portrait-arch">${d.has_photo ? `<img class="portrait big" src="${withToken(`/api/family/deceased/${d.id}/photo.jpg`)}" alt="${esc(d.name)} 님의 사진">` : `<div class="portrait big no-portrait"><span aria-hidden="true">♡</span><small>사진 등록 전</small></div>`}</div>
        <div class="dedication-copy"><span class="eyebrow">가족 추모 공간</span><h2>${esc(d.name)} <small>님</small></h2><p class="memorial-relation">${esc(d.honorific)}</p><div class="dates">${esc(fmtD(d.birth_date))} — ${esc(fmtD(d.death_date))}</div><p class="dedication-message">함께한 날들의 온기를<br>오래도록 간직하겠습니다.</p></div>
      </div><div class="memorial-records"><h3>함께 간직한 순간</h3>
      ${d.media.length ? `<div class="media-grid" style="margin-top:6px">${d.media.slice(0, 9).map((m) => m.kind === "video" || m.kind === "message_video"
        ? `<div><video src="${withToken(`/api/family/media/${m.id}`)}" controls playsinline></video><div class="cap">${esc(m.caption)}${m.ai_generated ? '<span class="ai-tag">인공지능 제작</span>' : ""}</div></div>`
        : m.kind === "voice" ? `<div><audio src="${withToken(`/api/family/media/${m.id}`)}" controls style="width:100%"></audio><div class="cap">${esc(m.caption)}</div></div>`
        : `<div><img src="${withToken(`/api/family/media/${m.id}`)}" alt=""><div class="cap">${esc(m.caption)}</div></div>`).join("")}</div>` : `<p class="muted">아직 함께 간직한 사진과 영상이 없습니다. 가족 앨범에 소중한 순간을 남겨 주세요.</p><button class="secondary small" type="button" data-to-album>가족 앨범에 남기기</button>`}
    </div></article>`).join("");
  const upcoming = data.upcoming.length ? data.upcoming.map((r) => `<div class="ritual"><span class="when">${esc(fmtDT(r.scheduled_at))}</span> ${esc(r.title)}</div>`).join("") : `<p class="muted">아직 예정된 추도식이 없습니다. 시설에 일정을 문의해 주세요.</p>`;
  const guest = data.guestbook.length ? data.guestbook.map((g) => `<div class="guest"><span class="who">${esc(g.author)}</span><span class="when">${esc(fmtDT(g.created_at))}</span><div>${esc(g.message)}</div></div>`).join("") : `<p class="muted">아직 남긴 글이 없습니다. 위 칸에 첫 마음을 남겨 주세요.</p>`;
  view.innerHTML = `${cards}
    <div class="card"><h3>다가오는 기일·추도식</h3>${upcoming}<button class="secondary small" style="margin-top:8px" id="toRitual">일정 전체 보기</button></div>
    <div class="card"><h3>가족 방명록</h3>
      <div class="field"><label for="gbMsg">가족에게, 그리고 ${esc(data.deceased[0]?.name || "고인")} 님께 남길 말</label><textarea id="gbMsg" aria-describedby="gbHelp"></textarea><small class="muted" id="gbHelp">남긴 글은 가족 모두가 봅니다.</small></div>
      <button id="gbSend">방명록에 남기기</button>
      <div style="margin-top:12px">${guest}</div></div>`;
  $("#toRitual").onclick = () => go("ritual");
  view.querySelectorAll("[data-to-album]").forEach((b) => b.onclick = () => go("album"));
  $("#gbSend").onclick = async () => {
    const b = $("#gbSend"), t = $("#gbMsg").value.trim();
    if (!t) { toast("남길 말을 먼저 적어 주세요."); $("#gbMsg").focus(); return; }
    if (b.disabled) return; b.disabled = true; b.textContent = "남기는 중입니다…";
    try { await api("/api/family/guestbook", { method: "POST", body: { message: t } }); toast("방명록에 글을 남겼습니다."); go("memorial"); }
    catch (e) { b.disabled = false; b.textContent = "방명록에 남기기"; toast(`글을 남기지 못했습니다. 연결을 확인한 뒤 다시 남겨 주세요. ${e.message}`, 5000); }
  };
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
  if (me.member.role === "view") { view.innerHTML = `<div class="card"><h2>기념일 대화</h2><p class="muted">대화는 계약하신 가족의 허락이 필요합니다. 계약자(${esc(me.contract.holder_name)} 님)에게 대화 허용을 요청해 주세요.</p><button class="secondary" type="button" id="toMemorial">추모 공간으로 가기</button></div>`; $("#toMemorial").onclick = () => go("memorial"); return; }
  if (!eligible.length) { view.innerHTML = `<div class="card"><h2>기념일 대화</h2><p class="muted">아직 대화 기능이 열려 있지 않습니다.</p><p class="muted">시설 상담 직원과 30분가량 이야기를 나누어 <b>기억 카드</b>를 만들고 직계가족 동의서를 등록하면 열립니다. 대화 기능은 선택 사항이며, 언제든 닫을 수 있습니다. 시설 담당자에게 문의해 주세요.</p><button class="secondary" type="button" id="toMemorial">추모 공간으로 가기</button></div>`; $("#toMemorial").onclick = () => go("memorial"); return; }
  const options = eligible.map((d) => `<option value="${d.id}">${esc(d.name)} 님${d.honorific ? ` (${esc(d.honorific)})` : ""}</option>`).join("");
  const first = eligible[0];
  view.innerHTML = `
    <div class="notice ai" role="note">이 화면의 목소리와 답변은 인공지능이 만든 것입니다. 실제 고인이 아닙니다.</div>
    <div class="card hero" style="margin-top:12px;text-align:left">
      <span class="eyebrow">인공지능 추모 대화</span>
      <h2>기념일 대화</h2>
      <p class="muted">기일·명절·생신처럼 특별한 날에, 가족이 남긴 기억과 말투로 만든 인공지능과 짧게 이야기합니다. 한 번에 ${me.chat_max_minutes}분입니다.</p>
      <p class="muted">${first.has_voice ? "가족이 등록한 목소리로 만든 인공지능 음성으로 답합니다." : `기본 인공지능 음성으로 답합니다. ${me.member.role === "manage" ? '<a href="#" id="toVoice" class="text-link">목소리 등록하기</a>' : "계약자가 목소리를 등록하면 그 음성으로 바뀝니다."}`}
      ${first.has_face && first.has_voice ? " 등록한 얼굴로 실시간 아바타가 나옵니다." : first.has_face ? " 실시간 아바타는 목소리 등록 뒤에 켜집니다." : ""}</p>
      <div class="field"><label>누구와 이야기할까요</label><select id="chatWho">${options}</select></div>
      <div class="field"><label>오늘의 자리</label><select id="occ"><option value="">평소</option><option>기일</option><option>명절</option><option>생신</option><option>49재</option></select></div>
      ${first.days_since_death !== null && first.days_since_death < 49 ? `<div class="notice">첫 대화는 49재 이후를 권합니다. (별세 후 ${first.days_since_death}일)</div>` : ""}
      <div class="check"><input type="checkbox" id="ack"><label for="ack" style="margin:0;color:var(--ink)">이 대화가 인공지능이 만든 음성·답변이며, 실제 고인이 아님을 이해했습니다.</label></div>
      ${me.member.is_minor ? `<div class="check"><input type="checkbox" id="guardian"><label for="guardian" style="margin:0;color:var(--ink)">보호자가 함께 있습니다.</label></div>` : ""}
      <button id="startChat" style="margin-top:8px">대화 시작하기</button>
      <p class="muted center" style="margin-top:10px">마음이 많이 힘드시면 자살예방 상담전화 <b>109</b>로 먼저 연락해 주세요.</p>
    </div>`;
  if ($("#toVoice")) $("#toVoice").onclick = (e) => { e.preventDefault(); go("settings"); setTimeout(() => $("#voiceCard")?.scrollIntoView({ behavior: "smooth" }), 300); };
  $("#startChat").onclick = async () => {
    if (!$("#ack").checked) { toast("인공지능 안내를 읽고 확인란에 표시해 주세요."); $("#ack").focus(); return; }
    const sb = $("#startChat"); if (sb.disabled) return; sb.disabled = true; sb.textContent = "대화를 준비하는 중입니다…";
    try {
      const r = await api("/api/family/chat/start", { method: "POST", body: { deceased_id: +$("#chatWho").value, occasion: $("#occ").value, acknowledged_ai: true, guardian_present: !!$("#guardian")?.checked } });
      runChat(r, eligible.find((d) => d.id === +$("#chatWho").value));
    } catch (e) { sb.disabled = false; sb.textContent = "대화 시작하기"; toast(`대화를 시작하지 못했습니다. ${e.message}`, 5000); }
  };
}

function runChat(sess, d) {
  clearTimers();
  let left = sess.max_seconds, ended = false, busy = false;
  view.innerHTML = `
    <div class="notice ai" role="note" style="text-align:center">인공지능이 만든 음성·영상입니다 · 실제 고인이 아닙니다</div>
    <div class="chat-wrap">
      <div class="shrine" id="stage">
        <div class="shrine-halo"></div>
        <div class="shrine-frame"><div class="shrine-inner">
          <div class="backdrop"></div>
          ${sess.photo_url ? `<img src="${withToken(sess.photo_url)}" alt="">` : `<div class="no-photo" aria-hidden="true">◯</div>`}
          <video id="avatarVideo" autoplay playsinline></video>
          <div class="rays"></div><div class="mist"></div>
        </div></div>
        <div class="shrine-particles"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
        <div class="shrine-caption"><span class="live-badge" id="liveBadge">인공지능 사진 아바타</span>
          <div class="voice-bars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
          <div class="voice-tag" id="voiceTag">${sess.voice_available ? "가족이 등록한 목소리로 만든 인공지능 음성" : "기본 인공지능 음성"}${sess.avatar_available ? " · 실시간 아바타 연결 중…" : ""}</div></div>
      </div>
      <div class="chat-head" style="margin:6px 0 4px">
        <div><h2 style="margin:0">${esc(d.name)} 님</h2><div class="timer" id="timer"></div></div>
        <button class="secondary small" id="endBtn" style="margin-left:auto">대화 마치기</button>
      </div>
      ${sess.notices.map((n) => `<div class="notice" style="margin-bottom:6px">${esc(n)}</div>`).join("")}
      <div class="chat-log" id="log"></div>
      <div class="chat-input">
        <button class="mic" id="mic" type="button" aria-label="말로 하기"><svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" style="fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/></svg></button>
        <input id="txt" aria-label="하고 싶은 말" placeholder="말하거나 글로 적어 주세요" autocomplete="off">
        <button class="small" id="send" style="min-height:48px">보내기</button>
      </div>
      <p class="muted center chat-foot">대화: ${esc(({ anthropic: "인공지능 언어 모델", mock: "규칙 기반 시연 대화" })[sess.provider] || sess.provider)} · 음성: ${esc(({ elevenlabs: "복제 음성", browser: "기기 기본 음성" })[sess.voice_provider || "browser"] || sess.voice_provider)} · 내 목소리 원본은 저장하지 않습니다</p>
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
      $("#liveBadge").textContent = st === "live" ? "인공지능 실시간 영상" : "인공지능 사진 아바타";
      $("#voiceTag").textContent = st === "live" ? `가족이 등록한 목소리와 사진으로 만든 인공지능 · 실시간 아바타(${sess.avatar_provider === "did" ? "D-ID" : "Simli"})` : `가족이 등록한 목소리로 만든 인공지능 음성 · 사진 아바타${reason ? ` (${reason})` : ""}`;
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
    $("#endBtn").textContent = "대화 처음 화면으로"; $("#endBtn").onclick = () => go("chat");
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
    rec.onerror = (e) => { speech.listening = false; $("#mic").classList.remove("listening"); stage.classList.remove("listening"); if (e.error !== "no-speech" && e.error !== "aborted") toast("말소리를 알아듣지 못했습니다. 다시 말하거나 글로 적어 주세요."); };
    rec.start();
  }
  speech.autoListen = false;
  $("#mic").onclick = () => { speech.autoListen = true; listen(); };
}

// ---------------- 4. 제사 일정·중계·공양 ----------------
async function renderRitual() {
  let rituals, offerings;
  try { [rituals, offerings] = await Promise.all([api("/api/family/rituals"), api("/api/family/offerings")]); } catch (e) { failCard("추도식 일정을", e, "ritual"); return; }
  const me = state.me;
  const kindName = { memorial: "기일 제례", holiday: "명절 차례", event: "법회·추모식" };
  const pStatus = { requested: "신청됨", accepted: "확정", rejected: "반려" };
  const items = rituals.filter((r) => !r.is_past).map((r) => `
    <div class="ritual">
      <div><span class="when">${esc(fmtDT(r.scheduled_at))}</span><span class="pill">${kindName[r.kind] || r.kind}</span><span class="pill">${r.access === "applied" ? "신청 가족만" : "누구나"}</span>${r.is_live_window && (r.has_camera || r.stream_url) ? '<span class="pill live">생중계 중</span>' : ""}${r.viewer_count ? `<span class="pill">${r.viewer_count}명 함께 참배 중</span>` : ""}</div>
      <h3 class="ritual-title">${esc(r.title)}</h3>
      ${r.note ? `<div class="muted">${esc(r.note)}</div>` : ""}
      ${r.my_participation ? `<div class="muted">우리 가족: ${esc(r.my_participation.deceased_name)} 님 · 상주 ${esc(r.my_participation.mourner_name || "-")} · ${pStatus[r.my_participation.status] || r.my_participation.status}${r.my_participation.order_no ? ` · 순서 ${r.my_participation.order_no}번` : ""}</div>` : ""}
      ${r.participants.length ? `<div class="muted">봉행 순서: ${r.participants.map((x) => `${x.order_no || "-"}. ${esc(x.deceased_name)}${x.is_mine ? " (우리)" : ""}`).join(" · ")}</div>` : ""}
      <div class="row" style="margin-top:8px;flex-wrap:wrap">
        ${r.is_live_window && r.has_camera && r.can_watch ? `<button class="small" data-live="${r.id}">생중계 보기</button>` : ""}
        ${r.is_live_window && r.has_camera && !r.can_watch ? `<span class="muted">참여를 신청한 가족만 볼 수 있습니다</span>` : ""}
        ${r.access === "applied" && !r.my_participation && me.member.role !== "view" ? `<button class="small secondary" data-join="${r.id}">제례 참여 신청</button>` : ""}
        ${r.is_live_window && r.stream_url ? `<a class="btn small secondary" href="${esc(r.stream_url)}" target="_blank" rel="noopener">외부 중계 열기 (새 창)</a>` : ""}
        ${r.replay_url ? `<a class="btn small secondary" href="${esc(r.replay_url)}" target="_blank" rel="noopener">다시 보기 (새 창)</a>` : ""}
        <button class="small secondary" data-offer="${r.id}">공양·헌화 신청</button>
      </div>
    </div>`).join("") || `<p class="muted">아직 예정된 추도식이 없습니다. 시설에 일정을 문의해 주세요.</p>`;
  const past = rituals.filter((r) => r.is_past).slice(-5).reverse().map((r) => `<div class="ritual"><span class="muted">${esc(fmtDT(r.scheduled_at))}</span> ${esc(r.title)} ${r.replay_url ? `<a class="text-link" href="${esc(r.replay_url)}" target="_blank" rel="noopener">다시 보기</a>` : ""}</div>`).join("");
  const kindLabel = { offering: "공양", flower: "헌화", prayer: "기도" };
  const statusLabel = { requested: "접수 대기", accepted: "접수됨", done: "봉행 완료", cancelled: "취소" };
  const myOff = offerings.length ? offerings.map((o) => `<div class="list-item"><div><b>${kindLabel[o.kind]}</b> ${o.ritual_title ? `· ${esc(o.ritual_title)}` : ""}<div class="muted meta">${esc(fmtDT(o.created_at))}${o.amount ? ` · ${o.amount.toLocaleString()}원` : ""}</div></div><span class="pill">${statusLabel[o.status] || o.status}</span></div>`).join("") : `<p class="muted">아직 신청한 공양·헌화가 없습니다. 아래에서 신청하실 수 있습니다.</p>`;
  view.innerHTML = `
    <div class="page-heading"><span class="eyebrow">원격 추도식</span><h1>추도식 일정과 생중계</h1><p class="muted">법회·추모식은 누구나, 제례는 참여를 신청한 가족만 생중계를 봅니다. 생중계는 봉행 30분 전부터 열리고, 화면에서 현장에 한마디를 남기거나 합장·헌화 마음을 보낼 수 있습니다.</p></div>
    <div class="card"><h2>다가오는 일정</h2>${items}</div>
    ${past ? `<div class="card"><h3>지난 일정</h3>${past}</div>` : ""}
    <div class="card"><h3>내 공양·헌화 신청</h3>${myOff}<button class="secondary" style="margin-top:10px" id="offerAny">공양·헌화·기도 신청하기</button></div>`;
  view.querySelectorAll("[data-live]").forEach((b) => b.onclick = () => openRitualLive(rituals.find((r) => r.id === +b.dataset.live)));
  view.querySelectorAll("[data-join]").forEach((b) => b.onclick = () => {
    const r = rituals.find((x) => x.id === +b.dataset.join);
    const m = modal(`<h2>${esc(r.title)} 참여 신청</h2><p class="muted">신청한 가족만 생중계를 볼 수 있고, 봉행 순서에 우리 가족 고인의 이름이 올라갑니다. 순서는 시설에서 정해 알려 드립니다.</p>
      <div class="field"><label for="jDec">고인</label><select id="jDec">${me.deceased.map((d) => `<option value="${d.id}">${esc(d.name)} 님${d.honorific ? ` (${esc(d.honorific)})` : ""}</option>`).join("")}</select></div>
      <div class="field"><label for="jMourner">상주(대표 가족) 이름</label><input id="jMourner" value="${esc(me.contract.holder_name)}"></div>
      <div class="field"><label for="jNote">전할 말(선택)</label><input id="jNote" aria-describedby="jNoteHelp"><small class="muted" id="jNoteHelp">예: 가족 여섯 명이 함께 봅니다</small></div>
      <button id="jGo">참여 신청하기</button>`);
    $("#jGo", m).onclick = async () => {
      const b = $("#jGo", m); if (b.disabled) return; b.disabled = true; b.textContent = "신청하는 중입니다…";
      try { await api(`/api/family/rituals/${r.id}/join`, { method: "POST", body: { deceased_id: +$("#jDec", m).value, mourner_name: $("#jMourner", m).value, note: $("#jNote", m).value } }); m.remove(); toast("참여 신청을 저장했습니다. 시설에서 순서를 정해 알려 드립니다.", 4500); go("ritual"); }
      catch (e) { b.disabled = false; b.textContent = "참여 신청하기"; toast(`참여 신청을 저장하지 못했습니다. ${e.message}`, 5000); }
    };
  });
  const openOffer = (ritualId) => {
    const m = modal(`<h2>공양·헌화·기도 신청</h2><p class="muted">시설에서 접수한 뒤 봉행합니다. 결제는 시범 운영 때 연결됩니다(지금은 신청만 받습니다).</p>
      <div class="field"><label for="ofKind">종류</label><select id="ofKind"><option value="offering">공양</option><option value="flower">헌화</option><option value="prayer">기도</option></select></div>
      <div class="field"><label for="ofRitual">일정</label><select id="ofRitual"><option value="">특정 일정 없음</option>${rituals.filter((r) => !r.is_past).map((r) => `<option value="${r.id}" ${r.id == ritualId ? "selected" : ""}>${esc(fmtDT(r.scheduled_at))} ${esc(r.title)}</option>`).join("")}</select></div>
      <div class="field"><label for="ofAmount">금액(원)</label><input id="ofAmount" type="number" inputmode="numeric" value="30000" min="0" step="1000"></div>
      <div class="field"><label for="ofNote">전할 말(선택)</label><input id="ofNote" aria-describedby="ofNoteHelp"><small class="muted" id="ofNoteHelp">예: 어머니 기일에 흰 국화로 부탁드립니다</small></div>
      <button id="ofSend">신청하기</button>`);
    $("#ofSend", m).onclick = async () => {
      const b = $("#ofSend", m); if (b.disabled) return; b.disabled = true; b.textContent = "신청하는 중입니다…";
      try { await api("/api/family/offerings", { method: "POST", body: { kind: $("#ofKind", m).value, ritual_id: $("#ofRitual", m).value ? +$("#ofRitual", m).value : null, amount: +$("#ofAmount", m).value || 0, note: $("#ofNote", m).value } }); m.remove(); toast("신청을 저장했습니다. 시설에서 확인한 뒤 연락드립니다.", 4000); go("ritual"); }
      catch (e) { b.disabled = false; b.textContent = "신청하기"; toast(`신청을 저장하지 못했습니다. ${e.message}`, 5000); }
    };
  };
  view.querySelectorAll("[data-offer]").forEach((b) => b.onclick = () => openOffer(+b.dataset.offer));
  $("#offerAny").onclick = () => openOffer(null);
}

// 틱톡 라이브처럼: 전체 화면 영상 + 지금 봉행 중인 고인 정보 + 가족 메시지가 아래에서 올라오고 + 합장·촛불·헌화 반응이 떠오른다.
const REACT_NAME = { "\u{1F64F}": "합장", "\u{1F56F}\uFE0F": "촛불", "\u{1F338}": "헌화", "\u{1F49B}": "마음" };
function openRitualLive(r) {
  clearTimers(); stopSpeech();
  const el = document.createElement("div"); el.className = "live-view";
  const src = () => withToken(`/api/family/rituals/${r.id}/stream`) + "&_=" + Date.now();
  el.innerHTML = `
    <img class="live-video" id="lvVideo" alt="">
    <div class="live-shade"></div>
    <div class="live-top"><span class="live-badge-red">생중계</span><span class="live-title">${esc(r.title)}</span><span class="live-viewers" id="lvViewers">1명 함께 참배 중</span><button class="live-close" id="lvClose" aria-label="생중계 닫기">닫기</button></div>
    <div class="live-now" id="lvNow"></div>
    <div class="live-fx" id="lvFx"></div>
    <div class="live-msgs" id="lvMsgs"></div>
    <div class="live-bar"><input id="lvInput" aria-label="현장에 남길 한마디" placeholder="현장에 한마디" maxlength="200" autocomplete="off"><button class="live-send" id="lvSend">보내기</button></div>
    <div class="live-react"><button class="live-orderbtn" id="lvOrder">봉행 순서</button>${["🙏", "🕯️", "🌸", "💛"].map((e) => `<button data-react="${e}" aria-label="${REACT_NAME[e] || "마음"} 보내기" title="${REACT_NAME[e] || "마음"}">${e}</button>`).join("")}</div>
    <div class="live-drawer hidden" id="lvDrawer"><div class="live-drawer-in"><h3>봉행 순서</h3><div id="lvOrderList"></div><button class="small ghost" id="lvDrawerClose" style="margin-top:10px">닫기</button></div></div>`;
  document.body.appendChild(el); document.body.classList.add("noscroll");
  const video = $("#lvVideo", el), msgs = $("#lvMsgs", el), fx = $("#lvFx", el);
  video.src = src();
  video.onerror = () => setTimeout(() => { if (el.isConnected) video.src = src(); }, 3000);
  let since = 0, rseq = -1, ended = false;
  const addMsg = (m) => { const d = document.createElement("div"); d.className = `live-msg ${m.sender === "site" ? "site" : ""} ${m.kind === "notice" ? "notice" : ""}`; d.innerHTML = `<b>${esc(m.author)}</b>${esc(m.message)}`; msgs.appendChild(d); while (msgs.children.length > 8) msgs.firstChild.remove(); };
  const float = (emoji) => { const i = document.createElement("i"); i.textContent = emoji; i.style.left = (10 + Math.random() * 70) + "%"; i.style.setProperty("--dx", (Math.random() * 60 - 30) + "px"); fx.appendChild(i); setTimeout(() => i.remove(), 2600); };
  async function poll() {
    if (!el.isConnected) return;
    let d; try { d = await api(`/api/family/rituals/${r.id}/live?since=${since}&rseq=${rseq}`); } catch (e) { return; }
    $("#lvViewers", el).textContent = `${d.viewer_count}명 함께 참배 중`;
    d.messages.forEach((m) => { since = Math.max(since, m.id); addMsg(m); });
    d.reactions.forEach((x) => { if (x.seq > rseq) { rseq = x.seq; float(x.emoji); } });
    if (d.rseq > rseq) rseq = d.rseq;
    const now = d.current;
    $("#lvNow", el).innerHTML = now
      ? `<div class="live-now-in"><span class="live-now-k">지금 ${d.current_order}/${d.order.length}</span><b>${esc(now.deceased_name)} 님</b><span>${esc(fmtD(now.birth_date))} ~ ${esc(fmtD(now.death_date))}</span><span>상주 ${esc(now.mourner_name || "-")}</span>${now.is_mine ? '<span class="live-mine">우리 가족 차례</span>' : ""}</div>`
      : (d.order.length ? `<div class="live-now-in"><span class="live-now-k">봉행 순서 ${d.order.length}가족</span><span>${d.current_order === 0 ? "곧 시작합니다" : "봉행을 마쳤습니다"}</span></div>` : "");
    $("#lvOrderList", el).innerHTML = d.order.map((x) => `<div class="live-order-row ${x.order_no === d.current_order ? "now" : ""} ${x.is_mine ? "mine" : ""}"><span class="no">${x.order_no || "-"}</span><div><b>${esc(x.deceased_name)} 님</b> <span class="muted">${esc(fmtD(x.birth_date))} ~ ${esc(fmtD(x.death_date))}</span><div class="muted meta">상주 ${esc(x.mourner_name || "-")}${x.is_mine ? " · 우리 가족" : ""}</div></div></div>`).join("") || '<p class="muted">아직 봉행 순서가 정해지지 않았습니다. 시설에서 정하면 이곳에 보입니다.</p>';
    if (!d.live && !ended) { ended = true; el.insertAdjacentHTML("beforeend", `<div class="live-ended" role="status">생중계를 마쳤습니다. 닫기를 누르면 일정 화면으로 돌아갑니다.</div>`); }
  }
  poll(); const t = setInterval(poll, 2000);
  const close = () => { clearInterval(t); video.src = ""; el.remove(); document.body.classList.remove("noscroll"); go("ritual"); };
  $("#lvClose", el).onclick = close;
  $("#lvOrder", el).onclick = () => $("#lvDrawer", el).classList.remove("hidden");
  $("#lvDrawerClose", el).onclick = () => $("#lvDrawer", el).classList.add("hidden");
  $("#lvDrawer", el).onclick = (e) => { if (e.target === $("#lvDrawer", el)) $("#lvDrawer", el).classList.add("hidden"); };
  const send = async () => { const txt = $("#lvInput", el).value.trim(); if (!txt) return; $("#lvSend", el).disabled = true; try { await api(`/api/family/rituals/${r.id}/messages`, { method: "POST", body: { message: txt } }); $("#lvInput", el).value = ""; poll(); } catch (e) { toast(`한마디를 보내지 못했습니다. ${e.message}`, 4000); } $("#lvSend", el).disabled = false; };
  $("#lvSend", el).onclick = send;
  $("#lvInput", el).addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
  el.querySelectorAll("[data-react]").forEach((b) => b.onclick = () => { float(b.dataset.react); api(`/api/family/rituals/${r.id}/reactions`, { method: "POST", body: { emoji: b.dataset.react } }).then((x) => { if (x?.seq) rseq = Math.max(rseq, x.seq); }).catch(() => {}); });
}

// ---------------- 5. 가족 초대·설정(작별 포함) ----------------
async function renderSettings() {
  const me = state.me; let members, history;
  try { [members, history] = await Promise.all([api("/api/family/members"), api("/api/family/chat/history")]); } catch (e) { failCard("설정을", e, "settings"); return; }
  const roleName = { view: "보기", chat: "보기·대화", manage: "관리" };
  const canManage = me.member.role === "manage";
  const cur = currentTheme();
  view.innerHTML = `
    <div class="page-heading settings-heading"><span class="eyebrow">설정</span><h1>마음에 맞게, 편안하게</h1><p class="muted">추모 공간의 모습과 가족, 알림을 정합니다.</p></div>
    <div class="card theme-settings"><h2>추모 공간 꾸미기</h2><p class="muted" style="margin-top:0">종교에 맞는 상징과 색을 고른 뒤 적용해 주세요. 바탕과 글꼴은 같고 상징과 강조색만 바뀝니다. ${canManage ? "가족 모두의 화면에 함께 적용됩니다." : "이 기기에서만 바뀝니다."}</p>
      <div class="theme-grid">${THEMES.map(([id, name, desc]) => `<button class="tile ${cur === id ? "active" : ""}" data-theme="${id}" aria-pressed="${cur === id}"><span class="theme-thumb" aria-hidden="true"></span><span class="sw" aria-hidden="true"></span><span>${name}<small>${desc}</small></span></button>`).join("")}</div>
      <div class="theme-preview" id="themePreview" data-preview-theme="${cur}" aria-label="테마 미리보기"><span class="preview-symbol" aria-hidden="true"></span><span class="serif">소중한 기억이 머무는 곳</span><small id="themePreviewName">${THEMES.find(t => t[0] === cur)?.[1] || "전통"} 테마 미리보기</small><span class="preview-fonts" id="themePreviewFonts">${THEME_FONTS[cur] || THEME_FONTS.classic}</span></div>
      <p class="muted" id="themeStatus" role="status">현재 ${THEMES.find(t => t[0] === cur)?.[1] || "전통"} 테마가 적용되어 있습니다.</p>
      <button id="applyThemeBtn" disabled>적용 중인 테마</button>
      <div class="row between motion-row" style="margin-top:12px"><span class="muted">화면 움직임(첫 화면 그림·전환 연출)</span><button class="small ${motionReduced() ? "ghost" : "secondary"}" id="motionBtn" ${window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 'disabled aria-label="기기 설정에 따라 움직임을 줄였습니다"' : ""}>${window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "기기 설정으로 줄였습니다" : motionReduced() ? "움직임 줄임 · 누르면 켭니다" : "움직임 켬 · 누르면 줄입니다"}</button></div></div>
    <div class="card"><h2>가족</h2>
      ${members.map((m) => `<div class="list-item"><div><b>${esc(m.name)}</b> <span class="muted">${esc(m.relation)}</span>${m.is_minor ? '<span class="pill">미성년</span>' : ""}</div><span class="pill">${roleName[m.role]}</span></div>`).join("")}
      ${canManage ? `<button class="secondary" style="margin-top:12px" id="inviteBtn">가족 초대 링크 만들기</button>` : `<p class="muted" style="margin-top:8px">가족 초대는 계약자(${esc(me.contract.holder_name)} 님)가 할 수 있습니다. 초대가 필요하면 계약자에게 요청해 주세요.</p>`}
    </div>
    <details class="card history-card"><summary>지난 대화 요약 <small>${history.length}건</small></summary>${history.length ? history.map((h) => `<div class="guest"><span class="who">${esc(h.deceased_name)} 님</span><span class="when">${esc(fmtDT(h.started_at))} · ${h.turns}회</span><div class="muted">${esc(h.summary || "(요약 없음)")}</div></div>`).join("") : `<p class="muted">아직 대화 기록이 없습니다. 대화 원문은 저장하지 않고 요약만 남깁니다. 대화는 아래 메뉴의 대화에서 시작합니다.</p>`}</details>
    <div class="card" id="voiceCard"><h3>목소리 등록</h3><div id="voiceBody"><p class="muted" role="status">목소리 등록 상태를 불러오는 중입니다…</p></div></div>
    <div class="card" id="faceCard"><h3>얼굴 등록 <span class="muted">(실시간 아바타)</span></h3><div id="faceBody"><p class="muted" role="status">얼굴 등록 상태를 불러오는 중입니다…</p></div></div>
    ${canManage && me.deceased.some((d) => d.ai_enabled) ? `<div class="card"><h3>대화 기능 작별</h3><p class="muted">대화 기능은 가족이 원하면 언제든 닫을 수 있습니다. 닫을 때 등록한 기억 카드와 음성 자료를 돌려받거나 삭제합니다.</p><button class="secondary" id="farewellBtn">작별 절차 살펴보기</button></div>` : ""}
    <div class="card"><h3>내 정보</h3><p>${esc(me.member.name)} · ${esc(me.member.relation)} · ${roleName[me.member.role]}</p><p class="muted">계약자 ${esc(me.contract.holder_name)} · 봉안함 ${esc(me.niche?.code || "-")} · ${me.contract.plan === "premium" ? "프리미엄" : "기본"}</p>
      <button class="secondary small" id="logout">이 기기에서 나가기</button></div>`;
  $("#motionBtn").onclick = () => { localStorage.setItem("motion", motionReduced() ? "" : "reduce"); applyMotion(); go("settings"); };
  let selectedTheme = cur, savedTheme = cur, savingTheme = false;
  const themeTiles = [...view.querySelectorAll(".tile")];
  const applyButton = $("#applyThemeBtn"), themeStatus = $("#themeStatus"), preview = $("#themePreview");
  const themeName = (id) => THEMES.find(t => t[0] === id)?.[1] || "전통";
  themeTiles.forEach((tile) => tile.onclick = () => {
    if (savingTheme) return;
    selectedTheme = tile.dataset.theme;
    themeTiles.forEach((item) => {
      item.classList.toggle("active", item === tile);
      item.setAttribute("aria-pressed", String(item === tile));
    });
    preview.dataset.previewTheme = selectedTheme;
    $("#themePreviewFonts").textContent = THEME_FONTS[selectedTheme];
    $("#themePreviewName").textContent = `${themeName(selectedTheme)} 테마 미리보기`;
    applyButton.disabled = selectedTheme === savedTheme;
    applyButton.textContent = selectedTheme === savedTheme ? "적용 중인 테마" : `${themeName(selectedTheme)} 테마 적용하기`;
    themeStatus.textContent = selectedTheme === savedTheme ? `현재 ${themeName(savedTheme)} 테마가 적용되어 있습니다.` : "미리보기입니다. 적용하기를 누르면 저장됩니다.";
  });
  applyButton.onclick = async () => {
    if (savingTheme || selectedTheme === savedTheme) return;
    savingTheme = true; applyButton.disabled = true;
    themeTiles.forEach(tile => tile.disabled = true);
    applyButton.textContent = "적용하는 중…";
    try {
      if (canManage) {
        if (!me.deceased[0]) throw new Error("고인 등록 후 테마를 적용할 수 있습니다.");
        await api("/api/family/theme", { method: "POST", body: { deceased_id: me.deceased[0].id, theme: selectedTheme } });
        me.deceased[0].theme = selectedTheme;
        localStorage.removeItem("theme_local");
      } else { localStorage.setItem("theme_local", selectedTheme); }
      savedTheme = selectedTheme; applyTheme(savedTheme);
      themeStatus.textContent = `${themeName(savedTheme)} 테마를 ${canManage ? "가족의 추모 공간에" : "이 기기에"} 적용했습니다.`;
      applyButton.textContent = "적용 완료";
      toast(themeStatus.textContent);
    } catch (e) {
      themeStatus.textContent = `테마를 적용하지 못했습니다. ${e.message}`;
      applyButton.disabled = false; applyButton.textContent = "다시 적용하기";
    } finally {
      savingTheme = false; themeTiles.forEach(tile => tile.disabled = false);
    }
  };
  $("#logout").onclick = () => {
    const m = modal(`<h2>이 기기에서 나갈까요?</h2><p>나가면 이 기기에서는 초대 링크를 다시 눌러야 들어올 수 있습니다. 가족 기록은 지워지지 않습니다.</p><div class="modal-actions"><button class="secondary" type="button" data-cancel>머무르기</button><button type="button" data-ok>나가기</button></div>`);
    $("[data-cancel]", m).onclick = () => m.querySelector(".modal-close").click();
    $("[data-ok]", m).onclick = () => { localStorage.removeItem("family_token"); location.href = "/"; };
  };
  renderVoiceCard(); renderFaceCard();
  $("#inviteBtn") && ($("#inviteBtn").onclick = () => {
    const m = modal(`<h2>가족 초대</h2><p class="muted">만든 링크를 카카오톡으로 보내 주세요. 링크를 누르면 바로 열립니다.</p>
      <div class="field"><label for="ivName">이름</label><input id="ivName"></div>
      <div class="field"><label for="ivRel">관계</label><input id="ivRel" aria-describedby="ivRelHelp"><small class="muted" id="ivRelHelp">예: 둘째 아들</small></div>
      <div class="field"><label for="ivRole">권한</label><select id="ivRole"><option value="view">보기만</option><option value="chat">보기·대화</option></select></div>
      <div class="field"><label for="ivDays">링크 유효기간 (일)</label><input id="ivDays" type="number" min="1" max="365" value="30"></div>
      <div class="check"><input type="checkbox" id="ivMinor"><label for="ivMinor" style="margin:0;color:var(--ink)">미성년자 (보호자 동반 필요)</label></div>
      <button id="ivGo">초대 링크 만들기</button><div id="ivOut" style="margin-top:12px"></div>`);
    $("#ivGo", m).onclick = async () => {
      $("#ivGo", m).disabled = true;
      try {
        const r = await api("/api/family/invite", { method: "POST", body: { name: $("#ivName", m).value, relation: $("#ivRel", m).value, role: $("#ivRole", m).value, is_minor: $("#ivMinor", m).checked, days:+$("#ivDays",m).value } });
        $("#ivOut", m).innerHTML = `<p class="muted" role="status">초대 링크를 만들었습니다. ${esc(fmtD(r.expires_at))}까지 들어올 수 있습니다.</p><div class="link-box">${esc(r.link)}</div><button class="small" style="margin-top:8px" id="ivCopy">링크 복사</button>`;
        $("#ivCopy", m).onclick = () => { navigator.clipboard?.writeText(r.link); toast("복사했습니다. 카카오톡에 붙여 넣어 보내세요."); };
      } catch (e) { toast(`초대 링크를 만들지 못했습니다. ${e.message}`, 5000); $("#ivGo", m).disabled = false; }
    };
  });
  $("#farewellBtn") && ($("#farewellBtn").onclick = () => {
    const d = me.deceased.find((x) => x.ai_enabled);
    const m = modal(`<h2>${esc(d.name)} 님과 작별</h2><p>대화 기능을 닫으면 되돌릴 수 없습니다. 다시 열려면 시설에서 처음부터 새로 등록해야 합니다.</p>
      <div class="field"><label for="fwWords">마지막 인사(방명록에 남습니다)</label><textarea id="fwWords" aria-describedby="fwHelp"></textarea><small class="muted" id="fwHelp">예: 고마웠어요. 이제 마음속에서 뵐게요.</small></div>
      <div class="field"><label for="fwAct">등록 자료 처리</label><select id="fwAct"><option value="return">돌려받기(화면에 표시)</option><option value="delete">삭제</option></select></div>
      <button class="danger" id="fwGo">작별하고 대화 기능 닫기</button>`);
    $("#fwGo", m).onclick = async () => {
      if (!confirm("대화 기능을 닫으면 되돌릴 수 없습니다. 닫을까요?")) return;
      try {
        const r = await api("/api/family/farewell", { method: "POST", body: { deceased_id: d.id, action: $("#fwAct", m).value, last_words: $("#fwWords", m).value } });
        m.remove(); state.me = await api("/api/family/me");
        if (r.exported) modal(`<h2>돌려받은 자료</h2><p class="muted">아래 내용을 따로 보관해 주세요. 시설 서버에서는 지웠습니다.</p><pre style="white-space:pre-wrap;font-size:14px">${esc(r.exported.memory_card || "(기억 카드 없음)")}</pre>`);
        else toast("작별 절차를 마쳤습니다. 대화 기능을 닫았습니다.");
        go("settings");
      } catch (e) { toast(`작별 절차를 마치지 못했습니다. ${e.message}`, 5000); }
    };
  });
}

// ---------------- 목소리 등록 (앱에서 직접 녹음 · 생전 기록) ----------------
const VOICE_SCRIPT = `<b>1분 정도, 평소 말투로 편하게</b> 이야기해 주세요. 조용한 곳에서, 휴대폰을 입에서 한 뼘쯤 떨어뜨리고요.<br>
예를 들면 — 가족 이름을 부르며 안부 묻기 · 요즘 지내는 이야기 · 좋아하는 음식이나 장소 · 가족에게 꼭 하고 싶은 말 · 자주 하시던 말씀<br>
<small>또박또박 읽는 말투보다 <b>평소 대화하듯 웃고 쉬어 가며</b> 말할수록 인공지능 목소리가 자연스러워집니다. 3분 가까이 길게 남기면 더 좋습니다.</small>`;

async function renderVoiceCard() {
  const box = $("#voiceBody"); if (!box) return;
  let v; try { v = await api("/api/family/voice"); } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  if (!v.provider_ready) { box.innerHTML = `<p class="muted">시설에서 아직 목소리 등록 기능을 켜지 않았습니다. 필요하면 시설 담당자에게 문의해 주세요.</p>`; return; }
  const rows = v.deceased.map((d) => `
    <div class="list-item" style="align-items:flex-start;flex-direction:column;gap:6px">
      <div class="row between" style="width:100%"><div><b>${esc(d.name)} 님</b> <span class="muted">${esc(d.honorific)}</span></div>
        ${d.has_voice ? '<span class="pill ok">목소리 등록됨</span>' : '<span class="pill">미등록</span>'}</div>
      <div class="muted">${d.has_voice ? `이 목소리로 대화가 재생됩니다.` : `자료 ${d.samples}개`}${d.consent ? ` · 동의: ${esc(d.consent.signer_name)} (${d.consent.kind === "lifetime_record" ? "생전 기록" : "음성 사용"})` : ""}</div>
      <div class="row" style="flex-wrap:wrap">
        ${d.has_voice ? `<button class="small secondary" data-vprev="${d.id}">미리 듣기</button>` : ""}
        ${v.can_manage ? `<button class="small ${d.has_voice ? "ghost" : ""}" data-vrec="${d.id}">${d.has_voice ? "다시 등록" : "목소리 등록"}</button>` : ""}
        ${v.can_manage && d.has_voice ? `<button class="small ghost" data-vdel="${d.id}">삭제</button>` : ""}
      </div>
      <audio data-vaudio="${d.id}" controls style="display:none;width:100%"></audio>
    </div>`).join("");
  box.innerHTML = `<p class="muted">살아 계실 때 직접 남기는 <b>생전 기록</b>이 가장 좋습니다. 고인의 음성 자료(휴대폰 영상·음성 메시지)도 가족 동의로 올릴 수 있습니다. 목소리는 대화에만 쓰이고, 작별하면 함께 지워집니다.</p>${rows}
    ${!v.can_manage ? '<p class="muted">등록은 계약자만 할 수 있습니다. 필요하면 계약자에게 요청해 주세요.</p>' : ""}`;
  box.querySelectorAll("[data-vprev]").forEach((b) => b.onclick = async () => {
    b.disabled = true; b.textContent = "미리 듣기를 만드는 중입니다…";
    try { const r = await fetch(withToken("/api/family/voice/preview"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ deceased_id: +b.dataset.vprev }) });
      if (!r.ok) throw new Error((await r.json()).detail); const a = box.querySelector(`[data-vaudio="${b.dataset.vprev}"]`); a.src = URL.createObjectURL(await r.blob()); a.style.display = "block"; a.play(); }
    catch (e) { toast(e.message, 4000); }
    b.disabled = false; b.textContent = "미리 듣기";
  });
  box.querySelectorAll("[data-vdel]").forEach((b) => b.onclick = async () => { if (confirm("등록된 목소리를 삭제하면 되돌릴 수 없습니다. 대화는 기본 음성으로 돌아갑니다. 삭제할까요?")) { await api(`/api/family/voice/${b.dataset.vdel}`, { method: "DELETE" }); renderVoiceCard(); } });
  box.querySelectorAll("[data-vrec]").forEach((b) => b.onclick = () => openRecorder(v.deceased.find((d) => d.id === +b.dataset.vrec), v.min_seconds));
}

function openRecorder(d, minSeconds) {
  const canRecord = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  const m = modal(`<h2>${esc(d.name)} 님 목소리 등록</h2>
    <div class="seg" style="margin-bottom:12px"><button class="active" data-kind="lifetime_record">본인이 직접 녹음<br><small>생전 기록</small></button><button data-kind="voice">고인의 음성 자료<br><small>가족 동의</small></button></div>
    <div class="script" id="script">${VOICE_SCRIPT}</div>
    <div id="recArea" style="margin-top:12px">
      ${canRecord ? `<div class="rec-time" id="recTime">0:00</div><button class="rec-btn" id="recBtn" type="button">녹음</button><p class="muted center" id="recHint" role="status">녹음 단추를 누르면 시작합니다</p>`
                  : `<div class="notice">이 브라우저에서는 마이크로 녹음할 수 없습니다(보안 연결 주소나 노트북에서 열면 됩니다). 아래에서 파일을 올려 주세요.</div>`}
      <audio id="recPlay" controls style="display:none;width:100%;margin-top:8px"></audio>
      <label class="btn secondary" style="margin-top:10px;cursor:pointer">파일로 올리기 (mp3·m4a·wav·영상)<input type="file" id="recFile" accept="audio/*,video/*" hidden></label>
    </div>
    <div class="check" style="margin-top:12px"><input type="checkbox" id="vAgree"><label for="vAgree" style="margin:0;color:var(--ink)" id="vAgreeText">이 목소리가 인공지능 대화에만 쓰이는 것에 본인으로서 동의합니다. 언제든 삭제할 수 있습니다.</label></div>
    <div class="field"><label for="vNote">메모(선택)</label><input id="vNote" aria-describedby="vNoteHelp"><small class="muted" id="vNoteHelp">예: 2026년 추석에 녹음</small></div>
    <button id="vGo" disabled>이 목소리로 등록</button><p class="muted center" id="vOut" role="status" style="margin-top:8px"></p>`);
  let kind = "lifetime_record", blob = null, filename = "recording.webm", rec = null, stream = null, t0 = 0, timer = null;
  const out = (msg) => { $("#vOut", m).textContent = msg; };
  const ready = () => { $("#vGo", m).disabled = !(blob && $("#vAgree", m).checked); };
  m.querySelectorAll("[data-kind]").forEach((b) => b.onclick = () => { m.querySelectorAll("[data-kind]").forEach((x) => x.classList.remove("active")); b.classList.add("active"); kind = b.dataset.kind;
    $("#vAgreeText", m).textContent = kind === "lifetime_record" ? "이 목소리가 인공지능 대화에만 쓰이는 것에 본인으로서 동의합니다. 언제든 삭제할 수 있습니다." : "가족 대표로서 고인의 음성을 인공지능 대화에만 쓰는 것에 동의합니다. 다른 가족이 반대하면 즉시 삭제하겠습니다.";
    $("#script", m).innerHTML = kind === "lifetime_record" ? VOICE_SCRIPT : "휴대폰 영상, 음성 메시지, 통화 녹음 등 <b>고인의 목소리가 또렷하게 1분 이상</b> 담긴 파일을 올려 주세요. 여러 사람이 함께 말하는 파일은 품질이 떨어집니다."; });
  $("#vAgree", m).onchange = ready;
  const setBlob = (b, name) => { blob = b; filename = name; const a = $("#recPlay", m); a.src = URL.createObjectURL(b); a.style.display = "block"; ready(); };
  $("#recFile", m).onchange = (e) => { const f = e.target.files[0]; if (f) { setBlob(f, f.name); out(`${f.name} (${(f.size / 1024 / 1024).toFixed(1)}MB)`); } };
  if (canRecord) {
    const btn = $("#recBtn", m), time = $("#recTime", m), hint = $("#recHint", m);
    btn.onclick = async () => {
      if (rec && rec.state === "recording") { rec.stop(); return; }
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
      catch { return toast("마이크 사용 허락이 필요합니다. 주소창 옆 마이크 표시를 눌러 허락해 주세요.", 5000); }
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
      const chunks = []; rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      rec.onstop = () => { stream.getTracks().forEach((t) => t.stop()); clearInterval(timer); btn.classList.remove("on"); btn.textContent = "녹음";
        const secs = (Date.now() - t0) / 1000; const b = new Blob(chunks, { type: rec.mimeType || mime });
        const ext = (rec.mimeType || mime).includes("mp4") ? "m4a" : (rec.mimeType || mime).includes("ogg") ? "ogg" : "webm";
        setBlob(b, `recording.${ext}`); hint.textContent = secs < minSeconds ? `${Math.round(secs)}초 — 너무 짧습니다. ${minSeconds}초 이상 다시 녹음해 주세요.` : `${Math.round(secs)}초를 녹음했습니다. 들어 보고 마음에 들면 아래 '이 목소리로 등록'을 눌러 주세요.`; if (secs < minSeconds) { blob = null; ready(); } };
      rec.start(250); t0 = Date.now(); btn.classList.add("on"); btn.textContent = "마치기"; hint.textContent = "녹음하는 중입니다. 다 말씀하셨으면 마치기를 눌러 주세요.";
      timer = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); time.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; time.classList.toggle("short", s < minSeconds); if (s >= 180) rec.stop(); }, 250);
    };
  }
  $("#vGo", m).onclick = async () => {
    if (!blob) return; $("#vGo", m).disabled = true; out("목소리를 올리는 중입니다. 만드는 데 1분쯤 걸립니다…");
    const fd = new FormData(); fd.append("deceased_id", d.id); fd.append("kind", kind); fd.append("agree", "true"); fd.append("note", $("#vNote", m).value); fd.append("file", blob, filename);
    try { const r = await api("/api/family/voice/register", { method: "POST", body: fd }); m.remove(); toast(`목소리를 등록했습니다${r.seconds ? ` (${Math.round(r.seconds)}초)` : ""}. 대화에서 바로 쓰입니다.`, 4000); renderVoiceCard(); state.me = await api("/api/family/me"); }
    catch (e) { out("목소리를 등록하지 못했습니다. " + e.message); $("#vGo", m).disabled = false; }
  };
}

// ---------------- 얼굴 등록 (실시간 아바타) ----------------
async function renderFaceCard() {
  const box = $("#faceBody"); if (!box) return;
  let v; try { v = await api("/api/family/avatar"); } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  if (!v.provider_ready) { box.innerHTML = `<p class="muted">시설에서 아직 실시간 아바타 기능을 켜지 않았습니다. 지금은 사진 아바타로 대화합니다.</p>`; return; }
  const isDid = v.provider === "did";
  box.innerHTML = `<p class="muted">말할 때 입이 움직이는 아바타입니다. <b>목소리 등록이 먼저</b> 되어 있어야 대화에서 쓰입니다. 화면에는 항상 '인공지능 실시간 영상' 표시가 붙습니다.<br>
    ${isDid ? "<b>D-ID</b>: 올린 정면 사진 <b>그대로</b>를 움직이므로 얼굴이 실제와 같습니다." : "<b>Simli</b>: 기본 얼굴은 무료 플랜에서 바로 되고, 사진으로 만든 얼굴은 유료 플랜이 필요합니다."}</p>` +
    v.deceased.map((d) => `<div class="list-item" style="align-items:flex-start;flex-direction:column;gap:6px">
      <div class="row between" style="width:100%"><div><b>${esc(d.name)} 님</b> <span class="muted">${esc(d.honorific)}</span></div>
        ${d.has_face ? `<span class="pill ok">${esc(d.face_label || "얼굴 등록됨")}</span>` : '<span class="pill">미등록</span>'}</div>
      <div class="muted">사진 ${d.has_photo ? "있음" : "없음"} · 목소리 ${d.has_voice ? "있음" : "없음"}${d.consent ? ` · 동의: ${esc(d.consent.signer_name)}` : ""}</div>
      ${v.can_manage && v.presets.length ? `<div class="row" style="width:100%"><select data-fpreset="${d.id}" style="flex:1"><option value="">기본 얼굴 고르기…</option>${v.presets.map((pf) => `<option value="${pf.id}">${esc(pf.label)}</option>`).join("")}</select><button class="small secondary" data-fpresetgo="${d.id}" style="min-height:44px">기본 얼굴로 시연</button></div>` : ""}
      <div class="row" style="flex-wrap:wrap">
        ${v.can_manage ? `<label class="btn small secondary" style="width:auto;cursor:pointer">정면 사진 올리기<input type="file" accept="image/*" data-fphoto="${d.id}" hidden></label>` : ""}
        ${v.can_manage && d.has_photo ? `<button class="small" data-freg="${d.id}">${d.has_face ? "사진으로 다시 만들기" : "사진으로 얼굴 만들기"}${isDid ? "" : " (유료)"}</button>` : ""}
        ${v.can_manage && d.has_face ? `<button class="small ghost" data-fdel="${d.id}">삭제</button>` : ""}
      </div><div class="muted" data-fout="${d.id}" role="status"></div></div>`).join("");
  box.querySelectorAll("[data-fpresetgo]").forEach((b) => b.onclick = async () => {
    const id = b.dataset.fpresetgo; const sel = box.querySelector(`[data-fpreset="${id}"]`); if (!sel.value) return toast("기본 얼굴을 먼저 골라 주세요.");
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
      <div class="check"><input type="checkbox" id="fAgree"><label for="fAgree" style="margin:0;color:var(--ink)">이 사진을 인공지능 대화의 얼굴로만 쓰는 것에 동의합니다. 다른 가족이 반대하면 즉시 삭제하겠습니다.</label></div>
      <button id="fGo" disabled>얼굴 만들기</button><p class="muted center" id="fOut" role="status" style="margin-top:8px"></p>`);
    let kind = "likeness";
    m.querySelectorAll("[data-kind]").forEach((k) => k.onclick = () => { m.querySelectorAll("[data-kind]").forEach((x) => x.classList.remove("active")); k.classList.add("active"); kind = k.dataset.kind; });
    $("#fAgree", m).onchange = () => { $("#fGo", m).disabled = !$("#fAgree", m).checked; };
    $("#fGo", m).onclick = async () => {
      $("#fGo", m).disabled = true; $("#fOut", m).textContent = "얼굴을 만드는 중입니다. 1~3분 걸릴 수 있습니다…";
      try { await api("/api/family/avatar/register", { method: "POST", body: { deceased_id: d.id, agree: true, kind } }); m.remove(); toast("얼굴을 등록했습니다. 다음 대화부터 실시간 아바타가 나옵니다.", 4000); renderFaceCard(); state.me = await api("/api/family/me"); }
      catch (e) { $("#fOut", m).textContent = "얼굴을 만들지 못했습니다. " + e.message; $("#fGo", m).disabled = false; }
    };
  });
  box.querySelectorAll("[data-fdel]").forEach((b) => b.onclick = async () => {
    if (b.dataset.armed !== "1") { b.dataset.armed = "1"; b.textContent = "삭제하면 되돌릴 수 없습니다 · 한 번 더 누르면 삭제"; setTimeout(() => { b.dataset.armed = ""; b.textContent = "삭제"; }, 5000); return; }
    await api(`/api/family/avatar/${b.dataset.fdel}`, { method: "DELETE" }); renderFaceCard();
  });
}

if ("speechSynthesis" in window) window.speechSynthesis.onvoiceschanged = () => {};
const community = createCommunity({api, $, esc, modal, toast, withToken, state, go, view, every});
boot();
