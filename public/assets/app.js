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

export function isTodayCard(card) {
  const t = todayHK();
  return (card.created_at || "").startsWith(t) || (card.updated_at || "").includes(t.replace(/-/g, "-"));
}
