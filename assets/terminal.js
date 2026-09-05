/* RateScout — Терминал: многопанельный монитор в стиле биржевого терминала (Bloomberg-like).
   Панели: график / watchlist / муверы / тепловая карта. Перетаскивание, ресайз, темы, сохранение раскладки.
   Данные — те же, что у классического монитора: /data/monitor.json (курс в USDT по датам).
   Математика (ре-база, диапазоны, %, OHLC, корреляция) портирована из monitor.js. Без внешних библиотек. */
(function () {
  var root = document.getElementById("terminal");
  if (!root) return;
  var canvas = document.getElementById("termCanvas");
  var bar = document.getElementById("termBar");
  if (!canvas || !bar) return;

  var EN = (document.documentElement.getAttribute("lang") || "ru").slice(0, 2) === "en";
  function T(ru, en) { return EN ? en : ru; }

  // ---------------- данные и утилиты ----------------
  var DATA = null;
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function dnum(s) { var p = s.slice(0, 10).split("-"); return Date.UTC(+p[0], +p[1] - 1, +p[2]) / 86400000 + (s.length > 10 ? (+s.slice(11, 13)) / 24 : 0); }
  function fmtDate(s) { return s.slice(8, 10) + "." + s.slice(5, 7); }
  function fmtNum(v) { if (v == null || isNaN(v)) return "—"; var a = Math.abs(v); if (a >= 1000) return Math.round(v).toLocaleString("ru-RU"); if (a >= 1) return v.toFixed(2); if (a >= 0.01) return v.toFixed(4); return v.toPrecision(3); }
  function fmtPct(p) { if (p == null || isNaN(p)) return ""; return (p >= 0 ? "+" : "") + p.toFixed(1) + "%"; }
  function name(s) { return (DATA.cur[s] || {}).n || s; }
  function ticker(s) { return (DATA.cur[s] || {}).t || ""; }

  var COLORS = ["#3399dd", "#33cc99", "#cc9944", "#cc5588", "#7a5cd0", "#5cc0d0", "#d05c8a", "#9ad04a",
                "#d0a24a", "#4ad0a2", "#d04a4a", "#4a7ad0", "#cdd04a", "#d04acd"];
  var RANGES = [{ k: 7, l: T("1Н", "1W") }, { k: 30, l: T("1М", "1M") }, { k: 90, l: T("3М", "3M") },
                { k: 180, l: T("6М", "6M") }, { k: 365, l: T("1Г", "1Y") }, { k: 1095, l: T("3Г", "3Y") },
                { k: 1825, l: T("5Л", "5Y") }, { k: 0, l: T("Всё", "All") }];
  var TOP_CRYPTO = ["bitcoin", "ethereum", "ripple", "litecoin", "dogecoin", "monero", "tron", "bitcoin-cash", "dash", "zcash", "cardano", "solana", "polkadot"];
  var STABLE_T = ["USDT", "USDC", "DAI", "BUSD", "TUSD", "USDP", "FDUSD", "USDD"];
  var FIAT_T = ["USD", "EUR", "RUB", "GBP", "UAH", "KZT", "TRY", "CNY", "JPY", "BYN"];

  function byName(a, b) { return (DATA.cur[a] ? DATA.cur[a].n : a) > (DATA.cur[b] ? DATA.cur[b].n : b) ? 1 : -1; }
  function groupSlugs(g) {
    if (g === "top") return TOP_CRYPTO.filter(function (s) { return DATA.series[s]; }).slice(0, 12);
    var set = g === "stable" ? STABLE_T : FIAT_T;
    return Object.keys(DATA.series).filter(function (s) { return set.indexOf(ticker(s)) >= 0; }).sort(byName).slice(0, 12);
  }
  // валюты панели: свой набор cfg.cur, иначе группа cfg.grp (для watch/heat/movers)
  function panelSlugs(p) {
    if (p.cfg.cur && p.cfg.cur.length) return p.cfg.cur.filter(function (s) { return DATA.series[s]; });
    return groupSlugs(p.cfg.grp || "top");
  }

  // ---------------- математика рядов ----------------
  function rebased(slug, base) {
    var s = DATA.series[slug]; if (!s) return [];
    if (base === "USD") return s.slice();
    var b = DATA.series[base]; if (!b) return s.slice();
    var bm = {}; b.forEach(function (p) { bm[p[0]] = p[1]; });
    var out = []; s.forEach(function (p) { var bv = bm[p[0]]; if (bv) out.push([p[0], p[1] / bv]); });
    return out;
  }
  function ratioSeries(a, b) {
    var A = DATA.series[a], B = DATA.series[b]; if (!A || !B) return [];
    var bm = {}; B.forEach(function (p) { bm[p[0]] = p[1]; });
    var out = []; A.forEach(function (p) { var bv = bm[p[0]]; if (bv) out.push([p[0], p[1] / bv]); });
    return out;
  }
  function rangeFilter(pts, days) {
    if (!days || pts.length < 2) return pts;
    var last = dnum(pts[pts.length - 1][0]) - days;
    return pts.filter(function (p) { return dnum(p[0]) >= last; });
  }
  function pctChange(slug, base, days) {
    var p = rangeFilter(rebased(slug, base), days); if (p.length < 2) return null;
    var a = p[0][1], b = p[p.length - 1][1]; if (!a) return null; return (b / a - 1) * 100;
  }
  function lastVal(slug, base) { var p = rebased(slug, base); return p.length ? p[p.length - 1][1] : null; }
  function makeScale(mn, mx, log, padT, h) {
    if (log && mn <= 0) log = false;
    var lmn = log ? Math.log(mn) / Math.LN10 : mn, lmx = log ? Math.log(mx) / Math.LN10 : mx;
    if (lmn === lmx) { lmx = lmn + 1; }
    return {
      log: log,
      Y: function (v) { var t = log ? Math.log(v) / Math.LN10 : v; return padT + h - (t - lmn) / (lmx - lmn) * h; },
      ticks: function () { var a = []; for (var i = 0; i <= 4; i++) { var t = lmn + (lmx - lmn) * i / 4; a.push(log ? Math.pow(10, t) : t); } return a; }
    };
  }
  function returnsMap(s, base, days) {
    var p = rangeFilter(rebased(s, base), days), m = {};
    for (var i = 1; i < p.length; i++) { if (p[i - 1][1]) m[p[i][0]] = p[i][1] / p[i - 1][1] - 1; }
    return m;
  }
  function corr(ma, mb) {
    var xs = [], ys = [];
    for (var d in ma) { if (mb[d] != null) { xs.push(ma[d]); ys.push(mb[d]); } }
    var n = xs.length; if (n < 3) return null;
    var mx = xs.reduce(function (a, b) { return a + b; }, 0) / n, my = ys.reduce(function (a, b) { return a + b; }, 0) / n;
    var sxy = 0, sx = 0, sy = 0;
    for (var i = 0; i < n; i++) { var dx = xs[i] - mx, dy = ys[i] - my; sxy += dx * dy; sx += dx * dx; sy += dy * dy; }
    if (!sx || !sy) return null; return sxy / Math.sqrt(sx * sy);
  }
  function heatColor(pc) {
    if (pc == null || isNaN(pc)) return "#161616";
    var t = Math.max(-8, Math.min(8, pc)) / 8;
    if (t >= 0) return "rgba(38,180,110," + (0.18 + 0.62 * t).toFixed(2) + ")";
    return "rgba(210,70,70," + (0.18 + 0.62 * (-t)).toFixed(2) + ")";
  }
  function volat(slug, base, days) {
    var p = rangeFilter(rebased(slug, base), days).map(function (x) { return x[1]; });
    var rets = []; for (var i = 1; i < p.length; i++) { if (p[i - 1]) rets.push(p[i] / p[i - 1] - 1); }
    if (!rets.length) return null;
    var m = rets.reduce(function (a, b) { return a + b; }, 0) / rets.length;
    return Math.sqrt(rets.reduce(function (a, b) { return a + (b - m) * (b - m); }, 0) / rets.length) * 100;
  }
  // метрики ряда по УЖЕ отрисованным точкам [[date,val]]: первый/послед./мин/макс/сред/волат/изм%
  function statsOf(pts) {
    if (!pts || pts.length < 2) return null;
    var v = pts.map(function (p) { return p[1]; });
    var mn = Math.min.apply(null, v), mx = Math.max.apply(null, v);
    var first = v[0], last = v[v.length - 1], avg = v.reduce(function (a, b) { return a + b; }, 0) / v.length;
    var rets = []; for (var i = 1; i < v.length; i++) { if (v[i - 1]) rets.push(v[i] / v[i - 1] - 1); }
    var vol = null; if (rets.length) { var m = rets.reduce(function (a, b) { return a + b; }, 0) / rets.length; vol = Math.sqrt(rets.reduce(function (a, b) { return a + (b - m) * (b - m); }, 0) / rets.length) * 100; }
    return { first: first, last: last, mn: mn, mx: mx, avg: avg, vol: vol, chg: first ? (last / first - 1) * 100 : null };
  }

  // ---------------- ссылки «открыть на сайте» ----------------
  var PREF = EN ? "/en" : "";
  var PAIRS = {}; // "from-to" -> 1 (ядровые пары со страницей /obmen/)
  function curUrl(slug) { return PREF + "/valuta/" + slug + "/"; }
  function bcLink(a, b) {
    var fa = DATA.cur[a] || {}, fb = DATA.cur[b] || {};
    if (fa.num || fb.num) return "https://www.bestchange.ru/index.php?mt=rates&from=" + (fa.id || "") + "&to=" + (fb.id || "") + "&p=" + DATA.ref;
    return "https://www.bestchange.ru/" + a + "-to-" + b + ".html?p=" + DATA.ref;
  }
  function pairUrl(a, b) { return PAIRS[a + "-" + b] ? PREF + "/obmen/" + a + "-" + b + "/" : bcLink(a, b); }
  function pairHasPage(a, b) { return !!PAIRS[a + "-" + b]; }
  function openUrl(u) { if (u) window.open(u, "_blank", "noopener"); }
  // навесить клики «открыть» на элементы [data-cur] и [data-pair="a|b"]
  function wireOpens(el) {
    Array.prototype.forEach.call(el.querySelectorAll("[data-cur]"), function (n) {
      n.title = T("Открыть на сайте", "Open on site"); n.classList.add("op-link");
      n.addEventListener("click", function (e) { e.stopPropagation(); openUrl(curUrl(n.getAttribute("data-cur"))); });
    });
    Array.prototype.forEach.call(el.querySelectorAll("[data-pair]"), function (n) {
      var ab = n.getAttribute("data-pair").split("|");
      n.title = pairHasPage(ab[0], ab[1]) ? T("Открыть пару на сайте", "Open pair on site") : T("Открыть на BestChange (реф.)", "Open on BestChange (ref)");
      n.classList.add("op-link");
      n.addEventListener("click", function (e) { e.stopPropagation(); openUrl(pairUrl(ab[0], ab[1])); });
    });
  }

  // ---------------- активный график: другие окна добавляют в него валюты/пары ----------------
  function chartPanels() { return STATE.panels.filter(function (p) { return p.t === "chart"; }); }
  function getActiveChart() {
    var p = STATE.panels.filter(function (x) { return x.id === activeId && x.t === "chart"; })[0];
    return p || chartPanels()[0] || null;
  }
  function markActive() {
    var a = getActiveChart(); activeId = a ? a.id : null;
    Array.prototype.forEach.call(canvas.querySelectorAll(".term-win"), function (w) {
      w.classList.toggle("win-active", a && +w.getAttribute("data-id") === activeId);
    });
  }
  function setActive(id) { var p = STATE.panels.filter(function (x) { return x.id === id; })[0]; if (p && p.t === "chart") { activeId = id; markActive(); } }
  // валюта уже на активном графике?
  function inActiveChart(slug) { var c = getActiveChart(); return !!(c && c.cfg.cur && c.cfg.cur.indexOf(slug) >= 0); }
  // значок «на активном графике»
  function onMark(slug) { return (chartableCur(slug) && inActiveChart(slug)) ? " <span class='on-chart' title='" + T("на графике", "on chart") + "'>●</span>" : ""; }
  // тумблер: нет на активном графике → добавить; есть → убрать (если графика нет — создать)
  function addToActiveChart(slug) {
    if (!DATA.series[slug]) return;
    var c = getActiveChart();
    if (!c) { c = { id: STATE.seq++, t: "chart", cfg: { cur: [slug], base: "USD", type: "line", range: 365, log: false }, g: nextPos() }; STATE.panels.push(c); }
    else { var i = c.cfg.cur.indexOf(slug); if (i >= 0) c.cfg.cur.splice(i, 1); else c.cfg.cur.push(slug); }
    activeId = c.id; renderAll(); saveWS();
  }
  function setActiveRatio(a, b) {
    if (!DATA.series[a] || !DATA.series[b]) return;
    var c = getActiveChart();
    if (!c) { c = { id: STATE.seq++, t: "chart", cfg: { cur: [a, b], base: "USD", type: "ratio", range: 365, log: false }, g: nextPos() }; STATE.panels.push(c); }
    else { c.cfg.cur = [a, b]; c.cfg.type = "ratio"; }
    activeId = c.id; renderAll(); saveWS();
  }
  // навесить «добавить в активный график» на [data-add] (валюта) и [data-addpair] (пара)
  function wireAdd(el) {
    Array.prototype.forEach.call(el.querySelectorAll("[data-add]"), function (n) {
      n.title = T("Добавить в активный график", "Add to active chart"); n.classList.add("op-link");
      n.addEventListener("click", function (e) { e.stopPropagation(); addToActiveChart(n.getAttribute("data-add")); });
    });
    Array.prototype.forEach.call(el.querySelectorAll("[data-addpair]"), function (n) {
      var ab = n.getAttribute("data-addpair").split("|");
      n.title = T("Открыть пару в активном графике", "Open pair in active chart"); n.classList.add("op-link");
      n.addEventListener("click", function (e) { e.stopPropagation(); setActiveRatio(ab[0], ab[1]); });
    });
  }

  // ---------------- состояние воркспейса ----------------
  var STATE = { theme: "bloomberg", panels: [], seq: 1, tiled: false, split: { x: 0.5, y: 0.5 } };
  var zTop = 10;
  var activeId = null; // id активного графика — с ним взаимодействуют остальные окна
  var LS_KEY = "rs_term_ws";

  function defaultWorkspace() {
    return {
      theme: "bloomberg",
      panels: [
        { t: "chart", cfg: { cur: groupSlugs("top").slice(0, 4), base: "USD", type: "line", range: 365, log: false }, g: [8, 8, 560, 340] },
        { t: "watch", cfg: { grp: "top", range: 30 }, g: [576, 8, 360, 340] },
        { t: "movers", cfg: { range: 30, n: 8 }, g: [8, 356, 360, 320] },
        { t: "heat", cfg: { grp: "top", range: 30 }, g: [376, 356, 560, 320] }
      ]
    };
  }
  // мобильная сетка: панели друг под другом на всю ширину
  function isMobile() { return window.matchMedia("(max-width:760px)").matches; }

  function saveWS() {
    var ws = { theme: STATE.theme, tiled: STATE.tiled, split: STATE.split, panels: STATE.panels.map(function (p) { return { t: p.t, cfg: p.cfg, g: p.g }; }) };
    try { localStorage.setItem(LS_KEY, JSON.stringify(ws)); } catch (e) {}
    writeURL(ws);
  }
  function writeURL(ws) {
    try {
      var b = btoa(unescape(encodeURIComponent(JSON.stringify(ws))));
      var q = new URLSearchParams(location.search); q.set("ws", b);
      history.replaceState(null, "", location.pathname + "?" + q.toString());
    } catch (e) {}
  }
  function loadWS() {
    var ws = null;
    try {
      var q = new URLSearchParams(location.search);
      if (q.get("ws")) ws = JSON.parse(decodeURIComponent(escape(atob(q.get("ws")))));
    } catch (e) { ws = null; }
    if (!ws) { try { var raw = localStorage.getItem(LS_KEY); if (raw) ws = JSON.parse(raw); } catch (e2) { ws = null; } }
    if (!ws || !ws.panels || !ws.panels.length) ws = defaultWorkspace();
    STATE.theme = ws.theme || "bloomberg";
    STATE.tiled = !!ws.tiled;
    STATE.split = (ws.split && typeof ws.split.x === "number") ? ws.split : { x: 0.5, y: 0.5 };
    STATE.panels = ws.panels.map(function (p) { p.id = STATE.seq++; return p; });
  }

  // ---------------- каркас: тулбар ----------------
  function buildBar() {
    bar.innerHTML =
      '<div class="tb-grp">' +
        '<button class="tb-btn tb-add" data-t="chart">+ ' + T("График", "Chart") + "</button>" +
        '<button class="tb-btn tb-add" data-t="watch">+ Watchlist</button>' +
        '<button class="tb-btn tb-add" data-t="movers">+ ' + T("Муверы", "Movers") + "</button>" +
        '<button class="tb-btn tb-add" data-t="heat">+ ' + T("Хитмап", "Heatmap") + "</button>" +
        '<button class="tb-btn tb-add" data-t="screen">+ ' + T("Скринер", "Screener") + "</button>" +
        '<button class="tb-btn tb-add" data-t="demand">+ ' + T("Спрос", "Demand") + "</button>" +
      "</div>" +
      '<div class="tb-grp">' +
        '<label class="tb-l">' + T("Раскладка", "Layout") + ': <select class="tb-sel" id="tbLayout">' +
          '<option value="">—</option>' +
          '<option value="overview">' + T("Обзор рынка", "Market overview") + "</option>" +
          '<option value="charts2">' + T("2 графика", "2 charts") + "</option>" +
          '<option value="charts4">' + T("4 графика", "4 charts") + "</option>" +
          '<option value="watchbig">' + T("Watchlist + график", "Watchlist + chart") + "</option>" +
        "</select></label>" +
        '<label class="tb-l">' + T("Тема", "Theme") + ': <select class="tb-sel" id="tbTheme">' +
          '<option value="bloomberg">Bloomberg</option>' +
          '<option value="dos">DOS-cyan</option>' +
          '<option value="dark">' + T("Тёмная", "Dark") + "</option>" +
        "</select></label>" +
      "</div>" +
      '<div class="tb-grp tb-right">' +
        '<button class="tb-btn' + (STATE.tiled ? " on" : "") + '" id="tbTile">⊞ ' + T("Сетка", "Tile") + "</button>" +
        '<button class="tb-btn" id="tbFull">⛶ ' + T("Во весь экран", "Fullscreen") + "</button>" +
        '<button class="tb-btn" id="tbShare">' + T("Ссылка", "Link") + "</button>" +
        '<button class="tb-btn" id="tbReset">' + T("Сброс", "Reset") + "</button>" +
      "</div>";
    Array.prototype.forEach.call(bar.querySelectorAll(".tb-add"), function (b) {
      b.addEventListener("click", function () { addPanel(b.getAttribute("data-t")); });
    });
    var themeSel = bar.querySelector("#tbTheme"); themeSel.value = STATE.theme;
    themeSel.addEventListener("change", function () { setTheme(themeSel.value); saveWS(); });
    bar.querySelector("#tbLayout").addEventListener("change", function () { if (this.value) { applyLayout(this.value); this.value = ""; } });
    bar.querySelector("#tbTile").addEventListener("click", function () { STATE.tiled = !STATE.tiled; this.classList.toggle("on", STATE.tiled); renderAll(); saveWS(); });
    bar.querySelector("#tbReset").addEventListener("click", function () {
      if (!confirm(T("Сбросить раскладку к стандартной?", "Reset layout to default?"))) return;
      try { localStorage.removeItem(LS_KEY); } catch (e) {}
      var ws = defaultWorkspace(); STATE.theme = ws.theme;
      STATE.panels = ws.panels.map(function (p) { p.id = STATE.seq++; return p; });
      setTheme(STATE.theme); renderAll(); saveWS();
    });
    var fb = bar.querySelector("#tbFull");
    if (fb) { fb.addEventListener("click", toggleFull); fb.textContent = (isFull() ? "⤢ " + T("Свернуть", "Exit") : "⛶ " + T("Во весь экран", "Fullscreen")); }
    bar.querySelector("#tbShare").addEventListener("click", function (e) {
      saveWS(); var btn = e.target, old = btn.textContent;
      var done = function () { btn.textContent = T("скопировано ✓", "copied ✓"); setTimeout(function () { btn.textContent = old; }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(location.href).then(done, done); else done();
    });
  }
  function setTheme(t) { STATE.theme = t; root.className = "term th-" + t + (isMobile() ? " term-mobile" : "") + (isFull() ? " term-full" : ""); var s = bar.querySelector("#tbTheme"); if (s) s.value = t; renderAll(); }

  // ---------------- полноэкранный режим рабочей области ----------------
  function fsEl() { return document.fullscreenElement || document.webkitFullscreenElement || null; }
  function isFull() { return fsEl() === root; }
  function reqFull() {
    var f = root.requestFullscreen || root.webkitRequestFullscreen;
    if (f) try { f.call(root); } catch (e) {}
  }
  function exitFull() {
    var f = document.exitFullscreen || document.webkitExitFullscreen;
    if (f) try { f.call(document); } catch (e) {}
  }
  function toggleFull() { if (isFull()) exitFull(); else reqFull(); }
  function onFullChange() {
    var fe = fsEl();
    var b = bar.querySelector("#tbFull");
    if (b) b.textContent = (fe === root ? "⤢ " + T("Свернуть", "Exit") : "⛶ " + T("Во весь экран", "Fullscreen"));
    root.classList.toggle("term-full", fe === root);
    var winFullEl = (fe && fe.classList && fe.classList.contains("term-win")) ? fe : null;
    Array.prototype.forEach.call(canvas.querySelectorAll(".term-win"), function (w) {
      w.classList.toggle("win-full-on", w === winFullEl);
      var fb = w.querySelector(".win-full"); if (fb) fb.textContent = (w === winFullEl) ? "⤢" : "⛶";
    });
    if (winFullEl) {
      // одна панель во весь экран — перерисовать только её тело (renderAll() убил бы fullscreen-элемент)
      var id = +winFullEl.getAttribute("data-id"), p = null;
      STATE.panels.forEach(function (x) { if (x.id === id) p = x; });
      if (p) drawBody(p, winFullEl.querySelector(".win-body"));
    } else {
      renderAll();
    }
  }
  document.addEventListener("fullscreenchange", onFullChange);
  document.addEventListener("webkitfullscreenchange", onFullChange);
  // доступная высота канвы: в фулскрине — вся высота экрана минус тулбар, иначе базовые 560px
  function availH() { return isFull() ? Math.max(400, (window.innerHeight || 800) - (bar.offsetHeight || 44) - 20) : 560; }

  // ---------------- панели ----------------
  var PTITLE = { chart: T("График", "Chart"), watch: "Watchlist", movers: T("Муверы", "Movers"), heat: T("Тепловая карта", "Heatmap"), screen: T("Скринер", "Screener"), demand: T("Спрос из поиска", "Search demand") };
  function nextPos() { var n = STATE.panels.length; return [24 + (n % 4) * 28, 24 + (n % 4) * 28, 440, 300]; }
  function addPanel(t) {
    var cfg;
    if (t === "chart") cfg = { cur: groupSlugs("top").slice(0, 3), base: "USD", type: "line", range: 365, log: false };
    else if (t === "watch") cfg = { grp: "top", range: 30 };
    else if (t === "movers") cfg = { range: 30, n: 8 };
    else if (t === "heat") cfg = { grp: "top", range: 30 };
    else if (t === "screen") cfg = { mode: "cur", quote: findQuote(), range: 30, sort: "chg", dir: -1, fchg: "", fvol: "", q: "" };
    else if (t === "demand") cfg = { view: "dir" };
    else return;
    STATE.panels.push({ id: STATE.seq++, t: t, cfg: cfg, g: (t === "screen" || t === "demand") ? [24, 24, 480, 380] : nextPos() });
    renderAll(); saveWS();
  }
  function findQuote() { // slug для котировки по умолчанию (USDT), иначе первый доступный стейбл/любой
    var pref = ["tether", "tether-trc20", "tether-erc20"];
    for (var i = 0; i < pref.length; i++) if (DATA.series[pref[i]]) return pref[i];
    var st = Object.keys(DATA.series).filter(function (s) { return ticker(s) === "USDT"; });
    return st[0] || Object.keys(DATA.series)[0];
  }
  function closePanel(id) { STATE.panels = STATE.panels.filter(function (p) { return p.id !== id; }); renderAll(); saveWS(); }

  function renderAll() {
    canvas.innerHTML = ""; crossEl = null;
    var tiled = STATE.tiled && !isMobile();
    root.classList.toggle("tiled", tiled);
    var maxB = 0;
    STATE.panels.forEach(function (p) {
      var el = renderPanel(p);
      canvas.appendChild(el);
      if (!tiled) { if (!isMobile()) maxB = Math.max(maxB, p.g[1] + p.g[3]); drawBody(p, el.querySelector(".win-body")); }
    });
    if (tiled) { buildTileCross(); layoutTiles(); redrawTiles(); }
    else if (!isMobile()) canvas.style.height = Math.max(availH(), maxB + 24) + "px";
    else canvas.style.height = "auto";
    markActive();
  }

  // ---------- тайл-режим: плитка (2×2 супер-сетка) + центральная крестовина ----------
  var tileRaf = null, crossEl = null, crossHasV = false, crossHasH = false;
  function tileGeom() {
    var W = canvas.clientWidth || 960, H = Math.max(availH(), 420), gap = 6;
    var q = [[], [], [], []];
    STATE.panels.forEach(function (p, i) { q[i % 4].push(p); });
    var hasTop = q[0].length || q[1].length, hasBot = q[2].length || q[3].length;
    var fx = Math.min(0.88, Math.max(0.12, STATE.split.x)), fy = Math.min(0.88, Math.max(0.12, STATE.split.y));
    var topH, botH, topY = 0, botY = 0;
    if (hasTop && hasBot) { topH = Math.round((H - gap) * fy); botH = H - gap - topH; botY = topH + gap; }
    else if (hasTop) { topH = H; botH = 0; } else { topH = 0; botH = H; }
    var leftW = Math.round((W - gap) * fx), rightW = W - gap - leftW, rightX = leftW + gap;
    var rects = {};
    function place(list, x, y, w, h) {
      if (!list.length || w <= 0 || h <= 0) return;
      var g2 = 6, each = (h - g2 * (list.length - 1)) / list.length;
      list.forEach(function (p, i) { rects[p.id] = [x, Math.round(y + i * (each + g2)), w, Math.round(each)]; });
    }
    if (hasTop) {
      if (q[0].length && q[1].length) { place(q[0], 0, topY, leftW, topH); place(q[1], rightX, topY, rightW, topH); }
      else place(q[0].length ? q[0] : q[1], 0, topY, W, topH);
    }
    if (hasBot) {
      if (q[2].length && q[3].length) { place(q[2], 0, botY, leftW, botH); place(q[3], rightX, botY, rightW, botH); }
      else place(q[2].length ? q[2] : q[3], 0, botY, W, botH);
    }
    var hasV = (q[0].length || q[2].length) && (q[1].length || q[3].length);
    return { W: W, H: H, gap: gap, rects: rects, leftW: leftW, topH: topH, hasV: hasV, hasH: !!(hasTop && hasBot) };
  }
  function layoutTiles() {
    var G = tileGeom();
    canvas.style.height = G.H + "px";
    STATE.panels.forEach(function (p) {
      var r = G.rects[p.id], el = canvas.querySelector('[data-id="' + p.id + '"]'); if (!el || !r) return;
      el.style.left = r[0] + "px"; el.style.top = r[1] + "px"; el.style.width = r[2] + "px"; el.style.height = r[3] + "px";
    });
    crossHasV = G.hasV; crossHasH = G.hasH;
    if (crossEl) {
      crossEl.style.left = (G.hasV ? G.leftW + G.gap / 2 : G.W / 2) + "px";
      crossEl.style.top = (G.hasH ? G.topH + G.gap / 2 : G.H / 2) + "px";
      crossEl.style.display = (G.hasV || G.hasH) ? "block" : "none";
      crossEl.className = "tile-cross" + (G.hasV && G.hasH ? " xy" : G.hasV ? " ax" : " ay");
    }
  }
  function buildTileCross() {
    crossEl = document.createElement("div"); crossEl.className = "tile-cross"; crossEl.title = T("Тяните — размеры окон", "Drag to resize windows");
    canvas.appendChild(crossEl);
    crossEl.addEventListener("pointerdown", function (e) {
      e.preventDefault(); e.stopPropagation();
      if (crossEl.setPointerCapture) try { crossEl.setPointerCapture(e.pointerId); } catch (er) {}
      function mv(ev) {
        var r = canvas.getBoundingClientRect();
        if (crossHasV) STATE.split.x = Math.min(0.88, Math.max(0.12, (ev.clientX - r.left) / r.width));
        if (crossHasH) STATE.split.y = Math.min(0.88, Math.max(0.12, (ev.clientY - r.top) / r.height));
        layoutTiles(); scheduleTileDraw();
      }
      function up() { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); redrawTiles(); saveWS(); }
      document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
    });
  }
  function scheduleTileDraw() {
    if (tileRaf) return;
    tileRaf = (window.requestAnimationFrame || function (f) { return setTimeout(f, 16); })(function () { tileRaf = null; redrawTiles(); });
  }
  function redrawTiles() {
    STATE.panels.forEach(function (p) { var el = canvas.querySelector('[data-id="' + p.id + '"]'); if (el) drawBody(p, el.querySelector(".win-body")); });
  }

  function renderPanel(p) {
    var el = document.createElement("section");
    el.className = "term-win win-" + p.t;
    el.setAttribute("data-id", p.id);
    if (!isMobile()) {
      el.style.left = p.g[0] + "px"; el.style.top = p.g[1] + "px";
      el.style.width = p.g[2] + "px"; el.style.height = p.g[3] + "px";
      el.style.zIndex = ++zTop;
    }
    el.innerHTML =
      '<header class="win-h"><span class="win-t">' + esc(PTITLE[p.t]) + "</span>" +
        '<span class="win-ctl">' + panelControls(p) + "</span>" +
        '<span class="win-tools">' +
          '<button class="win-full" title="' + T("Во весь экран", "Fullscreen") + '">⛶</button>' +
          '<button class="win-x" title="' + T("Закрыть", "Close") + '">✕</button>' +
        "</span>" +
      "</header>" +
      '<div class="win-body"></div>' +
      (isMobile() ? "" : '<div class="win-rz" title="' + T("Тянуть — размер", "Drag to resize") + '"></div>');
    wirePanel(p, el);
    return el;
  }

  // компактные контролы в шапке панели
  function panelControls(p) {
    if (p.t === "chart") {
      return '<button class="win-b win-pick" title="' + T("Выбрать валюты", "Pick currencies") + '">◧ ' + T("Валюты", "Currencies") + " (" + p.cfg.cur.length + ")</button>" +
        '<select class="win-s win-type">' +
          '<option value="line"' + (p.cfg.type === "line" ? " selected" : "") + ">" + T("Линии", "Lines") + "</option>" +
          '<option value="candle"' + (p.cfg.type === "candle" ? " selected" : "") + ">" + T("Свечи", "Candles") + "</option>" +
          '<option value="ratio"' + (p.cfg.type === "ratio" ? " selected" : "") + ">A/B</option>" +
        "</select>" +
        '<label class="win-log"><input type="checkbox" class="win-logc"' + (p.cfg.log ? " checked" : "") + "> log</label>" +
        rangeTabs(p.cfg.range);
    }
    if (p.t === "watch" || p.t === "heat") {
      return '<button class="win-b win-pick" title="' + T("Выбрать валюты", "Pick currencies") + '">◧ ' + T("Валюты", "Currencies") + " (" + panelSlugs(p).length + ")</button>" +
        '<select class="win-s win-grp">' +
          '<option value="top"' + (!p.cfg.cur && p.cfg.grp === "top" ? " selected" : "") + ">" + T("Топ-крипта", "Top crypto") + "</option>" +
          '<option value="stable"' + (!p.cfg.cur && p.cfg.grp === "stable" ? " selected" : "") + ">" + T("Стейблы", "Stables") + "</option>" +
          '<option value="fiat"' + (!p.cfg.cur && p.cfg.grp === "fiat" ? " selected" : "") + ">" + T("Фиат", "Fiat") + "</option>" +
          (p.cfg.cur && p.cfg.cur.length ? '<option value="" selected>' + T("свой набор", "custom") + "</option>" : "") +
        "</select>" + rangeTabs(p.cfg.range);
    }
    if (p.t === "movers") {
      return '<button class="win-b win-pick" title="' + T("Выбрать валюты", "Pick currencies") + '">◧ ' + T("Валюты", "Currencies") + " (" + (p.cfg.cur && p.cfg.cur.length ? p.cfg.cur.length : T("все", "all")) + ")</button>" + rangeTabs(p.cfg.range);
    }
    if (p.t === "screen") {
      var q = "";
      if (p.cfg.mode === "pair") {
        var opts = Object.keys(DATA.series).sort(byName).map(function (s) {
          return '<option value="' + esc(s) + '"' + (p.cfg.quote === s ? " selected" : "") + ">" + esc(ticker(s) || name(s)) + "</option>";
        }).join("");
        q = '<label class="win-log">B: <select class="win-s win-quote">' + opts + "</select></label>";
      }
      return '<select class="win-s win-mode">' +
          '<option value="cur"' + (p.cfg.mode === "cur" ? " selected" : "") + ">" + T("Валюты", "Currencies") + "</option>" +
          '<option value="pair"' + (p.cfg.mode === "pair" ? " selected" : "") + ">" + T("Пары к B", "Pairs vs B") + "</option>" +
        "</select>" + q + rangeTabs(p.cfg.range);
    }
    if (p.t === "demand") {
      return '<select class="win-s win-view">' +
          '<option value="dir"' + (p.cfg.view === "dir" ? " selected" : "") + ">" + T("Направления (GSC)", "Directions (GSC)") + "</option>" +
          '<option value="cur"' + (p.cfg.view === "cur" ? " selected" : "") + ">" + T("Валюты (GSC)", "Currencies (GSC)") + "</option>" +
          '<option value="trend"' + (p.cfg.view === "trend" ? " selected" : "") + ">" + T("Тренд (CoinGecko)", "Trending (CoinGecko)") + "</option>" +
          '<option value="yandex"' + (p.cfg.view === "yandex" ? " selected" : "") + ">" + T("Яндекс: запросы", "Yandex: queries") + "</option>" +
          '<option value="metrika"' + (p.cfg.view === "metrika" ? " selected" : "") + ">" + T("Метрика: фразы", "Metrika: phrases") + "</option>" +
        "</select>";
    }
    return "";
  }
  function rangeTabs(cur) {
    return '<span class="win-rng">' + RANGES.map(function (r) {
      return '<button class="win-r' + (r.k === cur ? " on" : "") + '" data-k="' + r.k + '">' + r.l + "</button>";
    }).join("") + "</span>";
  }

  function winFull(el) { var f = el.requestFullscreen || el.webkitRequestFullscreen; if (f) try { f.call(el); } catch (e) {} }
  function toggleWinFull(el) { if (fsEl() === el) exitFull(); else winFull(el); }
  function wirePanel(p, el) {
    el.querySelector(".win-x").addEventListener("click", function () { closePanel(p.id); });
    var full = el.querySelector(".win-full");
    if (full) full.addEventListener("click", function (e) { e.stopPropagation(); toggleWinFull(el); });
    var body = function () { return el.querySelector(".win-body"); };
    var rng = el.querySelectorAll(".win-r");
    Array.prototype.forEach.call(rng, function (b) {
      b.addEventListener("click", function () {
        p.cfg.range = +b.getAttribute("data-k");
        Array.prototype.forEach.call(rng, function (x) { x.classList.toggle("on", +x.getAttribute("data-k") === p.cfg.range); });
        drawBody(p, body()); saveWS();
      });
    });
    var typeSel = el.querySelector(".win-type");
    if (typeSel) typeSel.addEventListener("change", function () { p.cfg.type = typeSel.value; drawBody(p, body()); saveWS(); });
    var logc = el.querySelector(".win-logc");
    if (logc) logc.addEventListener("change", function () { p.cfg.log = logc.checked; drawBody(p, body()); saveWS(); });
    var grp = el.querySelector(".win-grp");
    if (grp) grp.addEventListener("change", function () {
      if (grp.value) { p.cfg.grp = grp.value; p.cfg.cur = null; }
      var pk = el.querySelector(".win-pick"); if (pk) pk.textContent = "◧ " + T("Валюты", "Currencies") + " (" + panelSlugs(p).length + ")";
      drawBody(p, body()); saveWS();
    });
    var pick = el.querySelector(".win-pick");
    if (pick) pick.addEventListener("click", function () { openPicker(p, el); });
    var mode = el.querySelector(".win-mode");
    if (mode) mode.addEventListener("change", function () { p.cfg.mode = mode.value; renderAll(); saveWS(); });
    var view = el.querySelector(".win-view");
    if (view) view.addEventListener("change", function () { p.cfg.view = view.value; drawBody(p, body()); saveWS(); });
    var quote = el.querySelector(".win-quote");
    if (quote) quote.addEventListener("change", function () { p.cfg.quote = quote.value; drawBody(p, body()); saveWS(); });
    if (p.t === "chart") {
      el.addEventListener("pointerdown", function () { setActive(p.id); });
      el.addEventListener("contextmenu", function (e) {
        if (e.target.closest(".win-h")) return; // по шапке — не мешаем
        e.preventDefault(); openChartMenu(p, e.clientX, e.clientY);
      });
    }
    if (!isMobile() && !STATE.tiled) enableDrag(p, el);
  }

  // ---------------- перетаскивание / ресайз + прилипание (стык-в-стык) ----------------
  var SNAP = 8; // порог прилипания, px
  function edgesX(p) { var a = [0, canvas.clientWidth]; STATE.panels.forEach(function (o) { if (o.id !== p.id) { a.push(o.g[0], o.g[0] + o.g[2]); } }); return a; }
  function edgesY(p) { var a = [0, canvas.clientHeight]; STATE.panels.forEach(function (o) { if (o.id !== p.id) { a.push(o.g[1], o.g[1] + o.g[3]); } }); return a; }
  function nearest(edges, vals) { // vals — точки окна (лев/прав или верх/низ); вернуть лучшую поправку в пределах SNAP
    var best = SNAP + 1;
    edges.forEach(function (E) { vals.forEach(function (v) { var d = E - v; if (Math.abs(d) < Math.abs(best)) best = d; }); });
    return Math.abs(best) <= SNAP ? best : 0;
  }
  function snapPos(p, nx, ny) {
    nx += nearest(edgesX(p), [nx, nx + p.g[2]]);
    ny += nearest(edgesY(p), [ny, ny + p.g[3]]);
    return [Math.max(0, nx), Math.max(0, ny)];
  }
  function snapSize(p, nw, nh) {
    nw += nearest(edgesX(p), [p.g[0] + nw]);
    nh += nearest(edgesY(p), [p.g[1] + nh]);
    return [Math.max(240, nw), Math.max(160, nh)];
  }
  function focusWin(el) { el.style.zIndex = ++zTop; }
  function enableDrag(p, el) {
    var h = el.querySelector(".win-h"), rz = el.querySelector(".win-rz");
    el.addEventListener("pointerdown", function () { focusWin(el); });
    h.addEventListener("pointerdown", function (e) {
      if (e.target.closest("button,select,input,label")) return;
      e.preventDefault(); focusWin(el);
      var sx = e.clientX, sy = e.clientY, ox = p.g[0], oy = p.g[1];
      function mv(ev) {
        var s = snapPos(p, Math.max(0, ox + (ev.clientX - sx)), Math.max(0, oy + (ev.clientY - sy)));
        p.g[0] = s[0]; p.g[1] = s[1];
        el.style.left = p.g[0] + "px"; el.style.top = p.g[1] + "px";
      }
      function up() { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); saveWS(); syncHeight(); }
      document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
    });
    if (rz) rz.addEventListener("pointerdown", function (e) {
      e.preventDefault(); e.stopPropagation(); focusWin(el);
      var sx = e.clientX, sy = e.clientY, ow = p.g[2], oh = p.g[3];
      function mv(ev) {
        var s = snapSize(p, Math.max(240, ow + (ev.clientX - sx)), Math.max(160, oh + (ev.clientY - sy)));
        p.g[2] = s[0]; p.g[3] = s[1];
        el.style.width = p.g[2] + "px"; el.style.height = p.g[3] + "px";
        drawBody(p, el.querySelector(".win-body"));
      }
      function up() { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); saveWS(); syncHeight(); }
      document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
    });
  }
  function syncHeight() {
    if (isMobile()) return;
    var maxB = 0; STATE.panels.forEach(function (p) { maxB = Math.max(maxB, p.g[1] + p.g[3]); });
    canvas.style.height = Math.max(availH(), maxB + 24) + "px";
  }

  // ---------------- отрисовка тела панели ----------------
  function drawBody(p, body) {
    if (!body) return;
    if (p.t === "chart") drawChart(p, body);
    else if (p.t === "watch") drawWatch(p, body);
    else if (p.t === "movers") drawMovers(p, body);
    else if (p.t === "heat") drawHeat(p, body);
    else if (p.t === "screen") drawScreen(p, body);
    else if (p.t === "demand") drawDemand(p, body);
  }
  function empty(msg) { return '<p class="win-empty">' + esc(msg) + "</p>"; }

  // ----- ГРАФИК -----
  function drawChart(p, body) {
    var cfg = p.cfg, sels = cfg.cur.filter(function (s) { return DATA.series[s]; });
    if (!sels.length) { body.innerHTML = empty(T("Нет валют. Нажмите «Валюты».", "No currencies. Click “Currencies”.")); return; }
    var W = body.clientWidth || 400, H = body.clientHeight || 240;
    var padL = 52, padR = 10, padT = 10, padB = 22, w = W - padL - padR, h = H - padT - padB;
    if (w < 40 || h < 30) { body.innerHTML = empty("…"); return; }
    var accent = COLORS[0];
    var bn = cfg.base === "USD" ? "USDT" : (ticker(cfg.base) || "");
    p._hover = null;
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '" preserveAspectRatio="none" class="win-svg">';

    if (cfg.type === "candle") {
      var pts = rangeFilter(rebased(sels[0], cfg.base), cfg.range), byDay = {};
      pts.forEach(function (pt) { var d = pt[0].slice(0, 10); (byDay[d] = byDay[d] || []).push(pt[1]); });
      var days = Object.keys(byDay).sort();
      var ohlc = days.map(function (d) { var a = byDay[d]; return { d: d, o: a[0], c: a[a.length - 1], h: Math.max.apply(null, a), l: Math.min.apply(null, a) }; });
      if (!ohlc.length) { body.innerHTML = empty(T("Нет данных.", "No data.")); return; }
      var vs = []; ohlc.forEach(function (c) { vs.push(c.h, c.l); });
      var mn = Math.min.apply(null, vs), mx = Math.max.apply(null, vs); if (mn === mx) { mn *= 0.99; mx *= 1.01; }
      var sc = makeScale(mn, mx, cfg.log, padT, h), cw = Math.max(2, Math.min(14, w / ohlc.length * 0.6));
      svg += grid(sc, W, padL, padR, fmtNum);
      ohlc.forEach(function (c, i) {
        var x = padL + (ohlc.length === 1 ? w / 2 : i / (ohlc.length - 1) * w), up = c.c >= c.o, col = up ? "#26d07c" : "#ff5c5c";
        svg += '<line x1="' + x.toFixed(1) + '" y1="' + sc.Y(c.h).toFixed(1) + '" x2="' + x.toFixed(1) + '" y2="' + sc.Y(c.l).toFixed(1) + '" stroke="' + col + '"/>';
        var yo = sc.Y(c.o), yc = sc.Y(c.c);
        svg += '<rect x="' + (x - cw / 2).toFixed(1) + '" y="' + Math.min(yo, yc).toFixed(1) + '" width="' + cw.toFixed(1) + '" height="' + Math.max(1, Math.abs(yc - yo)).toFixed(1) + '" fill="' + col + '"/>';
      });
      svg += xlabels(ohlc.map(function (c) { return c.d; }), padL, w, H, padB);
      svg += "</svg>"; body.innerHTML = svg + legendHTML([{ s: sels[0], col: "#26d07c", extra: T("свечи", "candles") }], p); wireOpens(body);
      p._hover = { kind: "candle", W: W, padL: padL, w: w, ohlc: ohlc, Xi: function (i) { return padL + (ohlc.length === 1 ? w / 2 : i / (ohlc.length - 1) * w); }, name: name(sels[0]), baseName: bn, stats: [statsOf(pts)] };
      attachHover(p, body);
      return;
    }

    if (cfg.type === "ratio") {
      if (sels.length < 2) { body.innerHTML = empty(T("Нужно ≥2 валюты для пары A/B.", "Need ≥2 currencies for A/B.")); return; }
      var rp = rangeFilter(ratioSeries(sels[0], sels[1]), cfg.range);
      if (rp.length < 2) { body.innerHTML = empty(T("Нет пересечения дат.", "No overlapping dates.")); return; }
      var rv = rp.map(function (x) { return x[1]; }), rmn = Math.min.apply(null, rv), rmx = Math.max.apply(null, rv);
      if (rmn === rmx) { rmn *= 0.99; rmx = rmx * 1.01 + 1e-9; }
      var rsc = makeScale(rmn, rmx, cfg.log, padT, h), rx0 = dnum(rp[0][0]), rxs = (dnum(rp[rp.length - 1][0]) - rx0) || 1;
      var RX = function (d) { return padL + (dnum(d) - rx0) / rxs * w; };
      svg += grid(rsc, W, padL, padR, fmtNum);
      svg += areaAndLine(rp, RX, rsc, accent);
      svg += xlabels(rp.map(function (x) { return x[0]; }), padL, w, H, padB, RX);
      var rpc = (rp[rp.length - 1][1] / rp[0][1] - 1) * 100;
      svg += "</svg>"; body.innerHTML = svg + legendHTML([{ pairAB: sels[0] + "|" + sels[1], col: accent, label: (ticker(sels[0]) || name(sels[0])) + "/" + (ticker(sels[1]) || name(sels[1])), val: fmtNum(rp[rp.length - 1][1]), pc: rpc }], p); wireOpens(body);
      var rmap = {}; rp.forEach(function (pt) { rmap[pt[0]] = pt[1]; });
      p._hover = { kind: "line", W: W, padL: padL, w: w, x0: rx0, xs: rxs, Xd: RX, dates: rp.map(function (pt) { return pt[0]; }), dnums: rp.map(function (pt) { return dnum(pt[0]); }), names: [(ticker(sels[0]) || sels[0]) + "/" + (ticker(sels[1]) || sels[1])], cols: [accent], maps: [rmap], baseName: "", stats: [statsOf(rp)] };
      attachHover(p, body);
      return;
    }

    // линии / area
    var single = sels.length === 1;
    var sd = sels.map(function (s) { return { s: s, pts: rangeFilter(rebased(s, cfg.base), cfg.range) }; }).filter(function (o) { return o.pts.length; });
    if (!sd.length) { body.innerHTML = empty(T("Нет данных за период.", "No data for the period.")); return; }
    sd.forEach(function (o) { var st = o.pts[0][1] || 1; o.norm = o.pts.map(function (pt) { return [pt[0], single ? pt[1] : pt[1] / st * 100]; }); });
    var allv = [], allx = []; sd.forEach(function (o) { o.norm.forEach(function (pt) { allv.push(pt[1]); allx.push(dnum(pt[0])); }); });
    var mn2 = Math.min.apply(null, allv), mx2 = Math.max.apply(null, allv); if (mn2 === mx2) { mn2 *= 0.99; mx2 = mx2 * 1.01 + 1; }
    var sc2 = makeScale(mn2, mx2, cfg.log, padT, h), x0 = Math.min.apply(null, allx), xs = (Math.max.apply(null, allx) - x0) || 1;
    function X(d) { return padL + (dnum(d) - x0) / xs * w; }
    svg += grid(sc2, W, padL, padR, single ? fmtNum : function (v) { return Math.round(v); });
    if (single) { svg += areaAndLine(sd[0].norm, X, sc2, accent); }
    else sd.forEach(function (o, i) {
      var col = COLORS[i % COLORS.length], d = "";
      o.norm.forEach(function (pt, k) { d += (k ? "L" : "M") + X(pt[0]).toFixed(1) + "," + sc2.Y(pt[1]).toFixed(1); });
      svg += '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.5"/>';
    });
    svg += xlabels(sd[0].norm.map(function (pt) { return pt[0]; }), padL, w, H, padB, X);
    svg += "</svg>";
    var leg = sd.map(function (o, i) {
      var last = o.norm[o.norm.length - 1][1], pc = pctChange(o.s, cfg.base, cfg.range);
      return { s: o.s, col: single ? accent : COLORS[i % COLORS.length], val: single ? fmtNum(last) : Math.round(last), pc: pc };
    });
    body.innerHTML = svg + legendHTML(leg, p); wireOpens(body);
    var uni = {}; sd.forEach(function (o) { o.pts.forEach(function (pt) { uni[pt[0]] = 1; }); });
    var udates = Object.keys(uni).sort();
    p._hover = {
      kind: "line", W: W, padL: padL, w: w, x0: x0, xs: xs, Xd: function (d) { return X(d); },
      dates: udates, dnums: udates.map(dnum),
      names: sd.map(function (o) { return name(o.s); }),
      cols: sd.map(function (o, i) { return single ? accent : COLORS[i % COLORS.length]; }),
      maps: sd.map(function (o) { var m = {}; o.pts.forEach(function (pt) { m[pt[0]] = pt[1]; }); return m; }),
      baseName: bn, stats: sd.map(function (o) { return statsOf(o.pts); })
    };
    attachHover(p, body);
  }
  function areaAndLine(pts, X, sc, col) {
    var line = "", area = "";
    pts.forEach(function (p, k) { var x = X(p[0]).toFixed(1), y = sc.Y(p[1]).toFixed(1); line += (k ? "L" : "M") + x + "," + y; area += (k ? "L" : "M") + x + "," + y; });
    var y0 = sc.Y(sc.ticks()[0]).toFixed(1), x1 = X(pts[pts.length - 1][0]).toFixed(1), xF = X(pts[0][0]).toFixed(1);
    area += "L" + x1 + "," + y0 + "L" + xF + "," + y0 + "Z";
    return '<path d="' + area + '" fill="' + col + '" fill-opacity="0.16" stroke="none"/>' +
      '<path d="' + line + '" fill="none" stroke="' + col + '" stroke-width="1.7"/>';
  }
  function grid(sc, W, padL, padR, fmt) {
    var s = "";
    sc.ticks().forEach(function (v) {
      var y = sc.Y(v);
      s += '<line x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (W - padR) + '" y2="' + y.toFixed(1) + '" class="win-grid"/>';
      s += '<text x="' + (padL - 5) + '" y="' + (y + 3).toFixed(1) + '" text-anchor="end" class="win-ax" font-size="10">' + esc(fmt(v)) + "</text>";
    });
    return s;
  }
  function xlabels(dates, padL, w, H, padB, X) {
    if (!dates.length) return "";
    var idx = dates.length <= 1 ? [0] : [0, Math.floor((dates.length - 1) / 2), dates.length - 1];
    return idx.map(function (k) {
      var x = X ? X(dates[k]) : padL + (dates.length === 1 ? w / 2 : k / (dates.length - 1) * w);
      return '<text x="' + x.toFixed(1) + '" y="' + (H - padB + 15) + '" text-anchor="middle" class="win-ax" font-size="10">' + fmtDate(dates[k]) + "</text>";
    }).join("");
  }
  function legendHTML(items, p) {
    return '<div class="win-leg">' + items.map(function (it) {
      var lbl = it.label || (it.s ? name(it.s) : "");
      var pcs = (it.pc == null || isNaN(it.pc)) ? "" : ' <em class="' + (it.pc >= 0 ? "up" : "dn") + '">' + fmtPct(it.pc) + "</em>";
      var val = it.val != null ? " <b>" + it.val + "</b>" : "";
      var oa = it.s ? " data-cur='" + esc(it.s) + "'" : (it.pairAB ? " data-pair='" + esc(it.pairAB) + "'" : "");
      return '<span class="win-lg"' + oa + "><i style=\"background:" + it.col + '"></i>' + esc(lbl) + (it.extra ? " · " + esc(it.extra) : "") + val + pcs + (oa ? " <span class='op-i'>↗</span>" : "") + "</span>";
    }).join("") + "</div>";
  }

  function statLine(st) {
    if (!st) return "";
    return '<div class="wt-s">' + T("период", "range") + ": " + (st.chg == null ? "—" : fmtPct(st.chg)) +
      " · " + T("волат", "vol") + " " + (st.vol == null ? "—" : st.vol.toFixed(1) + "%") +
      " · min " + fmtNum(st.mn) + " · max " + fmtNum(st.mx) + " · " + T("сред", "avg") + " " + fmtNum(st.avg) + "</div>";
  }
  // таймлайн-курсор: вертикаль + тултип со значениями в наведённой точке
  function attachHover(p, body) {
    var svg = body.querySelector("svg"); if (!svg || !p._hover) return;
    var cross = document.createElement("div"); cross.className = "win-cross"; cross.style.display = "none";
    var tip = document.createElement("div"); tip.className = "win-tip"; tip.style.display = "none";
    body.appendChild(cross); body.appendChild(tip);
    function leave() { cross.style.display = "none"; tip.style.display = "none"; }
    svg.addEventListener("mousemove", function (e) { onHover(e, p, body, svg, cross, tip); });
    svg.addEventListener("mouseleave", leave);
    svg.addEventListener("touchmove", function (e) { if (e.touches && e.touches[0]) onHover(e.touches[0], p, body, svg, cross, tip); });
  }
  function onHover(e, p, body, svg, cross, tip) {
    var H = p._hover; if (!H) return;
    var sr = svg.getBoundingClientRect(), br = body.getBoundingClientRect();
    var scale = sr.width / H.W; if (!scale) return;
    var vbX = (e.clientX - sr.left) / scale, html, cxVp;
    if (H.kind === "candle") {
      var n = H.ohlc.length; if (!n) return;
      var i = n === 1 ? 0 : Math.round((vbX - H.padL) / H.w * (n - 1)); i = Math.max(0, Math.min(n - 1, i));
      var c = H.ohlc[i]; cxVp = sr.left + H.Xi(i) * scale;
      var up = c.c >= c.o, col = up ? "#26d07c" : "#ff5c5c";
      html = '<div class="wt-d">' + fmtDate(c.d) + "." + c.d.slice(0, 4) + '</div><div class="wt-r"><i style="background:' + col + '"></i>' + esc(H.name) + "</div>" +
        '<div class="wt-o">O ' + fmtNum(c.o) + " · H " + fmtNum(c.h) + "<br>L " + fmtNum(c.l) + " · C " + fmtNum(c.c) + " " + esc(H.baseName) + "</div>" + statLine(H.stats && H.stats[0]);
    } else {
      var ds = H.dnums; if (!ds.length) return;
      var inv = H.x0 + (vbX - H.padL) / H.w * H.xs, bi = 0, bd = Infinity;
      for (var k = 0; k < ds.length; k++) { var dd = Math.abs(ds[k] - inv); if (dd < bd) { bd = dd; bi = k; } }
      var date = H.dates[bi]; cxVp = sr.left + H.Xd(date) * scale;
      var rows = H.names.map(function (nm, j) {
        var v = H.maps[j][date], st = H.stats && H.stats[j];
        var run = (st && st.first && v != null) ? (v / st.first - 1) * 100 : null;
        var runh = (run == null) ? "" : ' <em class="' + (run >= 0 ? "up" : "dn") + '">' + fmtPct(run) + "</em>";
        return '<div class="wt-r"><i style="background:' + H.cols[j] + '"></i>' + esc(nm) + " <b>" + (v == null ? "—" : fmtNum(v)) + "</b>" + runh + "</div>" + statLine(st);
      }).join("");
      html = '<div class="wt-d">' + fmtDate(date) + "." + date.slice(0, 4) + "</div>" + rows + (H.baseName ? '<div class="wt-u">' + esc(H.baseName) + "</div>" : "");
    }
    var xPx = cxVp - br.left;
    cross.style.display = "block"; cross.style.left = xPx.toFixed(1) + "px";
    tip.innerHTML = html; tip.style.display = "block";
    var tw = tip.offsetWidth || 140, left = xPx + 12; if (left + tw > br.width) left = xPx - tw - 12; if (left < 2) left = 2;
    tip.style.left = left.toFixed(1) + "px";
  }

  // ----- WATCHLIST -----
  function drawWatch(p, body) {
    var slugs = panelSlugs(p);
    if (!slugs.length) { body.innerHTML = empty(T("Пусто.", "Empty.")); return; }
    var rows = slugs.map(function (s) {
      return { s: s, last: lastVal(s, "USD"), pc: pctChange(s, "USD", p.cfg.range), spk: rangeFilter(rebased(s, "USD"), p.cfg.range) };
    }).sort(function (a, b) { return (b.pc == null ? -1e9 : b.pc) - (a.pc == null ? -1e9 : a.pc); });
    body.innerHTML =
      '<div class="win-tblw"><table class="win-tbl"><thead><tr><th>' + T("Валюта", "Currency") + "</th><th>" + T("Цена, USDT", "Price, USDT") + "</th><th></th><th>" + T("Δ", "Δ") + "</th></tr></thead><tbody>" +
      rows.map(function (r) {
        return "<tr><td class='wl-n' data-add='" + esc(r.s) + "'>" + esc(name(r.s)) + " <b>" + esc(ticker(r.s)) + "</b>" + onMark(r.s) + " <span class='op-i'>📈</span></td>" +
          "<td class='wl-p'>" + fmtNum(r.last) + "</td>" +
          "<td class='wl-s'>" + spark(r.spk, r.pc) + "</td>" +
          "<td class='wl-c " + (r.pc >= 0 ? "up" : "dn") + "'>" + fmtPct(r.pc) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    wireAdd(body);
  }
  function spark(pts, pc) {
    if (!pts || pts.length < 2) return "";
    var W = 60, H = 18, v = pts.map(function (p) { return p[1]; });
    var mn = Math.min.apply(null, v), mx = Math.max.apply(null, v), rg = (mx - mn) || 1;
    var d = ""; pts.forEach(function (p, i) { d += (i ? "L" : "M") + (i / (pts.length - 1) * W).toFixed(1) + "," + (H - (p[1] - mn) / rg * H).toFixed(1); });
    var col = pc >= 0 ? "#26d07c" : "#ff5c5c";
    return '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H + '"><path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.3"/></svg>';
  }

  // ----- МУВЕРЫ -----
  function drawMovers(p, body) {
    var universe = (p.cfg.cur && p.cfg.cur.length) ? p.cfg.cur.filter(function (s) { return DATA.series[s]; }) : Object.keys(DATA.series);
    var all = universe.map(function (s) { return { s: s, pc: pctChange(s, "USD", p.cfg.range) }; })
      .filter(function (o) { return o.pc != null && isFinite(o.pc); });
    all.sort(function (a, b) { return b.pc - a.pc; });
    var n = p.cfg.n || 8, gain = all.slice(0, n), loss = all.slice(-n).reverse();
    function col(list) {
      return "<tbody>" + list.map(function (r) {
        return "<tr><td class='wl-n' data-add='" + esc(r.s) + "'>" + esc(ticker(r.s) || name(r.s)) + onMark(r.s) + " <span class='op-i'>📈</span></td><td class='wl-c " + (r.pc >= 0 ? "up" : "dn") + "'>" + fmtPct(r.pc) + "</td></tr>";
      }).join("") + "</tbody>";
    }
    body.innerHTML =
      '<div class="movers-wrap">' +
        '<div class="mv-col"><div class="mv-h up">▲ ' + T("Рост", "Gainers") + '</div><table class="win-tbl">' + col(gain) + "</table></div>" +
        '<div class="mv-col"><div class="mv-h dn">▼ ' + T("Падение", "Losers") + '</div><table class="win-tbl">' + col(loss) + "</table></div>" +
      "</div>";
    wireAdd(body);
  }

  // ----- ТЕПЛОВАЯ КАРТА -----
  function drawHeat(p, body) {
    var slugs = panelSlugs(p);
    var cells = slugs.map(function (s) { return { s: s, pc: pctChange(s, "USD", p.cfg.range) }; });
    body.innerHTML = '<div class="heat-grid">' + cells.map(function (c) {
      return '<div class="ht-cell' + (inActiveChart(c.s) ? " on-chart-cell" : "") + '" data-add="' + esc(c.s) + '" style="background:' + heatColor(c.pc) + '"><span class="ht-t">' + esc(ticker(c.s) || name(c.s)) + "</span><span class='ht-p'>" + (c.pc == null ? "—" : fmtPct(c.pc)) + "</span></div>";
    }).join("") + "</div>";
    wireAdd(body);
  }

  // ----- СКРИНЕР (поиск валют/пар по показателям + открыть на сайте) -----
  function drawScreen(p, body) {
    var c = p.cfg, isPair = c.mode === "pair";
    body.innerHTML =
      '<div class="scr-f">' +
        '<input class="scr-q" placeholder="' + T("поиск…", "search…") + '" value="' + esc(c.q || "") + '">' +
        '<label class="scr-fl">' + T("изм% ≥", "chg% ≥") + ' <input class="scr-chg" type="number" step="1" value="' + esc(c.fchg == null ? "" : c.fchg) + '"></label>' +
        '<label class="scr-fl">' + T("вол% ≤", "vol% ≤") + ' <input class="scr-vol" type="number" step="0.1" value="' + esc(c.fvol == null ? "" : c.fvol) + '"></label>' +
        '<select class="scr-sort">' +
          '<option value="chg"' + (c.sort === "chg" ? " selected" : "") + ">" + T("по изм.", "by chg") + "</option>" +
          '<option value="vol"' + (c.sort === "vol" ? " selected" : "") + ">" + T("по волат.", "by vol") + "</option>" +
          '<option value="price"' + (c.sort === "price" ? " selected" : "") + ">" + T("по цене", "by price") + "</option>" +
          '<option value="name"' + (c.sort === "name" ? " selected" : "") + ">" + T("по имени", "by name") + "</option>" +
        "</select>" +
        '<button class="scr-dir" title="' + T("Направление", "Direction") + '">' + (c.dir < 0 ? "↓" : "↑") + "</button>" +
        '<span class="scr-cnt"></span>' +
      "</div><div class=\"win-tblw scr-tbl\"></div>";
    var tbl = body.querySelector(".scr-tbl"), cnt = body.querySelector(".scr-cnt");
    function build() {
      var quote = c.quote, list = [];
      Object.keys(DATA.series).forEach(function (s) {
        if (isPair && s === quote) return;
        var last, chg, vol, label, openAttr;
        if (isPair) {
          var rp = rangeFilter(ratioSeries(s, quote), c.range); if (rp.length < 2) return;
          last = rp[rp.length - 1][1]; chg = (last / rp[0][1] - 1) * 100;
          var rets = []; for (var i = 1; i < rp.length; i++) { if (rp[i - 1][1]) rets.push(rp[i][1] / rp[i - 1][1] - 1); }
          vol = null; if (rets.length) { var m = rets.reduce(function (a, b) { return a + b; }, 0) / rets.length; vol = Math.sqrt(rets.reduce(function (a, b) { return a + (b - m) * (b - m); }, 0) / rets.length) * 100; }
          label = esc(ticker(s) || name(s)) + "/" + esc(ticker(quote) || name(quote));
          openAttr = "data-addpair='" + esc(s) + "|" + esc(quote) + "'";
        } else {
          last = lastVal(s, "USD"); chg = pctChange(s, "USD", c.range); vol = volat(s, "USD", c.range);
          if (chg == null) return;
          label = esc(name(s)) + (ticker(s) ? " <b>" + esc(ticker(s)) + "</b>" : "") + onMark(s);
          openAttr = "data-add='" + esc(s) + "'";
        }
        list.push({ s: s, label: label, last: last, chg: chg, vol: vol, oa: openAttr });
      });
      var q = (c.q || "").toLowerCase().trim();
      var fchg = (c.fchg === "" || c.fchg == null) ? null : +c.fchg;
      var fvol = (c.fvol === "" || c.fvol == null) ? null : +c.fvol;
      list = list.filter(function (r) {
        if (q) { var cc = DATA.cur[r.s] || {}; if ((r.s + " " + (cc.n || "") + " " + (cc.t || "")).toLowerCase().indexOf(q) < 0) return false; }
        if (fchg != null && !isNaN(fchg) && !(r.chg >= fchg)) return false;
        if (fvol != null && !isNaN(fvol) && !(r.vol != null && r.vol <= fvol)) return false;
        return true;
      });
      var key = c.sort, dir = c.dir < 0 ? -1 : 1;
      list.sort(function (a, b) {
        if (key === "name") return (a.label > b.label ? 1 : -1) * dir;
        var va, vb;
        if (key === "vol") { va = a.vol == null ? -1e9 : a.vol; vb = b.vol == null ? -1e9 : b.vol; }
        else if (key === "price") { va = a.last == null ? -1e9 : a.last; vb = b.last == null ? -1e9 : b.last; }
        else { va = a.chg; vb = b.chg; }
        return (va - vb) * dir;
      });
      return list;
    }
    function renderTable() {
      var list = build();
      cnt.textContent = list.length + " " + T("шт", "items");
      if (!list.length) { tbl.innerHTML = empty(T("Ничего не найдено", "Nothing found")); return; }
      tbl.innerHTML = '<table class="win-tbl"><thead><tr><th>' + (isPair ? T("Пара", "Pair") : T("Валюта", "Currency")) + "</th><th>" + (isPair ? T("Курс", "Rate") : T("Цена", "Price")) + "</th><th>" + T("Изм%", "Chg%") + "</th><th>" + T("Вол%", "Vol%") + "</th></tr></thead><tbody>" +
        list.map(function (r) {
          return "<tr " + r.oa + "><td class='wl-n'>" + r.label + " <span class='op-i'>📈</span></td><td class='wl-p'>" + fmtNum(r.last) + "</td><td class='wl-c " + (r.chg >= 0 ? "up" : "dn") + "'>" + fmtPct(r.chg) + "</td><td class='wl-v'>" + (r.vol == null ? "—" : r.vol.toFixed(1)) + "</td></tr>";
        }).join("") + "</tbody></table>";
      wireAdd(tbl);
    }
    body.querySelector(".scr-q").addEventListener("input", function () { c.q = this.value; renderTable(); saveWS(); });
    body.querySelector(".scr-chg").addEventListener("input", function () { c.fchg = this.value; renderTable(); saveWS(); });
    body.querySelector(".scr-vol").addEventListener("input", function () { c.fvol = this.value; renderTable(); saveWS(); });
    body.querySelector(".scr-sort").addEventListener("change", function () { c.sort = this.value; renderTable(); saveWS(); });
    body.querySelector(".scr-dir").addEventListener("click", function () { c.dir = c.dir < 0 ? 1 : -1; this.textContent = c.dir < 0 ? "↓" : "↑"; renderTable(); saveWS(); });
    renderTable();
  }

  // ----- СПРОС ИЗ ПОИСКА (Google Search Console: популярные направления/валюты) -----
  function chartableCur(s) { return !!(s && DATA.series[s]); }
  // фраза-мусор (URL/путь/бренд) — не показываем как «запрос»
  function dmJunk(q) { var s = (q || "").toLowerCase().trim(); if (!s) return true; if (/^(https?:|www\.|\/)/.test(s)) return true; return s.indexOf("ratescout") >= 0; }
  // иконка-подсказка: 📈 построится в графике · ↗ откроет страницу на сайте · 🔍 нет у нас → поиск
  function dmCurIcon(s) { return chartableCur(s) ? "📈" : (s && DATA.cur[s] ? "↗" : "🔍"); }
  function drawDemand(p, body) {
    if (p.cfg.view === "trend") {
      var tr = DATA.trending || [];
      if (!tr.length) { body.innerHTML = empty(T("Тренд пока не загружен (обновляется из CoinGecko).", "Trending not loaded yet (updates from CoinGecko).")); return; }
      body.innerHTML = '<p class="dm-hint">' + T("Топ поиска CoinGecko. 📈 — в график · ↗ — страница валюты · 🔍 — поиск.", "Top searched on CoinGecko. 📈 — chart · ↗ — currency page · 🔍 — search.") + "</p>" +
        '<div class="win-tblw"><table class="win-tbl"><thead><tr><th>' + T("Монета", "Coin") + "</th><th>" + T("Ранг", "Rank") + "</th><th>24ч</th></tr></thead><tbody>" +
        tr.map(function (c, i) {
          var slug = c.slug || "";
          var nm = esc(c.name || c.symbol || "?") + (c.symbol ? " <b>" + esc(c.symbol) + "</b>" : "");
          return "<tr><td class='wl-n' data-tslug='" + esc(slug) + "' data-tname='" + esc(c.name || c.symbol || "") + "'>" + (i + 1) + ". " + nm + onMark(slug) + " <span class='op-i'>" + dmCurIcon(slug) + "</span></td>" +
            "<td class='wl-c'>" + (c.rank || "—") + "</td>" +
            "<td class='wl-c " + (c.chg24h >= 0 ? "up" : "dn") + "'>" + (c.chg24h == null ? "—" : fmtPct(c.chg24h)) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
      Array.prototype.forEach.call(body.querySelectorAll("[data-tslug]"), function (n) {
        n.classList.add("op-link");
        n.addEventListener("click", function (e) {
          e.stopPropagation();
          var s = n.getAttribute("data-tslug");
          if (chartableCur(s)) addToActiveChart(s);
          else if (s && DATA.cur[s]) openUrl(curUrl(s));
          else openUrl("https://yandex.ru/search/?text=" + encodeURIComponent((n.getAttribute("data-tname") || "") + " курс"));
        });
      });
      return;
    }
    if (p.cfg.view === "yandex") {
      var yq = (DATA.yandex || []).filter(function (r) { return !dmJunk(r.q); });
      if (!yq.length) { body.innerHTML = empty(T("Яндекс-запросы пока не загружены (Вебмастер).", "Yandex queries not loaded yet (Webmaster).")); return; }
      body.innerHTML = '<p class="dm-hint">' + T("Что ищут в Яндексе, чтобы найти сайт (показы·клики). ↗ — открыть в Яндексе.", "What people search in Yandex to find the site (shows·clicks). ↗ — open in Yandex.") + "</p>" +
        '<div class="win-tblw"><table class="win-tbl"><thead><tr><th>' + T("Запрос", "Query") + "</th><th>" + T("Показы", "Shows") + "</th><th>" + T("Клики", "Clicks") + "</th></tr></thead><tbody>" +
        yq.map(function (r) {
          return "<tr><td class='wl-n' data-yq='" + esc(r.q) + "'>" + esc(r.q) + " <span class='op-i'>↗</span></td>" +
            "<td class='wl-c'>" + (r.shows == null ? "—" : r.shows) + "</td><td class='wl-c'>" + (r.clicks == null ? "—" : r.clicks) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
      Array.prototype.forEach.call(body.querySelectorAll("[data-yq]"), function (n) {
        n.classList.add("op-link"); n.title = T("Открыть в Яндексе", "Open in Yandex");
        n.addEventListener("click", function (e) { e.stopPropagation(); openUrl("https://yandex.ru/search/?text=" + encodeURIComponent(n.getAttribute("data-yq"))); });
      });
      return;
    }
    if (p.cfg.view === "metrika") {
      var mq = (DATA.metrika || []).filter(function (r) { return !dmJunk(r.q); });
      if (!mq.length) { body.innerHTML = empty(T("Фразы Метрики пока не загружены (часть Яндекс скрывает).", "Metrika phrases not loaded yet (Yandex hides some).")); return; }
      body.innerHTML = '<p class="dm-hint">' + T("Поисковые фразы из Яндекс.Метрики (визиты). ↗ — открыть в Яндексе.", "Search phrases from Yandex Metrika (visits). ↗ — open in Yandex.") + "</p>" +
        '<div class="win-tblw"><table class="win-tbl"><thead><tr><th>' + T("Фраза", "Phrase") + "</th><th>" + T("Визиты", "Visits") + "</th></tr></thead><tbody>" +
        mq.map(function (r) { return "<tr><td class='wl-n' data-yq='" + esc(r.q) + "'>" + esc(r.q) + " <span class='op-i'>↗</span></td><td class='wl-c'>" + (r.visits == null ? "—" : r.visits) + "</td></tr>"; }).join("") + "</tbody></table></div>";
      Array.prototype.forEach.call(body.querySelectorAll("[data-yq]"), function (n) {
        n.classList.add("op-link"); n.title = T("Открыть в Яндексе", "Open in Yandex");
        n.addEventListener("click", function (e) { e.stopPropagation(); openUrl("https://yandex.ru/search/?text=" + encodeURIComponent(n.getAttribute("data-yq"))); });
      });
      return;
    }
    var pop = DATA.popular || {}, keys = Object.keys(pop);
    if (!keys.length) { body.innerHTML = empty(T("Данных поиска пока мало — накапливаются из Google Search Console.", "Little search data yet — accumulating from Google Search Console.")); return; }
    var hint = '<p class="dm-hint">' + T("По данным поиска Google (клики). 📈 — в график · ↗ — на сайте.", "From Google search (clicks). 📈 — chart · ↗ — on site.") + "</p>";
    if (p.cfg.view === "cur") {
      var agg = {};
      keys.forEach(function (k) { var c = pop[k]; k.split(">").forEach(function (s) { agg[s] = (agg[s] || 0) + c; }); });
      var rows = Object.keys(agg).map(function (s) { return { s: s, c: agg[s] }; }).sort(function (a, b) { return b.c - a.c; });
      body.innerHTML = hint + '<div class="win-tblw"><table class="win-tbl"><thead><tr><th>' + T("Валюта", "Currency") + "</th><th>" + T("Запросы", "Searches") + "</th></tr></thead><tbody>" +
        rows.map(function (r) { return "<tr><td class='wl-n' data-cur='" + esc(r.s) + "'>" + esc(name(r.s)) + (ticker(r.s) ? " <b>" + esc(ticker(r.s)) + "</b>" : "") + onMark(r.s) + " <span class='op-i'>" + dmCurIcon(r.s) + "</span></td><td class='wl-c'>" + r.c + "</td></tr>"; }).join("") +
        "</tbody></table></div>";
    } else {
      var drows = keys.map(function (k) { var ab = k.split(">"); return { a: ab[0], b: ab[1], c: pop[k] }; }).sort(function (x, y) { return y.c - x.c; });
      body.innerHTML = hint + '<div class="win-tblw"><table class="win-tbl"><thead><tr><th>' + T("Направление", "Direction") + "</th><th>" + T("Запросы", "Searches") + "</th></tr></thead><tbody>" +
        drows.map(function (r) { var ch = (chartableCur(r.a) || chartableCur(r.b)) ? "📈" : "↗"; return "<tr><td class='wl-n' data-a='" + esc(r.a) + "' data-b='" + esc(r.b) + "'>" + esc(name(r.a)) + " → " + esc(name(r.b)) + " <span class='op-i'>" + ch + "</span></td><td class='wl-c'>" + r.c + "</td></tr>"; }).join("") +
        "</tbody></table></div>";
    }
    // умный клик: в активный график (пара A/B или валюта в USDT), иначе — открыть на сайте
    Array.prototype.forEach.call(body.querySelectorAll("[data-cur]"), function (n) {
      n.classList.add("op-link"); n.title = T("В активный график", "Into active chart");
      n.addEventListener("click", function (e) { e.stopPropagation(); var s = n.getAttribute("data-cur"); if (DATA.series[s]) addToActiveChart(s); else openUrl(curUrl(s)); });
    });
    Array.prototype.forEach.call(body.querySelectorAll("[data-a]"), function (n) {
      n.classList.add("op-link"); n.title = T("В активный график", "Into active chart");
      n.addEventListener("click", function (e) {
        e.stopPropagation();
        var a = n.getAttribute("data-a"), b = n.getAttribute("data-b"), ca = !!DATA.series[a], cb = !!DATA.series[b];
        if (ca && cb) setActiveRatio(a, b);
        else if (ca) addToActiveChart(a);
        else if (cb) addToActiveChart(b);
        else openUrl(pairUrl(a, b));
      });
    });
  }

  // ---------------- контекстное меню по графику (правый клик) ----------------
  var menuEl = null;
  function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; document.removeEventListener("click", closeMenu); } }
  function openChartMenu(p, x, y) {
    closeMenu();
    var sels = p.cfg.cur.filter(function (s) { return DATA.series[s]; });
    var items = [];
    sels.slice(0, 6).forEach(function (s) { items.push({ l: T("Открыть ", "Open ") + name(s), f: function () { openUrl(curUrl(s)); } }); });
    if (sels.length >= 2) {
      var a = sels[0], b = sels[1];
      items.push({ sep: 1 });
      items.push({ l: T("Открыть пару ", "Open pair ") + (ticker(a) || a) + "/" + (ticker(b) || b) + (pairHasPage(a, b) ? "" : " (BestChange)"), f: function () { openUrl(pairUrl(a, b)); } });
      items.push({ l: T("График пары A/B", "A/B ratio chart"), f: function () { p.cfg.type = "ratio"; renderAll(); saveWS(); } });
    }
    items.push({ sep: 1 });
    items.push({ l: T("Тип: линии", "Type: lines"), f: function () { p.cfg.type = "line"; renderAll(); saveWS(); } });
    items.push({ l: T("Тип: свечи", "Type: candles"), f: function () { p.cfg.type = "candle"; renderAll(); saveWS(); } });
    items.push({ l: (p.cfg.log ? "✓ " : "") + T("Лог-шкала", "Log scale"), f: function () { p.cfg.log = !p.cfg.log; renderAll(); saveWS(); } });
    items.push({ sep: 1 });
    items.push({ l: T("Выбрать валюты…", "Pick currencies…"), f: function () { var el = canvas.querySelector('[data-id="' + p.id + '"]'); openPicker(p, el); } });
    items.push({ l: T("Экспорт CSV", "Export CSV"), f: function () { exportChartCSV(p); } });
    items.push({ l: T("Экспорт PNG", "Export PNG"), f: function () { exportChartPNG(p); } });
    showMenu(items, x, y);
  }
  // общая отрисовка контекстного меню
  function showMenu(items, x, y) {
    menuEl = document.createElement("div"); menuEl.className = "term-menu";
    menuEl.innerHTML = items.map(function (it, i) { return it.sep ? '<div class="tm-sep"></div>' : '<button data-i="' + i + '">' + esc(it.l) + "</button>"; }).join("");
    (fsEl() || document.body).appendChild(menuEl);
    var vw = window.innerWidth, vh = window.innerHeight, mw = menuEl.offsetWidth, mh = menuEl.offsetHeight;
    menuEl.style.left = Math.min(x, vw - mw - 4) + "px"; menuEl.style.top = Math.min(y, vh - mh - 4) + "px";
    Array.prototype.forEach.call(menuEl.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function (e) { e.stopPropagation(); var it = items[+b.getAttribute("data-i")]; closeMenu(); if (it && it.f) it.f(); });
    });
    setTimeout(function () { document.addEventListener("click", closeMenu); }, 0);
  }
  function webSearch(engine, q) {
    var t = encodeURIComponent(q);
    openUrl(engine === "g" ? "https://www.google.com/search?q=" + t : "https://yandex.ru/search/?text=" + t);
  }
  // меню по одной валюте (правый клик в любом окне)
  function openCurMenu(slug, dispName, x, y) {
    closeMenu();
    var ours = !!(slug && DATA.cur[slug]), q = ours ? name(slug) : (dispName || slug);
    var items = [];
    if (chartableCur(slug)) items.push({ l: "📈 " + (inActiveChart(slug) ? T("Убрать с активного графика", "Remove from active chart") : T("Добавить на активный график", "Add to active chart")), f: function () { addToActiveChart(slug); } });
    if (ours) items.push({ l: "↗ " + T("Страница валюты на сайте", "Currency page on site"), f: function () { openUrl(curUrl(slug)); } });
    items.push({ sep: 1 });
    items.push({ l: "🔍 Google: " + q, f: function () { webSearch("g", q + " курс криптовалюта"); } });
    items.push({ l: "🔍 " + T("Яндекс", "Yandex") + ": " + q, f: function () { webSearch("y", q + " курс криптовалюта"); } });
    showMenu(items, x, y);
  }
  // меню по направлению/паре (правый клик по строке направления)
  function openPairMenu(a, b, x, y) {
    closeMenu();
    var ca = chartableCur(a), cb = chartableCur(b), items = [];
    if (ca && cb) items.push({ l: "📈 " + T("Пара A/B в графике", "A/B pair in chart"), f: function () { setActiveRatio(a, b); } });
    else if (ca) items.push({ l: "📈 " + T("Открыть в графике", "Open in chart") + ": " + name(a), f: function () { addToActiveChart(a); } });
    else if (cb) items.push({ l: "📈 " + T("Открыть в графике", "Open in chart") + ": " + name(b), f: function () { addToActiveChart(b); } });
    items.push({ l: (pairHasPage(a, b) ? "↗ " + T("Страница направления", "Direction page") : "↗ " + T("Открыть на BestChange (реф.)", "Open on BestChange (ref)")), f: function () { openUrl(pairUrl(a, b)); } });
    items.push({ sep: 1 });
    var q = name(a) + " " + name(b) + " обмен";
    items.push({ l: "🔍 Google", f: function () { webSearch("g", q); } });
    items.push({ l: "🔍 " + T("Яндекс", "Yandex"), f: function () { webSearch("y", q); } });
    showMenu(items, x, y);
  }
  // меню по поисковой фразе (Яндекс/Метрика)
  function openPhraseMenu(q, x, y) {
    closeMenu();
    showMenu([
      { l: "🔍 Google: " + q, f: function () { webSearch("g", q); } },
      { l: "🔍 " + T("Яндекс", "Yandex") + ": " + q, f: function () { webSearch("y", q); } }
    ], x, y);
  }
  // меню фона терминала (пустое место / между окнами)
  function openBgMenu(x, y) {
    closeMenu();
    showMenu([
      { l: "◧ " + T("Выбрать валюты (активный график)", "Pick currencies (active chart)"), f: openPickerForActive },
      { sep: 1 },
      { l: "+ " + T("График", "Chart"), f: function () { addPanel("chart"); } },
      { l: "+ Watchlist", f: function () { addPanel("watch"); } },
      { l: "+ " + T("Муверы", "Movers"), f: function () { addPanel("movers"); } },
      { l: "+ " + T("Хитмап", "Heatmap"), f: function () { addPanel("heat"); } },
      { l: "+ " + T("Скринер", "Screener"), f: function () { addPanel("screen"); } },
      { l: "+ " + T("Спрос", "Demand"), f: function () { addPanel("demand"); } },
      { sep: 1 },
      { l: (STATE.tiled ? "✓ " : "") + "⊞ " + T("Сетка", "Tile"), f: function () { STATE.tiled = !STATE.tiled; renderAll(); saveWS(); } },
      { l: "⛶ " + T("Во весь экран", "Fullscreen"), f: toggleFull }
    ], x, y);
  }
  // делегированный правый клик (capture): валюта/пара → своё меню; фраза → Google/Яндекс;
  // тело графика → меню графика (bubble); поля ввода → родное; остальное → меню фона (без браузерного).
  canvas.addEventListener("contextmenu", function (e) {
    if (e.target.closest("input,select,textarea")) return;
    var el = e.target.closest("[data-cur],[data-add],[data-tslug],[data-a],[data-pair],[data-addpair]");
    if (el) {
      var pr = el.getAttribute("data-a") ? [el.getAttribute("data-a"), el.getAttribute("data-b")]
        : (el.getAttribute("data-pair") ? el.getAttribute("data-pair").split("|")
          : (el.getAttribute("data-addpair") ? el.getAttribute("data-addpair").split("|") : null));
      e.preventDefault(); e.stopPropagation();
      if (pr && pr[0] && pr[1]) openPairMenu(pr[0], pr[1], e.clientX, e.clientY);
      else { var slug = el.getAttribute("data-cur") || el.getAttribute("data-add") || el.getAttribute("data-tslug") || ""; if (slug) openCurMenu(slug, el.getAttribute("data-tname") || "", e.clientX, e.clientY); }
      return;
    }
    var yq = e.target.closest("[data-yq]");
    if (yq) { e.preventDefault(); e.stopPropagation(); openPhraseMenu(yq.getAttribute("data-yq"), e.clientX, e.clientY); return; }
    if (e.target.closest(".win-chart .win-body")) return; // тело графика → своё меню (bubble)
    e.preventDefault(); e.stopPropagation();
    openBgMenu(e.clientX, e.clientY);
  }, true);

  // ЛКМ по пустому месту (кроме графика, контролов и названий валют/направлений) →
  // открыть пикер выбора валют для активного графика.
  function openPickerForActive() {
    var p = getActiveChart();
    if (!p) { p = { id: STATE.seq++, t: "chart", cfg: { cur: [], base: "USD", type: "line", range: 365, log: false }, g: nextPos() }; STATE.panels.push(p); activeId = p.id; renderAll(); }
    var el = canvas.querySelector('[data-id="' + p.id + '"]');
    if (el) openPicker(p, el);
  }
  canvas.addEventListener("click", function (e) {
    if (isMobile()) return;
    // пропускаем: сам график (окно), шапки/ресайз/крестовину, контролы, валюты/направления/фразы
    if (e.target.closest("button,select,input,label,a,.win-chart,.win-h,.win-rz,.tile-cross,.op-link,[data-cur],[data-add],[data-tslug],[data-a],[data-pair],[data-addpair],[data-yq]")) return;
    openPickerForActive();
  });
  function exportChartCSV(p) {
    var sels = p.cfg.cur.filter(function (s) { return DATA.series[s]; }); if (!sels.length) return;
    var uni = {}, maps = sels.map(function (s) { var m = {}; rangeFilter(rebased(s, p.cfg.base), p.cfg.range).forEach(function (pt) { m[pt[0]] = pt[1]; uni[pt[0]] = 1; }); return m; });
    var dates = Object.keys(uni).sort();
    var head = ["date"].concat(sels.map(function (s) { return (ticker(s) || name(s)).replace(/[;,]/g, " "); }));
    var lines = [head.join(";")];
    dates.forEach(function (d) { lines.push([d].concat(maps.map(function (m) { return m[d] == null ? "" : m[d]; })).join(";")); });
    var a = document.createElement("a"); a.href = "data:text/csv;charset=utf-8," + encodeURIComponent("﻿" + lines.join("\n")); a.download = "ratescout-chart.csv"; document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }
  function exportChartPNG(p) {
    var el = canvas.querySelector('[data-id="' + p.id + '"]'); if (!el) return;
    var svg = el.querySelector("svg"); if (!svg) return;
    var vb = svg.viewBox.baseVal, W = vb.width || 400, H = vb.height || 240;
    var xml = new XMLSerializer().serializeToString(svg), url = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(xml)));
    var img = new Image();
    img.onload = function () {
      var cv = document.createElement("canvas"); cv.width = W * 2; cv.height = H * 2;
      var ctx = cv.getContext("2d"); ctx.fillStyle = "#0a0d12"; ctx.fillRect(0, 0, cv.width, cv.height); ctx.scale(2, 2); ctx.drawImage(img, 0, 0, W, H);
      try { var a = document.createElement("a"); a.href = cv.toDataURL("image/png"); a.download = "ratescout-chart.png"; document.body.appendChild(a); a.click(); document.body.removeChild(a); } catch (e) {}
    };
    img.src = url;
  }

  // ---------------- модалка выбора валют для графика ----------------
  var pickBox = null;
  function openPicker(p, el) {
    if (pickBox) pickBox.remove();
    var init = (p.cfg.cur && p.cfg.cur.length) ? p.cfg.cur : (p.t === "movers" ? [] : panelSlugs(p));
    var chosen = {}; init.forEach(function (s) { chosen[s] = 1; });
    pickBox = document.createElement("div"); pickBox.className = "term-pick";
    var slugs = Object.keys(DATA.series).sort(byName);
    pickBox.innerHTML =
      '<div class="pick-in">' +
        '<div class="pick-h"><b>' + T("Выбор валют", "Select currencies") + " · " + esc(PTITLE[p.t] || "") + '</b><button class="pick-x">✕</button></div>' +
        '<input class="pick-search" placeholder="' + T("поиск…", "search…") + '" autocomplete="off">' +
        '<div class="pick-presets"><button data-g="top">' + T("Топ-крипта", "Top crypto") + '</button><button data-g="stable">' + T("Стейблы", "Stables") + '</button><button data-g="fiat">' + T("Фиат", "Fiat") + '</button><button data-g="clr">' + T("Очистить", "Clear") + "</button></div>" +
        '<div class="pick-list"></div>' +
        '<div class="pick-f"><button class="pick-ok">' + T("Готово", "Done") + "</button></div>" +
      "</div>";
    (fsEl() || document.body).appendChild(pickBox);
    var listEl = pickBox.querySelector(".pick-list"), searchEl = pickBox.querySelector(".pick-search");
    var pbase = p.cfg.base || "USD", prng = p.cfg.range;
    function renderList(q) {
      q = (q || "").toLowerCase().trim();
      var fs = slugs.filter(function (s) { if (!q) return true; var c = DATA.cur[s] || {}; return (s + " " + (c.n || "") + " " + (c.t || "")).toLowerCase().indexOf(q) >= 0; });
      var hd = '<div class="pick-row pick-hd"><span>' + T("Валюта", "Currency") + "</span><span>" + T("Цена", "Price") + "</span><span>Δ%</span><span>" + T("вол%", "vol%") + "</span></div>";
      listEl.innerHTML = hd + fs.map(function (s) {
        var c = DATA.cur[s] || { n: s, t: "" };
        var last = lastVal(s, pbase), chg = pctChange(s, pbase, prng), vol = volat(s, pbase, prng);
        return '<label class="pick-i pick-row"><span class="pick-nm"><input type="checkbox" data-s="' + esc(s) + '"' + (chosen[s] ? " checked" : "") + "> " + esc(c.n) + " <b>" + esc(c.t) + "</b></span>" +
          '<span class="pick-p">' + fmtNum(last) + "</span>" +
          '<span class="pick-c ' + (chg >= 0 ? "up" : "dn") + '">' + (chg == null ? "—" : fmtPct(chg)) + "</span>" +
          '<span class="pick-v">' + (vol == null ? "—" : vol.toFixed(1)) + "</span></label>";
      }).join("");
      Array.prototype.forEach.call(listEl.querySelectorAll("input"), function (inp) {
        inp.addEventListener("change", function () { var s = inp.getAttribute("data-s"); if (inp.checked) chosen[s] = 1; else delete chosen[s]; });
      });
    }
    renderList("");
    searchEl.addEventListener("input", function () { renderList(searchEl.value); });
    Array.prototype.forEach.call(pickBox.querySelectorAll(".pick-presets button"), function (b) {
      b.addEventListener("click", function (e) {
        e.preventDefault();
        var g = b.getAttribute("data-g");
        chosen = {}; // группа/очистка ЗАМЕНЯЮТ выбор (иначе «Стейблы»/«Фиат» лишь доклеиваются и не переключают)
        if (g !== "clr") groupSlugs(g).forEach(function (s) { chosen[s] = 1; });
        renderList(searchEl.value);
      });
    });
    function apply() {
      p.cfg.cur = Object.keys(chosen).filter(function (s) { return DATA.series[s]; });
      pickBox.remove(); pickBox = null;
      // обновляем панель на месте (не renderAll — иначе вылет из фулскрина)
      var pel = canvas.querySelector('[data-id="' + p.id + '"]');
      if (pel) {
        var pk = pel.querySelector(".win-pick"); if (pk) pk.textContent = "◧ " + T("Валюты", "Currencies") + " (" + p.cfg.cur.length + ")";
        drawBody(p, pel.querySelector(".win-body"));
      } else { renderAll(); }
      saveWS();
    }
    pickBox.querySelector(".pick-ok").addEventListener("click", apply);
    pickBox.querySelector(".pick-x").addEventListener("click", function () { pickBox.remove(); pickBox = null; });
    pickBox.addEventListener("click", function (e) { if (e.target === pickBox) { pickBox.remove(); pickBox = null; } });
  }

  // ---------------- раскладки-пресеты ----------------
  function applyLayout(name) {
    var cw = canvas.clientWidth || 960, g = 8;
    function grid2(cells) { // cells: [[col,row,colspan,rowspan]] в сетке 2×2
      var cellW = (cw - g * 3) / 2, cellH = 320;
      return cells.map(function (c) { return [g + c[0] * (cellW + g), g + c[1] * (cellH + g), cellW * (c[2] || 1) + (c[2] > 1 ? g : 0), cellH * (c[3] || 1) + (c[3] > 1 ? g : 0)]; });
    }
    var P = [];
    if (name === "overview") {
      var gg = grid2([[0, 0], [1, 0], [0, 1], [1, 1]]);
      P = [
        { t: "chart", cfg: { cur: groupSlugs("top").slice(0, 4), base: "USD", type: "line", range: 365, log: false }, g: gg[0] },
        { t: "watch", cfg: { grp: "top", range: 30 }, g: gg[1] },
        { t: "movers", cfg: { range: 30, n: 8 }, g: gg[2] },
        { t: "heat", cfg: { grp: "top", range: 30 }, g: gg[3] }
      ];
    } else if (name === "charts2") {
      var g2 = grid2([[0, 0], [1, 0]]);
      P = [
        { t: "chart", cfg: { cur: ["bitcoin"].filter(function (s) { return DATA.series[s]; }), base: "USD", type: "line", range: 365, log: false }, g: g2[0] },
        { t: "chart", cfg: { cur: ["ethereum"].filter(function (s) { return DATA.series[s]; }), base: "USD", type: "line", range: 365, log: false }, g: g2[1] }
      ];
    } else if (name === "charts4") {
      var g4 = grid2([[0, 0], [1, 0], [0, 1], [1, 1]]), seed = groupSlugs("top");
      P = [0, 1, 2, 3].map(function (i) { return { t: "chart", cfg: { cur: [seed[i]].filter(Boolean), base: "USD", type: "line", range: 365, log: false }, g: g4[i] }; });
    } else if (name === "watchbig") {
      var cellW = (cw - g * 3) / 2;
      P = [
        { t: "watch", cfg: { grp: "top", range: 30 }, g: [g, g, cellW, 650] },
        { t: "chart", cfg: { cur: groupSlugs("top").slice(0, 3), base: "USD", type: "line", range: 365, log: false }, g: [g * 2 + cellW, g, cellW, 320] },
        { t: "heat", cfg: { grp: "top", range: 30 }, g: [g * 2 + cellW, g * 2 + 320, cellW, 322] }
      ];
    }
    if (!P.length) return;
    STATE.panels = P.map(function (p) { p.id = STATE.seq++; return p; });
    renderAll(); saveWS();
  }

  // ---------------- переключатель Классика ⇄ Терминал ----------------
  var VIEW_KEY = "rs_mon_view";
  var classicEl = document.getElementById("monitor");
  var btnTerm = document.getElementById("modeTerm");
  var btnClassic = document.getElementById("modeClassic");
  function setView(v) {
    try { localStorage.setItem(VIEW_KEY, v); } catch (e) {}
    if (v === "classic") {
      root.className = "th-" + STATE.theme; // без "term" → скрыт
      if (classicEl) classicEl.style.display = "";
      window.dispatchEvent(new Event("resize")); // перерисовать классический график
    } else {
      root.className = "term th-" + STATE.theme + (isMobile() ? " term-mobile" : "");
      if (classicEl) classicEl.style.display = "none";
      if (DATA) renderAll();
    }
    if (btnTerm) btnTerm.classList.toggle("on", v !== "classic");
    if (btnClassic) btnClassic.classList.toggle("on", v === "classic");
  }
  if (btnTerm) btnTerm.addEventListener("click", function () { setView("term"); });
  if (btnClassic) btnClassic.addEventListener("click", function () { setView("classic"); });
  function initialView() { var v = "term"; try { v = localStorage.getItem(VIEW_KEY) || "term"; } catch (e) {} return v; }

  // ---------------- init ----------------
  var mqMobile = window.matchMedia("(max-width:760px)");
  function onModeChange() { root.className = "term th-" + STATE.theme + (isMobile() ? " term-mobile" : ""); renderAll(); }
  if (mqMobile.addEventListener) mqMobile.addEventListener("change", onModeChange); else if (mqMobile.addListener) mqMobile.addListener(onModeChange);
  var rzTimer = null, lastW = window.innerWidth;
  window.addEventListener("resize", function () {
    // МОБИЛА: показ/скрытие адресной строки шлёт resize и слегка меняет размеры. Перерисовка тут запрещена —
    // renderAll() пересобирает DOM, меняет высоту → браузер снова дёргает панель → петля и прыжки страницы вверх.
    // Потоковой (столбиком) мобильной раскладке ресайз не нужен; поворот ловим отдельно (orientationchange).
    if (isMobile()) return;
    var w = window.innerWidth;
    if (Math.abs(w - lastW) < 24) return; // мелкий джиттер ширины игнорируем
    lastW = w;
    clearTimeout(rzTimer); rzTimer = setTimeout(function () { renderAll(); }, 200);
  });
  window.addEventListener("orientationchange", function () { clearTimeout(rzTimer); rzTimer = setTimeout(function () { lastW = window.innerWidth; renderAll(); }, 300); });

  // если стартуем в классическом виде — покажем его сразу, терминал подгрузим лениво
  if (initialView() === "classic") { root.className = "th-bloomberg"; if (classicEl) classicEl.style.display = ""; if (btnClassic) btnClassic.classList.add("on"); if (btnTerm) btnTerm.classList.remove("on"); }

  fetch("/data/monitor.json").then(function (r) { return r.json(); }).then(function (j) {
    DATA = j;
    (j.pairs || []).forEach(function (k) { PAIRS[k] = 1; });
    loadWS();
    buildBar();
    setView(initialView());
  }).catch(function () { canvas.innerHTML = '<p class="win-empty">' + T("Не удалось загрузить данные монитора.", "Failed to load monitor data.") + "</p>"; });
})();
