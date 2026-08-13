// Конвертер направления по ПОЛНОМУ каталогу BestChange (catalog.js).
// Выбор «отдаю/получаю» → CTA-ссылка на конкретное направление BestChange с реф-меткой.
(function () {
  var C = window.__CATALOG__;
  var REF = window.__REF__ || "1116359";
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

  function update() {
    var f = elFrom.value, t = elTo.value;
    if (f === t) { elGo.href = "https://www.bestchange.ru/?p=" + REF; elGo.textContent = "Выберите разные валюты"; return; }
    elGo.href = deep(f, t);
    elGo.textContent = "Найти курс: " + bySlug[f].t + " → " + bySlug[t].t + " →";
  }
  elFrom.addEventListener("change", update);
  elTo.addEventListener("change", update);
  if (elSwap) elSwap.addEventListener("click", function () {
    var a = elFrom.value; elFrom.value = elTo.value; elTo.value = a; update();
  });
  update();

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(function () {});
})();
