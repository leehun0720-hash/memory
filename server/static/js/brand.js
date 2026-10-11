// 가족 추모 공간 첫 화면 그림 (2026-10-11). 불교 테마는 연화문(lotus-bloom), 나머지 테마는 종교 상징 없는 촛불 선화(candle-light).
// - 정적 그림이 먼저 보이고, Lottie를 불러오면 그 위에 그려진다. 못 불러오면 정적 그림이 그대로 남는다(내용을 막지 않음).
// - 움직임 줄이기(기기 설정·앱 설정)를 켜면 마지막 장면에서 멈춘다. 움직이는 동안에는 '움직임 멈추기' 버튼을 준다.
// - 두 Lottie 모두 30fps, 0~90프레임 그리기 → 90~330프레임 반복 (scripts/make_memorial_lottie.py 참고).
const ART = {
  buddhist: { json: "/static/lottie/lotus-bloom.json", still: "/static/images/brand/lotus-static.svg", label: "연꽃이 선으로 그려지고 피어나는 그림" },
  other: { json: "/static/lottie/candle-light.json", still: "/static/images/brand/candle-light.svg", label: "둥근 선 안에 촛불이 켜지는 그림" },
};
const BLOOM = 90, END = 330;
let player = null, current = null;

function loadPlayer() {
  return (player ||= new Promise((resolve, reject) => {
    if (window.lottie) return resolve(window.lottie);
    const s = document.createElement("script");
    s.src = "/static/vendor/lottie_light.min.js"; s.async = true;
    s.onload = () => (window.lottie ? resolve(window.lottie) : reject(new Error("lottie")));
    s.onerror = () => { player = null; reject(new Error("lottie")); };
    document.head.append(s);
  }));
}

export function destroyArt() {
  if (!current) return;
  try { current.observer?.disconnect(); current.anim?.destroy(); } catch {}
  document.removeEventListener("visibilitychange", current.onVisible);
  current = null;
}

/** stage: 빈 요소. theme: classic|buddhist|catholic|christian. reduced: 움직임 줄이기 여부. */
export function mountArt(stage, theme, reduced = false) {
  if (!stage) return;
  destroyArt();
  const art = theme === "buddhist" ? ART.buddhist : ART.other;
  stage.classList.add("art-stage");
  stage.dataset.art = theme === "buddhist" ? "lotus" : "candle";
  stage.setAttribute("role", "img");
  stage.setAttribute("aria-label", art.label);
  stage.innerHTML = `<img class="art-still" src="${art.still}" alt="" aria-hidden="true"><div class="art-live" aria-hidden="true"></div>`;
  const live = stage.querySelector(".art-live");
  const me = { anim: null, observer: null, onVisible: null, paused: false };
  current = me;
  Promise.all([loadPlayer(), fetch(art.json).then((r) => { if (!r.ok) throw new Error(art.json); return r.json(); })])
    .then(([lottie, data]) => {
      if (current !== me || !stage.isConnected) return;
      const anim = lottie.loadAnimation({ container: live, renderer: "svg", loop: false, autoplay: false, animationData: data,
        rendererSettings: { preserveAspectRatio: "xMidYMid meet" } });
      me.anim = anim;
      stage.classList.add("is-live");
      if (reduced) { anim.goToAndStop(BLOOM, true); return; }
      anim.addEventListener("complete", () => { if (current === me && !me.paused) { anim.loop = true; anim.playSegments([BLOOM, END], true); } });
      anim.playSegments([0, BLOOM], true);
      // 멈춤 버튼 (움직임이 5초 넘게 이어지므로)
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "art-pause"; btn.setAttribute("aria-pressed", "false"); btn.textContent = "움직임 멈추기";
      btn.onclick = () => {
        me.paused = !me.paused;
        if (me.paused) anim.pause(); else anim.play();
        btn.setAttribute("aria-pressed", String(me.paused));
        btn.textContent = me.paused ? "다시 움직이기" : "움직임 멈추기";
      };
      stage.append(btn);
      stage.removeAttribute("role"); stage.removeAttribute("aria-label"); // 버튼이 들어가므로 그림 설명은 숨은 글로 둔다
      stage.insertAdjacentHTML("afterbegin", `<span class="sr-only">${art.label}</span>`);
      // 화면 밖·숨은 탭에서는 멈춘다
      const sync = (visible) => { if (me.paused) return; if (visible) anim.play(); else anim.pause(); };
      if ("IntersectionObserver" in window) { me.observer = new IntersectionObserver(([e]) => sync(e.isIntersecting && !document.hidden)); me.observer.observe(stage); }
      me.onVisible = () => sync(!document.hidden);
      document.addEventListener("visibilitychange", me.onVisible);
    })
    .catch(() => { stage.classList.remove("is-live"); });
}
