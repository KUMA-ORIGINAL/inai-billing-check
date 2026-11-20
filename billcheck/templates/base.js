/* Общие помощники страниц «Где мои деньги?». Встраивается в HTML при сборке. */
const $ = (sel, root = document) => root.querySelector(sel);
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") el.setAttribute("style", v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const fmt = cents => (cents / 100).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const plural = (n, forms) => {
  const m10 = n % 10, m100 = n % 100;
  return forms[m10 === 1 && m100 !== 11 ? 0 : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? 1 : 2];
};
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* приватный режим */ } }
};
const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
/** «2026-09-14 01:37:37» → «14 сентября, 01:37»; без времени → «14 сентября». */
function humanDate(iso, withTime = true) {
  const day = Number(iso.slice(8, 10)), month = MONTHS_GEN[Number(iso.slice(5, 7)) - 1];
  return withTime && iso.length > 10 ? `${day} ${month}, ${iso.slice(11, 16)}` : `${day} ${month}`;
}
/* Простые линейные иконки (24×24, обводка) по типу списания и находки */
const ICONS = {
  call: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2",
  sms: "M4 5h16v11H9l-5 4z",
  data: "M2 9a15 15 0 0 1 20 0M5.5 12.5a10 10 0 0 1 13 0M9 16a5 5 0 0 1 6 0M12 19.5h.01",
  subscription: "M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3",
  content: "M7 4l13 8-13 8z",
  night_charge: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z",
  new_subscription: "M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3",
  duplicate_charge: "M9 9h11v11H9zM5 15H4V4h11v1",
  international_rate: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18",
  day_spike: "M3 17l6-6 4 4 8-8M15 7h6v6",
  check: "M5 12l5 5L20 7",
  chevron: "M9 6l6 6-6 6",
  back: "M15 6l-6 6 6 6",
  upload: "M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3",
  file: "M14 3H6v18h12V7zM14 3v4h4",
  alert: "M12 3l10 18H2zM12 10v5M12 18h.01",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  share: "M4 12v7h16v-7M12 3v12M7 8l5-5 5 5",
  download: "M12 4v12M7 11l5 5 5-5M4 20h16",
  print: "M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5",
  close: "M6 6l12 12M18 6L6 18",
  users: "M16 20v-1a4 4 0 0 0-8 0v1M12 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 20v-1a4 4 0 0 0-3-3.9M17 5.1a3 3 0 0 1 0 5.8M4 20v-1a4 4 0 0 1 3-3.9M7 5.1a3 3 0 0 0 0 5.8"
};
function icon(name, cls = "icon") {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", cls); svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path"); path.setAttribute("d", ICONS[name] || ICONS.file);
  svg.append(path);
  return svg;
}
function initBigToggle() {
  const btn = $("#big-toggle");
  const setBig = on => {
    document.documentElement.classList.toggle("big", on);
    btn.setAttribute("aria-pressed", String(on));
    store.set("gmd-big", on ? "1" : "0");
  };
  btn.addEventListener("click", () => setBig(!document.documentElement.classList.contains("big")));
  setBig(store.get("gmd-big") === "1");
}
