// 가족·직원 아이디·비밀번호 로그인 (2026-10-14).
// 가족: 받은 초대 토큰을 가족 화면과 같은 자리(localStorage family_token)에 두고 처음 화면으로.
// 직원: 받은 직원 토큰을 관리자 콘솔의 키 자리(sessionStorage admin_key)에 두고 콘솔로. 탭을 닫으면 지워진다.
(() => {
  const $ = (s) => document.querySelector(s);
  const form = $("#loginForm"), msg = $("#loginMsg"), btn = $("#loginBtn");
  let kind = new URLSearchParams(location.search).get("as") === "staff" ? "staff" : "family";

  function setKind(k) {
    kind = k;
    for (const t of document.querySelectorAll(".login-tabs [role=tab]")) {
      const on = t.dataset.kind === k;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
    }
    form.setAttribute("aria-labelledby", k === "staff" ? "tabStaff" : "tabFamily");
    $("#helpFamily").hidden = k !== "family";
    $("#helpStaff").hidden = k !== "staff";
    $("#demoHint").classList.toggle("is-off", k !== "family");
    msg.textContent = "";
  }
  document.querySelectorAll(".login-tabs [role=tab]").forEach((t) => {
    t.addEventListener("click", () => setKind(t.dataset.kind));
    t.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const next = kind === "family" ? "staff" : "family";
      setKind(next);
      $(next === "staff" ? "#tabStaff" : "#tabFamily").focus();
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const login_id = $("#loginId").value.trim(), password = $("#loginPw").value;
    if (!login_id || !password) { msg.textContent = "아이디와 비밀번호를 넣어 주세요."; return; }
    btn.disabled = true; btn.textContent = "확인하는 중…"; msg.textContent = "";
    try {
      const r = await fetch(`/api/login/${kind}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ login_id, password }) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "로그인하지 못했습니다.");
      if (kind === "family") {
        localStorage.setItem("family_token", data.token);
        location.replace("/");
      } else {
        sessionStorage.setItem("admin_key", data.token);
        location.replace("/admin");
      }
    } catch (err) {
      msg.textContent = typeof err.message === "string" ? err.message : "로그인하지 못했습니다.";
      btn.disabled = false; btn.textContent = "로그인";
      $("#loginPw").select();
    }
  });

  // 공개 시연·내 컴퓨터 시연에서만 시연 가족 계정을 알려 준다(서버가 아니면 404).
  fetch("/api/login/hint").then((r) => (r.ok ? r.json() : null)).then((h) => {
    if (!h) return;
    $("#demoMember").textContent = h.member; $("#demoId").textContent = h.login_id; $("#demoPw").textContent = h.password;
    $("#demoHint").hidden = false;
    $("#demoFill").addEventListener("click", () => { setKind("family"); $("#loginId").value = h.login_id; $("#loginPw").value = h.password; btn.focus(); });
  }).catch(() => {});

  setKind(kind);
})();
