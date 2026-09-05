/* RateScout — страница «Тепловая карта»: все валюты одной картой, цвет = изменение цены за период.
   Плитки как в терминале (heat-grid/ht-cell/heatColor). Клик по плитке → страница валюты. Данные: /data/monitor.json. */
(function () {
  var grid = document.getElementById("hpGrid");
  if (!grid) return;
  var rangesEl = document.getElementById("hpRanges"),
      catsEl = document.getElementById("hpCats"),
      searchEl = document.getElementById("hpSearch"),
      noteEl = document.getElementById("hpNote");
  var EN = (document.documentElement.getAttribute("lang") || "ru").slice(0, 2) === "en";
  function T(r, e) { return EN ? e : r; }
  var PREF = EN ? "/en" : "";
  var DATA = null, sel = 30, cat = "", q = "";
  var RANGES = [{ k: 1, l: T("24ч", "24h") }, { k: 7, l: T("1Н", "1W") }, { k: 30, l: T("1М", "1M") },
                { k: 90, l: T("3М", "3M") }, { k: 180, l: T("6М", "6M") }, { k: 365, l: T("1Г", "1Y") }, { k: 0, l: T("Всё", "All") }];

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function dnum(s) { var p = s.slice(0, 10).split("-"); return Date.UTC(+p[0], +p[1] - 1, +p[2]) / 86400000 + (s.length > 10 ? (+s.slice(11, 13)) / 24 : 0); }
  function fmtPct(p) { if (p == null || isNaN(p)) return "—"; return (p >= 0 ? "+" : "") + p.toFixed(1) + "%"; }
  function name(s) { return (DATA.cur[s] || {}).n || s; }
  function ticker(s) { return (DATA.cur[s] || {}).t || ""; }
  function curUrl(s) { return PREF + "/valuta/" + s + "/"; }
  function rangeFilter(pts, days) { if (!days || pts.length < 2) return pts; var last = dnum(pts[pts.length - 1][0]) - days; return pts.filter(function (p) { return dnum(p[0]) >= last; }); }
  function pctChange(slug, days) { var p = DATA.series[slug]; if (!p) return null; p = rangeFilter(p, days); if (p.length < 2) return null; var a = p[0][1], b = p[p.length - 1][1]; if (!a) return null; return (b / a - 1) * 100; }
  function heatColor(pc) { if (pc == null || isNaN(pc)) return "#161616"; var t = Math.max(-8, Math.min(8, pc)) / 8; if (t >= 0) return "rgba(38,180,110," + (0.18 + 0.62 * t).toFixed(2) + ")"; return "rgba(210,70,70," + (0.18 + 0.62 * (-t)).toFixed(2) + ")"; }

  fetch("/data/monitor.json").then(function (r) { return r.json(); }).then(function (j) {
    DATA = j; buildRanges(); buildCats(); render();
  }).catch(function () { grid.innerHTML = '<p class="mon-empty">' + T("Не удалось загрузить данные.", "Failed to load data.") + "</p>"; });

  function buildRanges() {
    rangesEl.innerHTML = RANGES.map(function (r) { return '<button class="mon-btn' + (r.k === sel ? " on" : "") + '" data-k="' + r.k + '">' + r.l + "</button>"; }).join("");
    Array.prototype.forEach.call(rangesEl.querySelectorAll(".mon-btn"), function (b) {
      b.addEventListener("click", function () { sel = +b.getAttribute("data-k"); Array.prototype.forEach.call(rangesEl.querySelectorAll(".mon-btn"), function (x) { x.classList.toggle("on", +x.getAttribute("data-k") === sel); }); render(); });
    });
  }
  function buildCats() {
    if (!DATA.cats || !catsEl) return;
    var all = '<button type="button" data-c=""' + (cat ? "" : ' class="on"') + ">" + T("Все", "All") + "</button>";
    catsEl.innerHTML = all + DATA.cats.map(function (c) { return '<button type="button" data-c="' + c.s + '"' + (cat === c.s ? ' class="on"' : "") + ">" + esc(EN ? c.en : c.ru) + "</button>"; }).join("");
    Array.prototype.forEach.call(catsEl.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { cat = b.getAttribute("data-c"); Array.prototype.forEach.call(catsEl.querySelectorAll("button"), function (x) { x.classList.toggle("on", x.getAttribute("data-c") === cat); }); render(); });
    });
  }
  if (searchEl) searchEl.addEventListener("input", function () { q = searchEl.value.toLowerCase().trim(); render(); });

  function render() {
    var slugs = Object.keys(DATA.series).filter(function (s) {
      if (s === "tether-trc20") return false; // база USDT — плоская
      if (cat && (DATA.cur[s] || {}).cs !== cat) return false;
      if (q) { var c = DATA.cur[s] || {}; if ((s + " " + (c.n || "") + " " + (c.t || "")).toLowerCase().indexOf(q) < 0) return false; }
      return true;
    });
    var rows = slugs.map(function (s) { return { s: s, pc: pctChange(s, sel) }; })
      .sort(function (a, b) { return (b.pc == null ? -1e9 : b.pc) - (a.pc == null ? -1e9 : a.pc); });
    if (!rows.length) { grid.innerHTML = '<p class="mon-empty">' + T("Ничего не найдено", "Nothing found") + "</p>"; if (noteEl) noteEl.textContent = ""; return; }
    grid.innerHTML = rows.map(function (r) {
      return '<a class="ht-cell" href="' + curUrl(r.s) + '" title="' + esc(name(r.s)) + '" style="background:' + heatColor(r.pc) + '">' +
        '<span class="ht-t">' + esc(ticker(r.s) || name(r.s)) + '</span><span class="ht-p">' + (r.pc == null ? "—" : fmtPct(r.pc)) + "</span></a>";
    }).join("");
    if (noteEl) noteEl.textContent = T("Валют: ", "Currencies: ") + rows.length + " · " + T("цвет — изменение за период, клик — страница валюты.", "color = change over period, click — currency page.");
  }
})();
