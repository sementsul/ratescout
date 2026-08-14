#!/usr/bin/env python3
"""Генератор статического SEO-сайта RateScout (GitHub Pages) — полный каталог BestChange.

Источник каталога: currencies.json (330 валют, 6 категорий, слаги/ID/тикеры).
Структура — монитор (bestchange): каталог по категориям + конвертер по ВСЕМ валютам.
SEO: страница на КАЖДУЮ валюту (/valuta/<slug>/) со всеми направлениями обмена (deep-links + ?p=).
Тема — ретро-терминал (референс doshaven.eu). Комплаенс-страницы по правилам партнёрки и законам РФ/США.
"""
import json
import os
import re
import shutil
from datetime import datetime, timezone

try:
    import markdown as _md
    def md_render(s):
        return _md.markdown(s, extensions=["extra"])
except ImportError:                                  # фолбэк без пакета markdown
    def md_render(s):
        out = []
        for para in s.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            if para.startswith("## "):
                out.append(f"<h2>{para[3:]}</h2>")
            elif para.startswith("# "):
                out.append(f"<h1>{para[2:]}</h1>")
            elif para.startswith("- "):
                li = "".join(f"<li>{l[2:]}</li>" for l in para.splitlines() if l.startswith("- "))
                out.append(f"<ul>{li}</ul>")
            else:
                out.append(f"<p>{para}</p>")
        return "\n".join(out)

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
    f, t = CUR.get(frm, {}), CUR.get(to, {})
    # новые валюты (без BestChange-слага) — числовая ссылка по id; остальные — слаг
    if f.get("num") or t.get("num"):
        return f"https://www.bestchange.ru/index.php?mt=rates&from={f.get('id')}&to={t.get('id')}&p={REF}"
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


# топ-популярные направления (bm_top.dat → top.json, генерится fetch_rates.py)
TOP = []
_tp = os.path.join(ROOT, "top.json")
if os.path.exists(_tp):
    try:
        TOP = [p for p in json.load(open(_tp, encoding="utf-8")).get("pairs", [])
               if p.get("from") in CUR and p.get("to") in CUR]
    except (ValueError, OSError):
        TOP = []
TOP_SET = {(p["from"], p["to"]) for p in TOP}


def pair_url(f, t):
    return f"/obmen/{f}-{t}/"


def popular_involving(slug, n=8):
    return [p for p in TOP if p["from"] == slug or p["to"] == slug][:n]


def pair_link_li(p):
    return (f'<li><a href="{pair_url(p["from"], p["to"])}">'
            f'{CUR[p["from"]]["name"]} <span>{CUR[p["from"]]["ticker"]}</span> → '
            f'{CUR[p["to"]]["name"]} <span>{CUR[p["to"]]["ticker"]}</span></a></li>')


def popular_block(slug):
    pops = popular_involving(slug)
    if not pops:
        return ""
    return f'<h2 class="news">Популярные направления</h2><ul class="dlist">{"".join(pair_link_li(p) for p in pops)}</ul>'


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
    if v >= 0.01:
        return f"{v:.4f}".rstrip("0").rstrip(".")
    # очень малые значения — фиксированная запись без научной нотации
    return (f"{v:.12f}".rstrip("0").rstrip(".")) or "0"


NET = {"TRC20": "TRON (TRC20)", "ERC20": "Ethereum (ERC20)", "BEP20": "BNB Smart Chain (BEP20)",
       "BEP2": "Binance Chain (BEP2)", "POLYGON": "Polygon", "ARBITRUM": "Arbitrum",
       "OPTIMISM": "Optimism", "AVAX": "Avalanche", "AVALANCHE": "Avalanche", "SOL": "Solana",
       "SPL": "Solana (SPL)", "NEAR": "NEAR", "TON": "TON", "LN": "Lightning Network", "OMNI": "Omni"}
STABLE = {"USDT", "USDC", "DAI", "TUSD", "USDP", "BUSD", "PYUSD", "USDR", "USDQ", "UUSD", "USDS"}


def _net(name):
    toks = set(re.split(r"[^A-Za-z0-9]+", name.upper()))
    for k, v in NET.items():
        if k in toks:
            return v
    return None


def about_currency(slug, info):
    """Уникальный справочный блок про валюту (снижает thin-content, добавляет ключевые слова)."""
    name, ticker, cat = info["name"], info["ticker"], info["category"]
    net = _net(name)
    links = ['<a href="/blog/slovar-terminov-obmena/">Словарь терминов</a>']
    if cat == "Криптовалюты":
        kind = "стейблкоин, стоимость которого привязана к доллару США" if ticker in STABLE else "криптовалюта"
        s = f"<b>{name}</b> ({ticker}) — {kind}."
        if net:
            s += f" Сеть выпуска — {net}; от выбора сети зависят комиссия за перевод и совместимость адресов."
        s += (f" На этой странице собраны справочные курсы обмена {ticker} на другие криптовалюты, банки, "
              f"платёжные системы и наличные — по данным мониторинга обменных пунктов BestChange.")
        links = (['<a href="/blog/usdt-seti-trc20-erc20-bep20/">Сети USDT</a>'] if ticker in STABLE else []) + \
                ['<a href="/blog/komissii-setey-tron-eth-bsc/">Комиссии сетей</a>',
                 '<a href="/blog/chto-takoe-aml-proverka/">AML-проверка</a>'] + links
    elif cat == "Bank accounts and cards":
        s = (f"<b>{name}</b> ({ticker}) — банковская карта/реквизиты. Обмен обычно проходит переводом на карту "
             f"или счёт. Ниже — справочные курсы направлений с участием {name}.")
    elif cat == "Online banking":
        s = (f"<b>{name}</b> ({ticker}) — банк/онлайн-банкинг. Перевод выполняется через приложение или "
             f"реквизиты банка. Ниже — справочные курсы направлений с {name}.")
    elif cat == "Money transfers":
        s = (f"<b>{name}</b> ({ticker}) — система денежных переводов. Ниже — справочные курсы направлений "
             f"с участием {name} по данным мониторинга BestChange.")
    elif cat == "Cash":
        s = (f"<b>{name}</b> ({ticker}) — наличные. Обмен наличными проводится в офисах обменных пунктов "
             f"(в поддерживаемых городах). Ниже — справочные курсы направлений с {name}.")
    elif cat == "Digital currencies":
        s = (f"<b>{name}</b> ({ticker}) — электронная платёжная система / цифровая валюта. Ниже — справочные "
             f"курсы направлений обмена {name}.")
    else:
        s = f"<b>{name}</b> ({ticker}). Ниже — справочные курсы направлений обмена."
    facts = (f'<ul class="facts"><li>Тикер: <b>{ticker}</b></li><li>Категория: {cat}</li>'
             + (f"<li>Сеть: {net}</li>" if net else "") + "</ul>")
    return (f'<h2 class="news">О валюте {name}</h2><p>{s}</p>{facts}'
            f'<p class="related">Полезное: {" · ".join(links)}</p>')


def load_articles():
    arts, d = [], os.path.join(ROOT, "articles")
    if not os.path.isdir(d):
        return arts
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        raw = open(os.path.join(d, fn), encoding="utf-8").read()
        meta, body = {}, raw
        if raw.startswith("---"):
            _, fm, body = raw.split("---", 2)
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
        meta["html"] = md_render(body.strip())
        if meta.get("slug"):
            arts.append(meta)
    arts.sort(key=lambda a: a.get("date", ""), reverse=True)
    return arts


ARTS = load_articles()

DISCLOSURE = ("RateScout — независимый информационный сервис мониторинга курсов. Мы не обменный пункт и не "
              "проводим операции. Ссылки ведут в сервис BestChange (мониторинг курсов обменных пунктов); "
              "по партнёрской программе мы можем получать вознаграждение. Это не реклама от имени BestChange.")


METRIKA = """<!-- Yandex.Metrika counter -->
<script type="text/javascript">
   (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
   m[i].l=1*new Date();
   for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
   k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
   (window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=111586112', 'ym');
   ym(111586112, 'init', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", accurateTrackBounce:true, trackLinks:true});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/111586112" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->"""

GTAG = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-PPN27D6JXS"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-PPN27D6JXS');
</script>
<!-- /Google tag -->"""


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
<meta property="og:image" content="{BASE_URL}/assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{S['name']} — мониторинг курсов обмена">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{BASE_URL}/assets/og-image.png">
<meta name="robots" content="index,follow">
<meta name="yandex-verification" content="4b39ef5046fa7e8a">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#111111">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/styles.css">
{extra}
{METRIKA}
{GTAG}
</head>
<body>
<div id="wrapper">"""


HEADER = f"""<div id="header">
  <h1 id="logotop"><a href="/"><span class="logo">[⇄]</span> {S['name']}<span class="tld">.ru</span></a></h1>
</div>
<div id="topnav" class="doscyan dosborder">
  <ul id="menu-top">
    <li><a href="/">Монитор</a></li>
    <li><a href="/blog/">Блог</a></li>
    <li><a href="/o-servise/">Что такое BestChange</a></li>
    <li><a href="/aml/">AML-проверка</a></li>
    <li><a href="/raskrytie/">Раскрытие</a></li>
  </ul>
</div>
<div id="search">
  <input id="q" type="search" placeholder="Поиск валюты: BTC, USDT, Сбербанк…" autocomplete="off" aria-label="Поиск валюты">
  <ul id="qres"></ul>
</div>"""


def footer():
    return f"""<div id="footer">
  <div class="disc">{DISCLOSURE}</div>
  <div class="links"><a href="/o-servise/">О сервисе</a> · <a href="/aml/">AML-проверка</a> ·
    <a href="/raskrytie/">Раскрытие и дисклеймеры</a> · <a href="/politika/">Политика конфиденциальности</a></div>
  <div class="fine">18+. Информация носит справочный характер, не является рекламой, офертой или финансовой рекомендацией. Курсы меняются.
    © {S['name']} {S['domain']}.<br>
    <span class="erid">Владелец сайта: {S.get('owner_status','')} {S.get('owner','')}, ИНН {S.get('owner_inn','')}.</span></div>
</div>
</div>
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
    return f"""<div class="conv dosblue dosborder" id="conv" data-from="{preset_from}">
  <h3>Калькулятор направления</h3>
  <label>Отдаю<select id="cFrom"></select></label>
  <button class="swap" id="cSwap" type="button">⇅ поменять</button>
  <label>Получаю<select id="cTo"></select></label>
  <a class="cta" id="cGo" href="https://www.bestchange.ru/?p={REF}" target="_blank" rel="nofollow noopener sponsored">Открыть направление →</a>
</div>"""


# ---------------- главная = монитор-каталог ----------------
def render_home():
    total = len(CUR)
    cat_html = ""
    for c in CATS:
        items = "".join(f'<li><a href="{cpage(slug)}">{info["name"]} <span>{info["ticker"]}</span></a></li>'
                        for slug, info in GROUPED.get(c, []))
        cat_html += f'<h2 class="news">{c} <span class="cnt">{len(GROUPED.get(c, []))}</span></h2><ul class="dlist">{items}</ul>'

    ld = jsonld({"@context": "https://schema.org", "@type": "WebSite", "name": S["name"],
                 "url": BASE_URL, "description": S["tagline"]})
    org = jsonld({"@context": "https://schema.org", "@type": "Organization", "name": S["name"],
                  "url": BASE_URL, "logo": f"{BASE_URL}/assets/og-image.png",
                  "description": S["tagline"]})
    title = f"{S['name']} — справочник курсов обмена: {total} валют"
    desc = (f"Справочник курсов обмена криптовалют и денег по {total} валютам на основе мониторинга обменных "
            "пунктов BestChange. Все направления, AML-проверка криптоадресов.")
    body = f"""{HEADER}
<div id="main">
  <div id="content">
    <pre class="ascii">  ____       _        ____                  _
 |  _ \\ __ _| |_ ___ / ___|  ___ ___  _   _| |_
 | |_) / _` | __/ _ \\\\___ \\ / __/ _ \\| | | | __|
 |  _ < (_| | ||  __/ ___) | (_| (_) | |_| | |_
 |_| \\_\\__,_|\\__\\___|____/ \\___\\___/ \\__,_|\\__|</pre>
    <div class="dosblue dosborder">
      Справочник курсов обмена криптовалют и валют. Данные собраны из мониторинга обменных пунктов
      <b>BestChange</b> по <b>{total}</b> валютам и приведены для ознакомления.
      <a href="/o-servise/">Что такое BestChange →</a></div>
    {('<h2 class="news">Популярные направления</h2><ul class="dlist">' + "".join(pair_link_li(p) for p in TOP[:16]) + "</ul>") if TOP else ""}
    <h2 class="news">Каталог валют <span class="cnt">{total}</span></h2>
    {cat_html}
  </div>
  <div id="sidebar">
    {converter_html()}
    <div class="sblock"><h3>Разделы</h3><ul>
      <li><a href="/o-servise/">Что такое BestChange</a></li>
      <li><a href="/aml/">AML-проверка адреса</a></li>
      <li><a href="/raskrytie/">Раскрытие и дисклеймеры</a></li>
    </ul></div>
  </div>
  <div class="clearboth"></div>
</div>
{org}
{footer()}"""
    write("index.html", head(title, desc, "/", ld) + body)


# ---------------- страница валюты = все направления ----------------
def render_currency(slug, info):
    name, ticker, cat = info["name"], info["ticker"], info["category"]
    canonical = cpage(slug)
    title = f"Обмен {name} ({ticker}) — курсы и все направления | {S['name']}"
    desc = (f"Обмен {name} ({ticker}): справочная сводка курсов в обменниках из мониторинга BestChange. "
            f"Все направления обмена {ticker} на криптовалюты, банки и наличные. AML-проверка адресов.")
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
            dir_blocks += f'<h2 class="news">{name} → {c}</h2><ul class="dlist">{rows}</ul>'

    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Монитор", "item": BASE_URL},
        {"@type": "ListItem", "position": 2, "name": f"{name} ({ticker})", "item": BASE_URL + canonical}]}
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f"Как обменять {name} ({ticker})?",
         "acceptedAnswer": {"@type": "Answer",
          "text": f"Через мониторинг BestChange: он показывает курсы {name} в обменниках. Выберите направление в списке."}},
        {"@type": "Question", "name": f"Как проверить чистоту {ticker}?",
         "acceptedAnswer": {"@type": "Answer",
          "text": "Обмен идёт в пунктах из мониторинга BestChange с рейтингом и резервами. Для крипто можно сделать AML-проверку адреса."}}]}
    body = f"""{HEADER}
<div id="main">
  <div id="content">
    <nav class="crumbs"><a href="/">Монитор</a> / {name} <span class="tk">{ticker}</span></nav>
    <h1>Обмен {name} <span class="tk">{ticker}</span></h1>
    <p>Справочная сводка курсов обмена <b>{name} ({ticker})</b> в обменниках из мониторинга
       <b>BestChange</b>. Выберите направление ниже; обмен совершается на сайте выбранного обменника.</p>
    {about_currency(slug, info)}
    {popular_block(slug)}
    <h2 class="news">Направления обмена {ticker}</h2>
    {dir_blocks}
    <h2 class="news">Как обменять {name}</h2>
    <ol class="steps">
      <li>Выберите направление обмена {ticker} выше.</li>
      <li>В BestChange сравните курс, резерв и рейтинг обменников.</li>
      <li>Для крипто — сделайте <a href="/aml/">AML-проверку адреса</a>.</li>
      <li>Перейдите в выбранный обменник и проведите операцию.</li>
    </ol>
    <h2 class="news">Частые вопросы</h2>
    <details><summary>Как обменять {name} ({ticker})?</summary>
      <p>Через мониторинг BestChange — он показывает курсы обменных пунктов.</p></details>
    <details><summary>Как проверить чистоту {ticker}?</summary>
      <p>Обмен идёт в пунктах из мониторинга BestChange. Для крипто можно сделать AML-проверку адреса.</p></details>
  </div>
  <div id="sidebar">
    {converter_html(slug)}
    <div class="sblock"><h3>Разделы</h3><ul>
      <li><a href="/">Все валюты</a></li>
      <li><a href="/aml/">AML-проверка адреса</a></li>
      <li><a href="/o-servise/">Что такое BestChange</a></li>
    </ul></div>
  </div>
  <div class="clearboth"></div>
</div>
{jsonld(crumbs)}{jsonld(faq)}
{footer()}"""
    write(f"valuta/{slug}/index.html", head(title, desc, canonical) + body)


def render_pair(f, t):
    fi, ti = CUR.get(f), CUR.get(t)
    if not fi or not ti:
        return
    fN, fT, tN, tT = fi["name"], fi["ticker"], ti["name"], ti["ticker"]
    canonical = pair_url(f, t)
    r = rate_of(f, t)
    if r:
        rate_line = (f'<div class="big">{fmt_rate(r["rate"])} <span>{tT} за 1 {fT}</span></div>'
                     f'<div class="sub">по данным {r["count"]} обменников · суммарный резерв {fmt_rate(r["reserve"])} {tT}</div>')
        rate_meta = f"курс {fmt_rate(r['rate'])} {tT} за 1 {fT}, {r['count']} обменников, "
    else:
        rate_line = '<div class="sub">курс уточняется в мониторинге</div>'
        rate_meta = ""
    title = f"Обмен {fN} на {tN}" + (f" — курс {fmt_rate(r['rate'])} {tT}/{fT}" if r else "") + f" | {S['name']}"
    desc = (f"Обмен {fN} ({fT}) на {tN} ({tT}): {rate_meta}список обменников из мониторинга BestChange, "
            f"как обменять, AML-проверка адреса.")
    rev = f'<a href="{pair_url(t, f)}">Обратный обмен: {tN} → {fN}</a> · ' if (t, f) in TOP_SET else ""
    faq = jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f"Какой курс обмена {fN} на {tN}?", "acceptedAnswer": {"@type": "Answer",
         "text": (f"Лучшее значение — {fmt_rate(r['rate'])} {tT} за 1 {fT} среди {r['count']} обменников (мониторинг BestChange), значение справочное и меняется." if r else "Курс уточняется в мониторинге BestChange.")}},
        {"@type": "Question", "name": f"Как обменять {fT} на {tT}?", "acceptedAnswer": {"@type": "Answer",
         "text": "Откройте направление в BestChange, сравните курс и резерв обменников, выберите пункт и проведите операцию на его сайте. Для крипто рекомендуется AML-проверка адреса."}}]})
    crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Монитор", "item": BASE_URL},
        {"@type": "ListItem", "position": 2, "name": f"{fT} → {tT}", "item": BASE_URL + canonical}]})
    aml = '<li>Для криптовалюты — сделайте <a href="/aml/">AML-проверку адреса</a>.</li>' if fi["category"] == "Криптовалюты" else ""
    body = f"""{HEADER}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="/">Монитор</a> / {fT} → {tT}</nav>
    <h1>Обмен {fN} <span class="tk">{fT}</span> на {tN} <span class="tk">{tT}</span></h1>
    <div class="rate-box">
      {rate_line}
      <a class="cta" href="{bc_link(f, t)}" target="_blank" rel="nofollow noopener sponsored">Открыть направление в BestChange →</a>
    </div>
    <h2 class="news">Как обменять {fT} на {tT}</h2>
    <ol class="steps">
      <li>Откройте список обменников BestChange по направлению {fN} → {tN}.</li>
      <li>Сравните курс, резерв и рейтинг обменников.</li>
      {aml}
      <li>Проведите обмен на сайте выбранного обменника.</li>
    </ol>
    <p class="related">{rev}<a href="{cpage(f)}">О валюте {fN}</a> · <a href="{cpage(t)}">О валюте {tN}</a> ·
       <a href="/blog/slovar-terminov-obmena/">Словарь терминов</a></p>
    <h2 class="news">Частые вопросы</h2>
    <details><summary>Какой курс обмена {fN} на {tN}?</summary>
      <p>{('Лучшее значение — <b>'+fmt_rate(r['rate'])+' '+tT+'</b> за 1 '+fT+' среди '+str(r['count'])+' обменников. Справочно, меняется.') if r else 'Курс уточняется в мониторинге BestChange.'}</p></details>
    <details><summary>Безопасно ли это?</summary>
      <p>Обмен идёт в пунктах из мониторинга BestChange с рейтингом и резервами. Для крипто рекомендуется AML-проверка адреса.</p></details>
  </div>
</div>
{faq}{crumbs}
{footer()}"""
    write(f"obmen/{f}-{t}/index.html", head(title, desc, canonical) + body)


def render_page(slug, title, desc, body_html):
    canonical = f"/{slug}/"
    body = f"""{HEADER}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="/">Монитор</a> / {title}</nav>
    {body_html}
  </div>
</div>
{footer()}"""
    write(f"{slug}/index.html", head(f"{title} | {S['name']}", desc, canonical) + body)


def render_blog():
    if not ARTS:
        return
    cards = "".join(
        f'<li><a href="/blog/{a["slug"]}/">{a["title"]}</a>'
        f'<div class="apreview">{a.get("description","")}</div>'
        f'<div class="adate">{a.get("date","")}</div></li>' for a in ARTS)
    ld = jsonld({"@context": "https://schema.org", "@type": "Blog", "name": f"Блог {S['name']}",
                 "url": f"{BASE_URL}/blog/"})
    title = f"Блог — гайды по обмену криптовалют и валют | {S['name']}"
    desc = "Статьи и гайды: сети USDT, комиссии, AML-проверка, словарь терминов обмена криптовалют и валют."
    body = f"""{HEADER}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="/">Монитор</a> / Блог</nav>
    <h1>Блог</h1>
    <p>Справочные материалы и гайды об обмене криптовалют и валют.</p>
    <ul class="bloglist">{cards}</ul>
  </div>
</div>
{ld}
{footer()}"""
    write("blog/index.html", head(title, desc, "/blog/", ld) + body)


def render_article(a):
    slug, canonical = a["slug"], f"/blog/{a['slug']}/"
    title = f"{a['title']} | {S['name']}"
    desc = a.get("description", "")
    art_ld = jsonld({"@context": "https://schema.org", "@type": "Article", "headline": a["title"],
                     "description": desc, "datePublished": a.get("date", ""),
                     "author": {"@type": "Organization", "name": S["name"]},
                     "publisher": {"@type": "Organization", "name": S["name"]},
                     "mainEntityOfPage": BASE_URL + canonical})
    crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Блог", "item": f"{BASE_URL}/blog/"},
        {"@type": "ListItem", "position": 2, "name": a["title"], "item": BASE_URL + canonical}]})
    body = f"""{HEADER}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="/">Монитор</a> / <a href="/blog/">Блог</a> / {a['title']}</nav>
    <article class="post">
      <div class="adate">{a.get('date','')}</div>
      {a['html']}
    </article>
    <p><a href="/blog/">← Все статьи</a></p>
  </div>
</div>
{art_ld}{crumbs}
{footer()}"""
    write(f"blog/{slug}/index.html", head(title, desc, canonical) + body)


def compliance_pages():
    render_page("o-servise", "Что такое BestChange",
                "BestChange — мониторинг обменных пунктов: справочная информация о курсах обмена криптовалют и валют.",
                """<h1>Что такое BestChange</h1>
<p><b>BestChange</b> — мониторинг обменников электронных валют и криптовалют. Сервис собирает курсы, резервы и
   комиссии десятков обменных пунктов и показывает их актуальные значения в одном месте — не нужно обходить
   сайты обменников вручную.</p>
<h2>Как это работает</h2>
<ol class="steps"><li>Выбираете направление обмена.</li><li>BestChange показывает обменники, отсортированные по курсу.</li>
<li>Смотрите курс, рейтинг, резерв и отзывы, выбираете подходящий пункт.</li><li>Переходите и проводите операцию на сайте обменника.</li></ol>
<h2>Про мониторинг</h2>
<p>В мониторинг попадают обменники с рейтингом и резервами. RateScout — независимый информационный сервис,
   который помогает сориентироваться в данных и ведёт в BestChange к списку обменников. Сами обмен не проводим.</p>""")
    render_page("aml", "AML-проверка криптоадреса — зачем и как",
                "AML-проверка (Anti-Money Laundering): как проверить криптоадрес на связь с мошенничеством и санкциями перед обменом.",
                f"""<h1>AML-проверка криптоадреса</h1>
<p><b>AML</b> (Anti-Money Laundering) — проверка криптоадреса или транзакции на связь с мошенничеством, даркнетом,
   украденными средствами и санкциями. Снижает риск получить «грязные» монеты и блокировку на бирже.</p>
<h2>Когда делать</h2><ul><li>перед приёмом крупной суммы в крипте;</li><li>перед обменом крипты на рубли/наличные;</li>
<li>если контрагент незнаком.</li></ul>
<h2>Как проверить</h2>
<p>AML-проверка выполняется через специализированные сервисы анализа блокчейна: вы указываете адрес и получаете
   отчёт о рисках (доля связи с подозрительными источниками). Инструмент анализа адреса есть и у сервиса
   BestChange (раздел «Проверка адреса»), и у ряда других сервисов.</p>
<p>Справочная информация о том, как это работает —
   в <a href="https://www.bestchange.ru/wiki/amlfaq.html" target="_blank" rel="nofollow noopener">материалах BestChange по AML</a>.</p>""")
    render_page("raskrytie", "Раскрытие информации и дисклеймеры",
                "Партнёрское раскрытие и правовая информация RateScout (РФ и США).",
                f"""<h1>Раскрытие информации и дисклеймеры</h1>
<h2>Партнёрское раскрытие</h2><p>{DISCLOSURE}</p>
<p><i>English:</i> RateScout is an independent rate-monitoring service. Links lead to BestChange; we may earn a
   commission (FTC disclosure). Not advertising on behalf of BestChange.</p>
<h2>Дисклеймер</h2><p>Информация справочная, не является финансовой/инвестиционной/юридической рекомендацией.
   Курсы меняются. Решение об обмене — самостоятельно и на свой риск. 18+.</p>
<h2>Соответствие законодательству</h2>
<ul><li><b>РФ:</b> сайт — информационный ресурс (справочная информация о курсах и обменниках), не ведёт активного
   продвижения; при таком характере контента маркировка рекламы (ERID/ОРД) не требуется. Персональные данные —
   по 152-ФЗ (см. Политику). Если формат сменится на рекламный — материалы будут промаркированы.</li>
<li><b>США:</b> affiliate-раскрытие по FTC; сервис недоступен под санкциями (OFAC).</li></ul>
<h2>Сведения о владельце сайта</h2>
<p>{S.get('owner_status','')} <b>{S.get('owner','')}</b>, ИНН {S.get('owner_inn','')}. Сайт {S['domain']} —
   информационный сервис мониторинга курсов; владелец не является обменным пунктом и не проводит операции.
   Контакт: {S.get('owner_email','')}.</p>""")
    render_page("politika", "Политика конфиденциальности",
                f"Политика обработки данных и использования cookie на сайте {S['domain']} (152-ФЗ).",
                f"""<h1>Политика конфиденциальности</h1>
<p>Настоящая Политика описывает порядок обработки данных посетителей сайта {S['domain']}. Оператор:
   {S.get('owner_status','')} {S.get('owner','')}, ИНН {S.get('owner_inn','')} (далее — Оператор).
   Используя сайт, посетитель принимает условия настоящей Политики.</p>
<h2>1. Общие сведения</h2>
<p>{S['domain']} — информационный сайт-справочник курсов обмена. Регистрация и создание аккаунтов не
   предусмотрены, платежи и обмен на сайте не проводятся. Оператор не запрашивает у посетителей персональные
   данные (ФИО, телефон, паспортные и платёжные данные и т.п.).</p>
<h2>2. Какие данные обрабатываются</h2>
<ul><li>технические данные, автоматически передаваемые браузером: IP-адрес, тип/версия браузера и ОС,
   страна/регион, адрес страницы перехода (referer), дата и время посещения;</li>
<li>обезличенные данные веб-аналитики (просмотры страниц, источники переходов, поведение на сайте);</li>
<li>файлы cookie (см. раздел 5).</li></ul>
<p>Данные обрабатываются в обезличенном виде и используются в статистических целях.</p>
<h2>3. Цели обработки</h2>
<ul><li>обеспечение работы и безопасности сайта;</li>
<li>анализ посещаемости и улучшение содержимого;</li>
<li>формирование обезличенной статистики.</li></ul>
<h2>4. Правовые основания</h2>
<p>Обработка осуществляется в соответствии с Федеральным законом от 27.07.2006 № 152-ФЗ «О персональных
   данных», в том числе для достижения законных интересов Оператора по функционированию сайта, а также на
   основании согласия посетителя, выражаемого при использовании сайта.</p>
<h2>5. Cookie и веб-аналитика</h2>
<p>Сайт использует cookie для корректной работы и обезличенной аналитики. Для сбора статистики применяются
   сторонние сервисы <b>Яндекс.Метрика</b> и <b>Google Analytics</b>, обрабатывающие обезличенные данные на
   своих серверах согласно собственным политикам конфиденциальности.</p>
<p>В составе Яндекс.Метрики используется технология <b>Вебвизор</b>: она в обезличенном виде записывает действия
   посетителя на странице (перемещения курсора, клики, прокрутку, взаимодействие с элементами) для анализа
   удобства сайта. Данные Вебвизора хранятся на серверах Яндекса. Записи не используются для идентификации
   личности; поля ввода с потенциально чувствительными данными Вебвизором по умолчанию маскируются.</p>
<p>Cookie и веб-аналитику можно отключить в настройках браузера (в т.ч. режимом инкогнито или блокировщиками),
   а также через инструменты отказа Яндекс.Метрики и Google Analytics — часть функций сайта при этом может
   работать некорректно.</p>
<h2>6. Передача третьим лицам</h2>
<p>Оператор не продаёт данные и не передаёт их третьим лицам, кроме сервисов веб-аналитики (в обезличенном
   виде) и случаев, предусмотренных законодательством РФ.</p>
<h2>7. Сроки хранения</h2>
<p>Обезличенные статистические данные хранятся не дольше, чем необходимо для указанных целей, и/или в сроки,
   установленные используемыми сервисами аналитики.</p>
<h2>8. Права посетителя</h2>
<p>Посетитель вправе запросить сведения об обработке своих данных, их уточнение или удаление, отозвать
   согласие, направив обращение на {S.get('owner_email','')}, а также самостоятельно очистить cookie средствами
   браузера.</p>
<h2>9. Изменения Политики</h2>
<p>Оператор вправе изменять настоящую Политику; актуальная редакция размещается на этой странице.</p>
<h2>10. Контакты</h2>
<p>Оператор: {S.get('owner_status','')} {S.get('owner','')}, ИНН {S.get('owner_inn','')}.
   По вопросам обработки данных: {S.get('owner_email','')}.</p>""")


def catalog_js():
    cur = {slug: {"n": i["name"], "t": i["ticker"], "c": i["category"]} for slug, i in CUR.items()}
    js = "window.__CATALOG__=" + json.dumps({"order": CATS, "cur": cur}, ensure_ascii=False) + \
         ";window.__REF__=" + json.dumps(REF) + ";"
    write("assets/catalog.js", js)


def static_files():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def u_entry(loc, freq, pri):
        return (f"  <url><loc>{BASE_URL}{loc}</loc><lastmod>{today}</lastmod>"
                f"<changefreq>{freq}</changefreq><priority>{pri}</priority></url>")

    items = [u_entry("/", "hourly", "1.0")]
    items += [u_entry(cpage(s), "hourly", "0.6") for s in CUR]       # страницы валют — курсы меняются
    items += [u_entry(pair_url(p["from"], p["to"]), "hourly", "0.8") for p in TOP]   # лендинги топ-пар
    if ARTS:                                                          # блог
        items.append(u_entry("/blog/", "weekly", "0.7"))
        items += [u_entry(f"/blog/{a['slug']}/", "monthly", "0.6") for a in ARTS]
    items += [u_entry(u, "monthly", "0.4") for u in ("/o-servise/", "/aml/", "/raskrytie/", "/politika/")]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(items) + "\n</urlset>")
    write("robots.txt",
          "User-agent: *\n"
          "Allow: /\n"
          f"Sitemap: {BASE_URL}/sitemap.xml\n")
    write("CNAME", S["domain"] + "\n")
    write("manifest.webmanifest", json.dumps({
        "name": S["name"] + " — мониторинг курсов обмена", "short_name": S["name"],
        "description": S["tagline"], "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#111111", "theme_color": "#111111", "lang": "ru",
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
    render_blog()
    for a in ARTS:
        render_article(a)
    for p in TOP:
        render_pair(p["from"], p["to"])
    static_files()
    copy_assets()
    catalog_js()   # ПОСЛЕ copy_assets: иначе copytree затрёт dist/assets
    print(f"✅ dist/: главная + {len(CUR)} страниц валют + 4 комплаенс + {1+len(ARTS)} блог + {len(TOP)} пар + sitemap/robots/manifest/sw/CNAME")


if __name__ == "__main__":
    main()
