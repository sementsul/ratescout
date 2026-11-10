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

// Воркер отвечает только на свои домены. Иначе он же доступен по адресу
// *.workers.dev, который идёт мимо WAF-правила зоны: оттуда можно получить
// метку, просто скачав ссылку.
const ZONE_DOMAIN = "ratescout.ru";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD", "Cache-Control": "no-store" },
      });
    }

    if (url.hostname !== ZONE_DOMAIN && !url.hostname.endsWith("." + ZONE_DOMAIN)) {
      return new Response("Not Found", {
        status: 404,
        headers: { "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow" },
      });
    }

    const partner = (env && env.BC_PARTNER_ID) || PARTNER_DEFAULT;
    const erid = (env && env.BC_ERID) || ERID_DEFAULT;

    const langParam = (url.searchParams.get("lang") || "").toLowerCase();
    const lang = (langParam === "en" || langParam === "fr" || langParam === "es") ? "en" : "ru";
    const host = HOSTS[lang];
    // В статистике различаем зеркала: ru / en / fr / es (редирект у fr и es всё равно на .com).
    const langLabel = langParam === "en" || langParam === "fr" || langParam === "es" ? langParam : "ru";
    const ctx = { lang: langLabel, host: url.hostname, cf: request.cf };
    const noErid = url.searchParams.get("noerid") === "1";   // зеркала ES/FR: без erid
    const bare = noErid ? `${host}/` : `${host}/?erid=${enc(erid)}`;

    // Turnstile включается, когда заданы оба ключа (секрет — секретом воркера).
    const tsSecret = env && env.TS_SECRET;
    const tsSitekey = (env && env.TS_SITEKEY) || "";
    const turnstileOn = Boolean(tsSecret && tsSitekey);

    // Диагностика: показать состояние и цель перехода, НЕ редиректя.
    // Нужна, чтобы проверять настройку, не кликая по партнёрской ссылке
    // (клики владельца BestChange считает накруткой).
    if (url.searchParams.get("diag") === "1") {
      // ?diag=1&gate=1 — показать саму страницу-гейт: видно, отрисовывается ли
      // виджет Turnstile на этом домене (при чужом hostname он ругается ошибкой).
      if (url.searchParams.get("gate") === "1") {
        return gatePage(url, turnstileOn ? tsSitekey : "");
      }
      const cookieHeader = request.headers.get("Cookie") || "";
      return new Response(
        JSON.stringify(
          {
            host: url.hostname,
            lang: langLabel,
            bestchange: host,
            partner: partner,
            erid_configured: Boolean(erid),
            noerid: noErid,
            turnstile: {
              enabled: turnstileOn,
              sitekey_set: Boolean(tsSitekey),
              secret_set: Boolean(tsSecret),
            },
            cookies: {
              gate: hasGateCookie(cookieHeader),
              cf_clearance: /(?:^|;\s*)cf_clearance=/.test(cookieHeader),
            },
            target: buildTarget(url.searchParams, host, partner, erid, noErid),
          },
          null,
          2,
        ),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex, nofollow",
          },
        },
      );
    }

    // 1. Куки-гейт: без него метки не будет.
    if (!hasGateCookie(request.headers.get("Cookie"))) {
      const tsToken = url.searchParams.get("_ts");

      // 1a. Клиент вернулся с токеном Turnstile — проверяем на сервере.
      //     Токен одноразовый; при любой ошибке пускаем без метки, но не блокируем.
      if (tsToken && tsSecret) {
        const ok = await verifyTurnstile(tsSecret, tsToken, request.headers.get("CF-Connecting-IP"));
        track(env, ok ? "pass_turnstile" : "fail_turnstile", ctx);
        if (!ok) return redirect(bare);
        const target = buildTarget(url.searchParams, host, partner, erid, noErid);
        return redirect(target || bare, { "Set-Cookie": gateCookie() });
      }

      if (url.searchParams.get("js") === "1") {
        // Turnstile не загрузился / человек нажал «продолжить без проверки».
        // Не ломаем переход человеку, но и реферальную метку не отдаём.
        track(env, "no_tag_js", ctx);
        return redirect(bare);
      }

      // 1b. Cloudflare уже пропустил этого клиента через свой challenge (правило WAF
      //     на /go/*) — браузер проверен, не мучаем человека второй страницей.
      const cookieHeader = request.headers.get("Cookie") || "";
      if (/(?:^|;\s*)cf_clearance=/.test(cookieHeader)) {
        track(env, "pass_clearance", ctx);
        const target = buildTarget(url.searchParams, host, partner, erid, noErid);
        return redirect(target || bare, { "Set-Cookie": gateCookie() });
      }

      // 1c. Показываем капчу. Cookie тут НЕ ставится — иначе её получал бы любой бот
      //     за одно скачивание страницы.
      track(env, turnstileOn ? "gate_turnstile" : "gate_js", ctx);
      return gatePage(url, turnstileOn ? tsSitekey : "");
    }

    // 2. Анти-флуд: сотни кликов с одного адреса — это парсер, а не человек.
    if (await overLimit(request)) {
      track(env, "rate_limited", ctx);
      return new Response("Too Many Requests", {
        status: 429,
        headers: { "Retry-After": "60", "Cache-Control": "no-store" },
      });
    }

    // 3. Цель: только из белого списка параметров, никаких произвольных URL.
    const target = buildTarget(url.searchParams, host, partner, erid, noErid);
    track(env, target ? "tag" : "no_tag_bad", ctx);
    return redirect(target || bare);
  },
};

/* ─────────────────────────── helpers ─────────────────────────── */

function enc(v) {
  return encodeURIComponent(String(v));
}

/**
 * Счётчик событий в Workers Analytics Engine (биндинг ANALYTICS, необязательный).
 * Без биндинга — тихо ничего не делает. Считаем только то, что дошло до воркера:
 * запросы, которые Cloudflare отбил челленджем, сюда не попадают вообще.
 *
 * blobs:   [событие, язык, страна, хост, организация ASN]
 * doubles: [1, номер ASN]
 */
function track(env, event, ctx) {
  try {
    const ae = env && env.ANALYTICS;
    if (ae && typeof ae.writeDataPoint === "function") {
      const cf = (ctx && ctx.cf) || {};
      ae.writeDataPoint({
        indexes: [event],
        blobs: [
          event,
          (ctx && ctx.lang) || "ru",
          cf.country || "??",
          (ctx && ctx.host) || "",
          cf.asOrganization || "",
        ],
        doubles: [1, Number(cf.asn) || 0],
      });
    }
  } catch (e) {
    /* аналитика не должна ломать переход */
  }
}

function hasGateCookie(cookieHeader) {
  if (!cookieHeader) return false;
  return cookieHeader.split(";").some((part) => {
    const [name, ...rest] = part.trim().split("=");
    return name === GATE_COOKIE && rest.join("=") === "1";
  });
}

function buildTarget(params, host, partner, erid, noErid) {
  // noerid=1 — зеркала ES/FR намеренно не показывают маркировку erid: оставляем только p.
  const p = noErid ? `p=${enc(partner)}` : `p=${enc(partner)}&erid=${enc(erid)}`;

  if (params.get("mode") === "partner") {
    return `${host}/partner/account.html?${p}`;
  }

  // page=report — AML-проверка адреса BestChange
  if (params.get("page") === "report") {
    return `${host}/report/?${p}`;
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

function gateCookie() {
  return `${GATE_COOKIE}=1; Path=${GATE_PATH}; Max-Age=15552000; SameSite=Lax; Secure; HttpOnly`;
}

/**
 * Проверка токена Turnstile на стороне сервера.
 * Любая сетевая/HTTP-ошибка → false (не пускаем с меткой, но и не ломаем переход).
 */
async function verifyTurnstile(secret, token, ip) {
  try {
    const body = new FormData();
    body.append("secret", secret);
    body.append("response", token);
    if (ip) body.append("remoteip", ip);
    const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      body,
    });
    const data = await res.json();
    return data && data.success === true;
  } catch (e) {
    return false;
  }
}

/**
 * Страница-гейт с Turnstile: cookie ставится ТОЛЬКО после успешной проверки,
 * на сервере (см. ветку с _ts в fetch). Здесь cookie не выставляется — иначе
 * любой бот получал бы её просто за скачивание страницы.
 */
function gatePage(url, sitekey) {
  const next = new URL(url.toString());
  next.searchParams.delete("_ts");
  next.searchParams.delete("js");
  const back = next.pathname + next.search;

  // Turnstile не настроен (нет сайт-ключа) — прежнее поведение: cookie ставится
  // страницей, JS сразу возвращается на тот же адрес с js=1.
  if (!sitekey) {
    const legacy = back + (back.includes("?") ? "&" : "?") + "js=1";
    return new Response(
      `<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow"><title>Переход…</title></head><body>
<script>location.replace(${JSON.stringify(legacy)});</script></body></html>`,
      {
        status: 200,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-store",
          "X-Robots-Tag": "noindex, nofollow",
          "Set-Cookie": gateCookie(),
        },
      },
    );
  }

  const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Проверка…</title>
<style>
body{background:#000;color:#0f0;font:16px/1.5 monospace;padding:36px 20px;text-align:center}
a{color:#55ffff}
.box{margin:0 auto;max-width:420px}
#ts{margin:22px 0}
#skip{display:none;margin-top:18px;font-size:14px;opacity:.75}
</style>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
</head>
<body>
<div class="box">
<p>Проверяем, что вы человек…</p>
<div id="ts"><div class="cf-turnstile" data-sitekey="${sitekey}" data-callback="tsOk"></div></div>
<p id="skip">Не грузится? <a href="${back}${back.includes("?") ? "&" : "?"}js=1" rel="nofollow noopener">Продолжить без проверки</a></p>
</div>
<script>
function tsOk(token){
  var u=${JSON.stringify(back)}+(${JSON.stringify(back)}.indexOf("?")===-1?"?":"&")+"_ts="+encodeURIComponent(token);
  location.replace(u);
}
setTimeout(function(){document.getElementById("skip").style.display="block";},6000);
</script>
</body></html>`;

  return new Response(html, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex, nofollow",
      "Content-Security-Policy":
        "default-src 'none'; script-src 'unsafe-inline' https://challenges.cloudflare.com; " +
        "style-src 'unsafe-inline'; connect-src https://challenges.cloudflare.com; " +
        "frame-src https://challenges.cloudflare.com; " +
        "img-src data: https://challenges.cloudflare.com",
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