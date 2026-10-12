// 현장 화면(/screen?ritual=ID&key=관리자키): 제례 공간 TV에 띄운다. 영상 + 지금 순서 + 봉행 순서 + 가족 메시지·반응.
import { playReaction } from "./dream.js?v=20261012-3";
const qs = new URLSearchParams(location.search);
const KEY = qs.get("key") || sessionStorage.getItem("admin_key") || "";
const RID = +qs.get("ritual");
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtD = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`; };
async function api(path) { const r = await fetch(path, { headers: { "X-Admin-Key": KEY } }); if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText); return r.json(); }

let since = 0, rseq = -1, tts = false;
const counts = {};
$("#ttsBtn").onclick = () => { tts = !tts; $("#ttsBtn").textContent = `가족 메시지 읽어 주기 · ${tts ? "켜짐" : "꺼짐"}`; $("#ttsBtn").setAttribute("aria-pressed", String(tts)); if (tts) speak("가족 메시지를 읽어 드립니다."); };
function speak(text) { try { const u = new SpeechSynthesisUtterance(text); u.lang = "ko-KR"; u.rate = 0.95; speechSynthesis.speak(u); } catch {} }
function float(emoji) { playReaction($("#fx"), emoji); }   // 합장·촛불·헌화·마음 Lottie
function addMsg(m) {
  const d = document.createElement("div"); d.className = `live-msg ${m.sender === "site" ? "site" : ""} ${m.kind === "notice" ? "notice" : ""}`;
  d.innerHTML = `<b>${esc(m.author)}</b> ${esc(m.message)}`; const box = $("#msgs"); box.appendChild(d); while (box.children.length > 7) box.firstChild.remove();
  if (tts && m.sender === "family") speak(`${m.author}: ${m.message}`);
}
async function poll() {
  $("#videoWait").hidden = $("#video").naturalWidth > 0;   // 영상 첫 장면이 들어오면 대기 안내를 숨긴다
  let d; try { d = await api(`/api/admin/rituals/${RID}/live?since=${since}&rseq=${rseq}`); } catch (e) { $("#title").textContent = `현장 정보를 불러오지 못했습니다. ${e.message}`; return; }
  $("#title").textContent = d.title; $("#viewers").textContent = `${d.viewer_count}명 함께 참배 중`;
  d.messages.forEach((m) => { since = Math.max(since, m.id); addMsg(m); });
  d.reactions.forEach((x) => { if (x.seq > rseq) { rseq = x.seq; float(x.emoji); counts[x.emoji] = (counts[x.emoji] || 0) + 1; } });
  if (d.rseq > rseq) rseq = d.rseq;
  $("#counts").innerHTML = Object.entries(counts).map(([e, n]) => `<span>${e} ${n}</span>`).join("");
  const now = d.current;
  $("#now").innerHTML = now
    ? `<div class="k">지금 봉행 ${d.current_order} / ${d.order.length}</div><div class="name">${esc(now.deceased_name)} 님</div><div class="dates">${esc(fmtD(now.birth_date))} ~ ${esc(fmtD(now.death_date))}</div><div class="mourner">상주 ${esc(now.mourner_name || "-")}</div>`
    : `<div class="k">봉행 순서</div><div class="name">${d.order.length ? (d.current_order === 0 ? "곧 시작합니다" : "봉행을 마쳤습니다") : "준비하고 있습니다"}</div>`;
  $("#order").innerHTML = d.order.map((p) => `<div class="live-order-row ${p.order_no === d.current_order ? "now" : ""}"><span class="no">${p.order_no || "-"}</span><div><b>${esc(p.deceased_name)} 님</b> <span class="muted">${esc(fmtD(p.birth_date))} ~ ${esc(fmtD(p.death_date))}</span><div class="muted" style="font-size:14px">상주 ${esc(p.mourner_name || "-")}</div></div></div>`).join("");
}
if (!RID || !KEY) { $("#title").textContent = "관리자 콘솔의 진행 콘솔에서 '현장 화면 열기'로 열어 주세요."; $("#videoWait").firstChild.textContent = "열 일정을 찾지 못했습니다."; }
else {
  $("#video").src = `/api/admin/rituals/${RID}/stream?key=${encodeURIComponent(KEY)}&_=${Date.now()}`;
  $("#video").onload = () => { $("#videoWait").hidden = true; };
  $("#video").addEventListener("error", () => { $("#videoWait").hidden = false; });
  $("#video").onerror = () => setTimeout(() => { $("#video").src = `/api/admin/rituals/${RID}/stream?key=${encodeURIComponent(KEY)}&_=${Date.now()}`; }, 3000);
  poll(); setInterval(poll, 2000);
}
