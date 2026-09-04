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

  // ---------------- состояние воркспейса ----------------
  var STATE = { theme: "bloomberg", panels: [], seq: 1 };
  var zTop = 10;
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
    var ws = { theme: STATE.theme, panels: STATE.panels.map(function (p) { return { t: p.t, cfg: p.cfg, g: p.g }; }) };
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
        '<button class="tb-btn" id="tbShare">' + T("Ссылка", "Link") + "</button>" +
        '<button class="tb-btn" id="tbReset">' + T("Сброс", "Reset") + "</button>" +
      "</div>";
    Array.prototype.forEach.call(bar.querySelectorAll(".tb-add"), function (b) {
      b.addEventListener("click", function () { addPanel(b.getAttribute("data-t")); });
    });
    var themeSel = bar.querySelector("#tbTheme"); themeSel.value = STATE.theme;
    themeSel.addEventListener("change", function () { setTheme(themeSel.value); saveWS(); });
    bar.querySelector("#tbLayout").addEventListener("change", function () { if (this.value) { applyLayout(this.value); this.value = ""; } });
    bar.querySelector("#tbReset").addEventListener("click", function () {
      if (!confirm(T("Сбросить раскладку к стандартной?", "Reset layout to default?"))) return;
      try { localStorage.removeItem(LS_KEY); } catch (e) {}
      var ws = defaultWorkspace(); STATE.theme = ws.theme;
      STATE.panels = ws.panels.map(function (p) { p.id = STATE.seq++; return p; });
      setTheme(STATE.theme); renderAll(); saveWS();
    });
    bar.querySelector("#tbShare").addEventListener("click", function (e) {
      saveWS(); var btn = e.target, old = btn.textContent;
      var done = function () { btn.textContent = T("скопировано ✓", "copied ✓"); setTimeout(function () { btn.textContent = old; }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(location.href).then(done, done); else done();
    });
  }
  function setTheme(t) { STATE.theme = t; root.className = "term th-" + t + (isMobile() ? " term-mobile" : ""); var s = bar.querySelector("#tbTheme"); if (s) s.value = t; renderAll(); }

  // ---------------- панели ----------------
  var PTITLE = { chart: T("График", "Chart"), watch: "Watchlist", movers: T("Муверы", "Movers"), heat: T("Тепловая карта", "Heatmap"), screen: T("Скринер", "Screener") };
  function nextPos() { var n = STATE.panels.length; return [24 + (n % 4) * 28, 24 + (n % 4) * 28, 440, 300]; }
  function addPanel(t) {
    var cfg;
    if (t === "chart") cfg = { cur: groupSlugs("top").slice(0, 3), base: "USD", type: "line", range: 365, log: false };
    else if (t === "watch") cfg = { grp: "top", range: 30 };
    else if (t === "movers") cfg = { range: 30, n: 8 };
    else if (t === "heat") cfg = { grp: "top", range: 30 };
    else if (t === "screen") cfg = { mode: "cur", quote: findQuote(), range: 30, sort: "chg", dir: -1, fchg: "", fvol: "", q: "" };
    else return;
    STATE.panels.push({ id: STATE.seq++, t: t, cfg: cfg, g: t === "screen" ? [24, 24, 560, 420] : nextPos() });
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
    canvas.innerHTML = "";
    var maxB = 0;
    STATE.panels.forEach(function (p) {
      var el = renderPanel(p);
      canvas.appendChild(el);
      if (!isMobile()) maxB = Math.max(maxB, p.g[1] + p.g[3]);
      drawBody(p, el.querySelector(".win-body"));
    });
    if (!isMobile()) canvas.style.height = Math.max(560, maxB + 24) + "px";
    else canvas.style.height = "auto";
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
        '<span class="win-ctl">' + panelControls(p) + '<button class="win-x" title="' + T("Закрыть", "Close") + '">✕</button></span>' +
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
      return '<select class="win-s win-grp">' +
          '<option value="top"' + (p.cfg.grp === "top" ? " selected" : "") + ">" + T("Топ-крипта", "Top crypto") + "</option>" +
          '<option value="stable"' + (p.cfg.grp === "stable" ? " selected" : "") + ">" + T("Стейблы", "Stables") + "</option>" +
          '<option value="fiat"' + (p.cfg.grp === "fiat" ? " selected" : "") + ">" + T("Фиат", "Fiat") + "</option>" +
        "</select>" + rangeTabs(p.cfg.range);
    }
    if (p.t === "movers") return rangeTabs(p.cfg.range);
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
    return "";
  }
  function rangeTabs(cur) {
    return '<span class="win-rng">' + RANGES.map(function (r) {
      return '<button class="win-r' + (r.k === cur ? " on" : "") + '" data-k="' + r.k + '">' + r.l + "</button>";
    }).join("") + "</span>";
  }

  function wirePanel(p, el) {
    el.querySelector(".win-x").addEventListener("click", function () { closePanel(p.id); });
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
    if (grp) grp.addEventListener("change", function () { p.cfg.grp = grp.value; drawBody(p, body()); saveWS(); });
    var pick = el.querySelector(".win-pick");
    if (pick) pick.addEventListener("click", function () { openPicker(p, el); });
    var mode = el.querySelector(".win-mode");
    if (mode) mode.addEventListener("change", function () { p.cfg.mode = mode.value; renderAll(); saveWS(); });
    var quote = el.querySelector(".win-quote");
    if (quote) quote.addEventListener("change", function () { p.cfg.quote = quote.value; drawBody(p, body()); saveWS(); });
    if (p.t === "chart") el.addEventListener("contextmenu", function (e) {
      if (e.target.closest(".win-h")) return; // по шапке — не мешаем
      e.preventDefault(); openChartMenu(p, e.clientX, e.clientY);
    });
    if (!isMobile()) enableDrag(p, el);
  }

  // ---------------- перетаскивание / ресайз ----------------
  function focusWin(el) { el.style.zIndex = ++zTop; }
  function enableDrag(p, el) {
    var h = el.querySelector(".win-h"), rz = el.querySelector(".win-rz");
    el.addEventListener("pointerdown", function () { focusWin(el); });
    h.addEventListener("pointerdown", function (e) {
      if (e.target.closest("button,select,input,label")) return;
      e.preventDefault(); focusWin(el);
      var sx = e.clientX, sy = e.clientY, ox = p.g[0], oy = p.g[1];
      function mv(ev) {
        p.g[0] = Math.max(0, ox + (ev.clientX - sx)); p.g[1] = Math.max(0, oy + (ev.clientY - sy));
        el.style.left = p.g[0] + "px"; el.style.top = p.g[1] + "px";
      }
      function up() { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); saveWS(); syncHeight(); }
      document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
    });
    if (rz) rz.addEventListener("pointerdown", function (e) {
      e.preventDefault(); e.stopPropagation(); focusWin(el);
      var sx = e.clientX, sy = e.clientY, ow = p.g[2], oh = p.g[3];
      function mv(ev) {
        p.g[2] = Math.max(240, ow + (ev.clientX - sx)); p.g[3] = Math.max(160, oh + (ev.clientY - sy));
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
    canvas.style.height = Math.max(560, maxB + 24) + "px";
  }

  // ---------------- отрисовка тела панели ----------------
  function drawBody(p, body) {
    if (!body) return;
    if (p.t === "chart") drawChart(p, body);
    else if (p.t === "watch") drawWatch(p, body);
    else if (p.t === "movers") drawMovers(p, body);
    else if (p.t === "heat") drawHeat(p, body);
    else if (p.t === "screen") drawScreen(p, body);
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

  // ----- WATCHLIST -----
  function drawWatch(p, body) {
    var slugs = groupSlugs(p.cfg.grp);
    if (!slugs.length) { body.innerHTML = empty(T("Пусто.", "Empty.")); return; }
    var rows = slugs.map(function (s) {
      return { s: s, last: lastVal(s, "USD"), pc: pctChange(s, "USD", p.cfg.range), spk: rangeFilter(rebased(s, "USD"), p.cfg.range) };
    }).sort(function (a, b) { return (b.pc == null ? -1e9 : b.pc) - (a.pc == null ? -1e9 : a.pc); });
    body.innerHTML =
      '<div class="win-tblw"><table class="win-tbl"><thead><tr><th>' + T("Валюта", "Currency") + "</th><th>" + T("Цена, USDT", "Price, USDT") + "</th><th></th><th>" + T("Δ", "Δ") + "</th></tr></thead><tbody>" +
      rows.map(function (r) {
        return "<tr><td class='wl-n' data-cur='" + esc(r.s) + "'>" + esc(name(r.s)) + " <b>" + esc(ticker(r.s)) + "</b> <span class='op-i'>↗</span></td>" +
          "<td class='wl-p'>" + fmtNum(r.last) + "</td>" +
          "<td class='wl-s'>" + spark(r.spk, r.pc) + "</td>" +
          "<td class='wl-c " + (r.pc >= 0 ? "up" : "dn") + "'>" + fmtPct(r.pc) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    wireOpens(body);
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
    var all = Object.keys(DATA.series).map(function (s) { return { s: s, pc: pctChange(s, "USD", p.cfg.range) }; })
      .filter(function (o) { return o.pc != null && isFinite(o.pc); });
    all.sort(function (a, b) { return b.pc - a.pc; });
    var n = p.cfg.n || 8, gain = all.slice(0, n), loss = all.slice(-n).reverse();
    function col(list) {
      return "<tbody>" + list.map(function (r) {
        return "<tr><td class='wl-n' data-cur='" + esc(r.s) + "'>" + esc(ticker(r.s) || name(r.s)) + " <span class='op-i'>↗</span></td><td class='wl-c " + (r.pc >= 0 ? "up" : "dn") + "'>" + fmtPct(r.pc) + "</td></tr>";
      }).join("") + "</tbody>";
    }
    body.innerHTML =
      '<div class="win-movers">' +
        '<div class="mv-col"><div class="mv-h up">▲ ' + T("Рост", "Gainers") + '</div><table class="win-tbl">' + col(gain) + "</table></div>" +
        '<div class="mv-col"><div class="mv-h dn">▼ ' + T("Падение", "Losers") + '</div><table class="win-tbl">' + col(loss) + "</table></div>" +
      "</div>";
    wireOpens(body);
  }

  // ----- ТЕПЛОВАЯ КАРТА -----
  function drawHeat(p, body) {
    var slugs = groupSlugs(p.cfg.grp);
    var cells = slugs.map(function (s) { return { s: s, pc: pctChange(s, "USD", p.cfg.range) }; });
    body.innerHTML = '<div class="win-heat">' + cells.map(function (c) {
      return '<div class="ht-cell" data-cur="' + esc(c.s) + '" style="background:' + heatColor(c.pc) + '"><span class="ht-t">' + esc(ticker(c.s) || name(c.s)) + "</span><span class='ht-p'>" + (c.pc == null ? "—" : fmtPct(c.pc)) + "</span></div>";
    }).join("") + "</div>";
    wireOpens(body);
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
          openAttr = "data-pair='" + esc(s) + "|" + esc(quote) + "'";
        } else {
          last = lastVal(s, "USD"); chg = pctChange(s, "USD", c.range); vol = volat(s, "USD", c.range);
          if (chg == null) return;
          label = esc(name(s)) + (ticker(s) ? " <b>" + esc(ticker(s)) + "</b>" : "");
          openAttr = "data-cur='" + esc(s) + "'";
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
          return "<tr " + r.oa + "><td class='wl-n'>" + r.label + " <span class='op-i'>↗</span></td><td class='wl-p'>" + fmtNum(r.last) + "</td><td class='wl-c " + (r.chg >= 0 ? "up" : "dn") + "'>" + fmtPct(r.chg) + "</td><td class='wl-v'>" + (r.vol == null ? "—" : r.vol.toFixed(1)) + "</td></tr>";
        }).join("") + "</tbody></table>";
      wireOpens(tbl);
    }
    body.querySelector(".scr-q").addEventListener("input", function () { c.q = this.value; renderTable(); saveWS(); });
    body.querySelector(".scr-chg").addEventListener("input", function () { c.fchg = this.value; renderTable(); saveWS(); });
    body.querySelector(".scr-vol").addEventListener("input", function () { c.fvol = this.value; renderTable(); saveWS(); });
    body.querySelector(".scr-sort").addEventListener("change", function () { c.sort = this.value; renderTable(); saveWS(); });
    body.querySelector(".scr-dir").addEventListener("click", function () { c.dir = c.dir < 0 ? 1 : -1; this.textContent = c.dir < 0 ? "↓" : "↑"; renderTable(); saveWS(); });
    renderTable();
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
    menuEl = document.createElement("div"); menuEl.className = "term-menu";
    menuEl.innerHTML = items.map(function (it, i) { return it.sep ? '<div class="tm-sep"></div>' : '<button data-i="' + i + '">' + esc(it.l) + "</button>"; }).join("");
    document.body.appendChild(menuEl);
    var vw = window.innerWidth, vh = window.innerHeight, mw = menuEl.offsetWidth, mh = menuEl.offsetHeight;
    menuEl.style.left = Math.min(x, vw - mw - 4) + "px"; menuEl.style.top = Math.min(y, vh - mh - 4) + "px";
    Array.prototype.forEach.call(menuEl.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function (e) { e.stopPropagation(); var it = items[+b.getAttribute("data-i")]; closeMenu(); if (it && it.f) it.f(); });
    });
    setTimeout(function () { document.addEventListener("click", closeMenu); }, 0);
  }
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
    var chosen = {}; p.cfg.cur.forEach(function (s) { chosen[s] = 1; });
    pickBox = document.createElement("div"); pickBox.className = "term-pick";
    var slugs = Object.keys(DATA.series).sort(byName);
    pickBox.innerHTML =
      '<div class="pick-in">' +
        '<div class="pick-h"><b>' + T("Валюты на графике", "Currencies on chart") + '</b><button class="pick-x">✕</button></div>' +
        '<input class="pick-search" placeholder="' + T("поиск…", "search…") + '" autocomplete="off">' +
        '<div class="pick-presets"><button data-g="top">' + T("Топ-крипта", "Top crypto") + '</button><button data-g="stable">' + T("Стейблы", "Stables") + '</button><button data-g="fiat">' + T("Фиат", "Fiat") + '</button><button data-g="clr">' + T("Очистить", "Clear") + "</button></div>" +
        '<div class="pick-list"></div>' +
        '<div class="pick-f"><button class="pick-ok">' + T("Готово", "Done") + "</button></div>" +
      "</div>";
    document.body.appendChild(pickBox);
    var listEl = pickBox.querySelector(".pick-list"), searchEl = pickBox.querySelector(".pick-search");
    function renderList(q) {
      q = (q || "").toLowerCase().trim();
      var fs = slugs.filter(function (s) { if (!q) return true; var c = DATA.cur[s] || {}; return (s + " " + (c.n || "") + " " + (c.t || "")).toLowerCase().indexOf(q) >= 0; });
      listEl.innerHTML = fs.map(function (s) {
        var c = DATA.cur[s] || { n: s, t: "" };
        return '<label class="pick-i"><input type="checkbox" data-s="' + esc(s) + '"' + (chosen[s] ? " checked" : "") + "> " + esc(c.n) + " <b>" + esc(c.t) + "</b></label>";
      }).join("");
      Array.prototype.forEach.call(listEl.querySelectorAll("input"), function (inp) {
        inp.addEventListener("change", function () { var s = inp.getAttribute("data-s"); if (inp.checked) chosen[s] = 1; else delete chosen[s]; });
      });
    }
    renderList("");
    searchEl.addEventListener("input", function () { renderList(searchEl.value); });
    Array.prototype.forEach.call(pickBox.querySelectorAll(".pick-presets button"), function (b) {
      b.addEventListener("click", function () {
        var g = b.getAttribute("data-g");
        if (g === "clr") chosen = {}; else groupSlugs(g).forEach(function (s) { chosen[s] = 1; });
        renderList(searchEl.value);
      });
    });
    function apply() { p.cfg.cur = Object.keys(chosen).filter(function (s) { return DATA.series[s]; }); pickBox.remove(); pickBox = null; renderAll(); saveWS(); }
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
  var rzTimer = null;
  window.addEventListener("resize", function () { clearTimeout(rzTimer); rzTimer = setTimeout(function () { renderAll(); }, 150); });

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
