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
  { name: "POST → 405", url: "", cookie: "bcr=1", method: "POST", status: 405 },
];

const BASE = "https://ratescout.ru/go/bestchange";
let failed = 0;

for (const c of CASES) {
  const headers = c.cookie ? { Cookie: c.cookie } : {};
  const res = await worker.fetch(new Request(BASE + c.url, { method: c.method || "GET", headers }), {});
  const loc = res.headers.get("Location") || "";
  const ok = res.status === c.status && (!c.location || loc === c.location);
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${c.name} → ${res.status} ${loc}`);
  if (!ok && c.location) console.log(`        ожидали ${c.status} ${c.location}`);
}

// Гейт: ставит cookie, возвращается на тот же адрес с js=1, закрыт от индексации.
const gate = await worker.fetch(new Request(`${BASE}?from=usd&to=bitcoin`), {});
const cookie = gate.headers.get("Set-Cookie") || "";
const html = await gate.text();
const gateOk =
  cookie.includes("bcr=1") && cookie.includes("Path=/go") &&
  html.includes("location.replace") && html.includes("js=1") &&
  gate.headers.get("X-Robots-Tag") === "noindex, nofollow";
if (!gateOk) failed++;
console.log(`${gateOk ? "PASS" : "FAIL"}  гейт: Set-Cookie + возврат с js=1 + noindex`);

console.log(failed ? `\n${failed} тест(ов) упало` : "\nвсе тесты прошли");
process.exit(failed ? 1 : 0);