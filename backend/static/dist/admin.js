/**
 * Admin UI: plan details offcanvas + HTMX hooks.
 * Built target for Vite lives under admin-ui/; this file is the runtime fallback when npm is unavailable.
 */
function qs(sel) {
  return document.querySelector(sel);
}

function getBsOffcanvas(panel) {
  var bs = window.bootstrap;
  if (!bs || !bs.Offcanvas || !bs.Offcanvas.getOrCreateInstance) return null;
  return bs.Offcanvas.getOrCreateInstance(panel);
}

function initPlanDrawer() {
  var raw = document.getElementById("maestro-admin-plans-json");
  if (!raw || !raw.textContent || !raw.textContent.trim()) return;
  var plans;
  try {
    plans = JSON.parse(raw.textContent);
  } catch (_) {
    return;
  }
  var backdrop = qs("#plan-details-offcanvas-backdrop");
  var panel = qs("#plan-details-offcanvas");
  var closeBtn = qs("#plan-drawer-close");
  if (!backdrop || !panel) return;

  function setOpen(open) {
    backdrop.classList.toggle("is-open", open);
    panel.classList.toggle("is-open", open);
    backdrop.setAttribute("aria-hidden", open ? "false" : "true");
    panel.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function setVal(id, v) {
    var el = qs(id);
    if (!el) return;
    el.value = v == null ? "" : String(v);
  }

  function fillPlan(plan) {
    setVal("#plan-drawer-plan-id", String(plan.id != null ? plan.id : ""));
    var typeSel = qs("#plan-drawer-type");
    if (typeSel) typeSel.value = String(plan.plan_type || "monthly");
    setVal("#plan-drawer-list-price", String(plan.list_price != null ? plan.list_price : ""));
    setVal("#plan-drawer-session-limit", plan.session_limit == null ? "" : String(plan.session_limit));

    setVal("#discount-mode-plan-drawer", String(plan.discount_mode || "none"));
    setVal("#discount-pct-plan-drawer", plan.discount_percent == null ? "" : String(plan.discount_percent));
    var fixedPrice = plan.discount_mode === "fixed" && plan.price != null ? String(plan.price) : "";
    setVal("#reduced-price-plan-drawer", fixedPrice);
    setVal("#schedule-type-plan-drawer", String(plan.discount_schedule_type || "always"));
    setVal("#valid-from-plan-drawer", plan.discount_valid_from ? String(plan.discount_valid_from) : "");
    setVal("#valid-until-plan-drawer", plan.discount_valid_until ? String(plan.discount_valid_until) : "");
    setVal(
      "#duration-hours-plan-drawer",
      plan.discount_duration_hours == null ? "" : String(plan.discount_duration_hours),
    );

    var wrap = qs('[data-discount-suffix="plan-drawer"]');
    if (wrap) {
      var hs = wrap.querySelector('input[name="discount_hour_start"]');
      var he = wrap.querySelector('input[name="discount_hour_end"]');
      if (hs) hs.value = plan.discount_hour_start == null ? "" : String(plan.discount_hour_start);
      if (he) he.value = plan.discount_hour_end == null ? "" : String(plan.discount_hour_end);
    }

    var modeEl = qs("#discount-mode-plan-drawer");
    if (modeEl) modeEl.dispatchEvent(new Event("change", { bubbles: true }));
    var lp = qs("#plan-drawer-list-price");
    if (lp) lp.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.querySelectorAll(".js-plan-drawer-open").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = Number(btn.getAttribute("data-plan-id"));
      var plan = plans.find(function (p) {
        return Number(p.id) === id;
      });
      if (!plan) return;
      fillPlan(plan);
      setOpen(true);
    });
  });

  function close() {
    setOpen(false);
  }
  if (closeBtn) closeBtn.addEventListener("click", close);
  backdrop.addEventListener("click", close);
}

initPlanDrawer();

function initPublicUserDrawer() {
  var panel = qs("#pub-user-drawer-panel");
  var meta = qs("#pub-user-drawer-meta");
  var title = qs("#pub-user-drawer-title");
  if (!panel) return;
  var drawer = getBsOffcanvas(panel);

  function fill(uid, active, verified, name, email) {
    panel.querySelectorAll(".js-pub-drawer-user-id").forEach(function (inp) {
      inp.value = String(uid);
    });
    if (title) title.textContent = name ? "إجراءات: " + name : "إجراءات المستخدم";
    if (meta) meta.textContent = email ? "المعرف #" + uid + " · " + email : "المعرف #" + uid;

    var btnA = qs("#pub-drawer-btn-toggle-active");
    if (btnA) btnA.textContent = active === "1" ? "تعطيل الحساب" : "تفعيل الحساب";
    var btnV = qs("#pub-drawer-btn-toggle-verified");
    if (btnV) btnV.textContent = verified === "1" ? "إلغاء توثيق البريد" : "توثيق البريد";

    var resendForm = qs("#pub-drawer-form-resend");
    if (resendForm) resendForm.style.display = verified === "1" ? "none" : "block";
  }

  document.body.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest && e.target.closest(".js-pub-user-drawer-open");
    if (!btn) return;
    fill(
      btn.getAttribute("data-user-id") || "",
      btn.getAttribute("data-active") || "0",
      btn.getAttribute("data-verified") || "0",
      btn.getAttribute("data-user-name") || "",
      btn.getAttribute("data-user-email") || "",
    );
    if (drawer) drawer.show();
  });
}

function initTrashUserDrawer() {
  var panel = qs("#trash-user-drawer-panel");
  var meta = qs("#trash-user-drawer-meta");
  var title = qs("#trash-user-drawer-title");
  if (!panel) return;
  var drawer = getBsOffcanvas(panel);

  document.body.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest && e.target.closest(".js-trash-user-drawer-open");
    if (!btn) return;
    var uid = btn.getAttribute("data-user-id") || "";
    var name = btn.getAttribute("data-user-name") || "";
    var email = btn.getAttribute("data-user-email") || "";
    panel.querySelectorAll(".js-trash-drawer-user-id").forEach(function (inp) {
      inp.value = uid;
    });
    if (title) title.textContent = name ? "سلة المحذوفات: " + name : "إجراءات سلة المحذوفات";
    if (meta) meta.textContent = email ? "#" + uid + " · " + email : "المعرف #" + uid;
    if (drawer) drawer.show();
  });
}

initPublicUserDrawer();
initTrashUserDrawer();

document.body.addEventListener("htmx:afterSwap", function (e) {
  var t = e.detail && e.detail.target;
  if (t && t.id === "trash-users-deferred") {
    var el = document.getElementById("trash-users-select-all");
    if (el) el.checked = false;
  }
});
