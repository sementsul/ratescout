/* RateScout — профессиональный монитор: графики многих валют на одной шкале.
   Данные: /data/monitor.json (series: курс валюты в USDT по датам). База по умолчанию — доллар (USDT).
   Ре-база: делим ряды на ряд базовой валюты. Много валют → индекс (старт=100) для сравнимости; одна → цена в базе.
   Тип: линии (много валют) или свечи (по одной валюте; OHLC собираем из точек дня). Всё в SVG, без библиотек. */
(function () {
  var root = document.getElementById("monitor");
  if (!root) return;
  var host = document.getElementById("monChart");
  var listEl = document.getElementById("monList");
  var baseSel = document.getElementById("monBase");
  var typeSel = document.getElementById("monType");
  var rangesEl = document.getElementById("monRanges");
  var searchEl = document.getElementById("monSearch");
  var legEl = document.getElementById("monLegend");
  var noteEl = document.getElementById("monNote");
  var DATA = null, checked = {}, base = "USD", type = "line", sel = 0;
  var COLORS = ["#3399dd", "#33cc99", "#cc9944", "#cc5588", "#7a5cd0", "#5cc0d0", "#d05c8a", "#9ad04a",
                "#d0a24a", "#4ad0a2", "#d04a4a", "#4a7ad0", "#cdd04a", "#d04acd"];
  var RANGES = [{ k: 7, l: "Неделя" }, { k: 30, l: "Месяц" }, { k: 90, l: "3 мес" }, { k: 180, l: "6 мес" },
                { k: 365, l: "Год" }, { k: 1095, l: "3 года" }, { k: 1825, l: "5 лет" }, { k: 3650, l: "10 лет" }];

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function dnum(s) { var p = s.slice(0, 10).split("-"); return Date.UTC(+p[0], +p[1] - 1, +p[2]) / 86400000 + (s.length > 10 ? (+s.slice(11, 13)) / 24 : 0); }
  function fmtDate(s) { return s.slice(8, 10) + "." + s.slice(5, 7); }
  function fmtNum(v) { if (v == null || isNaN(v)) return "—"; var a = Math.abs(v); if (a >= 1000) return Math.round(v).toLocaleString("ru-RU"); if (a >= 1) return v.toFixed(2); if (a >= 0.01) return v.toFixed(4); return v.toPrecision(3); }

  fetch("/data/monitor.json").then(function (r) { return r.json(); }).then(function (j) {
    DATA = j;
    var slugs = Object.keys(j.series);
    baseSel.innerHTML = '<option value="USD">Доллар (USDT)</option>' +
      slugs.slice().sort(function (a, b) { return (j.cur[a] ? j.cur[a].n : a) > (j.cur[b] ? j.cur[b].n : b) ? 1 : -1; })
        .map(function (s) { var c = j.cur[s] || { n: s, t: "" }; return '<option value="' + s + '">' + esc(c.n) + " (" + esc(c.t) + ")</option>"; }).join("");
    ["bitcoin", "ethereum", "litecoin", "monero", "tron", "ripple", "dogecoin"].filter(function (s) { return j.series[s]; }).slice(0, 4).forEach(function (s) { checked[s] = 1; });
    if (!Object.keys(checked).length) slugs.slice(0, 4).forEach(function (s) { checked[s] = 1; });
    buildList(""); buildRanges(); draw();
  }).catch(function () { if (noteEl) noteEl.textContent = "Не удалось загрузить данные монитора."; });

  function buildList(q) {
    q = (q || "").toLowerCase().trim();
    var slugs = Object.keys(DATA.series).filter(function (s) {
      if (!q) return true;
      var c = DATA.cur[s] || {};
      return (s + " " + (c.n || "") + " " + (c.t || "")).toLowerCase().indexOf(q) >= 0;
    }).sort(function (a, b) { return (DATA.cur[a] ? DATA.cur[a].n : a) > (DATA.cur[b] ? DATA.cur[b].n : b) ? 1 : -1; });
    listEl.innerHTML = slugs.map(function (s) {
      var c = DATA.cur[s] || { n: s, t: "" };
      return '<label class="mon-item"><input type="checkbox" data-s="' + esc(s) + '"' + (checked[s] ? " checked" : "") + '> ' +
        '<span>' + esc(c.n) + ' <b>' + esc(c.t) + "</b></span></label>";
    }).join("");
    Array.prototype.forEach.call(listEl.querySelectorAll("input"), function (inp) {
      inp.addEventListener("change", function () { var s = inp.getAttribute("data-s"); if (inp.checked) checked[s] = 1; else delete checked[s]; draw(); });
    });
  }

  function selected() { return Object.keys(checked).filter(function (s) { return DATA.series[s]; }); }

  // ряд валюты в базовой валюте: [[date, value], ...]
  function rebased(slug) {
    var s = DATA.series[slug];
    if (base === "USD") return s.slice();
    var b = DATA.series[base]; if (!b) return s.slice();
    var bm = {}; b.forEach(function (p) { bm[p[0]] = p[1]; });
    var out = [];
    s.forEach(function (p) { var bv = bm[p[0]]; if (bv) out.push([p[0], p[1] / bv]); });
    return out;
  }
  function rangeFilter(pts) {
    if (!sel || pts.length < 2) return pts;
    var last = dnum(pts[pts.length - 1][0]) - sel;
    return pts.filter(function (p) { return dnum(p[0]) >= last; });
  }
  function spanDays() {
    var mx = 0;
    selected().forEach(function (s) { var p = DATA.series[s]; if (p.length > 1) mx = Math.max(mx, dnum(p[p.length - 1][0]) - dnum(p[0][0])); });
    return mx;
  }
  function buildRanges() {
    var span = spanDays();
    var av = RANGES.filter(function (r) { return span >= r.k; });
    var btns = av.concat([{ k: 0, l: "Всё" }]);
    sel = av.length ? av[av.length - 1].k : 0;
    rangesEl.innerHTML = btns.map(function (r) { return '<button class="mon-btn" data-k="' + r.k + '">' + r.l + "</button>"; }).join("");
    Array.prototype.forEach.call(rangesEl.querySelectorAll(".mon-btn"), function (b) {
      b.addEventListener("click", function () { sel = +b.getAttribute("data-k"); markR(); draw(); });
    });
    markR();
  }
  function markR() { Array.prototype.forEach.call(rangesEl.querySelectorAll(".mon-btn"), function (b) { b.classList.toggle("on", +b.getAttribute("data-k") === sel); }); }

  baseSel.addEventListener("change", function () { base = baseSel.value; buildRanges(); draw(); });
  typeSel.addEventListener("change", function () { type = typeSel.value; draw(); });
  searchEl.addEventListener("input", function () { buildList(searchEl.value); });

  function draw() {
    if (!DATA) return;
    var W = host.clientWidth || 700, H = 420, padL = 60, padR = 14, padT = 14, padB = 30, w = W - padL - padR, h = H - padT - padB;
    var sels = selected();
    if (!sels.length) { host.innerHTML = '<p class="mon-empty">Отметьте валюты справа, чтобы построить график.</p>'; legEl.innerHTML = ""; if (noteEl) noteEl.textContent = ""; return; }

    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '" class="mon-svg">';
    var baseName = base === "USD" ? "USDT" : (DATA.cur[base] ? DATA.cur[base].t : base);

    if (type === "candle") {
      var slug = sels[0];
      var pts = rangeFilter(rebased(slug));
      var byDay = {};
      pts.forEach(function (p) { var d = p[0].slice(0, 10); (byDay[d] = byDay[d] || []).push(p[1]); });
      var days = Object.keys(byDay).sort();
      var ohlc = days.map(function (d) { var a = byDay[d]; return { d: d, o: a[0], c: a[a.length - 1], h: Math.max.apply(null, a), l: Math.min.apply(null, a) }; });
      if (!ohlc.length) { host.innerHTML = '<p class="mon-empty">Нет данных.</p>'; return; }
      var vs = []; ohlc.forEach(function (c) { vs.push(c.h, c.l); });
      var mn = Math.min.apply(null, vs), mx = Math.max.apply(null, vs); if (mn === mx) { mn *= 0.99; mx *= 1.01; }
      function Y(v) { return padT + h - (v - mn) / (mx - mn) * h; }
      var cw = Math.max(2, Math.min(16, w / ohlc.length * 0.6));
      svg += grid(mn, mx, W, padL, padR, padT, h, fmtNum);
      ohlc.forEach(function (c, i) {
        var x = padL + (ohlc.length === 1 ? w / 2 : i / (ohlc.length - 1) * w);
        var up = c.c >= c.o, col = up ? "#33cc77" : "#dd5555";
        svg += '<line x1="' + x + '" y1="' + Y(c.h) + '" x2="' + x + '" y2="' + Y(c.l) + '" stroke="' + col + '" stroke-width="1"/>';
        var yo = Y(c.o), yc = Y(c.c), top = Math.min(yo, yc), bh = Math.max(1, Math.abs(yc - yo));
        svg += '<rect x="' + (x - cw / 2) + '" y="' + top + '" width="' + cw + '" height="' + bh + '" fill="' + col + '"/>';
      });
      svg += xlabels(ohlc.map(function (c) { return c.d; }), padL, w, H, padB);
      svg += "</svg>"; host.innerHTML = svg;
      legEl.innerHTML = '<span class="mon-lg"><i style="background:#33cc77"></i>' + esc((DATA.cur[slug] || {}).n || slug) + " · свечи (день)</span>";
      if (noteEl) noteEl.textContent = "Свечи — по одной валюте (" + ((DATA.cur[slug] || {}).n || slug) + "), цена в " + baseName + ". OHLC собран из точек дня." + (sels.length > 1 ? " Отмечено несколько — показана первая." : "");
      return;
    }

    // ЛИНИИ
    var single = sels.length === 1;
    var seriesData = sels.map(function (s) { return { s: s, pts: rangeFilter(rebased(s)) }; }).filter(function (o) { return o.pts.length; });
    if (!seriesData.length) { host.innerHTML = '<p class="mon-empty">Нет данных за период.</p>'; return; }
    // нормализация: одна валюта — реальная цена; несколько — индекс к 100 от старта
    seriesData.forEach(function (o) {
      var st = o.pts[0][1] || 1;
      o.norm = o.pts.map(function (p) { return [p[0], single ? p[1] : p[1] / st * 100]; });
    });
    var allv = [], allx = [];
    seriesData.forEach(function (o) { o.norm.forEach(function (p) { allv.push(p[1]); allx.push(dnum(p[0])); }); });
    var mn = Math.min.apply(null, allv), mx = Math.max.apply(null, allv); if (mn === mx) { mn *= 0.99; mx = mx * 1.01 + 1; }
    var x0 = Math.min.apply(null, allx), x1 = Math.max.apply(null, allx), xs = (x1 - x0) || 1;
    function X(d) { return padL + (dnum(d) - x0) / xs * w; }
    function Y(v) { return padT + h - (v - mn) / (mx - mn) * h; }
    svg += grid(mn, mx, W, padL, padR, padT, h, single ? fmtNum : function (v) { return Math.round(v); });
    seriesData.forEach(function (o, i) {
      var col = COLORS[i % COLORS.length], d = "";
      o.norm.forEach(function (p, k) { d += (k ? "L" : "M") + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1); });
      svg += '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.6"/>';
    });
    // подписи X по датам одной из серий
    var allDates = seriesData[0].norm.map(function (p) { return p[0]; });
    svg += xlabels(allDates, padL, w, H, padB, X);
    svg += "</svg>"; host.innerHTML = svg;
    legEl.innerHTML = seriesData.map(function (o, i) {
      var last = o.norm[o.norm.length - 1][1], c = DATA.cur[o.s] || { n: o.s, t: "" };
      return '<span class="mon-lg"><i style="background:' + COLORS[i % COLORS.length] + '"></i>' + esc(c.n) +
        " <b>" + (single ? fmtNum(last) + " " + baseName : Math.round(last)) + "</b></span>";
    }).join("");
    if (noteEl) noteEl.textContent = single
      ? "Цена в " + baseName + " (одна валюта — реальный курс)."
      : "Индекс относительной динамики (старт = 100), база — " + baseName + ". Так разномасштабные валюты сравнимы на одной шкале.";
  }

  function grid(mn, mx, W, padL, padR, padT, h, fmt) {
    var s = "";
    for (var i = 0; i <= 5; i++) {
      var v = mn + (mx - mn) * i / 5, y = padT + h - (v - mn) / (mx - mn) * h;
      s += '<line x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (W - padR) + '" y2="' + y.toFixed(1) + '" stroke="#2a2a2a"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (y + 3).toFixed(1) + '" text-anchor="end" fill="#7fa" font-size="11">' + esc(fmt(v)) + "</text>";
    }
    return s;
  }
  function xlabels(dates, padL, w, H, padB, X) {
    if (!dates.length) return "";
    var idx = dates.length <= 1 ? [0] : [0, Math.floor((dates.length - 1) / 2), dates.length - 1];
    return idx.map(function (k) {
      var x = X ? X(dates[k]) : padL + (dates.length === 1 ? w / 2 : k / (dates.length - 1) * w);
      return '<text x="' + x.toFixed(1) + '" y="' + (H - padB + 16) + '" text-anchor="middle" fill="#888" font-size="11">' + fmtDate(dates[k]) + "</text>";
    }).join("");
  }
  window.addEventListener("resize", function () { if (DATA) draw(); });
})();
