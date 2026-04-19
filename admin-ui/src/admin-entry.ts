/** When Node is available: `npm run build` in admin-ui/ emits ../backend/static/dist/admin.js (and CSS if admin.css is imported). */
// import "./admin.css";

type PlanRow = Record<string, unknown>;

function qs<T extends HTMLElement>(sel: string): T | null {
  return document.querySelector(sel) as T | null;
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
}

initPlanDrawer();

document.body.addEventListener("htmx:afterSwap", (e) => {
  const ev = e as CustomEvent<{ target?: HTMLElement }>;
  const t = ev.detail?.target;
  if (t && t.id === "trash-users-deferred") {
    const el = document.getElementById("trash-users-select-all") as HTMLInputElement | null;
    if (el) el.checked = false;
  }
});
