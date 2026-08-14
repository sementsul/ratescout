/* RateScout embeddable widget — self-contained, no deps. {{BASE}} подставляется при сборке.
   Режимы: обычный (курс, data-pair="usdt-rub") и конвертер (data-widget="converter"). */
(function () {
  var BASE = "{{BASE}}";
  function el(tag, style, html) {
    var e = document.createElement(tag);
    if (style) e.setAttribute("style", style);
    if (html != null) e.innerHTML = html;
    return e;
  }
  var CARD = "font:13px/1.4 system-ui,Arial,sans-serif;display:inline-block;border:1px solid #d0d5dd;border-radius:8px;padding:10px 14px;background:#fff;color:#111;min-width:200px";
  var LBL = "font-size:11px;color:#667085;text-transform:uppercase;letter-spacing:.04em";
  var BIG = "font-size:20px;font-weight:700;margin:2px 0";
  var LINK = "color:#0a66c2;text-decoration:none;font-weight:600";
  var ATTR = "display:block;margin-top:6px;font-size:11px;color:#98a2b3;text-decoration:none";
  var INP = "width:100%;box-sizing:border-box;padding:6px 8px;margin:4px 0;border:1px solid #d0d5dd;border-radius:6px;font:inherit;color:#111;background:#fff";
  var OPEN = "Обменять →";        // Обменять →
  var CRED = "Курсы: RateScout";                     // Курсы: RateScout

  function num(v) { v = parseFloat(String(v).replace(/\s/g, "")); return isNaN(v) ? 0 : v; }
  function fmt(v) {
    if (v >= 1000) return v.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
    if (v >= 1) return v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
    return v.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
  }

  function renderRate(box, data) {
    var k = (box.getAttribute("data-pair") || "usdt-rub").toLowerCase();
    var p = data.pairs[k]; if (!p) return;
    box.innerHTML = '<div style="' + CARD + '"><div style="' + LBL + '">' + p.from + ' → ' + p.to + '</div>' +
      '<div style="' + BIG + '">1 ' + p.from + ' = ' + p.rate + ' ' + p.to + '</div>' +
      '<a href="' + p.url + '" target="_blank" rel="noopener" style="' + LINK + '">' + OPEN + '</a>' +
      '<a href="' + BASE + '/" target="_blank" rel="noopener" style="' + ATTR + '">' + CRED + '</a></div>';
  }

  function renderConv(box, data) {
    var keys = Object.keys(data.pairs);
    var card = el("div", CARD);
    card.appendChild(el("div", LBL, "Конвертер RateScout")); // Конвертер RateScout
    var amt = el("input", INP); amt.type = "number"; amt.min = "0"; amt.step = "any"; amt.value = "1";
    var sel = el("select", INP);
    keys.forEach(function (k) {
      var o = el("option", null, data.pairs[k].from + " → " + data.pairs[k].to); o.value = k; sel.appendChild(o);
    });
    var out = el("div", BIG);
    var go = el("a", LINK, OPEN); go.target = "_blank"; go.rel = "noopener";
    var attr = el("a", ATTR, CRED); attr.href = BASE + "/"; attr.target = "_blank"; attr.rel = "noopener";
    function calc() {
      var p = data.pairs[sel.value]; if (!p) return;
      out.innerHTML = fmt(num(amt.value) * num(p.rate)) + " " + p.to;
      go.href = p.url;
    }
    amt.addEventListener("input", calc); sel.addEventListener("change", calc);
    card.appendChild(amt); card.appendChild(sel); card.appendChild(out); card.appendChild(go); card.appendChild(attr);
    box.innerHTML = ""; box.appendChild(card); calc();
  }

  function init() {
    var els = document.querySelectorAll(".ratescout-widget,#ratescout-widget,[data-ratescout-widget]");
    if (!els.length) return;
    fetch(BASE + "/widget-data.json").then(function (r) { return r.json(); }).then(function (d) {
      Array.prototype.forEach.call(els, function (b) {
        (b.getAttribute("data-widget") === "converter" ? renderConv : renderRate)(b, d);
      });
    }).catch(function () {});
  }
  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
