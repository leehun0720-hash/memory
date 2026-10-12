// 몽환적 실사 Lottie 장면 재생기 (2026-10-12). 장면 파일은 scripts/make_dream_lottie.py 가 만든다(손으로 고치지 않음).
// 움직임은 이 Lottie 장면들만 쓴다(CSS 키프레임 연출은 모두 걷어냄).
// - 앱 설정 '화면 움직임 줄이기'(html[data-motion="reduce"]) → 정지 장면 한 장.
// - 기기의 움직임 줄이기(prefers-reduced-motion) → 절반 속도로 느리게 반복 + '움직임 멈추기' 단추.
// - Lottie 를 못 불러오면 대체 그림(포스터)이나 빈 자리로 두고 내용은 막지 않는다.
// - 화면 밖·숨은 탭에서는 멈춘다.
const BASE = "/static/lottie/dream/";
const IMG = BASE + "img/";
let playerP = null, scenesP = null;
const dataCache = new Map();
const live = new Set();

export function appReduced() { return document.documentElement.dataset.motion === "reduce"; }
export function osReduced() { return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches; }

function loadPlayer() {
  return (playerP ||= new Promise((resolve, reject) => {
    if (window.lottie) return resolve(window.lottie);
    const s = document.createElement("script");
    s.src = "/static/vendor/lottie_light.min.js"; s.async = true;
    s.onload = () => (window.lottie ? resolve(window.lottie) : reject(new Error("lottie")));
    s.onerror = () => { playerP = null; reject(new Error("lottie")); };
    document.head.append(s);
  }));
}
function scenes() {
  return (scenesP ||= fetch(BASE + "scenes.json").then((r) => { if (!r.ok) throw new Error("scenes"); return r.json(); }).catch((e) => { scenesP = null; throw e; }));
}
function sceneData(name) {
  if (!dataCache.has(name)) dataCache.set(name, fetch(BASE + name + ".json").then((r) => { if (!r.ok) throw new Error(name); return r.json(); }).catch((e) => { dataCache.delete(name); throw e; }));
  return dataCache.get(name);
}

/** 이 화면의 장면을 모두 정리한다(탭을 옮길 때). */
export function destroyAll() { [...live].forEach((h) => h.destroy()); }

/**
 * 반복 장면을 stage 에 붙인다.
 * opts: { label, pause: 멈춤 단추(기본 true), credit: 출처 표시(기본 true), fit: "cover"|"contain" }
 * 돌려받는 handle: { destroy(), anim, ready: Promise }
 */
export function mountScene(stage, name, opts = {}) {
  const h = { anim: null, destroyed: false, observer: null, onVisible: null, paused: false };
  if (!stage) return h;
  stage.classList.add("dream-stage");
  stage.dataset.scene = name;
  stage.innerHTML = `<div class="dream-live" aria-hidden="true"></div>`;
  const holder = stage.querySelector(".dream-live");
  h.destroy = () => {
    if (h.destroyed) return; h.destroyed = true; live.delete(h);
    try { h.observer?.disconnect(); h.anim?.destroy(); } catch {}
    if (h.onVisible) document.removeEventListener("visibilitychange", h.onVisible);
  };
  live.add(h);
  // 대체 그림(포스터)은 Lottie 재생기와 따로 먼저 건다: 재생기를 못 불러와도 사진은 보인다
  scenes().then((meta) => { const p = meta[name]?.poster; if (p && !h.destroyed) stage.style.setProperty("--dream-poster", `url("${IMG + p}")`); }).catch(() => {});
  h.ready = Promise.all([loadPlayer(), scenes(), sceneData(name)]).then(([lottie, meta, data]) => {
    const m = meta[name] || {};
    if (opts.credit !== false && m.credit) stage.insertAdjacentHTML("beforeend", `<span class="dream-credit">${m.credit}</span>`);
    if (opts.label !== false) stage.insertAdjacentHTML("afterbegin", `<span class="sr-only">${opts.label || m.label || ""}</span>`);
    if (h.destroyed || !stage.isConnected) return h;
    const anim = lottie.loadAnimation({ container: holder, renderer: "svg", loop: false, autoplay: false, animationData: data, assetsPath: IMG,
      rendererSettings: { preserveAspectRatio: opts.fit === "contain" ? "xMidYMid meet" : `${opts.align || "xMidYMid"} slice`, progressiveLoad: false } });
    h.anim = anim;
    const show = () => stage.classList.add("is-live");
    anim.addEventListener("DOMLoaded", show);
    if (appReduced()) { anim.goToAndStop(m.still ?? 0, true); show(); return h; }
    const [a, b] = m.loop || [0, anim.totalFrames];
    if (osReduced()) anim.setSpeed(0.5);
    anim.addEventListener("complete", () => { if (!h.destroyed && !h.paused) { anim.loop = true; anim.playSegments([a, b], true); } });
    anim.playSegments([0, b], true);   // 밝아짐 → 첫 반복까지 한 번에, 이후 반복 구간만
    if (opts.pause !== false) {
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "dream-pause"; btn.setAttribute("aria-pressed", "false"); btn.textContent = "움직임 멈추기";
      btn.onclick = (ev) => {
        ev.stopPropagation();
        h.paused = !h.paused;
        if (h.paused) anim.pause(); else anim.play();
        btn.setAttribute("aria-pressed", String(h.paused));
        btn.textContent = h.paused ? "다시 움직이기" : "움직임 멈추기";
      };
      stage.append(btn);
    }
    const sync = (visible) => { if (h.paused || h.destroyed) return; if (visible) anim.play(); else anim.pause(); };
    if (opts.observe === false) return h;
    if ("IntersectionObserver" in window) { h.observer = new IntersectionObserver(([e]) => sync(e.isIntersecting && !document.hidden)); h.observer.observe(stage); }
    h.onVisible = () => sync(!document.hidden);
    document.addEventListener("visibilitychange", h.onVisible);
    return h;
  }).catch(() => { stage.classList.add("dream-failed"); return h; });
  return h;
}

/** 첫 화면 그림(테마별). 예전 brand.js 의 mountArt 자리. */
export function mountArt(stage, theme) {
  const t = ["classic", "buddhist", "catholic", "christian"].includes(theme) ? theme : "classic";
  if (stage) stage.dataset.theme = t;
  // 좁은 화면(세로 휴대폰)에서는 오른쪽 아래 꽃이 보이도록 오른쪽 기준으로 자른다
  return mountScene(stage, `entry-${t}`, { align: window.matchMedia?.("(max-width: 720px)").matches ? "xMaxYMid" : "xMidYMid" });
}

/** 말하기·듣기 표시. set("speaking"|"listening"|"idle") */
export function mountVoice(stage) {
  const h = mountScene(stage, "voice", { pause: false, credit: false, label: false, observe: false, fit: "contain" });
  let state = "idle";
  const apply = () => {
    const a = h.anim; if (!a) return;
    const seg = { speaking: [0, 30], listening: [30, 90], idle: [90, 91] }[state];
    if (state === "idle" || appReduced()) { a.loop = false; a.goToAndStop(state === "listening" ? 45 : state === "speaking" ? 14 : 90, true); return; }
    a.loop = true; a.playSegments(seg, true);
  };
  h.ready?.then(() => { if (h.anim) { h.anim.removeEventListener?.("complete"); h.anim.loop = true; apply(); } });
  h.set = (s) => { if (s === state) return; state = s; apply(); };
  return h;
}

const REACTION = { "\u{1F64F}": "hands", "\u{1F56F}️": "candle", "\u{1F56F}": "candle", "\u{1F338}": "flower", "\u{1F49B}": "heart" };
/** 생중계 반응 한 번(합장·촛불·헌화·마음). 동시에 너무 많으면 오래된 것부터 지운다. */
export function playReaction(box, emoji) {
  if (!box) return;
  const kind = REACTION[emoji] || "heart";
  const el = document.createElement("div");
  el.className = "dream-reaction";
  el.style.left = (4 + Math.random() * 62) + "%";
  box.appendChild(el);
  while (box.children.length > 10) box.firstChild.remove();
  const fallback = () => { el.textContent = emoji; el.classList.add("still"); setTimeout(() => el.remove(), 1800); };
  if (appReduced()) { fallback(); return; }
  Promise.all([loadPlayer(), sceneData("reaction-" + kind)]).then(([lottie, data]) => {
    if (!el.isConnected) return;
    const a = lottie.loadAnimation({ container: el, renderer: "svg", loop: false, autoplay: true, animationData: data, assetsPath: IMG });
    if (osReduced()) a.setSpeed(0.7);
    a.addEventListener("complete", () => { a.destroy(); el.remove(); });
    setTimeout(() => { if (el.isConnected) { try { a.destroy(); } catch {} el.remove(); } }, 6000);
  }).catch(fallback);
}
