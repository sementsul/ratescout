/**
 * Локальные тесты роутера /go/bestchange (без wrangler и без сети):
 *   node worker/test-go-router.mjs
 *
 * Проверяют ровно то, что легко сломать правкой: отдаётся ли метка без куки,
 * валидируются ли параметры, не превращается ли роутер в открытый редирект.
 */
import worker from "./go-router.js";

const CASES = [
  { name: "без куки → гейт", url: "?from=usd&to=bitcoin", cookie: null, status: 200 },
  { name: "с куки → 302 .ru", url: "?from=usd&to=bitcoin", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.ru/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96" },
  { name: "lang=en → .com", url: "?from=usd&to=bitcoin&lang=en", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.com/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96" },
  { name: "fid/tid → index.php", url: "?fid=93&tid=2", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.ru/index.php?mt=rates&from=93&to=2&p=1116359&erid=2VtzqvK5m96" },
  { name: "mode=partner", url: "?mode=partner", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.ru/partner/account.html?p=1116359&erid=2VtzqvK5m96" },
  { name: "page=report (AML)", url: "?page=report", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.ru/report/?p=1116359&erid=2VtzqvK5m96" },
  { name: "page=report + lang=en", url: "?page=report&lang=en", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.com/report/?p=1116359&erid=2VtzqvK5m96" },
  { name: "lang=fr → .com", url: "?lang=fr", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.com/?p=1116359&erid=2VtzqvK5m96" },
  { name: "lang=es → .com", url: "?from=bitcoin&to=usd&lang=es", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.com/bitcoin-to-usd.html?p=1116359&erid=2VtzqvK5m96" },
  { name: "noerid=1 → только p", url: "?from=bitcoin&to=usd&noerid=1", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.ru/bitcoin-to-usd.html?p=1116359" },
  { name: "noerid=1 + lang=es", url: "?from=bitcoin&to=usd&lang=es&noerid=1", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.com/bitcoin-to-usd.html?p=1116359" },
  { name: "noerid=1, js=1 без куки", url: "?from=bitcoin&to=usd&noerid=1&js=1", cookie: null, status: 302,
    location: "https://www.bestchange.ru/" },
  { name: "мусорный page → главная", url: "?page=..%2Fevil", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.ru/?p=1116359&erid=2VtzqvK5m96" },
  { name: "пусто → главная", url: "", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.ru/?p=1116359&erid=2VtzqvK5m96" },
  { name: "мусор в from → главная без метки", url: "?from=..%2F..%2Fevil&to=x", cookie: "bcr=1", status: 302,
    location: "https://www.bestchange.ru/?erid=2VtzqvK5m96" },
  { name: "js=1 без куки → без метки", url: "?from=usd&to=bitcoin&js=1", cookie: null, status: 302,
    location: "https://www.bestchange.ru/?erid=2VtzqvK5m96" },
  // Cloudflare уже провёл клиента через WAF-challenge → наша страница не нужна.
  { name: "cf_clearance → сразу с меткой", url: "?from=usd&to=bitcoin", cookie: "cf_clearance=abc", status: 302,
    location: "https://www.bestchange.ru/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96" },
  { name: "POST → 405", url: "", cookie: "bcr=1", method: "POST", status: 405 },
  // workers.dev идёт мимо WAF зоны — с такого хоста метку не выдаём вообще.
  { name: "чужой хост → 404", url: "?from=usd&to=bitcoin", cookie: "bcr=1", status: 404, base:
    "https://ratescout-go.sementsul-maksim.workers.dev/go/bestchange" },
  { name: "my-many.ratescout.ru → работает", url: "?from=usd&to=bitcoin", cookie: "bcr=1", status: 302,
    base: "https://my-many.ratescout.ru/go/bestchange",
    location: "https://www.bestchange.ru/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96" },
];

const BASE = "https://ratescout.ru/go/bestchange";
let failed = 0;
const ENV_TS_PROBE = { TS_SITEKEY: "0xTESTKEY", TS_SECRET: "test-secret" };

for (const c of CASES) {
  const headers = c.cookie ? { Cookie: c.cookie } : {};
  const res = await worker.fetch(new Request((c.base || BASE) + c.url, { method: c.method || "GET", headers }), {});
  const loc = res.headers.get("Location") || "";
  const ok = res.status === c.status && (!c.location || loc === c.location);
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${c.name} → ${res.status} ${loc}`);
  if (!ok && c.location) console.log(`        ожидали ${c.status} ${c.location}`);
}

// ── Диагностика ─────────────────────────────────────────────────────────────
const diag = await worker.fetch(new Request(`${BASE}?diag=1&from=usd&to=bitcoin`), ENV_TS_PROBE);
const diagJson = await diag.json();
const diagOk =
  diag.status === 200 &&
  diagJson.turnstile.enabled === true &&
  diagJson.partner === "1116359" &&
  diagJson.target === "https://www.bestchange.ru/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96" &&
  (diag.headers.get("X-Robots-Tag") || "").includes("noindex");
if (!diagOk) failed++;
console.log(`${diagOk ? "PASS" : "FAIL"}  diag: конфиг и цель без редиректа`);

// ?diag=1&gate=1 — сама страница-гейт, чтобы увидеть виджет без перехода.
const gateView = await worker.fetch(new Request(`${BASE}?diag=1&gate=1`), ENV_TS_PROBE);
const gateViewHtml = await gateView.text();
const gateViewOk =
  gateView.status === 200 &&
  gateViewHtml.includes("cf-turnstile") &&
  gateViewHtml.includes("0xTESTKEY") &&
  (gateView.headers.get("Location") || "") === "";
if (!gateViewOk) failed++;
console.log(`${gateViewOk ? "PASS" : "FAIL"}  diag&gate=1: HTML с виджетом, без редиректа`);

// ── Гейт ────────────────────────────────────────────────────────────────────
// Без Turnstile (ключи не заданы) — прежнее поведение: cookie ставится страницей,
// JS сразу возвращается с js=1 (иначе все первые клики уходили бы без метки).
const gate = await worker.fetch(new Request(`${BASE}?from=usd&to=bitcoin`), {});
const gateCookieHeader = gate.headers.get("Set-Cookie") || "";
const gateHtml = await gate.text();
const gateOk =
  gate.status === 200 &&
  gateCookieHeader.includes("bcr=1") &&
  gateCookieHeader.includes("Path=/go") &&
  gateCookieHeader.includes("HttpOnly") &&
  gateHtml.includes("js=1") &&
  gate.headers.get("X-Robots-Tag") === "noindex, nofollow";
if (!gateOk) failed++;
console.log(`${gateOk ? "PASS" : "FAIL"}  гейт без Turnstile: cookie + js=1 + noindex`);

// С настроенным Turnstile — страница с капчей и без cookie.
const ENV_TS = { TS_SITEKEY: "0xTESTKEY", TS_SECRET: "test-secret" };
const gateTs = await worker.fetch(new Request(`${BASE}?from=usd&to=bitcoin`), ENV_TS);
const tsHtml = await gateTs.text();
const tsOk =
  gateTs.status === 200 &&
  (gateTs.headers.get("Set-Cookie") || "") === "" &&
  tsHtml.includes("cf-turnstile") &&
  tsHtml.includes("0xTESTKEY") &&
  tsHtml.includes("challenges.cloudflare.com") &&
  (gateTs.headers.get("Content-Security-Policy") || "").includes("challenges.cloudflare.com");
if (!tsOk) failed++;
console.log(`${tsOk ? "PASS" : "FAIL"}  гейт с Turnstile: капча, sitekey, CSP, без cookie`);

// Подменяем siteverify: токен "good" — успех, остальное — отказ.
const realFetch = globalThis.fetch;
globalThis.fetch = async () =>
  new Response(JSON.stringify({ success: true }), { headers: { "Content-Type": "application/json" } });

const okRes = await worker.fetch(
  new Request(`${BASE}?from=usd&to=bitcoin&_ts=good`, { headers: { "CF-Connecting-IP": "203.0.113.7" } }),
  ENV_TS,
);
const okCookie = okRes.headers.get("Set-Cookie") || "";
const okGood =
  okRes.status === 302 &&
  okRes.headers.get("Location") === "https://www.bestchange.ru/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96" &&
  okCookie.includes("bcr=1") && okCookie.includes("HttpOnly") && okCookie.includes("Path=/go");
if (!okGood) failed++;
console.log(`${okGood ? "PASS" : "FAIL"}  Turnstile пройден: 302 с меткой + HttpOnly cookie`);

globalThis.fetch = async () => new Response(JSON.stringify({ success: false }));
const badRes = await worker.fetch(new Request(`${BASE}?from=usd&to=bitcoin&_ts=bad`), ENV_TS);
const badOk =
  badRes.status === 302 &&
  badRes.headers.get("Location") === "https://www.bestchange.ru/?erid=2VtzqvK5m96" &&
  (badRes.headers.get("Set-Cookie") || "") === "";
if (!badOk) failed++;
console.log(`${badOk ? "PASS" : "FAIL"}  Turnstile не пройден: 302 без метки, без cookie`);

// Сеть до siteverify недоступна — fail open: переход без метки, без 5xx.
globalThis.fetch = async () => { throw new Error("network down"); };
const netRes = await worker.fetch(new Request(`${BASE}?from=usd&to=bitcoin&_ts=x`), ENV_TS);
const netOk = netRes.status === 302 && netRes.headers.get("Location") === "https://www.bestchange.ru/?erid=2VtzqvK5m96";
if (!netOk) failed++;
console.log(`${netOk ? "PASS" : "FAIL"}  siteverify недоступен: fail open без метки`);
globalThis.fetch = realFetch;

// ── Счётчики Analytics Engine ───────────────────────────────────────────────
// Зеркала ES/FR должны различаться в статистике (в редиректе оба идут на .com).
const aeLang = [];
const ENV_AE_LANG = { ANALYTICS: { writeDataPoint: (p) => aeLang.push(p.blobs[1]) } };
await worker.fetch(
  new Request(`${BASE}?from=bitcoin&to=usd&lang=es&noerid=1`, { headers: { Cookie: "bcr=1" } }),
  ENV_AE_LANG,
);
await worker.fetch(
  new Request(`${BASE}?from=bitcoin&to=usd&lang=fr&noerid=1`, { headers: { Cookie: "bcr=1" } }),
  ENV_AE_LANG,
);
const langOk = aeLang.includes("es") && aeLang.includes("fr");
if (!langOk) failed++;
console.log(`${langOk ? "PASS" : "FAIL"}  в счётчике es/fr отдельно (${aeLang.join(", ")})`);

const aeEvents = [];
const ENV_AE = { ANALYTICS: { writeDataPoint: (p) => aeEvents.push(p.indexes[0]) } };
await worker.fetch(new Request(`${BASE}?from=usd&to=bitcoin`), ENV_AE);                        // гейт
await worker.fetch(
  new Request(`${BASE}?from=usd&to=bitcoin`, { headers: { Cookie: "cf_clearance=x" } }),
  ENV_AE,
);                                                                                            // прошёл CF
await worker.fetch(
  new Request(`${BASE}?from=usd&to=bitcoin`, { headers: { Cookie: "bcr=1" } }),
  ENV_AE,
);                                                                                            // метка
const aeOk =
  aeEvents.includes("gate_js") &&
  aeEvents.includes("pass_clearance") &&
  aeEvents.includes("tag") &&
  aeEvents.every((e) => typeof e === "string");
if (!aeOk) failed++;
console.log(`${aeOk ? "PASS" : "FAIL"}  Analytics Engine: gate_js + pass_clearance + tag (${aeEvents.join(", ")})`);

// Без биндинга счётчик не должен ломать переход.
const noAe = await worker.fetch(new Request(`${BASE}?from=usd&to=bitcoin`, { headers: { Cookie: "bcr=1" } }), {});
const noAeOk = noAe.status === 302;
if (!noAeOk) failed++;
console.log(`${noAeOk ? "PASS" : "FAIL"}  без биндинга ANALYTICS: работает`);

console.log(failed ? `\n${failed} тест(ов) упало` : "\nвсе тесты прошли");
process.exit(failed ? 1 : 0);