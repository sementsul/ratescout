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
