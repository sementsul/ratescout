#!/usr/bin/env python3
"""Генератор статического SEO-сайта RateScout (GitHub Pages) — полный каталог BestChange.

Источник каталога: currencies.json (330 валют, 6 категорий, слаги/ID/тикеры).
Структура — монитор (bestchange): каталог по категориям + конвертер по ВСЕМ валютам.
SEO: страница на КАЖДУЮ валюту (/valuta/<slug>/) со всеми направлениями обмена (deep-links + ?p=).
Тема — ретро-терминал (референс doshaven.eu). Комплаенс-страницы по правилам партнёрки и законам РФ/США.
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
SITE = json.load(open(os.path.join(ROOT, "data.json"), encoding="utf-8"))["site"]
CAT = json.load(open(os.path.join(ROOT, "currencies.json"), encoding="utf-8"))
CUR = CAT["currencies"]                      # {slug: {id,name,ticker,category}}
CATS = CAT["categories"]                     # порядок категорий
S = SITE
BASE_URL = f"https://{S['domain']}"
REF = S["ref"]


def bc_link(frm, to):
    return f"https://www.bestchange.ru/{frm}-to-{to}.html?p={REF}"


def cpage(slug):
    return f"/valuta/{slug}/"


def by_category():
    g = {c: [] for c in CATS}
    for slug, info in CUR.items():
        g.setdefault(info["category"], []).append((slug, info))
    for c in g:
        g[c].sort(key=lambda x: x[1]["name"])
    return g


GROUPED = by_category()

# реальные курсы (генерятся fetch_rates.py в CI из партнёрского API; ключ НЕ здесь)
RATES = {}
_rp = os.path.join(ROOT, "rates.json")
if os.path.exists(_rp):
    try:
        RATES = json.load(open(_rp, encoding="utf-8")).get("pairs", {})
    except (ValueError, OSError):
        RATES = {}


def rate_of(frm, to):
    return RATES.get(f"{frm}>{to}")


def fmt_rate(s):
    """Человекочитаемый курс без научной нотации."""
    try:
        v = float(s)
    except (TypeError, ValueError):
        return s
    if v >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    if v >= 1:
        return f"{v:,.2f}".replace(",", " ")
    return f"{v:.4g}"

DISCLOSURE = ("RateScout — независимый информационный сервис мониторинга курсов. Мы не обменный пункт и не "
              "проводим операции. Ссылки ведут в сервис BestChange (подбор лучших курсов в надёжных обменниках); "
              "по партнёрской программе мы можем получать вознаграждение. Это не реклама от имени BestChange.")


def head(title, desc, canonical, extra=""):
    return f"""<!doctype html>
<html lang="{S['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{BASE_URL}{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{BASE_URL}{canonical}">
<meta property="og:site_name" content="{S['name']}">
<meta name="robots" content="index,follow">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#0f6b34">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/styles.css">
{extra}
</head>
<body>"""


HEADER = f"""<header class="site">
  <a class="brand" href="/"><span class="logo">[◎]</span> {S['name']}<span class="tld">.ru</span></a>
  <nav>
    <a href="/">Монитор</a>
    <a href="/o-servise/">Что такое BestChange</a>
    <a href="/aml/">AML-проверка</a>
    <a href="/raskrytie/">Раскрытие</a>
  </nav>
</header>"""


def footer():
    return f"""<footer class="site">
  <div class="disc">{DISCLOSURE}</div>
  <div class="links"><a href="/o-servise/">О сервисе</a> · <a href="/aml/">AML-проверка</a> ·
    <a href="/raskrytie/">Раскрытие и дисклеймеры</a> · <a href="/politika/">Политика конфиденциальности</a></div>
  <div class="fine">18+. Информация справочная, не является финансовой рекомендацией. Курсы меняются.
    © {S['name']} {S['domain']}. <span class="erid">Реклама. ERID: — (регистрируется в ОРД)</span></div>
</footer>
<script src="/assets/catalog.js"></script>
<script src="/assets/app.js"></script>
</body></html>"""


def jsonld(o):
    return f'<script type="application/ld+json">{json.dumps(o, ensure_ascii=False)}</script>'


def write(path, html):
    full = os.path.join(DIST, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8").write(html)


def converter_html(preset_from=""):
    return f"""<div class="conv" id="conv" data-from="{preset_from}">
  <h3>Калькулятор направления</h3>
  <label>Отдаю<select id="cFrom"></select></label>
  <button class="swap" id="cSwap" type="button">⇅ поменять</button>
  <label>Получаю<select id="cTo"></select></label>
  <a class="cta" id="cGo" href="https://www.bestchange.ru/?p={REF}" target="_blank" rel="nofollow noopener sponsored">Найти лучший курс →</a>
  <div class="hint">Переход в BestChange. По партнёрской ссылке мы можем получать вознаграждение.</div>
</div>"""


# ---------------- главная = монитор-каталог ----------------
def render_home():
    total = len(CUR)
    # каталог по категориям (ссылки на страницы валют)
    cat_boxes = ""
    for c in CATS:
        items = "".join(f'<li><a href="{cpage(slug)}">{info["name"]} <span>{info["ticker"]}</span></a></li>'
                         for slug, info in GROUPED.get(c, []))
        cat_boxes += f'<div class="catbox"><h3>{c} <em>{len(GROUPED.get(c, []))}</em></h3><ul>{items}</ul></div>'

    ld = jsonld({"@context": "https://schema.org", "@type": "WebSite", "name": S["name"],
                 "url": BASE_URL, "description": S["tagline"]})
    title = f"{S['name']} — мониторинг курсов обмена: {total} валют, лучшие курсы"
    desc = ("Мониторинг курсов обмена криптовалют и денег: сравните лучшие курсы в надёжных обменниках через "
            f"BestChange. {total} валют, все направления, AML-проверка адресов.")
    body = f"""{HEADER}
<main>
<div class="hero-strip">
  <pre class="ascii">  ____       _        ____                  _
 |  _ \\ __ _| |_ ___ / ___|  ___ ___  _   _| |_
 | |_) / _` | __/ _ \\\\___ \\ / __/ _ \\| | | | __|
 |  _ < (_| | ||  __/ ___) | (_| (_) | |_| | |_
 |_| \\_\\__,_|\\__\\___|____/ \\___\\___/ \\__,_|\\__|</pre>
  <h1>Мониторинг лучших курсов обмена</h1>
  <p class="lead">{S['name']} сравнивает предложения надёжных обменников через <b>BestChange</b> по
     <b>{total}</b> валютам. Выберите направление в калькуляторе или валюту в каталоге ниже.</p>
</div>

<div class="monitor">
  <aside class="filters">{converter_html()}</aside>
  <section class="rows">
    <div class="rates-head"><h2 style="margin:0">Каталог валют</h2>
      <span>всего: <span class="count">{total}</span></span></div>
    <div class="catgrid">{cat_boxes}</div>
  </section>
</div>

<section class="about">
  <h2>Что такое BestChange и зачем он нужен</h2>
  <p><b>BestChange</b> — мониторинг обменных пунктов: собирает курсы десятков надёжных обменников и показывает,
     где выгоднее обменять криптовалюту или валюту. RateScout помогает подобрать направление среди {total} валют
     и ведёт в BestChange к проверенному обменнику. <a href="/o-servise/">Подробнее →</a></p>
</section>
<section class="aml-cta">
  <h2>Проверяйте криптоадреса (AML)</h2>
  <p>Перед обменом полезно проверить адрес на связь с мошенничеством и санкциями. <a href="/aml/">Как сделать AML-проверку →</a></p>
</section>
</main>
{ld}
{footer()}"""
    write("index.html", head(title, desc, "/", ld) + body)


# ---------------- страница валюты = все направления ----------------
def render_currency(slug, info):
    name, ticker, cat = info["name"], info["ticker"], info["category"]
    canonical = cpage(slug)
    title = f"Обмен {name} ({ticker}) — курсы и все направления | {S['name']}"
    desc = (f"Обмен {name} ({ticker}): лучшие курсы в надёжных обменниках через BestChange. Все направления "
            f"обмена {ticker} на криптовалюты, банки и наличные. AML-проверка адресов.")
    # направления: slug -> все остальные, по категориям
    dir_blocks = ""
    for c in CATS:
        def _row(ts, ti):
            r = rate_of(slug, ts)
            rr = f' <b class="rt">{fmt_rate(r["rate"])}</b>' if r else ''
            return (f'<li><a href="{bc_link(slug, ts)}" target="_blank" rel="nofollow noopener sponsored">'
                    f'{name} → {ti["name"]} <span>{ti["ticker"]}</span>{rr}</a></li>')
        rows = "".join(_row(ts, ti) for ts, ti in GROUPED.get(c, []) if ts != slug)
        if rows:
            dir_blocks += f'<div class="dirbox"><h3>{name} → {c}</h3><ul>{rows}</ul></div>'

    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Монитор", "item": BASE_URL},
        {"@type": "ListItem", "position": 2, "name": f"{name} ({ticker})", "item": BASE_URL + canonical}]}
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f"Как обменять {name} ({ticker}) выгодно?",
         "acceptedAnswer": {"@type": "Answer",
          "text": f"Через мониторинг BestChange: он сравнивает курсы {name} в надёжных обменниках и показывает лучший. Выберите направление и перейдите к обмену."}},
        {"@type": "Question", "name": f"Безопасно ли менять {ticker}?",
         "acceptedAnswer": {"@type": "Answer",
          "text": "Обмен идёт в проверенных пунктах BestChange с рейтингом и резервами. Для крипто рекомендуем AML-проверку адреса."}}]}
    body = f"""{HEADER}
<main class="doc">
<nav class="crumbs"><a href="/">Монитор</a> / {name} <span class="tk">{ticker}</span></nav>
<h1>Обмен {name} <span class="tk">{ticker}</span></h1>
<p>Сравните лучшие курсы обмена <b>{name} ({ticker})</b> в надёжных обменниках через мониторинг
   <b>BestChange</b> и выберите направление ниже. RateScout ведёт вас к проверенному пункту; сам обмен
   вы совершаете на сайте обменника.</p>

<div class="monitor">
  <aside class="filters">{converter_html(slug)}</aside>
  <section class="rows">
    <h2>Направления обмена {ticker}</h2>
    <div class="dirgrid">{dir_blocks}</div>
  </section>
</div>

<h2>Как обменять {name} на выгодных условиях</h2>
<ol class="steps">
  <li>Выберите направление обмена {ticker} выше.</li>
  <li>В BestChange сравните курс, резерв и рейтинг обменников.</li>
  <li>Для крипто — сделайте <a href="/aml/">AML-проверку адреса</a>.</li>
  <li>Перейдите в выбранный обменник и проведите операцию.</li>
</ol>
<h2>Частые вопросы</h2>
<details><summary>Как обменять {name} ({ticker}) выгодно?</summary>
  <p>Через мониторинг BestChange — он показывает лучший курс среди надёжных обменников.</p></details>
<details><summary>Безопасно ли менять {ticker}?</summary>
  <p>Обмен в проверенных пунктах BestChange. Для крипто рекомендуем AML-проверку адреса.</p></details>
</main>
{jsonld(crumbs)}{jsonld(faq)}
{footer()}"""
    write(f"valuta/{slug}/index.html", head(title, desc, canonical) + body)


def render_page(slug, title, desc, body_html):
    canonical = f"/{slug}/"
    body = f"""{HEADER}
<main class="doc">
<nav class="crumbs"><a href="/">Монитор</a> / {title}</nav>
{body_html}
</main>
{footer()}"""
    write(f"{slug}/index.html", head(f"{title} | {S['name']}", desc, canonical) + body)


def compliance_pages():
    render_page("o-servise", "Что такое BestChange и как подбирать лучший курс",
                "BestChange — мониторинг обменных пунктов: как найти лучший курс обмена криптовалют и валют в надёжных обменниках.",
                """<h1>Что такое BestChange</h1>
<p><b>BestChange</b> — мониторинг обменников электронных валют и криптовалют. Сервис в реальном времени собирает
   курсы, резервы и комиссии десятков обменных пунктов и показывает, где выгоднее обменять деньги или крипту
   прямо сейчас. Это экономит время и деньги — не нужно обходить сайты вручную.</p>
<h2>Как это работает</h2>
<ol class="steps"><li>Выбираете направление обмена.</li><li>BestChange показывает обменники, отсортированные по выгодности.</li>
<li>Смотрите рейтинг, резерв и отзывы, выбираете надёжный пункт.</li><li>Переходите и проводите операцию.</li></ol>
<h2>Почему это надёжно</h2>
<p>В мониторинг попадают проверенные обменники с рейтингом и резервами. RateScout — независимый информационный
   сервис, который помогает сориентироваться и ведёт в BestChange к лучшему предложению. Сами обмен не проводим.</p>""")
    render_page("aml", "AML-проверка криптоадреса — зачем и как",
                "AML-проверка (Anti-Money Laundering): как проверить криптоадрес на связь с мошенничеством и санкциями перед обменом.",
                f"""<h1>AML-проверка криптоадреса</h1>
<p><b>AML</b> (Anti-Money Laundering) — проверка криптоадреса или транзакции на связь с мошенничеством, даркнетом,
   украденными средствами и санкциями. Снижает риск получить «грязные» монеты и блокировку на бирже.</p>
<h2>Когда делать</h2><ul><li>перед приёмом крупной суммы в крипте;</li><li>перед обменом крипты на рубли/наличные;</li>
<li>если контрагент незнаком.</li></ul>
<h2>Как проверить</h2>
<p>AML-проверку можно выполнить через BestChange: вводите адрес — получаете отчёт о рисках. Доступны пакеты (ваучеры).</p>
<a class="cta" href="https://www.bestchange.ru/?p={REF}" target="_blank" rel="nofollow noopener sponsored">Сделать AML-проверку в BestChange →</a>
<p class="hint">Переход в BestChange. По партнёрской ссылке мы можем получать вознаграждение.</p>""")
    render_page("raskrytie", "Раскрытие информации и дисклеймеры",
                "Партнёрское раскрытие и правовая информация RateScout (РФ и США).",
                f"""<h1>Раскрытие информации и дисклеймеры</h1>
<h2>Партнёрское раскрытие</h2><p>{DISCLOSURE}</p>
<p><i>English:</i> RateScout is an independent rate-monitoring service. Links lead to BestChange; we may earn a
   commission (FTC disclosure). Not advertising on behalf of BestChange.</p>
<h2>Дисклеймер</h2><p>Информация справочная, не является финансовой/инвестиционной/юридической рекомендацией.
   Курсы меняются. Решение об обмене — самостоятельно и на свой риск. 18+.</p>
<h2>Соответствие законодательству</h2>
<ul><li><b>РФ:</b> рекламные материалы маркируются (ERID) и учитываются в ОРД; ПДн — по 152-ФЗ (см. Политику).</li>
<li><b>США:</b> affiliate-раскрытие по FTC; сервис недоступен под санкциями (OFAC).</li></ul>
<p class="hint">Правовые тексты — черновик, требуют проверки юристом перед публикацией.</p>""")
    render_page("politika", "Политика конфиденциальности",
                "Как RateScout обрабатывает данные и cookie (152-ФЗ).",
                """<h1>Политика конфиденциальности</h1>
<p>RateScout — статический информационный сайт. Регистрационные данные не собираем, операции не проводим. Сайт
   может использовать cookie и обезличенную аналитику. Продолжая пользоваться сайтом, вы соглашаетесь с cookie.</p>
<p>Персональные данные (152-ФЗ) не запрашиваем. Черновик, требует проверки юристом.</p>""")


def catalog_js():
    cur = {slug: {"n": i["name"], "t": i["ticker"], "c": i["category"]} for slug, i in CUR.items()}
    js = "window.__CATALOG__=" + json.dumps({"order": CATS, "cur": cur}, ensure_ascii=False) + \
         ";window.__REF__=" + json.dumps(REF) + ";"
    write("assets/catalog.js", js)


def static_files():
    urls = ["/", "/o-servise/", "/aml/", "/raskrytie/", "/politika/"] + [cpage(s) for s in CUR]
    items = "\n".join(f"  <url><loc>{BASE_URL}{u}</loc><changefreq>hourly</changefreq></url>" for u in urls)
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>')
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")
    write("CNAME", S["domain"] + "\n")
    write("manifest.webmanifest", json.dumps({
        "name": S["name"] + " — мониторинг курсов обмена", "short_name": S["name"],
        "description": S["tagline"], "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#f4f1e6", "theme_color": "#0f6b34", "lang": "ru",
        "icons": [{"src": "/assets/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}]
    }, ensure_ascii=False, indent=2))
    write("sw.js", "const C='ratescout-v1';\n"
          "self.addEventListener('install',e=>self.skipWaiting());\n"
          "self.addEventListener('activate',e=>self.clients.claim());\n"
          "self.addEventListener('fetch',e=>e.respondWith(fetch(e.request)"
          ".then(r=>{const c=r.clone();caches.open(C).then(x=>x.put(e.request,c));return r})"
          ".catch(()=>caches.match(e.request))));")
    write(".nojekyll", "")


def copy_assets():
    dst = os.path.join(DIST, "assets")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(ROOT, "assets"), dst)


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    render_home()
    for slug, info in CUR.items():
        render_currency(slug, info)
    compliance_pages()
    static_files()
    copy_assets()
    catalog_js()   # ПОСЛЕ copy_assets: иначе copytree затрёт dist/assets
    print(f"✅ dist/: главная + {len(CUR)} страниц валют + 4 комплаенс + sitemap/robots/manifest/sw/CNAME")


if __name__ == "__main__":
    main()
