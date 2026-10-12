// 유족 웹앱. 초대 링크(/?t=토큰)로 열리며 설치가 필요 없다.
import {createCommunity} from './community.js?v=20261012-serene';
import {mountArt, destroyAll as destroyArt, mountScene, mountVoice, playReaction} from './dream.js?v=20261012-3';
import {openVoiceRecorder} from './voice-recorder.js?v=20261012-1';
import {createKeepsake} from './keepsake.js?v=20261012-1';
import {createShop} from './shop.js?v=20261012-1';
const qs = new URLSearchParams(location.search);
// 초대 토큰은 영문·숫자·-·_ 로만 이뤄진다. 메신저에서 복사하며 붙은 한글·공백·따옴표, 링크 전체를 붙여 넣은 경우,
// '<초대 토큰>' 같은 자리표시를 걸러 낸다. 그대로 요청 머리글에 넣으면 브라우저가 요청을 거부하고(ISO-8859-1 오류),
// 저장된 값 때문에 '다시 열기'도 계속 실패하기 때문이다.
function cleanToken(v) {
  if (!v) return "";
  let s = String(v).trim();
  const at = s.lastIndexOf("t=");
  if (at >= 0) s = s.slice(at + 2);
  const m = s.match(/^[A-Za-z0-9_-]+/);
  return m && m[0].length >= 8 && m[0].length <= 128 ? m[0] : "";
}
const rawLinkToken = qs.get("t");
const linkToken = cleanToken(rawLinkToken);
const BAD_LINK = rawLinkToken !== null && !linkToken;          // 주소에 t= 는 있는데 쓸 수 있는 토큰이 아님
const storedToken = localStorage.getItem("family_token");
if (storedToken && !cleanToken(storedToken)) localStorage.removeItem("family_token");   // 예전에 저장된 망가진 값은 지운다
const TOKEN = linkToken || (BAD_LINK ? "" : cleanToken(storedToken));
if (rawLinkToken !== null) { if (linkToken) localStorage.setItem("family_token", linkToken); history.replaceState(null, "", location.pathname + location.hash); }   // 토큰만 지우고 #탭 지정은 남긴다

// /demo: 홈페이지·플랫폼의 'MVP 바로가기'가 여는 시연 시작 화면. 가족 링크가 저장돼 있어도 시작 화면부터 보여 준다.
const DEMO_ENTRY = location.pathname === "/demo" && !linkToken;
const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDT = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : `${d.getMonth() + 1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const fmtD = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`; };
const ago = (iso) => { if (!iso) return "아직 없음"; const s = Math.max(0, (Date.now() - new Date(iso)) / 1000); return s < 60 ? `${Math.round(s)}초 전` : s < 3600 ? `${Math.round(s / 60)}분 전` : `${Math.round(s / 3600)}시간 전`; };

async function api(path, opts = {}) {
  const headers = { "X-Family-Token": TOKEN || "", ...(opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}) };
  let r;
  try { r = await fetch(path, { ...opts, headers, body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body }); }
  catch { throw new Error("서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주세요."); }
  if (!r.ok) { let msg = r.statusText; try { msg = (await r.json()).detail || msg; } catch {} throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg)); }
  if (r.status === 204) return null;
  return r.json();
}
// 토큰은 보안 쿠키(서버가 /api/family/session 에서 발급)로 다니므로 주소에 싣지 않는다. 뒤에 "&_=" 를 붙이는 곳이 있어 "?" 만 맞춘다.
const withToken = (url) => (url.includes("?") ? url : url + "?");

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

const state = { me: null, tab: "visit", timers: [], focus: null };
const keepsake = createKeepsake({ api, esc, toast, modal, withToken, fmtDT });   // 추모 제단 · 생전 좋아하신 노래
const shop = createShop({ api, esc, toast, modal, withToken, fmtDT, fmtD, state, view, go });   // 추모 서비스(유료, 시연 결제)
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
const THEME_META = { classic: "#121410", buddhist: "#121410", catholic: "#121410", christian: "#121410" };
function applyTheme(t) {
  if (!THEME_META[t]) t = "classic";
  document.documentElement.dataset.theme = t;
  const meta = document.querySelector('meta[name="theme-color"]'); if (meta) meta.content = THEME_META[t];
  state.theme = t;
}
function currentTheme() { return (state.me?.member.role === "manage" ? null : localStorage.getItem("theme_local")) || state.me?.deceased?.[0]?.theme || "classic"; }
// ---------------- 테마 세부(2026-10-12): 강조색 · 배경 문양 · 바탕 빛 · 제목 글꼴 · 글자 크기 ----------------
// 강조색은 테마마다 네 가지. 문양·바탕·글꼴은 css/serene.css 가 html 의 data-* 로 바꾼다. 글자 크기는 이 기기에만 저장.
const ACCENTS = {
  classic: [["#4b5636", "먹 올리브"], ["#34506b", "쪽빛"], ["#55524b", "먹회색"], ["#7a3b2e", "대추빛"]],
  buddhist: [["#8f3b2b", "단청 주홍"], ["#94702c", "가사 금빛"], ["#9c4f5d", "연꽃 분홍"], ["#5b3a55", "먹자주"]],
  catholic: [["#3d4f6b", "청회색"], ["#3b6488", "성모 하늘빛"], ["#6c2e3a", "포도주빛"], ["#86692c", "제단 금빛"]],
  christian: [["#2f5a55", "짙은 청록"], ["#5a6a2e", "올리브"], ["#2e3f6e", "남색"], ["#7a5234", "나무 갈색"]],
};
const LOOK_OPTIONS = {
  pattern: [["off", "끄기", "바탕을 비워 둡니다"], ["soft", "은은하게", "흐릿하게 비칩니다"], ["clear", "조금 더 또렷하게", "문양이 잘 보입니다"]],
  tone: [["hanji", "한지", "따뜻한 미색"], ["dawn", "새벽 노을", "옅은 살구빛"], ["mist", "고요한 안개", "맑은 회녹빛"]],
  font: [["myeongjo", "명조", "단정한 붓글씨 느낌"], ["batang", "부드러운 바탕", "둥글고 다정한 획"], ["gothic", "또렷한 고딕", "가장 읽기 쉬움"]],
  size: [["normal", "보통", "기본 크기"], ["large", "크게", "한 단계 크게"], ["xlarge", "아주 크게", "두 단계 크게"]],
};
const PATTERN_NAME = { classic: "칠보 무늬", buddhist: "연꽃 · 구름", catholic: "장미창 · 백합", christian: "올리브 가지 · 빛" };
const STYLE_DEFAULT = { accent: "1", pattern: "soft", tone: "hanji", font: "myeongjo" };
function cleanStyle(x) {
  const o = { ...STYLE_DEFAULT };
  if (x && typeof x === "object") {
    if (["1", "2", "3", "4"].includes(x.accent)) o.accent = x.accent;
    for (const k of ["pattern", "tone", "font"]) if (LOOK_OPTIONS[k].some(([v]) => v === x[k])) o[k] = x[k];
  }
  return o;
}
function currentStyle() {
  let local = null;
  if (state.me?.member.role !== "manage") { try { local = JSON.parse(localStorage.getItem("style_local") || "null"); } catch {} }
  return cleanStyle(local || state.me?.deceased?.[0]?.theme_style);
}
function textSize() { const v = localStorage.getItem("text_size"); return ["normal", "large", "xlarge"].includes(v) ? v : "normal"; }
function applyLook(theme, style, size) {
  applyTheme(theme);
  const st = cleanStyle(style), root = document.documentElement;
  const [hex] = (ACCENTS[state.theme] || ACCENTS.classic)[+st.accent - 1];
  const n = parseInt(hex.slice(1), 16);
  root.style.setProperty("--accent", hex); root.style.setProperty("--gold-2", hex);
  root.style.setProperty("--glow", `${n >> 16}, ${(n >> 8) & 255}, ${n & 255}`);
  root.dataset.pattern = st.pattern; root.dataset.tone = st.tone; root.dataset.font = st.font; root.dataset.size = size || "normal";
}
function applySaved() { applyLook(state.me ? currentTheme() : (localStorage.getItem("theme_local") || "classic"), state.me ? currentStyle() : null, textSize()); }
// '화면 움직임 줄이기'(앱 설정)는 정지 장면, 기기의 움직임 줄이기는 느린 반복 + 멈춤 단추(js/dream.js).
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
  applySaved(); applyMotion();
  if (DEMO_ENTRY || !TOKEN) {
    $("#tabs").classList.add("hidden"); document.body.classList.add("is-entry");
    if (!BAD_LINK && await renderLauncher()) return;
    if (TOKEN) { location.replace("/"); return; }   // 시작 화면이 없는 서버(온라인)에서 /demo → 저장된 가족 링크로
    renderEntry(BAD_LINK);
    return;
  }
  try { state.me = await api("/api/family/me"); await api("/api/family/session", { method: "POST" }).catch(() => {}); }
  catch (e) {
    view.innerHTML = `<section class="memorial-hero entry-hero"><div class="memorial-hero-copy"><span class="eyebrow">가족 추모 공간</span><h1>추모 공간을<br>열지 못했습니다.</h1><p>${esc(e.message)}</p><p>초대 링크가 바뀌었을 수 있습니다. 계약하신 가족이나 시설 담당자에게 새 초대 링크를 요청해 주세요.</p><div class="row" style="gap:10px;flex-wrap:wrap"><button class="secondary" type="button" id="retryBoot">다시 열기</button><button class="secondary" type="button" id="forgetBoot">이 기기에 저장된 링크 지우기</button></div></div><div class="hero-art" id="heroArt"></div></section>`;
    $("#tabs").classList.add("hidden"); document.body.classList.add("is-entry"); $("#retryBoot").onclick = () => location.reload(); $("#forgetBoot").onclick = async () => { localStorage.removeItem("family_token"); await fetch("/api/family/session", { method: "DELETE" }).catch(() => {}); location.href = "/"; }; mountArt($("#heroArt"), state.theme, motionReduced()); return;
  }
  applySaved();
  $("#who").textContent = `${state.me.member.name} 님`;
  $("#who").dataset.initial = String(state.me.member.name || "").slice(-2);
  community.init();
  $("#tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) go(b.dataset.tab); });
  const want = location.hash.slice(1);   // /?t=…#ritual 처럼 탭을 지정해 열 수 있다
  const routes = ["visit", "memorial", "chat", "ritual", "settings", "shop", ...Object.keys(community.pages)];
  go(routes.includes(want) ? want : localStorage.getItem('memorial_easy')==='true'?'easy':'visit');
  window.addEventListener("popstate", () => { const t = location.hash.slice(1) || "visit"; if (t !== state.tab && routes.includes(t)) go(t, false); });
}
// 화면 이동은 방문 기록에 남겨 휴대폰 '뒤로 가기'로 앞 화면에 돌아오게 한다(주소의 #탭을 바꿔도 이동).
function go(tab, push = true) {
  const url = location.pathname + (tab === "visit" ? "" : "#" + tab);
  if (push && state.tab && state.tab !== tab) history.pushState(null, "", url); else history.replaceState(null, "", url);
  clearTimers(); stopSpeech(); destroyArt(); if (state.tab === "settings" && tab !== "settings") applySaved(); state.tab = tab;
  document.querySelectorAll("#tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
    if (b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  view.dataset.page = tab; document.body.dataset.page = tab;
  view.innerHTML = `<div class="card center"><p class="muted" role="status">화면을 불러오는 중입니다…</p></div>`;
  const render = ({ visit: renderVisit, memorial: renderMemorial, chat: renderChat, ritual: renderRitual, settings: renderSettings, shop: shop.page, ...community.pages })[tab];
  Promise.resolve(render()).then(() => {if(state.tab===tab)community.mount(tab);}).catch(e=>failCard("화면을", e, tab));
  window.scrollTo(0, 0);
}

// ---------------- 초대 링크 화면 (링크 없이 열었거나 링크가 망가졌을 때) ----------------
function renderEntry(bad) {
  view.innerHTML = `<section class="memorial-hero entry-hero"><div class="memorial-hero-copy"><span class="eyebrow">가족 추모 공간</span>
      <h1>${bad ? "초대 링크를<br>확인해 주세요." : "초대 링크로<br>들어와 주세요."}</h1>
      <p>${bad ? "주소의 초대 링크 부분이 올바르지 않습니다. 받은 링크를 앞뒤 글자 없이 그대로 눌러 주세요." : "계약하신 가족에게 받은 카카오톡 초대 링크를 누르면 바로 열립니다."}</p></div><div class="hero-art" id="heroArt"></div></section>
    <section class="card" aria-labelledby="linkTitle"><h2 id="linkTitle">받은 링크 붙여 넣기</h2>
      <p class="muted">카카오톡에서 받은 초대 링크를 통째로 붙여 넣어도 됩니다. 링크가 없으면 시설 담당자에게 초대를 요청해 주세요.</p>
      <form class="link-form" id="linkForm"><label class="sr-only" for="linkIn">초대 링크</label><input id="linkIn" autocomplete="off" inputmode="url" placeholder="예: https://…/?t=영문과숫자"><button type="submit">추모 공간 열기</button></form>
      <p class="muted" style="margin-top:14px">시설 직원이신가요? <a href="/admin">관리자 콘솔</a>에서 계약·가족을 관리하고 초대 링크를 복사할 수 있습니다.</p></section>`;
  $("#linkForm").onsubmit = (e) => {
    e.preventDefault();
    const t = cleanToken($("#linkIn").value);
    if (!t) { toast("초대 링크 모양이 아닙니다. 받은 링크를 그대로 붙여 넣어 주세요.", 4200); $("#linkIn").focus(); return; }
    location.href = "/?t=" + encodeURIComponent(t);
  };
  mountArt($("#heroArt"), state.theme, motionReduced());
}

// ---------------- 시연 시작 화면 (서버를 켠 컴퓨터에서 초대 링크 없이 열었거나 /demo) ----------------
async function renderLauncher() {
  let L;
  try { const r = await fetch("/api/launcher"); if (!r.ok) return false; L = await r.json(); } catch { return false; }
  const roleName = { view: "보기", chat: "보기·대화", manage: "계약자(관리)" };
  const pick = L.members.find((m) => m.role === "manage") || L.members[0];
  const admin = esc(L.admin_url);
  const staff = [
    ["overview", "현황 · 시연 카메라", "봉안실 카메라 상태, 시연 화면 켜고 끄기"],
    ["aisettings", "인공지능 연결 키 등록", "Claude · ElevenLabs · D-ID 키를 넣고 연결 테스트"],
    ["rituals", "의례 일정 · 생중계", "추도식 만들기, 지금 시작, 다음 차례로"],
    ["deceased", "고인 · 목소리 등록", "기억 카드, 동의서, 녹음·파일 올리기"],
  ];
  view.innerHTML = `<div class="launch">
    <section class="memorial-hero launch-intro" aria-labelledby="launchTitle"><div class="memorial-hero-copy"><span class="eyebrow">MVP 시연 · 가족 추모 공간</span>
      <h1 id="launchTitle">그리운 마음을,<br>가까이 전합니다.</h1>
      <p>${esc(L.facility || "봉안당")}의 원격 참배, 추도식 생중계, 인공지능 추모 대화를 직접 써 보세요. 시연 속 인물은 모두 가상입니다.</p>
      <div class="hero-cta">${pick ? `<a class="btn hero-primary" href="${esc(pick.url)}">${esc(pick.name)} 님으로 바로 체험 <span aria-hidden="true">→</span></a>` : ""}<a class="btn ghost-light" href="${admin}" target="_blank" rel="noopener">관리자 콘솔 열기 (새 창)</a></div></div>
      <div class="hero-art" id="heroArt"></div></section>
    ${TOKEN ? `<div class="card continue-bar"><span>이 기기에는 이전에 연 가족 화면이 저장돼 있습니다.</span><a class="btn small secondary" href="/">이어서 보기</a></div>` : ""}
    <div class="launch-grid">
      <section class="card" aria-labelledby="famTitle"><div class="launch-head"><span class="launch-no">01</span><div><h2 id="famTitle">가족으로 들어가기</h2><p class="muted">계정마다 권한이 달라 보이는 화면도 다릅니다.</p></div></div>
        ${L.members.length ? `<ul class="member-list">${L.members.map((m) => `<li><a class="member" href="${esc(m.url)}"><span class="avatar" aria-hidden="true">${esc(String(m.name || "").slice(-2))}</span>
          <span class="member-body"><b>${esc(m.name)}</b><span class="role-chip role-${esc(m.role)}">${roleName[m.role] || esc(m.role)}</span>
          <small>${esc(m.relation)} · ${esc(m.deceased_names || "고인 정보 등록 전")} · 봉안함 ${esc(m.niche_code || "-")} · ${m.plan === "premium" ? "프리미엄" : "기본"}</small></span><span class="go" aria-hidden="true">→</span></a></li>`).join("")}</ul>`
          : '<p class="muted">아직 시연 계정이 없습니다. 관리자 콘솔에서 계약·가족을 만들거나, 명령 창에서 python -m server.seed 를 실행해 주세요.</p>'}
      </section>
      <section class="card" aria-labelledby="staffTitle"><div class="launch-head"><span class="launch-no">02</span><div><h2 id="staffTitle">직원으로 운영하기</h2><p class="muted">관리자 콘솔은 새 창으로 열립니다.</p></div></div>
        <ul class="staff-links">${staff.map(([page, title, sub]) => `<li><a href="${admin}#${page}" target="_blank" rel="noopener"><span class="s-body"><b>${title}</b><small>${sub}</small></span><span class="go" aria-hidden="true">↗</span></a></li>`).join("")}</ul>
      </section>
    </div>
    <section class="card launch-steps" aria-labelledby="stepsTitle"><h2 id="stepsTitle">10분 시연 순서</h2><ol class="steps">
      <li><b>연결 키 등록</b><span>직원 콘솔 ‘인공지능 설정’에서 키를 넣고 연결 테스트. 키가 없어도 규칙 기반 대화로 시연됩니다.</span></li>
      <li><b>원격 참배</b><span>가족 화면 첫 장에서 봉안함 사진을 보고 ‘실시간으로 뵙기’.</span></li>
      <li><b>추도식 생중계</b><span>‘일정’에서 생중계를 열고 합장·헌화 반응과 메시지 보내기.</span></li>
      <li><b>인공지능 추모 대화</b><span>‘대화’에서 안내에 동의하고 이야기 나누기. 끝내면 요약만 남습니다.</span></li>
      <li><b>가족 기억</b><span>‘추모’에서 방명록을 쓰고, 가족 앨범에 기억 남기기.</span></li>
    </ol></section>
    <p class="launch-note">시연 표시 원칙: 인물·계약은 모두 가상입니다. 인공지능이 만든 답·목소리·사진에는 ‘인공지능’ 표시가 붙고, 현장 웹캠 대신 나오는 화면에는 ‘시연 화면’이 찍힙니다. 실제 결제·카카오톡 발송은 없습니다. 이 시작 화면은 서버를 켠 컴퓨터에서만 보이며, 가족에게는 초대 링크를 보내 주세요.</p>
  </div>`;
  mountArt($("#heroArt"), state.theme, motionReduced());
  return true;
}

// ---------------- 1. 원격 참배 ----------------
// 첫 화면 '바로 하기' 칸: [이동할 화면, 아이콘 선, 이름, 설명]
const HOME_QUICK = [
  ["memorial#altar", '<path d="M12 13.5V21"/><path d="M12 15.5c-2.5-.2-4.2-1.3-5-3 2.5-.3 4.2.6 5 3zM12 17.5c2.2-.4 3.6-1.5 4.2-3.2-2.2 0-3.6 1-4.2 3.2z"/><circle cx="12" cy="8" r="2"/><path d="M12 3.5a2.3 2.3 0 0 1 2.3 2.4 2.3 2.3 0 0 1 2.4 2.3A2.3 2.3 0 0 1 14.3 10.5 2.3 2.3 0 0 1 12 12.5a2.3 2.3 0 0 1-2.3-2 2.3 2.3 0 0 1-2.4-2.3 2.3 2.3 0 0 1 2.4-2.3A2.3 2.3 0 0 1 12 3.5z"/>', "헌화 · 스티커", "국화·촛불 올리기"],
  ["comfort", '<path d="M12 20s-7-4.4-7-9.5A3.8 3.8 0 0 1 12 8a3.8 3.8 0 0 1 7 2.5C19 15.6 12 20 12 20z"/>', "마음 남기기", "꽃 · 촛불 · 편지"],
  ["chat", '<path d="M4 5.5h16v10.5H9.5L5 19.5V16H4z"/><path d="M8 9.5h8M8 12.5h5"/>', "추모 대화", "인공지능과 기억 나누기"],
  ["ritual", '<rect x="3.5" y="6" width="17" height="12" rx="2"/><path d="m10.5 9.5 4 2.5-4 2.5z"/>', "추도식 생중계", "일정 · 실시간 참여"],
  ["shop", '<path d="M4.5 9.5h15l-1.2 10h-12.6z"/><path d="M8.5 9.5V7a3.5 3.5 0 0 1 7 0v2.5"/><path d="M12 13.2c-.9-1.1-2.8-.6-2.8.9 0 1.3 1.6 2.3 2.8 3 1.2-.7 2.8-1.7 2.8-3 0-1.5-1.9-2-2.8-.9z"/>', "추모 서비스", "헌화 · 선물 · 상차림"],
  ["calendar", '<rect x="4" y="5.5" width="16" height="14" rx="2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>', "함께 참배 약속", "기일 · 가족 일정"],
];
async function renderVisit() {
  const me = state.me;
  if (!me.niche) { view.innerHTML = `<div class="card empty-state"><h2>아직 연결된 봉안함이 없습니다</h2><p class="muted">시설에서 봉안함 번호를 연결하면 이 화면에서 참배하실 수 있습니다. 시설 담당자에게 연결을 요청해 주세요.</p><button class="secondary" type="button" id="toMemorial">추모 공간 열기</button></div>`; $("#toMemorial").onclick = () => go("memorial"); return; }
  const d = me.deceased[0];
  const liveLabel = `<svg viewBox="0 0 24 24" width="22" height="22" style="stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round"><path d="M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/></svg> 실시간으로 뵙기 <small class="btn-note">${me.live_seconds}초</small>`;
  const who = d ? d.name + " 님" : "우리 가족";
  view.innerHTML = `
    <section class="welcome-garden memorial-hero home-greet" aria-labelledby="heroTitle"><div class="memorial-hero-copy"><span class="eyebrow">원격 참배</span><h1 id="heroTitle">그리운 마음에, 따뜻한 안부를.</h1><p>${esc(who)}의 봉안함을 사진과 실시간 영상으로 뵙습니다.</p></div><div class="hero-art" id="heroArt"></div></section>
    <div class="home-grid">
      <section class="card tight visit-card" aria-labelledby="visitTitle">
        <div class="visit-head"><h2 id="visitTitle">${esc(who)}</h2><span class="niche-code">봉안함 ${esc(me.niche.code)}</span></div>
        <div class="viewer" id="viewer">
          <div class="snapshot" id="snap"><div class="placeholder">사진을 불러오는 중…</div></div>
          <div class="offering-layer" id="offering"></div>
          <div class="title-card" id="titleCard" hidden>${esc(d ? d.name + " 님을 뵙습니다" : "가족을 뵙습니다")}</div>
        </div>
        <div class="status-line"><span id="camStatus" role="status"><span class="dot"></span>카메라 상태를 확인하는 중입니다…</span><span class="row" style="gap:8px"><span id="snapAt"></span><button class="chime-toggle ${chimeEnabled() ? "on" : ""}" id="chimeBtn" type="button">종소리 ${chimeEnabled() ? "켬" : "끔"}</button></span></div>
      </section>
      <aside class="home-side" aria-label="바로 하기">
        <button id="liveBtn" class="live-cta" type="button">${liveLabel}</button>
        <p class="live-note">사진은 10초마다 새로 찍힙니다. 현장에 다른 참배객이 계시면 실시간 영상은 잠시 멈추고 사진으로 보여 드립니다.</p>
        <nav class="quick-grid" aria-label="자주 쓰는 기능">${HOME_QUICK.map(([route, icon, label, sub]) => `<button type="button" class="quick" data-go="${route}"><svg viewBox="0 0 24 24" aria-hidden="true">${icon}</svg><b>${label}</b><small>${sub}</small></button>`).join("")}</nav>
        <div class="card music-mini" id="homeMusic" hidden></div>
        <div class="card next-up" id="nextUp" hidden></div>
      </aside>
    </div>`;
  mountArt($("#heroArt"), state.theme, motionReduced());
  view.querySelectorAll("[data-go]").forEach((b) => b.onclick = () => { const [route, focus] = b.dataset.go.split("#"); state.focus = focus || null; go(route); });
  $("#snap").onclick = () => { if (!live.on) go("memorial"); };   // 화면 속 봉안함을 누르면 추모 공간
  $("#chimeBtn").onclick = () => { localStorage.setItem("chime", chimeEnabled() ? "0" : "1"); const on = chimeEnabled(); $("#chimeBtn").classList.toggle("on", on); $("#chimeBtn").textContent = `종소리 ${on ? "켬" : "끔"}`; if (on) chime(); };
  let visitSong = null;   // 참배 때 함께 흐를 노래(계약자가 정함)
  keepsake.homeMusic($("#homeMusic"), d, () => { state.focus = "music"; go("memorial"); }).then((x) => { visitSong = x; });
  api("/api/family/memorial").then((m) => {   // 다가오는 기일·추도식 한 건
    const r = m.upcoming?.[0], box = $("#nextUp");
    if (!r || !box) return;
    box.innerHTML = `<span class="when">${esc(fmtDT(r.scheduled_at))}</span><span class="what">${esc(r.title)}<small class="muted">다가오는 추도식</small></span><button class="secondary" type="button">일정 보기</button>`;
    $("button", box).onclick = () => go("ritual"); box.hidden = false;
  }).catch(() => {});
  const live = { on: false, timer: null, scene: null, title: null };
  let firstShown = false;

  const snap = $("#snap"), viewer = $("#viewer");
  async function refreshStatus() {
    try {
      const s = await api("/api/family/niche/status");
      const demo = s.live_protect === false;   // 관리자 콘솔에서 참배객 보호를 끈 시연 모드
      $("#camStatus").innerHTML = (s.camera_online
        ? (s.occupied && !demo ? `<span class="dot busy"></span>현장에 참배객이 계십니다` : `<span class="dot on"></span>카메라 연결됨`)
        : `<span class="dot"></span>현장 카메라가 꺼져 있습니다`) + (demo ? ' <span class="pill" title="참배객 감지를 꺼 둔 상태">시연 모드</span>' : "")
        + (s.demo_camera ? ' <span class="pill demo-cam" title="현장 웹캠 대신 윤회당 봉안실 사진으로 만든 시연 화면입니다. 실제 현장 중계가 아닙니다.">시연 화면</span>' : "")
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
    viewer.classList.remove("live"); live.scene?.destroy(); live.scene = null; clearTimeout(live.title); $("#titleCard").hidden = true;
    $("#liveBtn").disabled = false; $("#liveBtn").innerHTML = liveLabel;
    keepsake.onLiveEnd();
    showSnapshot(); if (msg) toast(msg);
  }
  $("#liveBtn").onclick = async () => {
    if ($("#liveBtn").disabled) return;
    $("#liveBtn").disabled = true; $("#liveBtn").textContent = "실시간 영상을 여는 중입니다…";
    try {
      const r = await api("/api/family/live/start", { method: "POST" });
      live.on = true; let left = r.seconds;
      // 연출: 종소리와 함께 양쪽 촛불과 향 연기 장면(Lottie offering)이 영상 위에 밝아지고, 잠시 '○○ 님을 뵙습니다'를 보여 준다.
      viewer.classList.add("live");
      live.scene = mountScene($("#offering"), "offering", { label: "실시간 영상 양쪽에 촛불이 흔들리고 향 연기가 오르는 그림" });
      $("#titleCard").hidden = false; live.title = setTimeout(() => { const t = $("#titleCard"); if (t) t.hidden = true; }, 4500);
      const img = new Image();
      img.onerror = () => endLive("실시간 영상이 끊겼습니다. 사진으로 보여 드립니다.");
      img.onload = () => { if (img.naturalWidth) snap.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`; };
      snap.innerHTML = ""; snap.classList.remove("reveal"); snap.classList.add("live"); snap.appendChild(img); snap.insertAdjacentHTML("beforeend", `<span class="badge live">실시간</span>`);
      img.src = withToken(`/api/family/live/stream?sid=${r.session_id}`);
      chime(); keepsake.onLiveStart(visitSong);
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
  const d0 = data.deceased[0];
  view.innerHTML = `${cards}
    ${d0 ? `<section class="card altar-card" id="altar" aria-label="추모 제단"><p class="muted" role="status">추모 제단을 차리는 중입니다…</p></section>
    <section class="card music-card" id="music" aria-label="생전 좋아하신 노래"><p class="muted" role="status">노래 목록을 불러오는 중입니다…</p></section>` : ""}
    <div class="card"><h3>다가오는 기일·추도식</h3>${upcoming}<button class="secondary small" style="margin-top:8px" id="toRitual">일정 전체 보기</button></div>
    <div class="card"><h3>가족 방명록</h3>
      <div class="field"><label for="gbMsg">가족에게, 그리고 ${esc(data.deceased[0]?.name || "고인")} 님께 남길 말</label><textarea id="gbMsg" aria-describedby="gbHelp"></textarea><small class="muted" id="gbHelp">남긴 글은 가족 모두가 봅니다.</small></div>
      <button id="gbSend">방명록에 남기기</button>
      <div style="margin-top:12px">${guest}</div></div>`;
  $("#toRitual").onclick = () => go("ritual");
  if (d0) {
    const d0me = state.me.deceased.find((x) => x.id === d0.id) || d0;
    Promise.all([keepsake.mountAltar($("#altar"), { ...d0, has_photo: d0.has_photo ?? d0me.has_photo }), keepsake.mountMusic($("#music"), d0)])
      .then(() => { if (state.focus) { document.getElementById(state.focus)?.scrollIntoView({ block: "start" }); state.focus = null; } });
  }
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
        <div class="shrine-scene" id="shrineScene"></div>
        <div class="shrine-frame"><div class="shrine-inner">
          ${sess.photo_url ? `<img src="${withToken(sess.photo_url)}" alt="${esc(d.name)} 님의 사진">` : `<div class="no-photo" aria-hidden="true">◯</div>`}
          <video id="avatarVideo" autoplay playsinline></video>
        </div></div>
        <div class="shrine-caption"><span class="live-badge" id="liveBadge">인공지능 사진 아바타</span>
          <div class="voice-scene" id="voiceScene" aria-hidden="true"></div>
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
  mountScene($("#shrineScene"), "shrine", { label: "고인 사진 둘레에 후광과 안개, 빛망울이 머무는 그림", credit: false });
  const voiceUI = mountVoice($("#voiceScene"));
  // 말하기·듣기 상태(stage 의 speaking·listening 표시)를 음성 장면에 그대로 옮긴다
  new MutationObserver(() => voiceUI.set(stage.classList.contains("listening") ? "listening" : stage.classList.contains("speaking") ? "speaking" : "idle"))
    .observe(stage, { attributes: true, attributeFilter: ["class"] });
  const say = (text, onend) => speakAs(sess, text, () => { stage.classList.remove("speaking"); onend?.(); }, () => stage.classList.add("speaking"));
  // 첫 인사는 후광 장면이 밝아진 뒤(약 3초)에 시작한다.
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
    if (!$("#endBtn")) return;   // 대화가 끝나기 전에 다른 화면으로 옮겼으면 고칠 단추가 없다
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
        <button class="small secondary" data-offer="${r.id}">상차림·헌화 주문</button>
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
    <div class="card"><h3>내 공양·헌화 신청</h3>${myOff}<button class="secondary" style="margin-top:10px" id="offerAny">추모 서비스 보기 (헌화·선물·상차림)</button></div>`;
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
  // 유료 추모 서비스 화면으로(의례별 단추는 상차림 분류 + 그 의례를 미리 골라 둔다). 옛 신청 창(openOffer)은 남겨 둔다.
  view.querySelectorAll("[data-offer]").forEach((b) => b.onclick = () => { state.shopPreset = { category: "table", ritual_id: +b.dataset.offer }; go("shop"); });
  $("#offerAny").onclick = () => go("shop");
  void openOffer;
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
  const float = (emoji) => playReaction(fx, emoji);   // 합장·촛불·헌화·마음 Lottie(한 번 재생)
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
function lookChoices(key) {
  return `<div class="look-choices" role="group">${LOOK_OPTIONS[key].map(([v, name, sub]) => `<button type="button" class="choice" data-look="${key}" data-value="${v}" aria-pressed="false"><b>${name}</b><small>${sub}</small></button>`).join("")}</div>`;
}
async function renderSettings() {
  const me = state.me; let members, history;
  try { [members, history] = await Promise.all([api("/api/family/members"), api("/api/family/chat/history")]); } catch (e) { failCard("설정을", e, "settings"); return; }
  const roleName = { view: "보기", chat: "보기·대화", manage: "관리" };
  const canManage = me.member.role === "manage";
  const cur = currentTheme();
  view.innerHTML = `
    <div class="page-heading settings-heading"><span class="eyebrow">설정</span><h1>마음에 맞게, 편안하게</h1><p class="muted">추모 공간의 모습과 가족, 알림을 정합니다.</p></div>
    <div class="card theme-settings"><h2>추모 공간 꾸미기</h2><p class="muted" style="margin-top:0">고르는 대로 이 화면 전체에 미리 보입니다. 마음에 들면 아래 <b>적용하기</b>를 눌러 주세요. ${canManage ? "상징·색·문양·바탕·글꼴은 가족 모두의 화면에 함께 적용됩니다." : "이 기기에서만 바뀝니다."} 글자 크기는 언제나 이 기기에만 적용됩니다.</p>
      <section class="look-group" aria-labelledby="lookTheme"><h3 id="lookTheme"><span class="look-no">1</span>종교 상징</h3>
        <div class="theme-grid">${THEMES.map(([id, name, desc]) => `<button class="tile ${cur === id ? "active" : ""}" type="button" data-theme="${id}" aria-pressed="${cur === id}"><span class="theme-thumb" aria-hidden="true"></span><span class="sw" aria-hidden="true"></span><span>${name}<small>${desc}</small></span></button>`).join("")}</div></section>
      <section class="look-group" aria-labelledby="lookAccent"><h3 id="lookAccent"><span class="look-no">2</span>강조색 <small class="muted">단추·제목 선·상징의 색</small></h3><div class="swatches" id="accentRow" role="group" aria-labelledby="lookAccent"></div></section>
      <section class="look-group" aria-labelledby="lookPattern"><h3 id="lookPattern"><span class="look-no">3</span>배경 문양 <small class="muted" id="patternName"></small></h3>${lookChoices("pattern")}</section>
      <section class="look-group" aria-labelledby="lookTone"><h3 id="lookTone"><span class="look-no">4</span>바탕 빛</h3>${lookChoices("tone")}</section>
      <section class="look-group" aria-labelledby="lookFont"><h3 id="lookFont"><span class="look-no">5</span>제목 글꼴</h3>${lookChoices("font")}</section>
      <section class="look-group" aria-labelledby="lookSize"><h3 id="lookSize"><span class="look-no">6</span>글자 크기 <small class="muted">이 기기만</small></h3>${lookChoices("size")}</section>
      <div class="look-actions"><p class="muted" id="themeStatus" role="status">지금 모습이 적용되어 있습니다.</p><div class="row"><button class="secondary" type="button" id="resetLookBtn" disabled>되돌리기</button><button type="button" id="applyThemeBtn" disabled>적용 중</button></div></div>
      <div class="row between motion-row" style="margin-top:12px"><span class="muted">화면 움직임(첫 화면·촛불·후광 장면)</span><button class="small ${motionReduced() ? "ghost" : "secondary"}" id="motionBtn" aria-pressed="${motionReduced()}">${motionReduced() ? "정지 화면 · 누르면 움직입니다" : window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "느리게 움직임(기기 설정) · 누르면 멈춥니다" : "움직임 켬 · 누르면 정지 화면"}</button></div></div>
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
  // 고른 값(sel)은 화면 전체에 바로 미리 보이고, 적용하기를 눌러야 저장된다(saved). 다른 화면으로 가면 저장된 모습으로 돌아간다(go).
  const saved = { theme: cur, ...currentStyle(), size: textSize() };
  let sel = { ...saved }, savingTheme = false;
  const themeTiles = [...view.querySelectorAll(".tile")];
  const applyButton = $("#applyThemeBtn"), resetButton = $("#resetLookBtn"), themeStatus = $("#themeStatus");
  const themeName = (id) => THEMES.find(t => t[0] === id)?.[1] || "일반";
  const same = () => ["theme", "accent", "pattern", "tone", "font", "size"].every((k) => sel[k] === saved[k]);
  function paint() {
    applyLook(sel.theme, sel, sel.size);
    themeTiles.forEach((t) => { const on = t.dataset.theme === sel.theme; t.classList.toggle("active", on); t.setAttribute("aria-pressed", String(on)); });
    $("#accentRow").innerHTML = (ACCENTS[sel.theme] || ACCENTS.classic).map(([hex, name], i) => `<button type="button" class="swatch ${sel.accent === String(i + 1) ? "active" : ""}" data-accent="${i + 1}" aria-pressed="${sel.accent === String(i + 1)}" style="--sw:${hex}"><span class="dot" aria-hidden="true"></span>${name}</button>`).join("");
    $("#accentRow").querySelectorAll("[data-accent]").forEach((b) => b.onclick = () => { if (!savingTheme) { sel.accent = b.dataset.accent; paint(); } });
    view.querySelectorAll("[data-look]").forEach((b) => { const on = sel[b.dataset.look] === b.dataset.value; b.classList.toggle("active", on); b.setAttribute("aria-pressed", String(on)); });
    $("#patternName").textContent = `${themeName(sel.theme)}: ${PATTERN_NAME[sel.theme] || ""}`;
    const dirty = !same();
    view.querySelector(".look-actions").classList.toggle("dirty", dirty);
    applyButton.disabled = !dirty || savingTheme; resetButton.disabled = !dirty || savingTheme;
    applyButton.textContent = dirty ? "적용하기" : "적용 중";
    themeStatus.textContent = dirty ? "미리 보는 중입니다. 적용하기를 눌러야 저장됩니다." : "지금 모습이 적용되어 있습니다.";
  }
  themeTiles.forEach((tile) => tile.onclick = () => { if (!savingTheme) { sel.theme = tile.dataset.theme; paint(); } });
  view.querySelectorAll("[data-look]").forEach((b) => b.onclick = () => { if (!savingTheme) { sel[b.dataset.look] = b.dataset.value; paint(); } });
  resetButton.onclick = () => { sel = { ...saved }; paint(); };
  applyButton.onclick = async () => {
    if (savingTheme || same()) return;
    savingTheme = true; paint(); applyButton.textContent = "적용하는 중…";
    const style = { accent: sel.accent, pattern: sel.pattern, tone: sel.tone, font: sel.font };
    try {
      if (canManage) {
        if (!me.deceased[0]) throw new Error("고인 등록 후 꾸밀 수 있습니다.");
        const r = await api("/api/family/theme", { method: "POST", body: { deceased_id: me.deceased[0].id, theme: sel.theme, style } });
        me.deceased[0].theme = sel.theme; me.deceased[0].theme_style = r.style || style;
        localStorage.removeItem("theme_local"); localStorage.removeItem("style_local");
      } else { localStorage.setItem("theme_local", sel.theme); localStorage.setItem("style_local", JSON.stringify(style)); }
      localStorage.setItem("text_size", sel.size);
      Object.assign(saved, sel);
      savingTheme = false; paint();
      themeStatus.textContent = `${themeName(sel.theme)} 테마와 세부 모습을 ${canManage ? "가족의 추모 공간에" : "이 기기에"} 적용했습니다.`;
      toast(themeStatus.textContent);
    } catch (e) {
      savingTheme = false; paint();
      themeStatus.textContent = `적용하지 못했습니다. ${e.message}`;
    }
  };
  paint();
  $("#logout").onclick = () => {
    const m = modal(`<h2>이 기기에서 나갈까요?</h2><p>나가면 이 기기에서는 초대 링크를 다시 눌러야 들어올 수 있습니다. 가족 기록은 지워지지 않습니다.</p><div class="modal-actions"><button class="secondary" type="button" data-cancel>머무르기</button><button type="button" data-ok>나가기</button></div>`);
    $("[data-cancel]", m).onclick = () => m.querySelector(".modal-close").click();
    $("[data-ok]", m).onclick = async () => { localStorage.removeItem("family_token"); await fetch("/api/family/session", { method: "DELETE" }).catch(() => {}); location.href = "/"; };
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
  const rows = v.deceased.map((d) => `
    <div class="list-item" style="align-items:flex-start;flex-direction:column;gap:6px">
      <div class="row between" style="width:100%"><div><b>${esc(d.name)} 님</b> <span class="muted">${esc(d.honorific)}</span></div>
        ${d.has_voice ? '<span class="pill ok">목소리 등록됨</span>' : d.samples ? '<span class="pill">자료 저장됨 · 만들기 전</span>' : '<span class="pill">미등록</span>'}</div>
      <div class="muted">${d.has_voice ? "이 목소리로 대화가 재생됩니다." : d.samples ? `저장한 자료 ${d.samples}개 · 모두 ${d.sample_seconds || 0}초${(d.sample_seconds || 0) < v.min_seconds ? ` (${v.min_seconds}초 이상 필요)` : ""}` : "아직 자료가 없습니다."}${d.consent ? ` · 동의: ${esc(d.consent.signer_name)} (${d.consent.kind === "lifetime_record" ? "생전 기록" : "음성 사용"})` : ""}</div>
      <div class="row" style="flex-wrap:wrap">
        ${d.has_voice && v.can_manage ? `<button class="small secondary" data-vprev="${d.id}">미리 듣기</button>` : ""}
        ${v.can_manage ? `<button class="small ${d.has_voice ? "ghost" : ""}" data-vrec="${d.id}">${d.has_voice ? "다시 등록" : d.samples ? "자료 더하기" : "목소리 등록"}</button>` : ""}
        ${v.can_manage && !d.has_voice && d.samples && v.provider_ready && (d.sample_seconds || 0) >= v.min_seconds ? `<button class="small" data-vbuild="${d.id}">저장한 자료로 목소리 만들기</button>` : ""}
        ${v.can_manage && d.has_voice ? `<button class="small ghost" data-vdel="${d.id}">삭제</button>` : ""}
      </div>
      <audio data-vaudio="${d.id}" controls style="display:none;width:100%"></audio>
    </div>`).join("");
  box.innerHTML = `<p class="muted">살아 계실 때 직접 남기는 <b>생전 기록</b>이 가장 좋습니다. 고인의 음성 자료(휴대폰 영상·음성 메시지·통화 녹음)도 가족 동의로 올릴 수 있습니다. <b>바로 녹음</b>하거나 <b>파일을 여러 개</b> 올려 합칠 수 있습니다. 목소리는 대화에만 쓰이고, 작별하면 함께 지워집니다.</p>
    ${!v.provider_ready ? '<div class="notice" style="margin-bottom:8px">시설에서 아직 음성 복제 기능을 켜지 않았습니다. 지금 녹음하거나 올린 자료와 동의는 안전하게 저장해 두고, 기능이 켜지면 ‘저장한 자료로 목소리 만들기’로 바로 만들 수 있습니다.</div>' : ""}
    ${rows}
    ${!v.can_manage ? '<p class="muted">등록은 계약자만 할 수 있습니다. 필요하면 계약자에게 요청해 주세요.</p>' : ""}`;
  box.querySelectorAll("[data-vprev]").forEach((b) => b.onclick = async () => {
    b.disabled = true; b.textContent = "미리 듣기를 만드는 중입니다…";
    try { const r = await fetch(withToken("/api/family/voice/preview"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ deceased_id: +b.dataset.vprev }) });
      if (!r.ok) throw new Error((await r.json()).detail); const a = box.querySelector(`[data-vaudio="${b.dataset.vprev}"]`); a.src = URL.createObjectURL(await r.blob()); a.style.display = "block"; a.play(); }
    catch (e) { toast(e.message, 4000); }
    b.disabled = false; b.textContent = "미리 듣기";
  });
  box.querySelectorAll("[data-vdel]").forEach((b) => b.onclick = async () => { if (confirm("등록된 목소리를 삭제하면 되돌릴 수 없습니다. 대화는 기본 음성으로 돌아갑니다. 삭제할까요?")) { await api(`/api/family/voice/${b.dataset.vdel}`, { method: "DELETE" }); renderVoiceCard(); } });
  box.querySelectorAll("[data-vbuild]").forEach((b) => b.onclick = async () => {
    if (b.disabled) return; b.disabled = true; b.textContent = "목소리를 만드는 중입니다… (1분쯤)";
    try { const r = await api(`/api/family/voice/${b.dataset.vbuild}/build`, { method: "POST" }); toast(`목소리를 만들었습니다${r.seconds ? ` (자료 ${r.files}개 · ${r.seconds}초)` : ""}. 대화에서 바로 쓰입니다.`, 4500); renderVoiceCard(); state.me = await api("/api/family/me"); }
    catch (e) { toast(`목소리를 만들지 못했습니다. ${e.message}`, 6000); b.disabled = false; b.textContent = "저장한 자료로 목소리 만들기"; }
  });
  box.querySelectorAll("[data-vrec]").forEach((b) => b.onclick = () => openRecorder(v.deceased.find((d) => d.id === +b.dataset.vrec), v));
}

// 목소리 등록 창은 관리자 콘솔과 같은 js/voice-recorder.js 를 쓴다(실시간 녹음 · 여러 형식 파일 올리기).
function openRecorder(d, v) {
  openVoiceRecorder({
    modal, toast, title: `${d.name} 님 목소리 등록`, script: VOICE_SCRIPT,
    formats: v.formats, accept: v.accept, maxMB: v.max_mb, minSeconds: v.min_seconds, providerReady: v.provider_ready,
    upload: { url: "/api/family/voice/register", headers: { "X-Family-Token": TOKEN || "" }, fields: { deceased_id: d.id } },
    onDone: async () => { renderVoiceCard(); state.me = await api("/api/family/me"); },
  });
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
