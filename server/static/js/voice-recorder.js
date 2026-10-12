// 목소리 등록 창 (2026-10-12). 유족 앱(설정 → 목소리 등록)과 관리자 콘솔(고인 편집 → 복제 음성)이 함께 쓴다.
// ① 실시간 녹음: 소리 크기 막대, 여러 번 나눠 녹음해 모으기(3초 미만은 버림, 한 번에 최대 3분)
// ② 파일 올리기: 여러 개·여러 형식(음성·영상), 고르기·끌어 놓기
// 모은 자료는 한 번에 올리고(진행률), 서버가 모두 mp3 로 바꿔 합친 뒤 목소리를 만든다(server/voice.py).
const fmtSec = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const escHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const VOICE_ACCEPT = ".mp3,.m4a,.aac,.wav,.wave,.flac,.ogg,.oga,.opus,.webm,.weba,.wma,.amr,.3gp,.3ga,.3g2,.caf,.aif,.aiff,.aifc,.mka,.spx,.mp4,.m4v,.mov,.mkv,.avi,.wmv,.mpeg,.mpg,.ts,audio/*,video/*";
export const VOICE_FORMATS = "mp3 · m4a · aac · wav · flac · ogg · opus · webm · wma · amr · 3gp · caf · aiff, 영상(mp4 · mov · mkv · avi 등)";
export const VOICE_SCRIPT_DEFAULT = `<b>1분 정도, 평소 말투로 편하게</b> 이야기해 주세요. 조용한 곳에서, 휴대폰을 입에서 한 뼘쯤 떨어뜨리고요.`;

/**
 * opts: {
 *   modal(html) → 창 요소, toast(msg, ms),
 *   title, formats, accept, maxMB, minSeconds, providerReady,
 *   script: 녹음 안내 글(HTML), consentFields: true 면 서명자 이름·관계 칸을 보여 준다(관리자 콘솔, 동의서가 없을 때),
 *   upload: { url, headers }  — FormData(file 여러 개, kind, agree, note, signer_name, relation)를 POST,
 *   onDone(result)
 * }
 */
export function openVoiceRecorder(opts) {
  const esc = escHtml, toast = opts.toast || ((m) => alert(m));
  const minSeconds = opts.minSeconds || 15, maxMB = opts.maxMB || 100, script = opts.script || VOICE_SCRIPT_DEFAULT;
  const canRecord = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  const m = opts.modal(`<div class="voice-rec"><h2>${esc(opts.title || "목소리 등록")}</h2>
    <div class="seg" style="margin-bottom:12px" role="group" aria-label="누구의 목소리인가요"><button class="active" type="button" data-kind="lifetime_record">본인이 직접 녹음<br><small>생전 기록</small></button><button type="button" data-kind="voice">고인의 음성 자료<br><small>가족 동의</small></button></div>
    <div class="seg voice-tabs" role="tablist" aria-label="자료 넣는 방법"><button class="active" type="button" role="tab" aria-selected="true" data-vtab="rec">실시간 녹음</button><button type="button" role="tab" aria-selected="false" data-vtab="file">파일 올리기</button></div>
    <section data-vpanel="rec" class="voice-panel">
      <div class="script" data-vscript>${script}</div>
      ${canRecord ? `<div class="rec-time" data-vtime>0:00</div>
        <div class="level" aria-hidden="true"><i data-vlevel></i></div>
        <button class="rec-btn" data-vrecbtn type="button" aria-label="녹음 시작">녹음</button>
        <p class="muted center" data-vhint role="status">녹음 단추를 누르면 시작합니다. 여러 번 나눠 녹음해도 모두 합쳐 씁니다.</p>`
      : `<div class="notice">이 화면에서는 마이크 녹음을 쓸 수 없습니다(보안 연결 주소 https 나 이 컴퓨터에서 열면 됩니다). 휴대폰 녹음 앱으로 녹음한 뒤 ‘파일 올리기’를 써 주세요.</div>`}
    </section>
    <section data-vpanel="file" class="voice-panel" hidden>
      <label class="drop" data-vdrop><input type="file" data-vfile accept="${esc(opts.accept || VOICE_ACCEPT)}" multiple hidden>
        <b>음성·영상 파일을 고르거나 여기에 끌어다 놓으세요</b><span class="muted">여러 개를 한꺼번에 올릴 수 있습니다 · 파일 하나 ${maxMB}MB까지</span>
        <span class="muted" style="font-size:14px">${esc(opts.formats || VOICE_FORMATS)}</span></label>
      <p class="muted" style="font-size:14px;margin:6px 0 0">휴대폰 영상·음성 메시지·통화 녹음처럼 <b>그분 목소리가 또렷한 부분</b>이 좋습니다. 여러 사람이 함께 말하거나 음악이 큰 파일은 품질이 떨어집니다. 영상은 소리만 꺼내 씁니다.</p>
    </section>
    <h3 style="margin:14px 0 4px">모은 자료 <span class="muted" data-vtotal></span></h3>
    <ul class="voice-items" data-vitems><li class="muted">아직 없습니다. 녹음하거나 파일을 올려 주세요.</li></ul>
    ${opts.consentFields ? `<div class="row" style="gap:8px;flex-wrap:wrap;margin-top:12px"><div class="field" style="flex:1 1 160px"><label>동의한 분 이름</label><input data-vsigner autocomplete="off"></div><div class="field" style="flex:1 1 120px"><label>고인과의 관계</label><input data-vrelation placeholder="예: 큰딸" autocomplete="off"></div></div>` : ""}
    <div class="check" style="margin-top:12px"><input type="checkbox" id="vAgreeBox"><label for="vAgreeBox" style="margin:0;color:var(--ink)" data-vagreetext>${opts.consentFields ? "이 목소리를 인공지능 대화에만 쓰는 것에 대해 위 분께 동의를 받았습니다(서면 동의서 보관)." : "이 목소리가 인공지능 대화에만 쓰이는 것에 본인으로서 동의합니다. 언제든 삭제할 수 있습니다."}</label></div>
    <div class="field"><label for="vNoteBox">메모(선택)</label><input id="vNoteBox"><small class="muted">예: 2026년 추석에 녹음</small></div>
    <div class="progress" data-vprog hidden><i></i></div>
    <button data-vgo type="button" disabled>${opts.providerReady ? "이 자료로 목소리 등록" : "자료와 동의 저장"}</button><p class="muted center" data-vout role="status" style="margin-top:8px"></p></div>`);
  const $ = (sel) => m.querySelector(sel);
  let kind = "lifetime_record", rec = null, stream = null, t0 = 0, timer = null, meter = null, busy = false;
  const items = [];   // { blob, name, secs, kind: 'rec'|'file', url }
  const out = (msg) => { $("[data-vout]").textContent = msg; };
  const total = () => items.reduce((a, x) => a + (x.secs || 0), 0);
  const ready = () => {
    const known = items.every((x) => x.secs != null), t = total();
    $("[data-vtotal]").textContent = items.length ? `${items.length}개 · ${known ? "" : "약 "}${fmtSec(t)}${known && t < minSeconds ? ` — ${minSeconds}초 이상 필요` : ""}` : "";
    const signerOk = !opts.consentFields || ($("[data-vsigner]").value.trim() !== "");
    $("[data-vgo]").disabled = busy || !items.length || !$("#vAgreeBox").checked || !signerOk || (known && t < minSeconds);
  };
  const paint = () => {
    const ul = $("[data-vitems]");
    if (!items.length) { ul.innerHTML = '<li class="muted">아직 없습니다. 녹음하거나 파일을 올려 주세요.</li>'; ready(); return; }
    ul.innerHTML = items.map((x, i) => `<li><span class="vi-name">${x.kind === "rec" ? "녹음" : "파일"} · ${esc(x.name)}</span><span class="muted">${x.secs != null ? fmtSec(x.secs) : "길이는 올린 뒤 확인"} · ${(x.blob.size / 1024 / 1024).toFixed(1)}MB</span>
      <audio controls preload="metadata" src="${x.url}"></audio><button class="small ghost" type="button" data-vrm="${i}">빼기</button></li>`).join("");
    ul.querySelectorAll("[data-vrm]").forEach((b) => b.onclick = () => { const [x] = items.splice(+b.dataset.vrm, 1); URL.revokeObjectURL(x.url); paint(); });
    ready();
  };
  const probe = (blob) => new Promise((res) => {   // 브라우저가 읽을 수 있으면 길이를 미리 잰다(wma·amr 등은 서버에서)
    const el = document.createElement(blob.type.startsWith("video/") ? "video" : "audio"); const url = URL.createObjectURL(blob);
    let done = false; const fin = (s) => { if (done) return; done = true; URL.revokeObjectURL(url); res(Number.isFinite(s) && s > 0 ? s : null); };
    el.preload = "metadata"; el.onloadedmetadata = () => fin(el.duration); el.onerror = () => fin(null); setTimeout(() => fin(null), 4000); el.src = url;
  });
  const addBlob = async (blob, name, kindOf, secs) => {
    if (blob.size > maxMB * 1024 * 1024) { toast(`‘${name}’은 ${(blob.size / 1024 / 1024).toFixed(0)}MB라 너무 큽니다. ${maxMB}MB 이하로 올려 주세요.`, 5000); return; }
    if (items.length >= 10) { toast("자료는 10개까지 모을 수 있습니다.", 4000); return; }
    items.push({ blob, name, kind: kindOf, secs: secs ?? await probe(blob), url: URL.createObjectURL(blob) }); paint();
  };
  const showTab = (t) => {
    m.querySelectorAll("[data-vtab]").forEach((b) => { const on = b.dataset.vtab === t; b.classList.toggle("active", on); b.setAttribute("aria-selected", String(on)); });
    m.querySelectorAll("[data-vpanel]").forEach((p) => { p.hidden = p.dataset.vpanel !== t; });
  };
  m.querySelectorAll("[data-vtab]").forEach((b) => b.onclick = () => showTab(b.dataset.vtab));
  m.querySelectorAll("[data-kind]").forEach((b) => b.onclick = () => {
    m.querySelectorAll("[data-kind]").forEach((x) => x.classList.remove("active")); b.classList.add("active"); kind = b.dataset.kind;
    if (!opts.consentFields) $("[data-vagreetext]").textContent = kind === "lifetime_record" ? "이 목소리가 인공지능 대화에만 쓰이는 것에 본인으로서 동의합니다. 언제든 삭제할 수 있습니다." : "가족 대표로서 고인의 음성을 인공지능 대화에만 쓰는 것에 동의합니다. 다른 가족이 반대하면 즉시 삭제하겠습니다.";
    $("[data-vscript]").innerHTML = kind === "lifetime_record" ? script : "고인의 목소리를 녹음기로 다시 녹음하기보다는 <b>‘파일 올리기’</b>로 원본 파일(휴대폰 영상·음성 메시지·통화 녹음)을 올리는 편이 훨씬 깨끗합니다.";
    if (kind === "voice") showTab("file");
  });
  $("#vAgreeBox").onchange = ready;
  if (opts.consentFields) $("[data-vsigner]").oninput = ready;
  // 파일: 고르기·끌어 놓기
  const takeFiles = async (list) => { for (const f of list) await addBlob(f, f.name, "file"); out(""); };
  $("[data-vfile]").onchange = (e) => { takeFiles([...e.target.files]); e.target.value = ""; };
  const drop = $("[data-vdrop]");
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => takeFiles([...(e.dataTransfer?.files || [])]));
  // 녹음: 소리 크기 표시 + 여러 번 녹음
  const stopMeter = () => { if (meter) { cancelAnimationFrame(meter.raf); try { meter.ctx.close(); } catch {} meter = null; } const lv = $("[data-vlevel]"); if (lv) lv.style.width = "0%"; };
  const startMeter = (s) => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)(); const an = ctx.createAnalyser(); an.fftSize = 1024;
      ctx.createMediaStreamSource(s).connect(an); const buf = new Float32Array(an.fftSize); const lv = $("[data-vlevel]");
      const tick = () => { an.getFloatTimeDomainData(buf); let sum = 0; for (const x of buf) sum += x * x; const rms = Math.sqrt(sum / buf.length);
        lv.style.width = Math.min(100, Math.round(rms * 400)) + "%"; lv.classList.toggle("loud", rms > 0.22); meter.raf = requestAnimationFrame(tick); };
      meter = { ctx, raf: requestAnimationFrame(tick) };
    } catch { /* 소리 크기 표시는 없어도 녹음은 된다 */ }
  };
  if (canRecord) {
    const btn = $("[data-vrecbtn]"), time = $("[data-vtime]"), hint = $("[data-vhint]");
    btn.onclick = async () => {
      if (rec && rec.state === "recording") { rec.stop(); return; }
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
      catch { return toast("마이크 사용 허락이 필요합니다. 주소창 옆 마이크 표시를 눌러 허락해 주세요.", 5000); }
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus", "audio/ogg"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
      const chunks = []; rec = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: 128000 } : undefined);
      rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop()); clearInterval(timer); stopMeter(); btn.classList.remove("on"); btn.textContent = "녹음"; btn.setAttribute("aria-label", "녹음 시작");
        const secs = (Date.now() - t0) / 1000, type = rec.mimeType || mime || "audio/webm"; const b = new Blob(chunks, { type });
        const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
        if (secs < 3) { hint.textContent = "너무 짧아 담지 않았습니다. 3초 이상 말씀해 주세요."; return; }
        addBlob(b, `녹음 ${items.filter((x) => x.kind === "rec").length + 1}.${ext}`, "rec", secs);
        hint.textContent = `${Math.round(secs)}초를 담았습니다. 더 녹음하거나, 아래에서 들어 보고 등록해 주세요.`;
      };
      rec.start(250); t0 = Date.now(); startMeter(stream); btn.classList.add("on"); btn.textContent = "마치기"; btn.setAttribute("aria-label", "녹음 마치기");
      hint.textContent = "녹음하는 중입니다. 막대가 움직이면 소리가 잘 들어가고 있습니다. 다 말씀하셨으면 마치기를 눌러 주세요.";
      timer = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); time.textContent = fmtSec(s); time.classList.toggle("short", total() + s < minSeconds); if (s >= 180) rec.stop(); }, 250);
    };
  }
  const cleanup = () => { try { if (rec && rec.state === "recording") rec.stop(); } catch {} stopMeter(); items.forEach((x) => URL.revokeObjectURL(x.url)); };
  new MutationObserver((_, ob) => { if (!m.isConnected) { cleanup(); ob.disconnect(); } }).observe(document.body, { childList: true });
  // 올리기(진행률 표시)
  $("[data-vgo]").onclick = async () => {
    if (busy || !items.length) return; busy = true; ready();
    const fd = new FormData(); fd.append("kind", kind); fd.append("agree", "true"); fd.append("note", $("#vNoteBox").value);
    if (opts.consentFields) { fd.append("signer_name", $("[data-vsigner]").value.trim()); fd.append("relation", $("[data-vrelation]").value.trim()); }
    Object.entries(opts.upload.fields || {}).forEach(([k, val]) => fd.append(k, val));
    items.forEach((x) => fd.append("file", x.blob, x.name));
    const prog = $("[data-vprog]"); prog.hidden = false; const bar = prog.querySelector("i");
    out("자료를 올리는 중입니다…");
    try {
      const r = await new Promise((resolve, reject) => {
        const x = new XMLHttpRequest(); x.open("POST", opts.upload.url);
        Object.entries(opts.upload.headers || {}).forEach(([k, val]) => x.setRequestHeader(k, val));
        x.upload.onprogress = (e) => { if (e.lengthComputable) { const p = Math.round((e.loaded / e.total) * 100); bar.style.width = p + "%"; if (p >= 100) out(opts.providerReady ? "올렸습니다. 소리를 다듬고 목소리를 만드는 중입니다… (1분쯤)" : "올렸습니다. 소리를 다듬어 저장하는 중입니다…"); } };
        x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch {} if (x.status >= 200 && x.status < 300) resolve(j); else reject(new Error(typeof j.detail === "string" ? j.detail : "자료를 처리하지 못했습니다.")); };
        x.onerror = () => reject(new Error("서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주세요."));
        x.send(fd);
      });
      m.remove();
      if (r.pending) toast(r.message || "자료와 동의를 저장했습니다.", 6000);
      else toast(`목소리를 등록했습니다 (자료 ${r.files}개${r.seconds ? ` · ${r.seconds}초` : ""}). 대화에서 바로 쓰입니다.`, 4500);
      opts.onDone?.(r);
    } catch (e) { out("목소리를 등록하지 못했습니다. " + e.message); prog.hidden = true; bar.style.width = "0%"; busy = false; ready(); }
  };
  return m;
}
