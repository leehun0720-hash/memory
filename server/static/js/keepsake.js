// 추모 제단(국화·촛불·스티커 놓기)과 생전 좋아하신 노래 (2026-10-12). app.js 가 createKeepsake 로 만든다.
// - 제단: 고인 사진 아래 판에 아이템을 골라 끌어 놓고(자리·기울기·크기·짧은 글) 가족 모두가 본다. 그림은 /static/images/altar/*.svg
// - 노래: 계약자가 올리고 '참배 때 틀 곡'을 정한다. 실시간으로 뵙기를 열면 종소리 뒤에 천천히 커지며 흐르고, 끝나면 천천히 작아진다.
//   화면을 옮겨도 아래 작은 막대에서 계속 흐르며 언제든 멈출 수 있다.

export const ALTAR_GROUPS = [
  ["flower", "꽃", [["chrysanthemum-white", "흰 국화"], ["chrysanthemum-yellow", "노란 국화"], ["carnation", "카네이션"], ["rose-white", "흰 장미"], ["lily", "백합"], ["lotus", "연꽃"]]],
  ["light", "빛 · 향", [["candle", "촛불"], ["incense", "향"]]],
  ["sticker", "스티커", [["heart", "하트"], ["star", "별"], ["butterfly", "나비"], ["dove", "비둘기"], ["hands", "합장"], ["text-miss", "보고 싶어요"], ["text-love", "사랑합니다"], ["text-thanks", "고맙습니다"]]],
];
const ITEM_NAME = Object.fromEntries(ALTAR_GROUPS.flatMap(([, , items]) => items));
const itemSrc = (id) => `/static/images/altar/${id}.svg`;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const mmss = (s) => (s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "");

export function createKeepsake({ api, esc, toast, modal, withToken, fmtDT }) {
  // ───────── 노래 ─────────
  const tune = { audio: null, song: null, fadeT: null, fromLive: false };
  const visitMusicOn = () => localStorage.getItem("visit_music") !== "0";
  function dock() {
    let el = document.getElementById("musicDock");
    if (!el) {
      el = document.createElement("div"); el.id = "musicDock"; el.className = "music-dock"; el.hidden = true;
      el.setAttribute("role", "region"); el.setAttribute("aria-label", "지금 흐르는 노래");
      document.body.appendChild(el);
    }
    return el;
  }
  function renderDock() {
    const el = dock(), a = tune.audio;
    if (!a) { el.hidden = true; el.innerHTML = ""; document.body.classList.remove("has-dock"); return; }
    el.hidden = false; document.body.classList.add("has-dock");
    el.innerHTML = `<span class="note" aria-hidden="true">♪</span><span class="t"><small>생전 좋아하신 노래</small><b>${esc(tune.song.title)}</b></span>
      <button type="button" class="small ghost" data-pp>${a.paused ? "이어 듣기" : "잠시 멈춤"}</button><button type="button" class="small ghost" data-stop>끄기</button>`;
    el.querySelector("[data-pp]").onclick = () => { if (a.paused) a.play().catch(() => {}); else a.pause(); };
    el.querySelector("[data-stop]").onclick = () => stopSong(true);
  }
  function fade(a, to, ms, done) {
    clearInterval(tune.fadeT);
    const from = a.volume, steps = 24; let i = 0;
    tune.fadeT = setInterval(() => { i++; a.volume = clamp(from + (to - from) * i / steps, 0, 1); if (i >= steps) { clearInterval(tune.fadeT); done?.(); } }, ms / steps);
  }
  function playSong(song, { fromLive = false } = {}) {
    if (!song) return;
    stopSong(false);
    const a = new Audio(withToken(`/api/family/media/${song.id}`));
    a.preload = "auto"; a.volume = 0;
    tune.audio = a; tune.song = song; tune.fromLive = fromLive;
    a.addEventListener("play", renderDock); a.addEventListener("pause", renderDock);
    a.addEventListener("ended", () => { if (tune.audio === a) { tune.audio = null; renderDock(); } });
    a.play().then(() => fade(a, .7, 2600)).catch(() => { if (tune.audio === a) { tune.audio = null; renderDock(); } toast("노래를 틀지 못했습니다. 화면을 한 번 누른 뒤 다시 들어 주세요.", 4000); });
    renderDock();
  }
  function stopSong(soft = true) {
    const a = tune.audio; if (!a) return;
    tune.audio = null; renderDock();
    if (soft && !a.paused) fade(a, 0, 1600, () => a.pause()); else { clearInterval(tune.fadeT); a.pause(); }
  }
  const loadMusic = (did) => api(`/api/family/music?deceased_id=${did}`);

  // 참배 첫 화면: 실시간 보기와 함께 틀 노래 한 곡
  async function homeMusic(box, d, goMusic) {
    if (!box || !d) return null;
    let m; try { m = await loadMusic(d.id); } catch { return null; }
    if (!box.isConnected) return null;
    const song = m.items.find((s) => s.id === m.visit_music_id) || null;
    if (!song) {
      if (m.can_manage) {
        box.innerHTML = `<span class="note" aria-hidden="true">♪</span><span class="t"><b>생전 좋아하신 노래</b><small>올려 두면 참배할 때 함께 흐릅니다.</small></span><button type="button" class="small secondary" data-go-music>노래 올리기</button>`;
        box.hidden = false; box.querySelector("[data-go-music]").onclick = goMusic;
      }
      return null;
    }
    box.innerHTML = `<span class="note" aria-hidden="true">♪</span><span class="t"><small>생전 좋아하신 노래</small><b>${esc(song.title)}</b></span>
      <button type="button" class="small secondary" data-play>들려 드리기</button>
      <label class="mini-switch"><input type="checkbox" data-auto ${visitMusicOn() ? "checked" : ""}> 참배할 때 함께 틀기</label>`;
    box.querySelector("[data-play]").onclick = () => playSong(song);
    box.querySelector("[data-auto]").onchange = (e) => { localStorage.setItem("visit_music", e.target.checked ? "1" : "0"); toast(e.target.checked ? "참배할 때 노래가 함께 흐릅니다." : "참배할 때 노래를 틀지 않습니다."); };
    box.hidden = false;
    return song;
  }
  function onLiveStart(song) { if (song && visitMusicOn()) setTimeout(() => playSong(song, { fromLive: true }), 1800); }
  function onLiveEnd() { if (tune.audio && tune.fromLive) stopSong(true); }

  // 추모 공간: 노래 목록 · 올리기(계약자)
  async function mountMusic(box, d) {
    if (!box || !d) return;
    let m; try { m = await loadMusic(d.id); } catch (e) { box.innerHTML = `<h3>생전 좋아하신 노래</h3><p class="muted">${esc(e.message)}</p>`; return; }
    const rows = m.items.map((s) => `<li class="song ${s.id === m.visit_music_id ? "is-visit" : ""}"><button type="button" class="small secondary" data-play="${s.id}" aria-label="${esc(s.title)} 듣기">▶ 듣기</button>
      <span class="song-t"><b>${esc(s.title)}</b><small>${mmss(s.seconds)}${s.id === m.visit_music_id ? " · 참배 때 흐르는 곡" : ""}</small></span>
      ${m.can_manage ? `${s.id === m.visit_music_id ? "" : `<button type="button" class="small ghost" data-visit="${s.id}">참배 때 틀기</button>`}<button type="button" class="small ghost" data-del="${s.id}">빼기</button>` : ""}</li>`).join("");
    box.innerHTML = `<div class="row between"><h3 style="margin:0">생전 좋아하신 노래</h3><span class="muted">${m.items.length}곡</span></div>
      <p class="muted" style="margin:6px 0 12px">참배(실시간으로 뵙기)를 열면 고른 곡이 종소리 뒤에 잔잔히 흐릅니다. 다른 화면으로 옮겨도 아래 막대에서 계속 들을 수 있습니다.</p>
      ${rows ? `<ul class="song-list">${rows}</ul>` : `<p class="muted">아직 올린 노래가 없습니다.${m.can_manage ? " 아래에서 고인이 즐겨 부르시던 노래를 올려 주세요." : " 계약하신 가족이 올릴 수 있습니다."}</p>`}
      ${m.can_manage ? `<form class="song-up" id="songUp"><div class="form-row"><label for="songTitle">곡 이름</label><input id="songTitle" maxlength="80" placeholder="예: 고향의 봄 · 어머니 애창곡"></div>
        <div class="form-row"><label for="songFile">음원 파일</label><input id="songFile" type="file" accept="audio/*,video/*,.mp3,.m4a,.aac,.wav,.flac,.ogg,.opus,.wma,.amr,.3gp,.mp4,.mov,.webm"></div>
        <button type="submit">노래 올리기</button><p class="muted song-note">가족이 가진 음원만 올려 주세요. 가족끼리만 듣고 밖으로 공유되지 않습니다. mp3·m4a·wav·영상 등, 한 곡 10분 · 100MB까지(${m.max}곡).</p></form>` : ""}`;
    box.querySelectorAll("[data-play]").forEach((b) => b.onclick = () => playSong(m.items.find((s) => s.id === +b.dataset.play)));
    box.querySelectorAll("[data-visit]").forEach((b) => b.onclick = async () => {
      try { await api("/api/family/music/visit", { method: "PUT", body: { deceased_id: d.id, media_id: +b.dataset.visit } }); toast("참배할 때 이 노래가 흐릅니다."); mountMusic(box, d); } catch (e) { toast(e.message, 4000); }
    });
    box.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => {
      const s = m.items.find((x) => x.id === +b.dataset.del);
      const md = modal(`<h2>‘${esc(s.title)}’을 뺄까요?</h2><p>빼면 가족 모두의 목록에서 사라지고 되돌릴 수 없습니다. 파일이 필요하면 원본을 따로 간직해 주세요.</p><div class="modal-actions"><button class="secondary" type="button" data-cancel>그대로 두기</button><button type="button" data-ok>빼기</button></div>`);
      md.querySelector("[data-cancel]").onclick = () => md.querySelector(".modal-close").click();
      md.querySelector("[data-ok]").onclick = async () => {
        try { if (tune.song?.id === s.id) stopSong(false); await api(`/api/family/music/${s.id}`, { method: "DELETE" }); md.querySelector(".modal-close").click(); toast("노래를 뺐습니다."); mountMusic(box, d); }
        catch (e) { toast(e.message, 4000); }
      };
    });
    const form = box.querySelector("#songUp");
    if (form) form.onsubmit = async (e) => {
      e.preventDefault();
      const file = form.querySelector("#songFile").files[0];
      if (!file) { toast("올릴 음원 파일을 골라 주세요."); return; }
      const btn = form.querySelector("button[type=submit]"); btn.disabled = true; btn.textContent = "올리는 중… 음원을 다듬고 있습니다";
      const fd = new FormData(); fd.append("deceased_id", d.id); fd.append("title", form.querySelector("#songTitle").value.trim()); fd.append("file", file);
      try { const r = await api("/api/family/music", { method: "POST", body: fd }); toast(`‘${r.title}’을 올렸습니다.`); mountMusic(box, d); }
      catch (err) { btn.disabled = false; btn.textContent = "노래 올리기"; toast(`올리지 못했습니다. ${err.message}`, 5000); }
    };
  }

  // ───────── 추모 제단 ─────────
  async function mountAltar(box, d) {
    if (!box || !d) return;
    let data; try { data = await api(`/api/family/altar/${d.id}`); } catch (e) { box.innerHTML = `<h3>추모 제단</h3><p class="muted">${esc(e.message)}</p>`; return; }
    const flowerIds = new Set(ALTAR_GROUPS[0][2].map(([id]) => id));
    const flowers = data.items.filter((x) => flowerIds.has(x.item)).length;
    const people = new Set(data.items.map((x) => x.author)).size;
    box.innerHTML = `<div class="row between"><h3 style="margin:0">추모 제단</h3><span class="muted">꽃 ${flowers}송이 · 가족 ${people}명</span></div>
      <p class="muted" style="margin:6px 0 12px">꽃과 촛불, 마음을 담은 스티커를 골라 원하는 자리에 놓아 주세요. 가족 모두에게 보입니다.</p>
      <div class="altar-board" id="altarBoard">
        <div class="altar-portrait">${d.has_photo ? `<img src="${withToken(`/api/family/deceased/${d.id}/photo.jpg`)}" alt="${esc(d.name)} 님의 사진">` : `<span aria-hidden="true">♡</span>`}<b>${esc(d.name)} 님</b></div>
        <div class="altar-items" id="altarItems"></div>
      </div>
      <div class="altar-tray" id="altarTray">
        <div class="seg altar-tabs" role="tablist" aria-label="놓을 것 고르기">${ALTAR_GROUPS.map(([g, name], i) => `<button type="button" role="tab" data-group="${g}" aria-selected="${i === 0}" class="${i === 0 ? "active" : ""}">${name}</button>`).join("")}</div>
        <div class="altar-pick" id="altarPick"></div>
      </div>
      <div class="altar-place" id="altarPlace" hidden></div>`;
    const board = box.querySelector("#altarBoard"), layer = box.querySelector("#altarItems");
    layer.innerHTML = data.items.map((x) => `<button type="button" class="altar-item" data-id="${x.id}" style="left:${+x.x}%;top:${+x.y}%;--rot:${+x.rot}deg;--sc:${+x.scale}" aria-label="${esc(x.author)} 님이 놓은 ${esc(ITEM_NAME[x.item] || "")}${x.message ? ": " + esc(x.message) : ""}"><img src="${itemSrc(x.item)}" alt=""></button>`).join("");
    layer.querySelectorAll(".altar-item").forEach((b) => b.onclick = () => {
      const x = data.items.find((i) => i.id === +b.dataset.id);
      const md = modal(`<div class="altar-detail"><img src="${itemSrc(x.item)}" alt=""><div><h2>${esc(ITEM_NAME[x.item] || "")}</h2><p class="muted">${esc(x.author)} 님 · ${esc(fmtDT(x.created_at))}</p>${x.message ? `<p class="preserve">${esc(x.message)}</p>` : ""}</div></div>
        ${x.can_remove ? `<div class="modal-actions"><button class="secondary" type="button" data-remove>${x.mine ? "치우기" : "정리하기(계약자)"}</button></div>` : ""}`);
      const rm = md.querySelector("[data-remove]");
      if (rm) rm.onclick = async () => { try { await api(`/api/family/altar/item/${x.id}`, { method: "DELETE" }); md.querySelector(".modal-close").click(); mountAltar(box, d); } catch (e) { toast(e.message, 4000); } };
    });
    const pick = box.querySelector("#altarPick");
    const showGroup = (g) => {
      box.querySelectorAll("[data-group]").forEach((t) => { const on = t.dataset.group === g; t.classList.toggle("active", on); t.setAttribute("aria-selected", String(on)); });
      pick.innerHTML = ALTAR_GROUPS.find(([id]) => id === g)[2].map(([id, name]) => `<button type="button" class="altar-choice" data-item="${id}"><img src="${itemSrc(id)}" alt=""><span>${name}</span></button>`).join("");
      pick.querySelectorAll("[data-item]").forEach((b) => b.onclick = () => startPlacing(b.dataset.item));
    };
    box.querySelectorAll("[data-group]").forEach((t) => t.onclick = () => showGroup(t.dataset.group));
    showGroup("flower");

    // 놓기: 판 아래쪽에 미리 놓고 → 끌어서(또는 화살표 키로) 옮기고 → 기울기·크기·글 → 놓기
    function startPlacing(item) {
      box.querySelector(".altar-ghost")?.remove();
      const p = { item, x: Math.round(50 + (Math.random() * 30 - 15)), y: Math.round(74 + (Math.random() * 10 - 5)), rot: Math.round(Math.random() * 16 - 8), scale: 1 };
      const ghost = document.createElement("div");
      ghost.className = "altar-item altar-ghost"; ghost.tabIndex = 0; ghost.setAttribute("role", "img");
      ghost.setAttribute("aria-label", `${ITEM_NAME[item]} 놓을 자리. 끌거나 화살표 키로 옮길 수 있습니다.`);
      ghost.innerHTML = `<img src="${itemSrc(item)}" alt="">`;
      layer.appendChild(ghost);
      const place = () => { ghost.style.left = p.x + "%"; ghost.style.top = p.y + "%"; ghost.style.setProperty("--rot", p.rot + "deg"); ghost.style.setProperty("--sc", p.scale); };
      place();
      const tray = box.querySelector("#altarTray"), panel = box.querySelector("#altarPlace");
      panel.hidden = false; tray.hidden = true;
      panel.innerHTML = `<p class="place-hint"><b>${ITEM_NAME[item]}</b>을(를) 판 위에서 원하는 자리로 끌어 옮겨 주세요.</p>
        <div class="place-tools"><button type="button" class="small ghost" data-rot="-6">↺ 왼쪽으로</button><button type="button" class="small ghost" data-rot="6">↻ 오른쪽으로</button>
          <button type="button" class="small ghost" data-sc="-.15">작게</button><button type="button" class="small ghost" data-sc=".15">크게</button></div>
        <label class="sr-only" for="altarMsg">함께 남길 말</label><input id="altarMsg" maxlength="120" placeholder="함께 남길 말 (선택, 120자)">
        <div class="row" style="gap:8px;margin-top:10px"><button type="button" class="secondary" data-cancel>그만두기</button><button type="button" data-put>여기에 놓기</button></div>`;
      panel.querySelectorAll("[data-rot]").forEach((b) => b.onclick = () => { p.rot = clamp(p.rot + +b.dataset.rot, -45, 45); place(); });
      panel.querySelectorAll("[data-sc]").forEach((b) => b.onclick = () => { p.scale = clamp(+(p.scale + +b.dataset.sc).toFixed(2), .6, 1.6); place(); });
      panel.querySelector("[data-cancel]").onclick = () => { ghost.remove(); panel.hidden = true; panel.innerHTML = ""; tray.hidden = false; };
      panel.querySelector("[data-put]").onclick = async (e) => {
        const btn = e.currentTarget; if (btn.disabled) return; btn.disabled = true; btn.textContent = "놓는 중…";
        try {
          await api(`/api/family/altar/${d.id}`, { method: "POST", body: { item, x: p.x, y: p.y, rot: p.rot, scale: p.scale, message: panel.querySelector("#altarMsg").value.trim() } });
          toast(`${ITEM_NAME[item]}을(를) 놓았습니다.`); mountAltar(box, d);
        } catch (err) { btn.disabled = false; btn.textContent = "여기에 놓기"; toast(err.message, 4000); }
      };
      let drag = null;   // 끌기(손가락·마우스) — 판 안에서만
      ghost.addEventListener("pointerdown", (ev) => { drag = ev.pointerId; ghost.setPointerCapture(ev.pointerId); ghost.classList.add("dragging"); ev.preventDefault(); });
      ghost.addEventListener("pointermove", (ev) => {
        if (drag !== ev.pointerId) return;
        const r = board.getBoundingClientRect();
        p.x = Math.round(clamp((ev.clientX - r.left) / r.width * 100, 4, 96) * 10) / 10; p.y = Math.round(clamp((ev.clientY - r.top) / r.height * 100, 6, 94) * 10) / 10; place();
      });
      const end = (ev) => { if (drag === ev.pointerId) { drag = null; ghost.classList.remove("dragging"); } };
      ghost.addEventListener("pointerup", end); ghost.addEventListener("pointercancel", end);
      ghost.addEventListener("keydown", (ev) => {
        const step = ev.shiftKey ? 6 : 2, k = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[ev.key];
        if (!k) return; ev.preventDefault(); p.x = clamp(p.x + k[0], 4, 96); p.y = clamp(p.y + k[1], 6, 94); place();
      });
      ghost.focus({ preventScroll: true });
      board.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  return { mountAltar, mountMusic, homeMusic, playSong, stopSong, onLiveStart, onLiveEnd };
}
