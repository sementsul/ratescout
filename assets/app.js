// Конвертер направления по ПОЛНОМУ каталогу BestChange (catalog.js).
// Выбор «отдаю/получаю» → CTA-ссылка на конкретное направление BestChange с реф-меткой.
(function () {
  var C = window.__CATALOG__;
  var REF = window.__REF__ || "1116359";

  // ---- поиск по валютам (на всех страницах) ----
  (function () {
    var q = document.getElementById("q"), qres = document.getElementById("qres");
    if (!q || !qres || !C || !C.cur) return;
    var PRE = q.getAttribute("data-prefix") || "";
    var all = Object.keys(C.cur).map(function (s) {
      return { slug: s, n: C.cur[s].n, t: C.cur[s].t, key: (C.cur[s].n + " " + C.cur[s].t + " " + s).toLowerCase() };
    });
    function render(list) {
      qres.innerHTML = list.map(function (x) {
        return '<li><a href="' + PRE + '/valuta/' + x.slug + '/">' + x.n + ' <span>' + x.t + '</span></a></li>';
      }).join("");
      qres.style.display = list.length ? "block" : "none";
    }
    q.addEventListener("input", function () {
      var v = q.value.trim().toLowerCase();
      if (!v) { render([]); return; }
      render(all.filter(function (x) { return x.key.indexOf(v) >= 0; }).slice(0, 12));
    });
    q.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { var a = qres.querySelector("a"); if (a) location.href = a.getAttribute("href"); }
    });
    document.addEventListener("click", function (e) {
      if (e.target !== q && !qres.contains(e.target)) render([]);
    });
  })();

  // ---- запомнить ручной выбор языка (клик по переключателю в шапке) ----
  Array.prototype.forEach.call(document.querySelectorAll(".langsw"), function (a) {
    a.addEventListener("click", function () {
      try { localStorage.setItem("rs_lang", a.getAttribute("data-lang")); } catch (e) {}
    });
  });

  // ---- сквозной поиск по ВСЕМ статьям блога (индекс встроен в страницу) ----
  (function () {
    var bq = document.getElementById("bq"), list = document.getElementById("bloglist");
    if (!bq || !list) return;
    var nores = document.getElementById("bnores");
    var pager = document.querySelector(".pager");
    var origHTML = list.innerHTML;                       // пагинированный список текущей страницы
    var INDEX = [];
    var idxEl = document.getElementById("blogIndex");
    if (idxEl) { try { INDEX = JSON.parse(idxEl.textContent); } catch (e) { INDEX = []; } }
    function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
    bq.addEventListener("input", function () {
      var v = bq.value.trim().toLowerCase();
      if (!v) {                                          // пусто — вернуть исходную страницу + пейджер
        list.innerHTML = origHTML;
        if (pager) pager.style.display = "";
        if (nores) nores.hidden = true;
        return;
      }
      if (INDEX.length) {                                // сквозной поиск по всем статьям
        var hits = INDEX.filter(function (a) { return a.k.indexOf(v) >= 0; });
        list.innerHTML = hits.map(function (a) {
          return '<li><a href="' + a.u + '">' + esc(a.t) + '</a>' +
                 '<div class="apreview">' + esc(a.d) + '</div>' +
                 '<div class="adate">' + esc(a.dt) + '</div></li>';
        }).join("");
        if (pager) pager.style.display = "none";         // при поиске пагинация не нужна
        if (nores) nores.hidden = hits.length > 0;
      } else {                                           // фолбэк: фильтр текущей страницы
        var shown = 0;
        Array.prototype.forEach.call(list.querySelectorAll("li"), function (li) {
          var hit = (li.getAttribute("data-search") || "").indexOf(v) >= 0;
          li.style.display = hit ? "" : "none"; if (hit) shown++;
        });
        if (nores) nores.hidden = shown > 0;
      }
    });
  })();

  var conv = document.getElementById("conv");
  if (!C || !conv) return;

  var elFrom = document.getElementById("cFrom"),
      elTo = document.getElementById("cTo"),
      elGo = document.getElementById("cGo"),
      elSwap = document.getElementById("cSwap");

  // список слагов по порядку категорий
  var order = C.order || [];
  var bySlug = C.cur || {};
  var byCat = {};
  Object.keys(bySlug).forEach(function (s) {
    var c = bySlug[s].c;
    (byCat[c] = byCat[c] || []).push(s);
  });
  order.forEach(function (c) { if (byCat[c]) byCat[c].sort(function (a, b) { return bySlug[a].n.localeCompare(bySlug[b].n); }); });

  function fill(sel, selected) {
    sel.innerHTML = "";
    order.forEach(function (c) {
      var list = byCat[c]; if (!list) return;
      var og = document.createElement("optgroup"); og.label = c;
      list.forEach(function (s) {
        var o = document.createElement("option");
        o.value = s; o.textContent = bySlug[s].n + " (" + bySlug[s].t + ")";
        if (s === selected) o.selected = true;
        og.appendChild(o);
      });
      sel.appendChild(og);
    });
  }

  var presetFrom = conv.getAttribute("data-from") || "";
  var slugs = Object.keys(bySlug);
  var defFrom = presetFrom || slugs[0];
  // получатель по умолчанию — популярный USDT TRC20, иначе первый отличный
  var defTo = (bySlug["tether-trc20"] && "tether-trc20") || slugs.find(function (s) { return s !== defFrom; });
  if (defTo === defFrom) defTo = slugs.find(function (s) { return s !== defFrom; });

  fill(elFrom, defFrom);
  fill(elTo, defTo);

  function deep(frm, to) { return "https://www.bestchange.ru/" + frm + "-to-" + to + ".html?p=" + REF; }

  var OPEN = conv.getAttribute("data-open") || "Открыть";
  var APPROX = conv.getAttribute("data-approx") || "≈";
  var SAMEMSG = OPEN === "Open" ? "Choose different currencies" : "Выберите разные валюты";

  // встроенная карта лучших курсов {to: rate} для валюты-владельца (на странице валюты)
  var RATES = null, ROWNER = "", elAmt = document.getElementById("cAmt"), elOut = document.getElementById("cOut");
  var rn = document.getElementById("convRates");
  if (rn) { try { RATES = JSON.parse(rn.textContent); ROWNER = rn.getAttribute("data-owner") || ""; } catch (e) { RATES = null; } }

  function fmtNum(v) {
    if (!isFinite(v)) return "";
    if (v >= 1000) return v.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
    if (v >= 1) return v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
    if (v >= 0.01) return v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
    return v.toFixed(10).replace(/0+$/, "").replace(/\.$/, "");
  }
  function estimate() {
    if (!elOut) return;
    var f = elFrom.value, t = elTo.value;
    var amt = elAmt ? parseFloat(elAmt.value) : NaN;
    // оценка возможна только для валюты-владельца встроенной карты
    if (!RATES || f !== ROWNER || !RATES[t] || !(amt >= 0)) { elOut.textContent = ""; return; }
    var got = amt * parseFloat(RATES[t]);
    elOut.innerHTML = APPROX + " <b>" + fmtNum(got) + "</b> " + bySlug[t].t;
  }

  function update() {
    var f = elFrom.value, t = elTo.value;
    if (f === t) { elGo.href = "https://www.bestchange.ru/?p=" + REF; elGo.textContent = SAMEMSG; if (elOut) elOut.textContent = ""; return; }
    elGo.href = deep(f, t);
    elGo.textContent = OPEN + ": " + bySlug[f].t + " → " + bySlug[t].t + " →";
    estimate();
  }
  if (elAmt) elAmt.addEventListener("input", estimate);
  elFrom.addEventListener("change", update);
  elTo.addEventListener("change", update);
  if (elSwap) elSwap.addEventListener("click", function () {
    var a = elFrom.value; elFrom.value = elTo.value; elTo.value = a; update();
  });
  update();

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(function () {});
})();

// ---- интерактивный график динамики цены (страницы валют) ----
(function () {
  var wrap = document.querySelector(".rschart-wrap");
  if (!wrap) return;
  var host = wrap.querySelector(".rschart"), tip = wrap.querySelector(".rstip");
  var unit = wrap.getAttribute("data-unit") || "USDT";
  var raw;
  try { raw = JSON.parse(wrap.querySelector(".rschart-data").textContent); } catch (e) { return; }
  if (!raw || raw.length < 2) return;
  function tms(s) { var p = s.split(/[- :]/); return Date.UTC(+p[0], +p[1] - 1, +p[2], +p[3] || 0, +p[4] || 0); }
  var ALL = raw.map(function (d) { return { t: tms(d[0]), v: d[1], hourly: d[0].indexOf(":") >= 0 }; });
  function fmt(v) {
    if (v >= 1000) return v.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
    if (v >= 1) return v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
    if (v >= 0.01) return (+v.toFixed(4)).toString();
    return (+v.toFixed(8)).toString();
  }
  function p2(n) { return (n < 10 ? "0" : "") + n; }
  function dd(ms) { var d = new Date(ms); return { D: d.getUTCDate(), M: d.getUTCMonth() + 1, Y: d.getUTCFullYear(), h: d.getUTCHours() }; }
  function axisTime(ms, span, hourly) {
    var o = dd(ms);
    if (hourly && span <= 2 * 864e5) return p2(o.h) + ":00";   // часы — только если точки почасовые
    if (span <= 180 * 864e5) return p2(o.D) + "." + p2(o.M);    // дни
    return p2(o.M) + "." + o.Y;                                 // месяцы
  }
  function fmtDate(ms) { var o = dd(ms); return p2(o.D) + "." + p2(o.M) + "." + o.Y; }
  function fullTime(pt) {
    var o = dd(pt.t);
    return pt.hourly ? p2(o.D) + "." + p2(o.M) + "." + o.Y + " " + p2(o.h) + ":00 UTC"  // почасовая точка (с годом)
                     : p2(o.D) + "." + p2(o.M) + "." + o.Y;                             // дневная точка
  }

  var H = 220, padL = 58, padR = 12, padT = 10, padB = 26, plotH = H - padT - padB;
  var pts = [], range = "all", per = wrap.querySelector(".rsperiod");
  var RMAP = { "24h": 864e5, "7d": 7 * 864e5, "30d": 30 * 864e5, "1y": 365 * 864e5,
    "3y": 3 * 365 * 864e5, "5y": 5 * 365 * 864e5, "10y": 10 * 365 * 864e5 };
  function filtered() {
    if (range === "all" || !RMAP[range]) return ALL;
    var t1 = ALL[ALL.length - 1].t;
    var f = ALL.filter(function (d) { return d.t >= t1 - RMAP[range]; });
    return f.length >= 2 ? f : ALL;
  }
  function draw() {
    var W = Math.max(320, Math.round(host.clientWidth || 640)), plotW = W - padL - padR;
    var d = filtered(), vs = d.map(function (x) { return x.v; });
    var mn = Math.min.apply(null, vs), mx = Math.max.apply(null, vs), span = (mx - mn) || (mx || 1);
    var t0 = d[0].t, t1 = d[d.length - 1].t, tspan = (t1 - t0) || 1;
    // почасовой вид, только если в выборке есть внутридневные точки (иначе показываем дни)
    var hourly = false, j;
    for (j = 1; j < d.length; j++) { if (d[j].t - d[j - 1].t < 20 * 3600e3) { hourly = true; break; } }
    function X(t) { return padL + (t - t0) / tspan * plotW; }
    function Y(v) { return padT + (1 - (v - mn) / span) * plotH; }
    pts = d.map(function (x) { return { px: X(x.t), py: Y(x.v), v: x.v, t: x.t, hourly: x.hourly }; });
    if (per) per.textContent = "Период: " + fmtDate(t0) + (t0 === t1 ? "" : " — " + fmtDate(t1)) + " (UTC)";
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="rssvg" width="100%" height="' + H + '">', i;
    for (i = 0; i <= 4; i++) {
      var yv = mn + span * i / 4, yy = Y(yv);
      s += '<line x1="' + padL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - padR) + '" y2="' + yy.toFixed(1) + '" class="rsgrid"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (yy + 3).toFixed(1) + '" class="rsylab">' + fmt(yv) + '</text>';
    }
    for (i = 0; i <= 4; i++) {
      var tt = t0 + tspan * i / 4, xx = X(tt);
      s += '<text x="' + xx.toFixed(1) + '" y="' + (H - 8) + '" class="rsxlab">' + axisTime(tt, tspan, hourly) + '</text>';
    }
    s += '<polyline fill="none" stroke="#55ff55" stroke-width="2" points="' +
      pts.map(function (p) { return p.px.toFixed(1) + "," + p.py.toFixed(1); }).join(" ") + '"/>';
    s += '<line class="rsguide" y1="' + padT + '" y2="' + (padT + plotH) + '" style="display:none"/>';
    s += '<circle class="rsdot" r="3.5" style="display:none"/></svg>';
    host.innerHTML = s;
  }
  function move(e) {
    if (!pts.length) return;
    var r = host.getBoundingClientRect(), W = Math.max(320, Math.round(host.clientWidth || 640));
    var sx = (e.clientX - r.left) / r.width * W, best = pts[0], bd = 1e9, k;
    for (k = 0; k < pts.length; k++) { var q = Math.abs(pts[k].px - sx); if (q < bd) { bd = q; best = pts[k]; } }
    var svg = host.querySelector("svg"); if (!svg) return;
    var g = svg.querySelector(".rsguide"), dot = svg.querySelector(".rsdot");
    g.setAttribute("x1", best.px); g.setAttribute("x2", best.px); g.style.display = "";
    dot.setAttribute("cx", best.px); dot.setAttribute("cy", best.py); dot.style.display = "";
    tip.innerHTML = "<b>" + fmt(best.v) + " " + unit + "</b><span>" + fullTime(best) + "</span>";
    tip.hidden = false;
    var leftPx = host.offsetLeft + best.px / W * r.width;
    tip.style.left = Math.max(0, leftPx - tip.offsetWidth / 2) + "px";
    tip.style.top = Math.max(0, host.offsetTop + best.py / H * r.height - tip.offsetHeight - 8) + "px";
  }
  function leave() {
    tip.hidden = true;
    var svg = host.querySelector("svg"); if (!svg) return;
    var g = svg.querySelector(".rsguide"), dot = svg.querySelector(".rsdot");
    if (g) g.style.display = "none"; if (dot) dot.style.display = "none";
  }
  host.addEventListener("mousemove", move);
  host.addEventListener("mouseleave", leave);
  host.addEventListener("touchmove", function (e) { if (e.touches[0]) { move(e.touches[0]); } }, { passive: true });
  Array.prototype.forEach.call(wrap.querySelectorAll(".rsrange button"), function (b) {
    b.addEventListener("click", function () {
      range = b.getAttribute("data-r");
      Array.prototype.forEach.call(wrap.querySelectorAll(".rsrange button"), function (x) { x.classList.remove("on"); });
      b.classList.add("on"); draw();
    });
  });
  var rt;
  window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(draw, 150); });
  draw();
})();

// ---- сортировка обзора графиков (/grafiki/): ликвидность / рост / падение ----
(function () {
  var tbl = document.querySelector(".marktbl"), bar = document.querySelector(".sortbar");
  if (!tbl || !bar) return;
  var tbody = tbl.querySelector("tbody");
  var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
  function num(r, a) { var v = r.getAttribute(a); return v === null || v === "" ? null : parseFloat(v); }
  function apply(key) {
    var arr = rows.slice();
    arr.sort(function (a, b) {
      if (key === "liq") { return (num(b, "data-liq") || 0) - (num(a, "data-liq") || 0); }
      var ca = num(a, "data-chg"), cb = num(b, "data-chg");
      if (ca === null && cb === null) return 0;
      if (ca === null) return 1;             // без изменения — в конец
      if (cb === null) return -1;
      return key === "up" ? cb - ca : ca - cb;
    });
    arr.forEach(function (r) { tbody.appendChild(r); });
  }
  Array.prototype.forEach.call(bar.querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () {
      Array.prototype.forEach.call(bar.querySelectorAll("button"), function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      apply(b.getAttribute("data-s"));
    });
  });
})();

// ---- фильтр обзора графиков по категории (/grafiki/) ----
(function () {
  var bar = document.querySelector(".catbar"), tbl = document.querySelector(".marktbl");
  if (!bar || !tbl) return;
  var rows = Array.prototype.slice.call(tbl.querySelectorAll("tbody tr"));
  Array.prototype.forEach.call(bar.querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () {
      Array.prototype.forEach.call(bar.querySelectorAll("button"), function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      var f = b.getAttribute("data-f");
      rows.forEach(function (r) { r.style.display = (!f || r.getAttribute("data-cat") === f) ? "" : "none"; });
    });
  });
})();
