/**
 * RateScout — /go/bestchange: единый редирект-роутер партнёрских ссылок BestChange.
 * Cloudflare Worker, маршрут: ratescout.ru/go/*
 *
 * ЗАЧЕМ. Раньше партнёрская метка ?p=1116359 лежала в статическом HTML/JSON каждого сайта:
 * любой парсер, разобравший страницу, получал сотни готовых реферальных ссылок и кликал по ним.
 * Теперь в HTML нет ни одного адреса bestchange.* с меткой — только внутренние /go/...,
 * а метку подставляет этот Worker, и только живому браузеру.
 *
 * КАК РАБОТАЕТ.
 *   1) Нет cookie bcr=1 → отдаём крошечную страницу-«гейт»: она ставит cookie заголовком
 *      Set-Cookie и мгновенно возвращается на тот же URL с js=1. Пользователь этого не видит
 *      (один лишний хоп ~30–80 мс).
 *   2) С cookie → валидируем параметры и отдаём 302 на BestChange с ?p= и erid.
 *   3) Парсер без JS/кук застревает на гейте и до BestChange не доходит.
 *   4) Грубый лимит переходов на IP (Cache API, 30/мин — щедро, чтобы не резать NAT/CGNAT).
 *
 * ПАРАМЕТРЫ.
 *   from, to     — слаги валют (usd, bitcoin, tether-trc20 …)  → /{from}-to-{to}.html
 *   fid, tid     — числовые id валют                            → /index.php?mt=rates&from&to
 *   mode=partner — регистрация в партнёрке                      → /partner/account.html
 *   lang=ru|en   — BestChange.ru или BestChange.com
 *
 * Окружение (Settings → Variables в дашборде воркера), все необязательные:
 *   BC_PARTNER_ID — партнёрская метка (по умолчанию 1116359)
 *   BC_ERID       — erid креатива  (по умолчанию 2VtzqvK5m96)
 */

const PARTNER_DEFAULT = "1116359";
const ERID_DEFAULT = "2VtzqvK5m96";

const HOSTS = {
  ru: "https://www.bestchange.ru",
  en: "https://www.bestchange.com",
};

const SLUG_RE = /^[a-z0-9][a-z0-9_-]{1,23}$/i;   // usd, bitcoin, tether-trc20
const ID_RE = /^\d{1,6}$/;                        // числовые id каталога
const GATE_COOKIE = "bcr";
const GATE_PATH = "/go";
const IP_LIMIT = 30;                              // переходов с одного IP за 60 с

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD", "Cache-Control": "no-store" },
      });
    }

    const partner = (env && env.BC_PARTNER_ID) || PARTNER_DEFAULT;
    const erid = (env && env.BC_ERID) || ERID_DEFAULT;

    const lang = url.searchParams.get("lang") === "en" ? "en" : "ru";
    const host = HOSTS[lang];

    // 1. Куки-гейт: без него — только страница-заглушка, метки не будет.
    if (!hasGateCookie(request.headers.get("Cookie"))) {
      if (url.searchParams.get("js") === "1") {
        // JS работает, а cookie не сохранилась (приватный режим, блокировщик кук).
        // Не ломаем переход человеку, но и реферальную метку не отдаём.
        return redirect(`${host}/?erid=${enc(erid)}`);
      }
      return gatePage(url, host, erid);
    }

    // 2. Анти-флуд: сотни кликов с одного адреса — это парсер, а не человек.
    if (await overLimit(request)) {
      return new Response("Too Many Requests", {
        status: 429,
        headers: { "Retry-After": "60", "Cache-Control": "no-store" },
      });
    }

    // 3. Цель: только из белого списка параметров, никаких произвольных URL.
    const target = buildTarget(url.searchParams, host, partner, erid);
    return redirect(target || `${host}/?erid=${enc(erid)}`);
  },
};

/* ─────────────────────────── helpers ─────────────────────────── */

function enc(v) {
  return encodeURIComponent(String(v));
}

function hasGateCookie(cookieHeader) {
  if (!cookieHeader) return false;
  return cookieHeader.split(";").some((part) => {
    const [name, ...rest] = part.trim().split("=");
    return name === GATE_COOKIE && rest.join("=") === "1";
  });
}

function buildTarget(params, host, partner, erid) {
  const p = `p=${enc(partner)}&erid=${enc(erid)}`;

  if (params.get("mode") === "partner") {
    return `${host}/partner/account.html?${p}`;
  }

  const fid = params.get("fid");
  const tid = params.get("tid");
  if (fid || tid) {
    if (!ID_RE.test(fid || "") || !ID_RE.test(tid || "")) return null;
    return `${host}/index.php?mt=rates&from=${fid}&to=${tid}&${p}`;
  }

  const from = params.get("from");
  const to = params.get("to");
  if (from || to) {
    if (!SLUG_RE.test(from || "") || !SLUG_RE.test(to || "")) return null;
    return `${host}/${from.toLowerCase()}-to-${to.toLowerCase()}.html?${p}`;
  }

  // Без параметров — просто главная BestChange (кнопки «открыть мониторинг»).
  return `${host}/?${p}`;
}

function redirect(location, headers = {}) {
  return new Response(null, {
    status: 302,
    headers: {
      Location: location,
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex, nofollow",
      ...headers,
    },
  });
}

/** Страница-гейт: ставит cookie и сразу возвращается на тот же адрес с js=1. */
function gatePage(url, host, erid) {
  const next = new URL(url.toString());
  next.searchParams.set("js", "1");
  const back = next.pathname + next.search;

  const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Переход…</title>
<style>body{background:#000;color:#0f0;font:16px/1.5 monospace;padding:40px;text-align:center}
a{color:#55ffff}</style></head>
<body>
<p>Переход на BestChange…</p>
<p><a href="${host}/?erid=${enc(erid)}" rel="nofollow noopener">Продолжить вручную</a></p>
<script>location.replace(${JSON.stringify(back)});</script>
</body></html>`;

  return new Response(html, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex, nofollow",
      "Set-Cookie": `${GATE_COOKIE}=1; Path=${GATE_PATH}; Max-Age=86400; SameSite=Lax; Secure`,
    },
  });
}

/**
 * Грубый счётчик на IP через Cache API: ключ живёт 60 с, значение — число попаданий.
 * Кэш в Workers общий на дата-центр и «best effort» — это именно грубый предохранитель
 * от массового клика, а не точный rate limiter (для точного есть правило Cloudflare).
 */
async function overLimit(request) {
  if (typeof caches === "undefined" || !caches.default) return false;

  const ip = request.headers.get("CF-Connecting-IP");
  if (!ip) return false;

  const key = new Request(`https://rate-limit.invalid/${enc(ip)}`, { method: "GET" });
  try {
    const hit = await caches.default.match(key);
    const seen = hit ? parseInt(await hit.text(), 10) || 0 : 0;
    if (seen >= IP_LIMIT) return true;
    await caches.default.put(
      key,
      new Response(String(seen + 1), { headers: { "Cache-Control": "max-age=60" } }),
    );
  } catch (e) {
    return false; // кэш недоступен — не блокируем живых людей
  }
  return false;
}