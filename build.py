#!/usr/bin/env python3
"""Генератор статического SEO-сайта RateScout (GitHub Pages) — RU + EN (i18n).

RU в корне (/), EN в /en/. hreflang между версиями, переключатель языка.
Данные (курсы/каталог/пары) общие; локализуются только тексты и внутренние ссылки.
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
except ImportError:
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
CUR = CAT["currencies"]
CATS = CAT["categories"]
S = SITE
BASE_URL = f"https://{S['domain']}"
REF = S["ref"]

LANGS = ["ru", "en"]
PREF = {"ru": "", "en": "/en"}
LOCALE = {"ru": "ru", "en": "en"}

# перевод категорий для EN
CAT_EN = {"Криптовалюты": "Cryptocurrencies", "Digital currencies": "Digital currencies",
          "Bank accounts and cards": "Bank accounts and cards", "Online banking": "Online banking",
          "Money transfers": "Money transfers", "Cash": "Cash", "Прочее": "Other"}


def cat_name(c, lang):
    return CAT_EN.get(c, c) if lang == "en" else c


def bc_link(frm, to):
    f, t = CUR.get(frm, {}), CUR.get(to, {})
    if f.get("num") or t.get("num"):
        return f"https://www.bestchange.ru/index.php?mt=rates&from={f.get('id')}&to={t.get('id')}&p={REF}"
    return f"https://www.bestchange.ru/{frm}-to-{to}.html?p={REF}"


def cpage(lang, slug):
    return f"{PREF[lang]}/valuta/{slug}/"


def pair_url(lang, f, t):
    return f"{PREF[lang]}/obmen/{f}-{t}/"


def by_category():
    g = {c: [] for c in CATS}
    for slug, info in CUR.items():
        g.setdefault(info["category"], []).append((slug, info))
    for c in g:
        g[c].sort(key=lambda x: x[1]["name"])
    return g


GROUPED = by_category()

RATES = {}
_rp = os.path.join(ROOT, "rates.json")
if os.path.exists(_rp):
    try:
        RATES = json.load(open(_rp, encoding="utf-8")).get("pairs", {})
    except (ValueError, OSError):
        RATES = {}


def rate_of(frm, to):
    return RATES.get(f"{frm}>{to}")


TOP = []
_tp = os.path.join(ROOT, "top.json")
if os.path.exists(_tp):
    try:
        TOP = [p for p in json.load(open(_tp, encoding="utf-8")).get("pairs", [])
               if p.get("from") in CUR and p.get("to") in CUR]
    except (ValueError, OSError):
        TOP = []
TOP_SET = {(p["from"], p["to"]) for p in TOP}


def fmt_rate(s):
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
    return (f"{v:.12f}".rstrip("0").rstrip(".")) or "0"


# ---------------- переводы UI ----------------
TR = {
    "ru": {
        "nav_monitor": "Монитор", "nav_blog": "Блог", "nav_about": "Что такое BestChange",
        "nav_aml": "AML-проверка", "nav_disc": "Раскрытие",
        "search_ph": "Поиск: BTC, USDT, Sberbank…", "search_aria": "Поиск валюты",
        "monitor": "Монитор", "sections": "Разделы", "all_cur": "Все валюты",
        "catalog": "Каталог валют", "total": "всего", "popular": "Популярные направления",
        "about_cur": "О валюте", "directions": "Направления обмена", "how_to": "Как обменять",
        "faq": "Частые вопросы", "useful": "Полезное", "open_dir": "Открыть направление →",
        "find_rate": "Открыть направление →", "calc": "Калькулятор направления",
        "give": "Отдаю", "get": "Получаю", "swap": "⇅ поменять",
        "ticker": "Тикер", "category": "Категория", "network": "Сеть",
        "glossary": "Словарь терминов", "usdt_nets": "Сети USDT", "fees": "Комиссии сетей", "aml_link": "AML-проверка",
        "open_bc": "Открыть направление в BestChange →",
        "blog_search_ph": "Поиск по статьям…", "blog_noresults": "Ничего не найдено. Попробуйте другой запрос.",
    },
    "en": {
        "nav_monitor": "Monitor", "nav_blog": "Blog", "nav_about": "What is BestChange",
        "nav_aml": "AML check", "nav_disc": "Disclosure",
        "search_ph": "Search currency: BTC, USDT, Sberbank…", "search_aria": "Currency search",
        "monitor": "Monitor", "sections": "Sections", "all_cur": "All currencies",
        "catalog": "Currency catalog", "total": "total", "popular": "Popular directions",
        "about_cur": "About", "directions": "Exchange directions for", "how_to": "How to exchange",
        "faq": "FAQ", "useful": "Useful", "open_dir": "Open direction →",
        "find_rate": "Open direction →", "calc": "Direction calculator",
        "give": "Send", "get": "Receive", "swap": "⇅ swap",
        "ticker": "Ticker", "category": "Category", "network": "Network",
        "glossary": "Glossary", "usdt_nets": "USDT networks", "fees": "Network fees", "aml_link": "AML check",
        "open_bc": "Open direction on BestChange →",
        "blog_search_ph": "Search articles…", "blog_noresults": "Nothing found. Try a different query.",
    },
}


def tr(lang, key):
    return TR[lang][key]


# ---------------- вывод ----------------
def out_path(lang, path):
    """path вида '/valuta/x/' → файл в dist с учётом префикса языка."""
    p = (PREF[lang] + path).strip("/")
    return (p + "/index.html") if p else "index.html"


def write(lang, path, html):
    full = os.path.join(DIST, out_path(lang, path))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8").write(html)


def jsonld(o):
    return f'<script type="application/ld+json">{json.dumps(o, ensure_ascii=False)}</script>'


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


# Ранний выбор языка: если пользователь НЕ выбирал вручную (нет rs_lang) — редирект
# на версию под язык браузера (ru → корень, иначе → /en/). Ручной выбор (клик по .langsw)
# сохраняется в localStorage и отключает автоопределение. Ботов не трогаем (SEO).
LANGREDIR = """<script>(function(){try{
var ua=navigator.userAgent||"";if(/bot|crawl|spider|slurp|bing|yandex|google/i.test(ua))return;
var p=location.pathname,isEn=p==="/en"||p.indexOf("/en/")===0,cur=isEn?"en":"ru";
var s=localStorage.getItem("rs_lang"),want;
if(s==="ru"||s==="en"){want=s;}else{var n=(navigator.languages&&navigator.languages[0])||navigator.language||"en";want=/^ru\\b/i.test(n)?"ru":"en";}
if(want===cur)return;
var t=want==="en"?("/en"+(p==="/"?"/":p)):p.replace(/^\\/en(\\/|$)/,"/");
location.replace(t+location.search+location.hash);
}catch(e){}})();</script>"""


def hreflangs(path):
    tags = []
    for lg in LANGS:
        tags.append(f'<link rel="alternate" hreflang="{LOCALE[lg]}" href="{BASE_URL}{PREF[lg]}{path}">')
    tags.append(f'<link rel="alternate" hreflang="x-default" href="{BASE_URL}{path}">')
    return "\n".join(tags)


def head(lang, title, desc, path, extra=""):
    canonical = f"{BASE_URL}{PREF[lang]}{path}"
    return f"""<!doctype html>
<html lang="{LOCALE[lang]}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{LANGREDIR}
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
{hreflangs(path)}
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="{S['name']}">
<meta property="og:image" content="{BASE_URL}/assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
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


def header(lang, path):
    other = "en" if lang == "ru" else "ru"
    switch = f'<a class="langsw" data-lang="{other}" href="{PREF[other]}{path}">{"EN" if other == "en" else "RU"}</a>'
    return f"""<div id="header">
  <h1 id="logotop"><a href="{PREF[lang]}/"><span class="logo">[⇄]</span> {S['name']}<span class="tld">.ru</span></a></h1>
  {switch}
</div>
<div id="topnav" class="doscyan dosborder">
  <ul id="menu-top">
    <li><a href="{PREF[lang]}/">{tr(lang,'nav_monitor')}</a></li>
    <li><a href="{PREF[lang]}/blog/">{tr(lang,'nav_blog')}</a></li>
    <li><a href="{PREF[lang]}/o-servise/">{tr(lang,'nav_about')}</a></li>
    <li><a href="{PREF[lang]}/aml/">{tr(lang,'nav_aml')}</a></li>
    <li><a href="{PREF[lang]}/raskrytie/">{tr(lang,'nav_disc')}</a></li>
  </ul>
</div>"""


def search_box(lang):
    return f"""<div class="conv dosblue dosborder" id="search">
  <h3>{tr(lang,'search_aria')}</h3>
  <input id="q" type="search" data-prefix="{PREF[lang]}" placeholder="{tr(lang,'search_ph')}" autocomplete="off" aria-label="{tr(lang,'search_aria')}">
  <ul id="qres"></ul>
</div>"""


def footer(lang):
    if lang == "ru":
        disc = ("RateScout — независимый информационный сервис мониторинга курсов. Мы не обменный пункт и не "
                "проводим операции. Ссылки ведут в сервис BestChange (мониторинг курсов обменных пунктов); "
                "по партнёрской программе мы можем получать вознаграждение. Это не реклама от имени BestChange.")
        links = (f'<a href="/o-servise/">О сервисе</a> · <a href="/aml/">AML-проверка</a> · '
                 f'<a href="/raskrytie/">Раскрытие и дисклеймеры</a> · <a href="/politika/">Политика конфиденциальности</a>')
        fine = ("18+. Информация носит справочный характер, не является рекламой, офертой или финансовой "
                f"рекомендацией. Курсы меняются. © {S['name']} {S['domain']}.<br>"
                f"<span class=\"erid\">Владелец сайта: {S.get('owner_status','')} {S.get('owner','')}, ИНН {S.get('owner_inn','')}.</span>")
    else:
        disc = ("RateScout is an independent rate-monitoring service. We are not an exchange office and do not "
                "process transactions. Links lead to BestChange (a monitor of exchange office rates); through the "
                "affiliate program we may earn a commission. This is not advertising on behalf of BestChange.")
        links = (f'<a href="/en/o-servise/">About</a> · <a href="/en/aml/">AML check</a> · '
                 f'<a href="/en/raskrytie/">Disclosure</a> · <a href="/en/politika/">Privacy policy</a>')
        fine = ("18+. Information is for reference only and is not advertising, an offer or financial advice. "
                f"Rates change. © {S['name']} {S['domain']}.<br>"
                f"<span class=\"erid\">Site owner: {S.get('owner','')} (self-employed, RU tax ID {S.get('owner_inn','')}).</span>")
    return f"""<div id="footer">
  <div class="disc">{disc}</div>
  <div class="links">{links}</div>
  <div class="fine">{fine}</div>
</div>
</div>
<script src="/assets/catalog.js"></script>
<script src="/assets/app.js"></script>
</body></html>"""


def converter_html(lang, preset_from=""):
    return f"""<div class="conv dosblue dosborder" id="conv" data-from="{preset_from}" data-prefix="{PREF[lang]}" data-open="{'Open' if lang=='en' else 'Открыть'}">
  <h3>{tr(lang,'calc')}</h3>
  <label>{tr(lang,'give')}<select id="cFrom"></select></label>
  <button class="swap" id="cSwap" type="button">{tr(lang,'swap')}</button>
  <label>{tr(lang,'get')}<select id="cTo"></select></label>
  <a class="cta" id="cGo" href="https://www.bestchange.ru/?p={REF}" target="_blank" rel="nofollow noopener sponsored">{tr(lang,'find_rate')}</a>
</div>"""


# ---------------- «О валюте» ----------------
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


def about_currency(slug, info, lang):
    name, ticker, cat = info["name"], info["ticker"], info["category"]
    net = _net(name)
    if lang == "ru":
        links = ['<a href="/blog/slovar-terminov-obmena/">Словарь терминов</a>']
        if cat == "Криптовалюты":
            kind = "стейблкоин, привязанный к доллару США" if ticker in STABLE else "криптовалюта"
            s = f"<b>{name}</b> ({ticker}) — {kind}."
            if net:
                s += f" Сеть выпуска — {net}; от выбора сети зависят комиссия и совместимость адресов."
            s += (f" Здесь собраны справочные курсы обмена {ticker} на другие криптовалюты, банки, платёжные "
                  f"системы и наличные — по данным мониторинга BestChange.")
            links = (['<a href="/blog/usdt-seti-trc20-erc20-bep20/">Сети USDT</a>'] if ticker in STABLE else []) + \
                    ['<a href="/blog/komissii-setey-tron-eth-bsc/">Комиссии сетей</a>',
                     '<a href="/blog/chto-takoe-aml-proverka/">AML-проверка</a>'] + links
        elif cat == "Bank accounts and cards":
            s = f"<b>{name}</b> ({ticker}) — банковская карта/реквизиты. Ниже — справочные курсы направлений с {name}."
        elif cat == "Online banking":
            s = f"<b>{name}</b> ({ticker}) — банк/онлайн-банкинг. Ниже — справочные курсы направлений с {name}."
        elif cat == "Money transfers":
            s = f"<b>{name}</b> ({ticker}) — система денежных переводов. Ниже — справочные курсы направлений."
        elif cat == "Cash":
            s = f"<b>{name}</b> ({ticker}) — наличные. Ниже — справочные курсы направлений с {name}."
        elif cat == "Digital currencies":
            s = f"<b>{name}</b> ({ticker}) — электронная платёжная система. Ниже — справочные курсы направлений."
        else:
            s = f"<b>{name}</b> ({ticker}). Ниже — справочные курсы направлений."
        facts = (f'<ul class="facts"><li>{tr(lang,"ticker")}: <b>{ticker}</b></li><li>{tr(lang,"category")}: {cat_name(cat,lang)}</li>'
                 + (f"<li>{tr(lang,'network')}: {net}</li>" if net else "") + "</ul>")
        used = "Полезное"
    else:
        links = ['<a href="/en/blog/slovar-terminov-obmena/">Glossary</a>']
        if cat == "Криптовалюты":
            kind = "a USD-pegged stablecoin" if ticker in STABLE else "a cryptocurrency"
            s = f"<b>{name}</b> ({ticker}) is {kind}."
            if net:
                s += f" Issued on {net}; the network affects transfer fees and address compatibility."
            s += (f" Below are reference exchange rates for {ticker} to other crypto, banks, payment systems and "
                  f"cash — based on BestChange monitoring data.")
            links = (['<a href="/en/blog/usdt-seti-trc20-erc20-bep20/">USDT networks</a>'] if ticker in STABLE else []) + \
                    ['<a href="/en/blog/komissii-setey-tron-eth-bsc/">Network fees</a>',
                     '<a href="/en/blog/chto-takoe-aml-proverka/">AML check</a>'] + links
        elif cat == "Bank accounts and cards":
            s = f"<b>{name}</b> ({ticker}) — a bank card / details. Reference rates for directions with {name} below."
        elif cat == "Online banking":
            s = f"<b>{name}</b> ({ticker}) — a bank / online banking. Reference rates for directions with {name} below."
        elif cat == "Money transfers":
            s = f"<b>{name}</b> ({ticker}) — a money transfer system. Reference rates for directions below."
        elif cat == "Cash":
            s = f"<b>{name}</b> ({ticker}) — cash. Reference rates for directions with {name} below."
        elif cat == "Digital currencies":
            s = f"<b>{name}</b> ({ticker}) — an electronic payment system. Reference rates for directions below."
        else:
            s = f"<b>{name}</b> ({ticker}). Reference rates for directions below."
        facts = (f'<ul class="facts"><li>{tr(lang,"ticker")}: <b>{ticker}</b></li><li>{tr(lang,"category")}: {cat_name(cat,lang)}</li>'
                 + (f"<li>{tr(lang,'network')}: {net}</li>" if net else "") + "</ul>")
        used = "Useful"
    return (f'<h2 class="news">{tr(lang,"about_cur")} {name}</h2><p>{s}</p>{facts}'
            f'<p class="related">{used}: {" · ".join(links)}</p>')


# ---------------- статьи/блог ----------------
def load_articles(lang):
    arts, d = [], os.path.join(ROOT, "articles", "en") if lang == "en" else os.path.join(ROOT, "articles")
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


ARTS = {lg: load_articles(lg) for lg in LANGS}


def popular_involving(slug, n=8):
    return [p for p in TOP if p["from"] == slug or p["to"] == slug][:n]


def pair_link_li(p, lang):
    return (f'<li><a href="{pair_url(lang, p["from"], p["to"])}">'
            f'{CUR[p["from"]]["name"]} <span>{CUR[p["from"]]["ticker"]}</span> → '
            f'{CUR[p["to"]]["name"]} <span>{CUR[p["to"]]["ticker"]}</span></a></li>')


def popular_block(slug, lang):
    pops = popular_involving(slug)
    if not pops:
        return ""
    return f'<h2 class="news">{tr(lang,"popular")}</h2><ul class="dlist">{"".join(pair_link_li(p, lang) for p in pops)}</ul>'


# ---------------- страницы ----------------
def render_home(lang):
    total = len(CUR)
    cat_html = ""
    for c in CATS:
        items = "".join(f'<li><a href="{cpage(lang, slug)}">{info["name"]} <span>{info["ticker"]}</span></a></li>'
                        for slug, info in GROUPED.get(c, []))
        cat_html += f'<h2 class="news">{cat_name(c, lang)} <span class="cnt">{len(GROUPED.get(c, []))}</span></h2><ul class="dlist">{items}</ul>'
    ld = jsonld({"@context": "https://schema.org", "@type": "WebSite", "name": S["name"],
                 "url": BASE_URL + PREF[lang] + "/", "inLanguage": LOCALE[lang], "description": S["tagline"]})
    org = jsonld({"@context": "https://schema.org", "@type": "Organization", "name": S["name"],
                  "url": BASE_URL, "logo": f"{BASE_URL}/assets/og-image.png"})
    if lang == "ru":
        title = f"{S['name']} — справочник курсов обмена: {total} валют"
        desc = (f"Справочник курсов обмена криптовалют и денег по {total} валютам на основе мониторинга обменных "
                "пунктов BestChange. Все направления, AML-проверка криптоадресов.")
        intro = (f"Справочник курсов обмена криптовалют и валют. Данные собраны из мониторинга обменных пунктов "
                 f"<b>BestChange</b> по <b>{total}</b> валютам и приведены для ознакомления. "
                 f'<a href="/o-servise/">Что такое BestChange →</a>')
    else:
        title = f"{S['name']} — currency exchange rates directory: {total} currencies"
        desc = (f"Directory of crypto and money exchange rates across {total} currencies, based on BestChange "
                "exchange monitoring. All directions, crypto address AML check.")
        intro = (f"A directory of crypto and currency exchange rates. Data is collected from the <b>BestChange</b> "
                 f"exchange monitor across <b>{total}</b> currencies and provided for reference. "
                 f'<a href="/en/o-servise/">What is BestChange →</a>')
    pop = (f'<h2 class="news">{tr(lang,"popular")}</h2><ul class="dlist">'
           + "".join(pair_link_li(p, lang) for p in TOP[:16]) + "</ul>") if TOP else ""
    body = f"""{header(lang, "/")}
<div id="main">
  <div id="content">
    <pre class="ascii">  ____       _        ____                  _
 |  _ \\ __ _| |_ ___ / ___|  ___ ___  _   _| |_
 | |_) / _` | __/ _ \\\\___ \\ / __/ _ \\| | | | __|
 |  _ < (_| | ||  __/ ___) | (_| (_) | |_| | |_
 |_| \\_\\__,_|\\__\\___|____/ \\___\\___/ \\__,_|\\__|</pre>
    <div class="dosblue dosborder">{intro}</div>
    {pop}
    <h2 class="news">{tr(lang,'catalog')} <span class="cnt">{total}</span></h2>
    {cat_html}
  </div>
  <div id="sidebar">
    {converter_html(lang)}
    {search_box(lang)}
    <div class="sblock"><h3>{tr(lang,'sections')}</h3><ul>
      <li><a href="{PREF[lang]}/o-servise/">{tr(lang,'nav_about')}</a></li>
      <li><a href="{PREF[lang]}/aml/">{tr(lang,'nav_aml')}</a></li>
      <li><a href="{PREF[lang]}/raskrytie/">{tr(lang,'nav_disc')}</a></li>
    </ul></div>
  </div>
  <div class="clearboth"></div>
</div>
{org}
{footer(lang)}"""
    write(lang, "/", head(lang, title, desc, "/", ld) + body)


def render_currency(slug, info, lang):
    name, ticker = info["name"], info["ticker"]
    path = f"/valuta/{slug}/"
    dir_blocks = ""
    for c in CATS:
        rows = ""
        for ts, ti in GROUPED.get(c, []):
            if ts == slug:
                continue
            r = rate_of(slug, ts)
            rr = f' <b class="rt">{fmt_rate(r["rate"])}</b>' if r else ''
            rows += (f'<li><a href="{bc_link(slug, ts)}" target="_blank" rel="nofollow noopener sponsored">'
                     f'{name} → {ti["name"]} <span>{ti["ticker"]}</span>{rr}</a></li>')
        if rows:
            dir_blocks += f'<h2 class="news">{name} → {cat_name(c, lang)}</h2><ul class="dlist">{rows}</ul>'
    if lang == "ru":
        title = f"Обмен {name} ({ticker}) — курсы и все направления | {S['name']}"
        desc = (f"Обмен {name} ({ticker}): справочная сводка курсов в обменниках из мониторинга BestChange. "
                f"Все направления обмена {ticker}. AML-проверка адресов.")
        intro = (f"Справочная сводка курсов обмена <b>{name} ({ticker})</b> в обменниках из мониторинга "
                 f"<b>BestChange</b>. Выберите направление ниже; обмен совершается на сайте обменника.")
        steps = [f"Выберите направление обмена {ticker} выше.",
                 "В BestChange сравните курс, резерв и рейтинг обменников.",
                 f'Для крипто — сделайте <a href="{PREF[lang]}/aml/">AML-проверку адреса</a>.',
                 "Перейдите в выбранный обменник и проведите операцию."]
        faq_q1, faq_a1 = f"Как обменять {name} ({ticker})?", "Через мониторинг BestChange — он показывает курсы обменных пунктов."
        faq_q2, faq_a2 = f"Как проверить чистоту {ticker}?", "Обмен идёт в пунктах из мониторинга BestChange. Для крипто можно сделать AML-проверку адреса."
    else:
        title = f"Exchange {name} ({ticker}) — rates and all directions | {S['name']}"
        desc = (f"Exchange {name} ({ticker}): reference summary of rates in exchange offices from BestChange "
                f"monitoring. All {ticker} directions. Address AML check.")
        intro = (f"Reference summary of <b>{name} ({ticker})</b> exchange rates in offices from the "
                 f"<b>BestChange</b> monitor. Pick a direction below; the exchange happens on the office's site.")
        steps = [f"Choose an exchange direction for {ticker} above.",
                 "On BestChange compare rate, reserve and exchanger rating.",
                 f'For crypto — do an <a href="{PREF[lang]}/aml/">AML check of the address</a>.',
                 "Go to the chosen exchanger and complete the operation."]
        faq_q1, faq_a1 = f"How to exchange {name} ({ticker})?", "Via the BestChange monitor — it shows exchange office rates."
        faq_q2, faq_a2 = f"How to check {ticker} cleanliness?", "The exchange runs in offices from BestChange monitoring. For crypto you can do an address AML check."
    faq = jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": faq_q1, "acceptedAnswer": {"@type": "Answer", "text": faq_a1}},
        {"@type": "Question", "name": faq_q2, "acceptedAnswer": {"@type": "Answer", "text": faq_a2}}]})
    crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": tr(lang, "monitor"), "item": BASE_URL + PREF[lang] + "/"},
        {"@type": "ListItem", "position": 2, "name": f"{name} ({ticker})", "item": BASE_URL + PREF[lang] + path}]})
    steps_html = "".join(f"<li>{s}</li>" for s in steps)
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {name} <span class="tk">{ticker}</span></nav>
    <h1>{'Exchange' if lang=='en' else 'Обмен'} {name} <span class="tk">{ticker}</span></h1>
    <p>{intro}</p>
    {about_currency(slug, info, lang)}
    {popular_block(slug, lang)}
    <h2 class="news">{tr(lang,'directions')} {ticker}</h2>
    {dir_blocks}
    <h2 class="news">{tr(lang,'how_to')} {name}</h2>
    <ol class="steps">{steps_html}</ol>
    <h2 class="news">{tr(lang,'faq')}</h2>
    <details><summary>{faq_q1}</summary><p>{faq_a1}</p></details>
    <details><summary>{faq_q2}</summary><p>{faq_a2}</p></details>
  </div>
  <div id="sidebar">
    {converter_html(lang, slug)}
    {search_box(lang)}
    <div class="sblock"><h3>{tr(lang,'sections')}</h3><ul>
      <li><a href="{PREF[lang]}/">{tr(lang,'all_cur')}</a></li>
      <li><a href="{PREF[lang]}/aml/">{tr(lang,'nav_aml')}</a></li>
      <li><a href="{PREF[lang]}/o-servise/">{tr(lang,'nav_about')}</a></li>
    </ul></div>
  </div>
  <div class="clearboth"></div>
</div>
{faq}{crumbs}
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path) + body)


def render_pair(f, t, lang):
    fi, ti = CUR.get(f), CUR.get(t)
    if not fi or not ti:
        return
    fN, fT, tN, tT = fi["name"], fi["ticker"], ti["name"], ti["ticker"]
    path = f"/obmen/{f}-{t}/"
    r = rate_of(f, t)
    if lang == "ru":
        rate_line = ((f'<div class="big">{fmt_rate(r["rate"])} <span>{tT} за 1 {fT}</span></div>'
                      f'<div class="sub">по данным {r["count"]} обменников · резерв {fmt_rate(r["reserve"])} {tT}</div>')
                     if r else '<div class="sub">курс уточняется в мониторинге</div>')
        title = f"Обмен {fN} на {tN}" + (f" — курс {fmt_rate(r['rate'])} {tT}/{fT}" if r else "") + f" | {S['name']}"
        desc = (f"Обмен {fN} ({fT}) на {tN} ({tT}): " + (f"курс {fmt_rate(r['rate'])} {tT} за 1 {fT}, {r['count']} обменников, " if r else "")
                + "как обменять, AML-проверка адреса. Мониторинг BestChange.")
        h1 = f"Обмен {fN} <span class=\"tk\">{fT}</span> на {tN} <span class=\"tk\">{tT}</span>"
        h_how = f"Как обменять {fT} на {tT}"
        steps = [f"Откройте список обменников BestChange по направлению {fN} → {tN}.",
                 "Сравните курс, резерв и рейтинг обменников."] + \
                ([f'Для криптовалюты — сделайте <a href="{PREF[lang]}/aml/">AML-проверку адреса</a>.'] if fi["category"] == "Криптовалюты" else []) + \
                ["Проведите обмен на сайте выбранного обменника."]
        rev = f'<a href="{pair_url(lang, t, f)}">Обратный обмен: {tN} → {fN}</a> · ' if (t, f) in TOP_SET else ""
        rel = f'{rev}<a href="{cpage(lang, f)}">О валюте {fN}</a> · <a href="{cpage(lang, t)}">О валюте {tN}</a>'
        q1 = f"Какой курс обмена {fN} на {tN}?"
        a1 = (f"Лучшее значение — <b>{fmt_rate(r['rate'])} {tT}</b> за 1 {fT} среди {r['count']} обменников. Справочно, меняется." if r else "Курс уточняется в мониторинге BestChange.")
        q2, a2 = "Безопасно ли это?", "Обмен идёт в пунктах из мониторинга BestChange с рейтингом и резервами. Для крипто рекомендуется AML-проверка адреса."
    else:
        rate_line = ((f'<div class="big">{fmt_rate(r["rate"])} <span>{tT} per 1 {fT}</span></div>'
                      f'<div class="sub">across {r["count"]} exchangers · reserve {fmt_rate(r["reserve"])} {tT}</div>')
                     if r else '<div class="sub">rate to be confirmed in the monitor</div>')
        title = f"Exchange {fN} to {tN}" + (f" — rate {fmt_rate(r['rate'])} {tT}/{fT}" if r else "") + f" | {S['name']}"
        desc = (f"Exchange {fN} ({fT}) to {tN} ({tT}): " + (f"rate {fmt_rate(r['rate'])} {tT} per 1 {fT}, {r['count']} exchangers, " if r else "")
                + "how to exchange, address AML check. BestChange monitor.")
        h1 = f"Exchange {fN} <span class=\"tk\">{fT}</span> to {tN} <span class=\"tk\">{tT}</span>"
        h_how = f"How to exchange {fT} to {tT}"
        steps = [f"Open the BestChange exchanger list for {fN} → {tN}.",
                 "Compare rate, reserve and exchanger rating."] + \
                ([f'For crypto — do an <a href="{PREF[lang]}/aml/">AML check of the address</a>.'] if fi["category"] == "Криптовалюты" else []) + \
                ["Complete the exchange on the chosen exchanger's site."]
        rev = f'<a href="{pair_url(lang, t, f)}">Reverse: {tN} → {fN}</a> · ' if (t, f) in TOP_SET else ""
        rel = f'{rev}<a href="{cpage(lang, f)}">About {fN}</a> · <a href="{cpage(lang, t)}">About {tN}</a>'
        q1 = f"What is the {fN} to {tN} rate?"
        a1 = (f"Best value — <b>{fmt_rate(r['rate'])} {tT}</b> per 1 {fT} across {r['count']} exchangers. For reference, it changes." if r else "The rate is confirmed in the BestChange monitor.")
        q2, a2 = "Is it safe?", "The exchange runs in offices from BestChange monitoring with ratings and reserves. For crypto an address AML check is recommended."
    faq = jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q1, "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", a1)}},
        {"@type": "Question", "name": q2, "acceptedAnswer": {"@type": "Answer", "text": a2}}]})
    crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": tr(lang, "monitor"), "item": BASE_URL + PREF[lang] + "/"},
        {"@type": "ListItem", "position": 2, "name": f"{fT} → {tT}", "item": BASE_URL + PREF[lang] + path}]})
    steps_html = "".join(f"<li>{s}</li>" for s in steps)
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {fT} → {tT}</nav>
    <h1>{h1}</h1>
    <div class="rate-box">
      {rate_line}
      <a class="cta" href="{bc_link(f, t)}" target="_blank" rel="nofollow noopener sponsored">{tr(lang,'open_bc')}</a>
    </div>
    <h2 class="news">{h_how}</h2>
    <ol class="steps">{steps_html}</ol>
    <p class="related">{rel} · <a href="{PREF[lang]}/blog/slovar-terminov-obmena/">{tr(lang,'glossary')}</a></p>
    <h2 class="news">{tr(lang,'faq')}</h2>
    <details><summary>{q1}</summary><p>{a1}</p></details>
    <details><summary>{q2}</summary><p>{a2}</p></details>
  </div>
</div>
{faq}{crumbs}
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path) + body)


def render_page(lang, slug, title, desc, body_html, crumb_title):
    path = f"/{slug}/"
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {crumb_title}</nav>
    {body_html}
  </div>
</div>
{footer(lang)}"""
    write(lang, path, head(lang, f"{title} | {S['name']}", desc, path) + body)


def render_blog(lang):
    arts = ARTS[lang]
    if not arts:
        return
    def dsearch(a):
        return (a["title"] + " " + a.get("description", "") + " " + a["slug"]).lower().replace('"', "&quot;")
    cards = "".join(
        f'<li data-search="{dsearch(a)}"><a href="{PREF[lang]}/blog/{a["slug"]}/">{a["title"]}</a>'
        f'<div class="apreview">{a.get("description","")}</div><div class="adate">{a.get("date","")}</div></li>' for a in arts)
    ld = jsonld({"@context": "https://schema.org", "@type": "Blog", "name": f"{S['name']} Blog",
                 "url": f"{BASE_URL}{PREF[lang]}/blog/"})
    if lang == "ru":
        title = f"Блог — гайды по обмену криптовалют и валют | {S['name']}"
        desc = "Статьи и гайды: сети USDT, комиссии, AML-проверка, словарь терминов обмена."
        h1, lead = "Блог", "Справочные материалы и гайды об обмене криптовалют и валют."
    else:
        title = f"Blog — crypto and currency exchange guides | {S['name']}"
        desc = "Articles and guides: USDT networks, fees, AML check, exchange glossary."
        h1, lead = "Blog", "Reference materials and guides on crypto and currency exchange."
    body = f"""{header(lang, "/blog/")}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {h1}</nav>
    <h1>{h1}</h1><p>{lead}</p>
    <div id="blogsearch">
      <input id="bq" type="search" placeholder="{tr(lang,'blog_search_ph')}" autocomplete="off" aria-label="{tr(lang,'blog_search_ph')}">
    </div>
    <ul class="bloglist" id="bloglist">{cards}</ul>
    <p id="bnores" class="related" hidden>{tr(lang,'blog_noresults')}</p>
  </div>
</div>
{ld}
{footer(lang)}"""
    write(lang, "/blog/", head(lang, title, desc, "/blog/", ld) + body)


def render_article(a, lang):
    path = f"/blog/{a['slug']}/"
    title = f"{a['title']} | {S['name']}"
    desc = a.get("description", "")
    art_ld = jsonld({"@context": "https://schema.org", "@type": "Article", "headline": a["title"],
                     "description": desc, "datePublished": a.get("date", ""), "inLanguage": LOCALE[lang],
                     "author": {"@type": "Organization", "name": S["name"]},
                     "publisher": {"@type": "Organization", "name": S["name"]},
                     "mainEntityOfPage": BASE_URL + PREF[lang] + path})
    back = "← All articles" if lang == "en" else "← Все статьи"
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / <a href="{PREF[lang]}/blog/">{tr(lang,'nav_blog')}</a> / {a['title']}</nav>
    <article class="post"><div class="adate">{a.get('date','')}</div>{a['html']}</article>
    <p><a href="{PREF[lang]}/blog/">{back}</a></p>
  </div>
</div>
{art_ld}
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path) + body)


def compliance_pages(lang):
    if lang == "ru":
        render_page(lang, "o-servise", "Что такое BestChange",
                    "BestChange — мониторинг обменных пунктов: справочная информация о курсах обмена криптовалют и валют.",
                    """<h1>Что такое BestChange</h1>
<p><b>BestChange</b> — мониторинг обменников электронных валют и криптовалют. Сервис собирает курсы, резервы и
   комиссии десятков обменных пунктов и показывает их значения в одном месте — не нужно обходить сайты вручную.</p>
<h2>Как это работает</h2>
<ol class="steps"><li>Выбираете направление обмена.</li><li>BestChange показывает обменники, отсортированные по курсу.</li>
<li>Смотрите курс, рейтинг, резерв и отзывы, выбираете подходящий пункт.</li><li>Переходите и проводите операцию на сайте обменника.</li></ol>
<h2>Про мониторинг</h2>
<p>В мониторинг попадают обменники с рейтингом и резервами. RateScout — независимый информационный сервис,
   который помогает сориентироваться и ведёт в BestChange к списку обменников. Сами обмен не проводим.</p>""",
                    "Что такое BestChange")
        render_page(lang, "aml", "AML-проверка криптоадреса — зачем и как",
                    "AML-проверка: как проверить криптоадрес на связь с мошенничеством и санкциями перед обменом.",
                    """<h1>AML-проверка криптоадреса</h1>
<p><b>AML</b> (Anti-Money Laundering) — проверка криптоадреса или транзакции на связь с мошенничеством, даркнетом,
   украденными средствами и санкциями. Снижает риск получить «грязные» монеты и блокировку на бирже.</p>
<h2>Когда делать</h2><ul><li>перед приёмом крупной суммы в крипте;</li><li>перед обменом крипты на рубли/наличные;</li>
<li>если контрагент незнаком.</li></ul>
<h2>Как проверить</h2>
<p>AML-проверка выполняется через специализированные сервисы анализа блокчейна: вы указываете адрес и получаете
   отчёт о рисках. Инструмент анализа адреса есть и у BestChange, и у ряда других сервисов.</p>""",
                    "AML-проверка")
        render_page(lang, "raskrytie", "Раскрытие информации и дисклеймеры",
                    "Партнёрское раскрытие и правовая информация RateScout.",
                    f"""<h1>Раскрытие информации и дисклеймеры</h1>
<h2>Партнёрское раскрытие</h2><p>RateScout — независимый информационный сервис. Ссылки ведут в BestChange; по
   партнёрской программе возможно вознаграждение. Это не реклама от имени BestChange.</p>
<h2>Дисклеймер</h2><p>Информация справочная, не является финансовой/инвестиционной/юридической рекомендацией.
   Курсы меняются. Решение об обмене — самостоятельно и на свой риск. 18+.</p>
<h2>Соответствие законодательству</h2>
<ul><li><b>РФ:</b> сайт — информационный ресурс, активного продвижения не ведёт; маркировка рекламы (ERID/ОРД) не требуется. ПДн — по 152-ФЗ.</li>
<li><b>США:</b> affiliate-раскрытие по FTC; сервис недоступен под санкциями (OFAC).</li></ul>
<h2>Сведения о владельце сайта</h2>
<p>{S.get('owner_status','')} <b>{S.get('owner','')}</b>, ИНН {S.get('owner_inn','')}. Владелец не является
   обменным пунктом и не проводит операции. Контакт: {S.get('owner_email','')}.</p>""",
                    "Раскрытие")
        render_page(lang, "politika", "Политика конфиденциальности",
                    f"Политика обработки данных и cookie на сайте {S['domain']} (152-ФЗ).",
                    f"""<h1>Политика конфиденциальности</h1>
<p>Настоящая Политика описывает порядок обработки данных посетителей сайта {S['domain']}. Оператор:
   {S.get('owner_status','')} {S.get('owner','')}, ИНН {S.get('owner_inn','')}.</p>
<h2>Какие данные</h2><ul><li>технические данные браузера (IP, тип браузера/ОС, referer, дата/время);</li>
<li>обезличенная веб-аналитика;</li><li>cookie.</li></ul>
<h2>Аналитика</h2><p>Используются Яндекс.Метрика и Google Analytics (обезличенные данные). В составе Метрики —
   Вебвизор (запись действий на странице в обезличенном виде; поля с чувствительными данными маскируются).
   Cookie можно отключить в браузере.</p>
<h2>Права</h2><p>Запрос сведений, уточнение или удаление данных, отзыв согласия — на {S.get('owner_email','')}.
   Обработка — по 152-ФЗ. Актуальная редакция — на этой странице.</p>""",
                    "Политика")
    else:
        render_page(lang, "o-servise", "What is BestChange",
                    "BestChange — an exchange office monitor: reference information about crypto and currency exchange rates.",
                    """<h1>What is BestChange</h1>
<p><b>BestChange</b> is a monitor of e-currency and crypto exchange offices. It collects rates, reserves and
   fees from dozens of offices and shows them in one place — no need to check each site manually.</p>
<h2>How it works</h2>
<ol class="steps"><li>Choose an exchange direction.</li><li>BestChange shows exchangers sorted by rate.</li>
<li>Check rate, rating, reserve and reviews, pick a suitable office.</li><li>Go and complete the operation on the exchanger's site.</li></ol>
<h2>About the monitor</h2>
<p>Exchangers with ratings and reserves are listed. RateScout is an independent information service that helps you
   navigate and leads to the BestChange exchanger list. We do not process exchanges ourselves.</p>""",
                    "What is BestChange")
        render_page(lang, "aml", "Crypto address AML check — why and how",
                    "AML check: how to verify a crypto address for links to fraud and sanctions before exchanging.",
                    """<h1>Crypto address AML check</h1>
<p><b>AML</b> (Anti-Money Laundering) is a check of a crypto address or transaction for links to fraud, darknet,
   stolen funds and sanctions. It reduces the risk of receiving "dirty" coins and getting funds frozen.</p>
<h2>When to do it</h2><ul><li>before receiving a large crypto amount;</li><li>before exchanging crypto to cash/bank;</li>
<li>if the counterparty is unknown.</li></ul>
<h2>How to check</h2>
<p>An AML check is done via blockchain analysis services: you enter an address and get a risk report. An address
   analysis tool is available on BestChange and a number of other services.</p>""",
                    "AML check")
        render_page(lang, "raskrytie", "Disclosure and disclaimers",
                    "Affiliate disclosure and legal information of RateScout.",
                    f"""<h1>Disclosure and disclaimers</h1>
<h2>Affiliate disclosure</h2><p>RateScout is an independent information service. Links lead to BestChange; through
   the affiliate program we may earn a commission. This is not advertising on behalf of BestChange (FTC disclosure).</p>
<h2>Disclaimer</h2><p>Information is for reference and is not financial, investment or legal advice. Rates change.
   You decide to exchange on your own and at your own risk. 18+.</p>
<h2>Legal</h2><ul><li><b>US:</b> FTC affiliate disclosure; the service is unavailable to sanctioned persons/territories (OFAC).</li>
<li><b>RU:</b> informational resource; no active promotion.</li></ul>
<h2>Site owner</h2>
<p><b>{S.get('owner','')}</b> (self-employed, RU tax ID {S.get('owner_inn','')}). The owner is not an exchange
   office and does not process transactions. Contact: {S.get('owner_email','')}.</p>""",
                    "Disclosure")
        render_page(lang, "politika", "Privacy policy",
                    f"Data and cookie processing policy on {S['domain']}.",
                    f"""<h1>Privacy policy</h1>
<p>This policy describes how visitor data is processed on {S['domain']}. Operator: {S.get('owner','')}
   (self-employed, RU tax ID {S.get('owner_inn','')}).</p>
<h2>What data</h2><ul><li>technical browser data (IP, browser/OS, referer, date/time);</li>
<li>anonymised web analytics;</li><li>cookies.</li></ul>
<h2>Analytics</h2><p>Yandex.Metrica and Google Analytics are used (anonymised data). Metrica includes Webvisor
   (records on-page actions anonymously; fields with sensitive data are masked). Cookies can be disabled in the browser.</p>
<h2>Rights</h2><p>To request, correct or delete data, or withdraw consent — email {S.get('owner_email','')}.
   The current version is on this page.</p>""",
                    "Privacy")


def write_catalog_js():
    cur = {slug: {"n": i["name"], "t": i["ticker"], "c": i["category"]} for slug, i in CUR.items()}
    js = "window.__CATALOG__=" + json.dumps({"order": CATS, "cur": cur}, ensure_ascii=False) + \
         ";window.__REF__=" + json.dumps(REF) + ";"
    open(os.path.join(DIST, "assets", "catalog.js"), "w", encoding="utf-8").write(js)


def static_files():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def u_entry(loc, freq, pri):
        return (f"  <url><loc>{BASE_URL}{loc}</loc><lastmod>{today}</lastmod>"
                f"<changefreq>{freq}</changefreq><priority>{pri}</priority></url>")

    items = []
    for lg in LANGS:
        pr = PREF[lg]
        items.append(u_entry(pr + "/", "hourly", "1.0" if lg == "ru" else "0.9"))
        items += [u_entry(pr + f"/valuta/{s}/", "hourly", "0.6") for s in CUR]
        items += [u_entry(pr + f"/obmen/{p['from']}-{p['to']}/", "hourly", "0.8") for p in TOP]
        if ARTS[lg]:
            items.append(u_entry(pr + "/blog/", "weekly", "0.7"))
            items += [u_entry(pr + f"/blog/{a['slug']}/", "monthly", "0.6") for a in ARTS[lg]]
        items += [u_entry(pr + f"/{u}/", "monthly", "0.4") for u in ("o-servise", "aml", "raskrytie", "politika")]
    open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(items) + "\n</urlset>")
    open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")
    open(os.path.join(DIST, "CNAME"), "w", encoding="utf-8").write(S["domain"] + "\n")
    open(os.path.join(DIST, "manifest.webmanifest"), "w", encoding="utf-8").write(json.dumps({
        "name": S["name"] + " — мониторинг курсов обмена", "short_name": S["name"],
        "description": S["tagline"], "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#111111", "theme_color": "#111111", "lang": "ru",
        "icons": [{"src": "/assets/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}]
    }, ensure_ascii=False, indent=2))
    open(os.path.join(DIST, "sw.js"), "w", encoding="utf-8").write(
        "const C='ratescout-v1';\nself.addEventListener('install',e=>self.skipWaiting());\n"
        "self.addEventListener('activate',e=>self.clients.claim());\n"
        "self.addEventListener('fetch',e=>e.respondWith(fetch(e.request)"
        ".then(r=>{const c=r.clone();caches.open(C).then(x=>x.put(e.request,c));return r})"
        ".catch(()=>caches.match(e.request))));")
    open(os.path.join(DIST, ".nojekyll"), "w").write("")


def copy_assets():
    dst = os.path.join(DIST, "assets")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(ROOT, "assets"), dst)


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    for lang in LANGS:
        render_home(lang)
        for slug, info in CUR.items():
            render_currency(slug, info, lang)
        compliance_pages(lang)
        render_blog(lang)
        for a in ARTS[lang]:
            render_article(a, lang)
        for p in TOP:
            render_pair(p["from"], p["to"], lang)
    static_files()
    copy_assets()
    write_catalog_js()
    print(f"✅ dist/: {LANGS} × (главная + {len(CUR)} валют + {len(TOP)} пар + {1+len(ARTS['ru'])} блог + 4 инфо) + sitemap/robots")


if __name__ == "__main__":
    main()
