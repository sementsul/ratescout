# Cloudflare: роутер /go/bestchange (пошагово)

Единый редирект-роутер партнёрских ссылок BestChange для RateScout и MyMany.
Код: `worker/go-router.js`. Один воркер обслуживает два маршрута в одной зоне `ratescout.ru`,
поэтому **DNS трогать не нужно**:

| Сайт | Боевой хост | Ссылки в вёрстке |
|---|---|---|
| RateScout | `ratescout.ru` | `https://ratescout.ru/go/bestchange?from=…&to=…` |
| MyMany | `my-many.ratescout.ru` | `https://my-many.ratescout.ru/go/bestchange?from=…&to=…` |

> `my-many.ru` — старый домен: там только страница «MyMany переехал», ссылок на обмен нет.
> Каждый сайт ведёт на роутер **своего** хоста, поэтому посетитель не прыгает между брендами.

Что это даёт: в HTML и JSON сайтов больше нет ссылок `bestchange.*?...p=1116359`. Все переходы идут
через `/go/bestchange`, а метку подставляет воркер — и только браузеру с cookie. Парсер, который дёргает href без JS, до BestChange не доходит вообще.

Логику воркера можно прогнать локально, без сети и без wrangler: `node worker/test-go-router.mjs`
(24 кейса — гейт, капча, метка, валидация, отсечение открытого редиректа).

Параметры роутера:

| Параметр | Куда ведёт |
|---|---|
| `from`,`to` | `bestchange.{ru,com}/<from>-to-<to>.html` |
| `fid`,`tid` | `bestchange.{ru,com}/index.php?mt=rates&from=&to=` (пары без своей страницы) |
| `mode=partner` | `…/partner/account.html` (партнёрская программа) |
| `page=report` | `…/report/` (AML-проверка адреса) |
| `lang=en` \| `fr` \| `es` | домен `.com` вместо `.ru` |
| `noerid=1` | редирект без `erid` (так ходят зеркала ES/FR) |
| без параметров | главная BestChange с меткой |

## Капча (Turnstile)

Без cookie роутер показывает страницу с капчей Cloudflare Turnstile. Cookie `bcr=1`
ставится **только после успешной серверной проверки токена**, поэтому скачивание
страницы само по себе ничего не даёт — это и отсекает ботов, которые умеют исполнять JS.

Включается переменными воркера (без правки кода):

1. Cloudflare → **Turnstile** → *Add widget*: имя `ratescout-go`, режим **Managed**,
   hostnames: `ratescout.ru`, `my-many.ratescout.ru`.
2. Скопировать **Site Key** и **Secret Key**.
3. Workers → `ratescout-go` → **Settings → Variables and Secrets**:
   - `TS_SITEKEY` — обычная переменная (site key);
   - `TS_SECRET` — **Secret** (secret key).
4. **Deploy** (переменные применяются к новой версии воркера).

Поведение при сбоях:

| Ситуация | Что происходит |
|---|---|
| Оба ключа заданы | показывается капча |
| Ключей нет | старый вариант: мгновенный JS-переход, но **без метки** |
| Токен не прошёл проверку | переход на BestChange **без метки**, без ошибки для человека |
| `siteverify` недоступен | то же — fail open без метки |
| Скрипт Turnstile не загрузился | через 6 с появляется ссылка «продолжить без проверки» (без метки) |

Проверка после включения: откройте в приватном окне
`https://ratescout.ru/go/bestchange?from=usd&to=bitcoin` — должна появиться капча,
после неё переход на `bestchange.ru/usd-to-bitcoin.html?p=…`; повторный клик по
любой партнёрской ссылке уже проходит без капчи (cookie на 180 дней).

---

## 0. Проверить исходное состояние

1. Зона `ratescout.ru` в Cloudflare — **оранжевое облако** (Proxied). Сейчас так и есть:
   `nslookup ratescout.ru` отдаёт адреса `104.21.x.x` / `172.67.x.x`, а не GitHub Pages.
2. `my-many.ratescout.ru` — боевой хост my-many, поддомен **той же зоны**, тоже Proxied
   (`104.21.60.168` / `172.67.198.108`), canonical сайта указывает сюда. Отдельная зона, DNS-записи
   и сертификаты не нужны — только второй маршрут воркера.
3. Тариф Free. Лимиты, которые нас касаются: **100 000 запросов воркера в сутки**, 10 мс CPU на запрос.
   Переходов у сайта на порядки меньше — с запасом.

---

## 1. Создать воркер

1. Cloudflare Dashboard → **Workers & Pages** → **Create** → **Worker**.
2. Имя: `ratescout-go` → **Deploy**.
3. **Edit code** → удалить шаблон, вставить целиком содержимое `worker/go-router.js` → **Deploy**.

Проверка на техническом домене (он появляется сразу):

```
https://ratescout-go.<ваш-аккаунт>.workers.dev/go/bestchange?from=usd&to=bitcoin
```

Ожидаемо: страница «Переход на BestChange…» → мгновенный редирект на
`https://www.bestchange.ru/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96`.

Если вместо этого 404 — маршрут ещё не привязан, это нормально, идём дальше.

---

## 2. Привязать маршруты к доменам

Workers & Pages → `ratescout-go` → **Settings** → **Domains & Routes** → **Add** → **Route** —
и так **два раза**:

| # | Zone | Route |
|---|---|---|
| 1 | `ratescout.ru` | `ratescout.ru/go/*` |
| 2 | `ratescout.ru` | `my-many.ratescout.ru/go/*` |

**Add route** каждый раз. С этого момента `/go/*` на обоих хостах обслуживает воркер, а не GitHub
Pages (страницы сайтов это не затрагивает — маршрут точечный).

> Почему не отдельный поддомен вида `go.ratescout.ru`: оба боевых хоста уже в зоне и проксируются,
> так что дополнительный маршрут — одна строка в настройках воркера. Ни DNS, ни сертификата,
> ни нового проксируемого хоста (а прокси Cloudflare в РФ, как вы отмечали, режут — лишний не нужен).

---

## 3. Проверить, что работает

```bash
# 1) без cookie — страница-гейт (200) и Set-Cookie: bcr=1
curl -sI "https://ratescout.ru/go/bestchange?from=usd&to=bitcoin" | head -20

# 2) с cookie — 302 на BestChange с меткой
curl -sI -b "bcr=1" "https://ratescout.ru/go/bestchange?from=usd&to=bitcoin" | grep -i location
#    Location: https://www.bestchange.ru/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96

# 3) английская версия
curl -sI -b "bcr=1" "https://ratescout.ru/go/bestchange?from=usd&to=bitcoin&lang=en" | grep -i location
#    Location: https://www.bestchange.com/usd-to-bitcoin.html?p=1116359&erid=2VtzqvK5m96

# 4) мусор в параметрах — на главную BestChange, но БЕЗ партнёрской метки
curl -sI -b "bcr=1" "https://ratescout.ru/go/bestchange?from=..%2f..%2fevil&to=x" | grep -i location
#    Location: https://www.bestchange.ru/?erid=2VtzqvK5m96

# 5) тот же роутер на хосте my-many — ссылки оттуда ведут сюда
curl -sI -b "bcr=1" "https://my-many.ratescout.ru/go/bestchange?from=bitcoin&to=usd" | grep -i location
#    Location: https://www.bestchange.ru/bitcoin-to-usd.html?p=1116359&erid=2VtzqvK5m96
```

Пункт 1 — ключевой: **пустой** запрос без куки не должен отдавать 302. Именно это отсекает
парсеры, которые просто бегут по ссылкам.

---

## 4. WAF: лимит на переходы (а не капча на всех)

Капча (Managed Challenge) на весь `/go/*` — плохая идея: она встанет перед каждым живым
покупателем и убьёт конверсию, а парсер с headless-браузером её всё равно пройдёт.

Правильный инструмент — **rate limiting**:

1. Security → **WAF** → **Rate limiting rules** → **Create rule**.
2. Настройки:

| Поле | Значение |
|---|---|
| Rule name | `go-router flood` |
| If incoming requests match | `URI Path` **starts with** `/go/` |
| With the same | IP |
| Requests | 10 |
| Period | 10 seconds |
| Action | Block |

3. **Deploy**.

На Free-плане доступно одно такое правило — этого достаточно. Если панель предлагает другие
значения периода/блока (зависит от тарифа) — берите минимальные из доступных.

Человек физически не делает 10 переходов за 10 секунд; парсер, кликающий сотни ссылок, упирается
в блок на втором-третьем.

---

## 5. Bot Fight Mode

Security → **Bots** → **Bot Fight Mode** → **On** (если ещё не включён — судя по тому, что сайт
отдаёт 403 на curl с не-браузерным User-Agent, он уже работает).

Это бесплатный слой: известные плохие боты и «пустые» UA получают JS-челлендж или 403 ещё до
воркера.

---

## 6. Закрыть /go/ от индексации

Уже сделано в коде: `build.py` пишет в `robots.txt` строку `Disallow: /go/`, а воркер отдаёт
`X-Robots-Tag: noindex, nofollow` на всех ответах. После деплоя проверить:

```bash
curl -s https://ratescout.ru/robots.txt | grep -i /go/
```

> Важно: `Disallow` в robots.txt только запрещает обход. От «утечки веса» защищает `rel="nofollow
> sponsored"` на самих ссылках — он в вёрстке уже стоит, его не снимаем.

---

## 7. Проверить, что метки больше нет в статике

```bash
# на странице валют my-many не должно быть ни одного ?p=
curl -s "https://my-many.ratescout.ru/valuta/bitcoin/" | grep -c "p=1116359"     # → 0
curl -s "https://my-many.ratescout.ru/data/chains/bitcoin.json" | grep -c "bestchange"  # → 0

# а ссылки должны вести на свой же хост
curl -s "https://my-many.ratescout.ru/data/chains/bitcoin.json" | grep -o "https://[^\"]*go/bestchange" | head -1
#    https://my-many.ratescout.ru/go/bestchange
```

Ожидаемо: нули. Если не нули — деплой my-many ещё не прошёл (крон каждые 15 минут) или правка
не влита в `main`.

---

## 8. Откат за минуту

- Удалить маршруты `ratescout.ru/go/*` и `my-many.ratescout.ru/go/*`
  (Workers → Settings → Domains & Routes → Delete).
  Сайты продолжат работать, `/go/*` начнёт отдавать 404 GitHub Pages, а ссылки — вести в никуда.
  **Поэтому порядок такой: сначала воркер и маршруты, потом мерж правок my-many.**
- Или удалить правило rate limiting — останется только куки-гейт.

---

## Чего не делать

- **Managed Challenge на весь `/go/*`** — капча перед каждым переходом. Конверсия в минус,
  парсеры с headless-браузером проходят.
- **Параметр вида `?url=https://…`** в роутере — это открытый редирект, за него сайт выкидывают
  из индекса и вешают фишинг. В `go-router.js` цель собирается только из белого списка.
- **Прятать `p=` через JS на клиенте** — уже пройденный этап: `p=` всё равно приходит в браузер,
  и любой, кто откроет devtools или запустит headless-браузер, его увидит. Метка должна жить
  только на сервере.