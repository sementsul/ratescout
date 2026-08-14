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

  // ---- поиск по статьям блога (на странице /blog/) ----
  (function () {
    var bq = document.getElementById("bq"), list = document.getElementById("bloglist");
    if (!bq || !list) return;
    var items = Array.prototype.slice.call(list.querySelectorAll("li"));
    var nores = document.getElementById("bnores");
    bq.addEventListener("input", function () {
      var v = bq.value.trim().toLowerCase(), shown = 0;
      items.forEach(function (li) {
        var hit = !v || (li.getAttribute("data-search") || "").indexOf(v) >= 0;
        li.style.display = hit ? "" : "none";
        if (hit) shown++;
      });
      if (nores) nores.hidden = shown > 0;
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
  var SAMEMSG = OPEN === "Open" ? "Choose different currencies" : "Выберите разные валюты";
  function update() {
    var f = elFrom.value, t = elTo.value;
    if (f === t) { elGo.href = "https://www.bestchange.ru/?p=" + REF; elGo.textContent = SAMEMSG; return; }
    elGo.href = deep(f, t);
    elGo.textContent = OPEN + ": " + bySlug[f].t + " → " + bySlug[t].t + " →";
  }
  elFrom.addEventListener("change", update);
  elTo.addEventListener("change", update);
  if (elSwap) elSwap.addEventListener("click", function () {
    var a = elFrom.value; elFrom.value = elTo.value; elTo.value = a; update();
  });
  update();

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(function () {});
})();
