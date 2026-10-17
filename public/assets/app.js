const DATA_BASE = (() => {
  const p = window.location.pathname;
  if (p.includes("/requirement-trendradar/")) {
    return "/requirement-trendradar/data";
  }
  return "/data";
})();

export async function loadJson(name) {
  const res = await fetch(`${DATA_BASE}/${name}`);
  if (!res.ok) throw new Error(`Failed to load ${name}: ${res.status}`);
  return res.json();
}

export function qs(sel, root = document) {
  return root.querySelector(sel);
}

export function qsa(sel, root = document) {
  return [...root.querySelectorAll(sel)];
}

export function setActiveNav() {
  const page = document.body.dataset.page;
  qsa("nav a").forEach((a) => {
    if (a.dataset.page === page) a.classList.add("active");
  });
}

export function verdictBadge(v) {
  return `<span class="badge badge-${v}">${v}</span>`;
}

export function todayHK() {
  const now = new Date();
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  const hk = new Date(utc + 8 * 3600000);
  return hk.toISOString().slice(0, 10);
}

export function formatMetaDisplay(iso) {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (m) return `${m[1]} ${m[2]}`;
  return iso.slice(0, 16);
}

export async function renderSiteMetaBar() {
  const el = document.getElementById("site-meta-bar");
  if (!el) return;
  try {
    const meta = await loadJson("meta.json");
    const when = formatMetaDisplay(meta.updated_at);
    let html = `数据更新于 <strong>${when}</strong>（${meta.timezone_label || "香港"}）`;
    if (meta.trends_demo_active) {
      html += ` · <span class="status-partial">Trends 为演示数据</span>`;
    }
    if (meta.last_run_failed) {
      html += ` · <span class="status-fail">最近一次流水线失败（见 <a href="runs.html">Runs</a> / GitHub Actions）</span>`;
    }
    if (meta.job_leads_updated_at) {
      const jl = meta.job_leads_count ?? 0;
      const rec = meta.job_leads_recommend_count ?? 0;
      html += ` · 接单帖 <a href="jobs.html">${jl}</a>（推荐 ${rec}）`;
      if (meta.fiverr_skipped) {
        html += ` · <span class="status-partial">Fiverr 已跳过</span>`;
      }
    }
    html += ` · 调度 <code>${meta.schedule || "every_4h"}</code>`;
    el.innerHTML = html;
  } catch {
    el.innerHTML = `<span class="status-fail">无法加载 meta.json</span>`;
  }
}

export function initWeeklyTabs(root = document) {
  const tabs = qsa(".weekly-tabs button", root);
  const panels = qsa(".weekly-panel", root);
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      tabs.forEach((b) => b.classList.toggle("active", b === btn));
      panels.forEach((p) => p.classList.toggle("active", p.dataset.panel === target));
    });
  });
}
