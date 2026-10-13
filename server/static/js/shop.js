// 추모 서비스(유료) — 봉안함 헌화 · 선물하기 · 제사 상차림 · 기도 (2026-10-12). app.js 가 createShop 으로 만든다.
// 가격은 시연용 예시, 결제는 시연 결제다: 카드 번호 같은 결제 정보를 받지 않고 돈이 오가지 않는다. 금액은 서버가 계산한다.
// 흐름: 고르기 → 수량·날짜·의례·선물·요청 → 결제 방법 → 시연 결제 → 접수(영수 번호) → 직원 준비 → 완료 사진.

const ICON = {
  "flower-one": "/static/images/altar/chrysanthemum-white.svg", "flower-bouquet": "/static/images/altar/rose-white.svg",
  "flower-monthly": "/static/images/altar/lily.svg", "gift-frame": "/static/images/services/frame.svg",
  "gift-plant": "/static/images/services/plant.svg", "gift-letter": "/static/images/altar/text-love.svg",
  "table-simple": "/static/images/services/table.svg", "table-standard": "/static/images/services/table.svg",
  "table-full": "/static/images/services/table.svg", "prayer-memorial": "/static/images/altar/hands.svg",
  "prayer-lamp": "/static/images/services/lamp.svg",
};
const won = (n) => `${Number(n || 0).toLocaleString("ko-KR")}원`;
const STEPS = ["paid", "preparing", "done"];

export function createShop({ api, esc, toast, modal, withToken, fmtDT, fmtD, state, view, go }) {
  let catalog = null;
  async function loadCatalog() { if (!catalog) catalog = await api("/api/family/services"); return catalog; }

  async function page() {
    const preset = state.shopPreset || {}; state.shopPreset = null;
    view.innerHTML = `<div class="page-heading"><span class="eyebrow">추모 서비스</span><h1>마음을 대신 전해 드립니다</h1>
      <p class="muted">봉안함 헌화, 선물, 제사 상차림을 시설 직원이 정성껏 준비하고 사진으로 알려 드립니다.</p></div>
      <div class="notice demo-pay" role="note"><b>시연 결제</b> · 가격은 예시이며 실제 결제·청구가 일어나지 않습니다. 카드 번호 같은 결제 정보는 받지 않습니다.</div>
      <p class="free-line"><b>헌화·상차림을 주문하지 않아도</b> 원격 참배, 추도식 생중계, 추모 공간, 인공지능 대화는 추가 요금 없이 이용합니다. 아래는 원할 때만 고르는 선택 서비스입니다. <button type="button" class="link-btn" data-policy>안심 안내 · 요금표</button></p>
      <div id="shopBody" aria-live="polite"><p class="muted" role="status">서비스를 불러오는 중입니다…</p></div>`;
    view.querySelector("[data-policy]").onclick = () => { state.focus = "price"; go("policy"); };
    let cat, orders;
    try { [cat, orders] = await Promise.all([loadCatalog(), api("/api/family/orders")]); }
    catch (e) { $("#shopBody").innerHTML = `<div class="card" role="alert"><p>${esc(e.message)}</p></div>`; return; }
    const body = view.querySelector("#shopBody"); if (!body) return;
    const cats = [["all", "전체"], ...Object.entries(cat.categories)];
    body.innerHTML = `<div class="shop-chips" role="tablist" aria-label="서비스 분류">${cats.map(([id, name]) => `<button type="button" role="tab" class="chip" data-cat="${id}">${esc(name)}</button>`).join("")}</div>
      <div class="shop-grid" id="shopGrid"></div>
      <section class="card my-orders" id="myOrders" aria-labelledby="ordersTitle"><h2 id="ordersTitle">주문 내역</h2>${ordersHtml(orders)}</section>`;
    const grid = body.querySelector("#shopGrid");
    const show = (c) => {
      body.querySelectorAll("[data-cat]").forEach((b) => { const on = b.dataset.cat === c; b.classList.toggle("active", on); b.setAttribute("aria-selected", String(on)); });
      grid.innerHTML = cat.items.filter((s) => c === "all" || s.category === c).map((s) => `<article class="card svc">
        <img class="svc-icon" src="${ICON[s.id] || ICON["flower-one"]}" alt="">
        <div class="svc-body"><span class="svc-cat">${esc(s.category_name)}</span><h3>${esc(s.name)}</h3><p class="muted">${esc(s.desc)}</p>
          <div class="svc-foot"><b class="svc-price">${won(s.price)}<small> / ${esc(s.unit)}</small></b><button type="button" class="small" data-order="${esc(s.id)}">${s.gift ? "주문 · 선물" : "주문하기"}</button></div></div></article>`).join("");
      grid.querySelectorAll("[data-order]").forEach((b) => b.onclick = () => openOrder(cat.items.find((s) => s.id === b.dataset.order), preset));
    };
    body.querySelectorAll("[data-cat]").forEach((b) => b.onclick = () => show(b.dataset.cat));
    show(preset.category && cat.categories[preset.category] ? preset.category : "all");
    bindOrders(body);
  }

  function ordersHtml(orders) {
    if (!orders.length) return `<p class="muted">아직 주문이 없습니다. 위에서 마음을 전할 서비스를 골라 주세요.</p>`;
    return `<ul class="order-list">${orders.map((o) => {
      const at = STEPS.indexOf(o.status);
      const steps = ["접수", "준비 중", "완료"].map((t, i) => `<li class="${at >= i ? "on" : ""}">${t}</li>`).join("");
      return `<li class="order ${esc(o.status)}"><img class="svc-icon sm" src="${ICON[o.service] || ICON["flower-one"]}" alt="">
        <div class="order-body"><div class="row between"><b>${esc(o.service_name)}</b><span class="pill">${esc(o.status_name)}</span></div>
        <div class="muted meta">${esc(o.qty)}${esc(o.unit)} · ${won(o.total)} · ${esc(o.pay_method_name)} · ${esc(fmtDT(o.created_at))}</div>
        ${o.gift_to_name ? `<div class="gift-tag">${o.gift_for_me ? `${esc(o.member_name)} 님이 보낸 선물` : `${esc(o.gift_to_name)} 님께 보낸 선물`}${o.card_message ? ` · “${esc(o.card_message)}”` : ""}</div>` : !o.mine ? `<div class="muted meta">${esc(o.member_name)} 님 주문</div>` : ""}
        ${o.ritual_title ? `<div class="muted meta">의례: ${esc(o.ritual_title)} · ${esc(fmtDT(o.ritual_at))}</div>` : o.deliver_on ? `<div class="muted meta">봉행일: ${esc(fmtD(o.deliver_on))}</div>` : ""}
        ${["cancelled", "refunded"].includes(o.status) ? "" : `<ol class="order-steps">${steps}</ol>`}
        ${o.staff_note ? `<p class="staff-note">시설에서: ${esc(o.staff_note)}</p>` : ""}
        ${o.has_photo ? `<img class="order-photo" src="${withToken(`/api/family/orders/${o.id}/photo.jpg`)}" alt="${esc(o.service_name)} 완료 사진">` : ""}
        <div class="muted meta">영수 번호 ${esc(o.receipt)}</div>
        ${o.can_cancel ? `<button type="button" class="small ghost" data-cancel-order="${o.id}">주문 취소(시연 환불)</button>` : ""}</div></li>`;
    }).join("")}</ul>`;
  }
  function bindOrders(root) {
    root.querySelectorAll("[data-cancel-order]").forEach((b) => b.onclick = () => {
      const md = modal(`<h2>주문을 취소할까요?</h2><p>아직 준비를 시작하지 않은 주문이라 바로 취소됩니다. 시연이라 실제 환불 절차는 없습니다.</p><div class="modal-actions"><button class="secondary" type="button" data-no>그대로 두기</button><button type="button" data-yes>취소하기</button></div>`);
      md.querySelector("[data-no]").onclick = () => md.querySelector(".modal-close").click();
      md.querySelector("[data-yes]").onclick = async () => {
        try { await api(`/api/family/orders/${b.dataset.cancelOrder}/cancel`, { method: "POST" }); md.querySelector(".modal-close").click(); toast("주문을 취소했습니다(시연 환불)."); refreshOrders(); }
        catch (e) { toast(e.message, 4500); }
      };
    });
  }
  async function refreshOrders() {
    const box = view.querySelector("#myOrders"); if (!box) return;
    try { const orders = await api("/api/family/orders"); box.innerHTML = `<h2 id="ordersTitle">주문 내역</h2>${ordersHtml(orders)}`; bindOrders(box); } catch {}
  }

  async function openOrder(s, preset = {}) {
    const d = state.me.deceased[0];
    if (!d) { toast("고인 정보가 등록된 뒤 주문할 수 있습니다."); return; }
    let rituals = [];
    if (s.needs_ritual) { try { rituals = (await api("/api/family/rituals")).filter((r) => new Date(r.scheduled_at) > Date.now() - 86400000); } catch {} }
    const today = new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
    const md = modal(`<div class="order-form"><div class="order-head"><img class="svc-icon" src="${ICON[s.id] || ICON["flower-one"]}" alt=""><div><span class="svc-cat">${esc(s.category_name)}</span><h2>${esc(s.name)}</h2><p class="muted">${esc(s.desc)}</p></div></div>
      <div class="field"><span class="label">대상</span><p style="margin:0">${esc(d.name)} 님 · 봉안함 ${esc(state.me.niche?.code || "-")}</p></div>
      ${s.max_qty > 1 ? `<div class="field"><label for="odQty">수량</label><div class="qty"><button type="button" class="small ghost" data-q="-1" aria-label="하나 줄이기">−</button><input id="odQty" type="number" min="1" max="${s.max_qty}" value="1" inputmode="numeric"><span>${esc(s.unit)}</span><button type="button" class="small ghost" data-q="1" aria-label="하나 늘리기">+</button></div></div>` : ""}
      ${s.needs_ritual ? `<div class="field"><label for="odRitual">올릴 의례</label>${rituals.length ? `<select id="odRitual">${rituals.map((r) => `<option value="${r.id}" ${preset.ritual_id === r.id ? "selected" : ""}>${esc(fmtDT(r.scheduled_at))} · ${esc(r.title)}</option>`).join("")}</select>` : `<p class="muted" style="margin:0">다가오는 의례가 없습니다. 시설에 의례 일정을 먼저 문의해 주세요.</p>`}</div>` : ""}
      ${s.date ? `<div class="field"><label for="odDate">봉행 날짜 <small class="muted">(비워 두면 시설이 가까운 날 올립니다)</small></label><input id="odDate" type="date" min="${today}"></div>` : ""}
      ${s.gift ? `<div class="field"><label for="odGift">선물로 보내기 <small class="muted">(선택)</small></label><select id="odGift"><option value="">내 이름으로 올리기</option>${catalog.members.map((m) => `<option value="${m.id}">${esc(m.name)} 님께 선물 (${esc(m.relation)})</option>`).join("")}</select></div>
        <div class="field"><label for="odCard">메시지 카드 <small class="muted">(100자)</small></label><input id="odCard" maxlength="100" placeholder="예: 어머니, 늘 그립습니다"></div>` : ""}
      <div class="field"><label for="odNote">${s.letter ? "편지 내용 <small class=\"muted\">(1000자, 한지에 인쇄)</small>" : "요청 사항 <small class=\"muted\">(선택)</small>"}</label><textarea id="odNote" maxlength="${s.letter ? 1000 : 300}"></textarea></div>
      <fieldset class="field pay"><legend>결제 방법 <small class="muted">(시연)</small></legend>${Object.entries(catalog.pay_methods).map(([id, name], i) => `<label class="pay-opt"><input type="radio" name="odPay" value="${id}" ${i === 0 ? "checked" : ""}> ${esc(name)}</label>`).join("")}</fieldset>
      <div class="order-total"><span>합계</span><b id="odTotal">${won(s.price)}</b></div>
      <label class="check demo-ok"><input type="checkbox" id="odDemo"> 시연 결제이며 실제로 청구되지 않는다는 것을 확인했습니다.</label>
      <div class="modal-actions"><button type="button" class="secondary" data-close>닫기</button><button type="button" id="odPayBtn" disabled>${won(s.price)} 시연 결제하기</button></div></div>`);
    const qty = md.querySelector("#odQty"), payBtn = md.querySelector("#odPayBtn");
    const n = () => Math.min(s.max_qty, Math.max(1, Math.round(+(qty?.value || 1) || 1)));
    const total = () => { const t = won(s.price * n()); md.querySelector("#odTotal").textContent = t; payBtn.textContent = `${t} 시연 결제하기`; };
    md.querySelectorAll("[data-q]").forEach((b) => b.onclick = () => { qty.value = n() + +b.dataset.q; qty.value = n(); total(); });
    qty?.addEventListener("input", total);
    const noRitual = s.needs_ritual && !rituals.length;
    md.querySelector("#odDemo").onchange = (e) => { payBtn.disabled = !e.target.checked || noRitual; };
    md.querySelector("[data-close]").onclick = () => md.querySelector(".modal-close").click();
    payBtn.onclick = async () => {
      if (payBtn.disabled) return;
      payBtn.disabled = true; payBtn.textContent = "결제하는 중(시연)…";
      const body = { service: s.id, deceased_id: d.id, qty: n(), pay_method: md.querySelector("[name=odPay]:checked").value,
        ritual_id: s.needs_ritual ? +md.querySelector("#odRitual").value : null, deliver_on: md.querySelector("#odDate")?.value || null,
        gift_to: md.querySelector("#odGift")?.value ? +md.querySelector("#odGift").value : null,
        card_message: md.querySelector("#odCard")?.value.trim() || "", note: md.querySelector("#odNote").value.trim() };
      try {
        const o = await api("/api/family/orders", { method: "POST", body });
        md.querySelector(".modal-close").click();
        const done = modal(`<div class="paid-done"><span class="paid-mark" aria-hidden="true">✓</span><h2>결제가 끝났습니다 <small class="muted">(시연)</small></h2>
          <p>${esc(o.service_name)} · ${esc(o.qty)}${esc(o.unit)} · <b>${won(o.total)}</b></p>
          ${o.gift_to_name ? `<p>${esc(o.gift_to_name)} 님께 선물로 보냈습니다. 받는 분의 화면에도 보입니다.</p>` : ""}
          <p class="muted">시설에서 접수한 뒤 준비를 시작합니다. 준비가 끝나면 이 화면의 주문 내역에 완료 사진이 올라옵니다.</p>
          <p class="muted">영수 번호 ${esc(o.receipt)} · 실제 청구 없음</p></div><div class="modal-actions"><button type="button" data-ok>확인</button></div>`);
        done.querySelector("[data-ok]").onclick = () => done.querySelector(".modal-close").click();
        refreshOrders();
      } catch (e) { payBtn.disabled = false; total(); toast(`결제하지 못했습니다. ${e.message}`, 5000); }
    };
  }
  const $ = (sel) => view.querySelector(sel);
  return { page, openOrder };
}
