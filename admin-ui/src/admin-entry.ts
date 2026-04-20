/** When Node is available: `npm run build` in admin-ui/ emits ../backend/static/dist/admin.js (and CSS if admin.css is imported). */
// import "./admin.css";

type PlanRow = Record<string, unknown>;

function qs<T extends HTMLElement>(sel: string): T | null {
  return document.querySelector(sel) as T | null;
}

type BsOffcanvasLike = { show: () => void; hide: () => void };

function getBsOffcanvas(panel: HTMLElement): BsOffcanvasLike | null {
  const bs = (window as unknown as { bootstrap?: { Offcanvas?: { getOrCreateInstance?: (el: HTMLElement) => BsOffcanvasLike } } }).bootstrap;
  if (!bs?.Offcanvas?.getOrCreateInstance) return null;
  return bs.Offcanvas.getOrCreateInstance(panel);
}

function initPlanDrawer(): void {
  const raw = document.getElementById("maestro-admin-plans-json");
  if (!raw || !raw.textContent?.trim()) return;
  let plans: PlanRow[];
  try {
    plans = JSON.parse(raw.textContent) as PlanRow[];
  } catch {
    return;
  }
  const backdrop = qs<HTMLElement>("#plan-details-offcanvas-backdrop");
  const panel = qs<HTMLElement>("#plan-details-offcanvas");
  const closeBtn = qs<HTMLButtonElement>("#plan-drawer-close");
  if (!backdrop || !panel) return;

  function setOpen(open: boolean): void {
    backdrop.classList.toggle("is-open", open);
    panel.classList.toggle("is-open", open);
    backdrop.setAttribute("aria-hidden", open ? "false" : "true");
    panel.setAttribute("aria-hidden", open ? "false" : "true");
    document.body.style.overflow = open ? "hidden" : "";
  }

  function setVal(id: string, v: string | number | null | undefined): void {
    const el = qs<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(id);
    if (!el) return;
    el.value = v == null ? "" : String(v);
  }

  function fillPlan(plan: PlanRow): void {
    setVal("#plan-drawer-plan-id", String(plan.id ?? ""));
    const typeSel = qs<HTMLSelectElement>("#plan-drawer-type");
    if (typeSel) typeSel.value = String(plan.plan_type ?? "monthly");
    setVal("#plan-drawer-list-price", String(plan.list_price ?? ""));
    setVal("#plan-drawer-session-limit", plan.session_limit == null ? "" : String(plan.session_limit));

    setVal("#discount-mode-plan-drawer", String(plan.discount_mode ?? "none"));
    setVal("#discount-pct-plan-drawer", plan.discount_percent == null ? "" : String(plan.discount_percent));
    const fixedPrice =
      plan.discount_mode === "fixed" && plan.price != null ? String(plan.price) : "";
    setVal("#reduced-price-plan-drawer", fixedPrice);
    setVal("#schedule-type-plan-drawer", String(plan.discount_schedule_type ?? "always"));
    setVal("#valid-from-plan-drawer", plan.discount_valid_from ? String(plan.discount_valid_from) : "");
    setVal("#valid-until-plan-drawer", plan.discount_valid_until ? String(plan.discount_valid_until) : "");
    setVal(
      "#duration-hours-plan-drawer",
      plan.discount_duration_hours == null ? "" : String(plan.discount_duration_hours),
    );

    const wrap = qs<HTMLElement>('[data-discount-suffix="plan-drawer"]');
    if (wrap) {
      const hs = wrap.querySelector<HTMLInputElement>('input[name="discount_hour_start"]');
      const he = wrap.querySelector<HTMLInputElement>('input[name="discount_hour_end"]');
      if (hs) hs.value = plan.discount_hour_start == null ? "" : String(plan.discount_hour_start);
      if (he) he.value = plan.discount_hour_end == null ? "" : String(plan.discount_hour_end);
    }

    qs<HTMLSelectElement>("#discount-mode-plan-drawer")?.dispatchEvent(new Event("change", { bubbles: true }));
    qs<HTMLInputElement>("#plan-drawer-list-price")?.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.querySelectorAll(".js-plan-drawer-open").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number((btn as HTMLElement).getAttribute("data-plan-id"));
      const plan = plans.find((p) => Number(p.id) === id);
      if (!plan) return;
      fillPlan(plan);
      setOpen(true);
    });
  });

  function close(): void {
    setOpen(false);
  }
  closeBtn?.addEventListener("click", close);
  backdrop.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (panel.classList.contains("is-open")) close();
  });
}

initPlanDrawer();

function initPublicUserDrawer(): void {
  const panel = qs<HTMLElement>("#pub-user-drawer-panel");
  const meta = qs<HTMLElement>("#pub-user-drawer-meta");
  const title = qs<HTMLElement>("#pub-user-drawer-title");
  if (!panel) return;
  const drawer = getBsOffcanvas(panel);

  function fill(uid: string, active: string, verified: string, name: string, email: string): void {
    panel.querySelectorAll<HTMLInputElement>(".js-pub-drawer-user-id").forEach((inp) => {
      inp.value = String(uid);
    });
    if (title) title.textContent = name ? `إجراءات: ${name}` : "إجراءات المستخدم";
    if (meta) meta.textContent = email ? `المعرف #${uid} · ${email}` : `المعرف #${uid}`;

    const btnA = qs<HTMLButtonElement>("#pub-drawer-btn-toggle-active");
    if (btnA) btnA.textContent = active === "1" ? "تعطيل الحساب" : "تفعيل الحساب";
    const btnV = qs<HTMLButtonElement>("#pub-drawer-btn-toggle-verified");
    if (btnV) btnV.textContent = verified === "1" ? "إلغاء توثيق البريد" : "توثيق البريد";

    const resendForm = qs<HTMLElement>("#pub-drawer-form-resend");
    if (resendForm) resendForm.style.display = verified === "1" ? "none" : "block";
  }

  document.body.addEventListener("click", (e) => {
    const btn = (e.target as HTMLElement | null)?.closest?.(".js-pub-user-drawer-open");
    if (!btn) return;
    fill(
      btn.getAttribute("data-user-id") || "",
      btn.getAttribute("data-active") || "0",
      btn.getAttribute("data-verified") || "0",
      btn.getAttribute("data-user-name") || "",
      btn.getAttribute("data-user-email") || "",
    );
    drawer?.show();
  });
}

function initTrashUserDrawer(): void {
  const panel = qs<HTMLElement>("#trash-user-drawer-panel");
  const meta = qs<HTMLElement>("#trash-user-drawer-meta");
  const title = qs<HTMLElement>("#trash-user-drawer-title");
  if (!panel) return;
  const drawer = getBsOffcanvas(panel);

  document.body.addEventListener("click", (e) => {
    const btn = (e.target as HTMLElement | null)?.closest?.(".js-trash-user-drawer-open");
    if (!btn) return;
    const uid = btn.getAttribute("data-user-id") || "";
    const name = btn.getAttribute("data-user-name") || "";
    const email = btn.getAttribute("data-user-email") || "";
    panel.querySelectorAll<HTMLInputElement>(".js-trash-drawer-user-id").forEach((inp) => {
      inp.value = uid;
    });
    if (title) title.textContent = name ? `سلة المحذوفات: ${name}` : "إجراءات سلة المحذوفات";
    if (meta) meta.textContent = email ? `#${uid} · ${email}` : `المعرف #${uid}`;
    drawer?.show();
  });
}

initPublicUserDrawer();
initTrashUserDrawer();

document.body.addEventListener("htmx:afterSwap", (e) => {
  const ev = e as CustomEvent<{ target?: HTMLElement }>;
  const t = ev.detail?.target;
  if (t && t.id === "trash-users-deferred") {
    const el = document.getElementById("trash-users-select-all") as HTMLInputElement | null;
    if (el) el.checked = false;
  }
});
