#!/usr/bin/env python3
"""Генератор статического SEO-сайта RateScout (GitHub Pages) — RU + EN (i18n).

RU в корне (/), EN в /en/. hreflang между версиями, переключатель языка.
Данные (курсы/каталог/пары) общие; локализуются только тексты и внутренние ссылки.
"""
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

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
INDEXNOW_KEY = "b394aeced6a92ed48a09e2bd30099905"  # публичный ключ IndexNow (ключ-файл на сайте)

LANGS = ["ru", "en"]
PREF = {"ru": "", "en": "/en"}
LOCALE = {"ru": "ru", "en": "en"}
BLOG_PER_PAGE = 6            # статей на страницу блога (пагинация 1 2 3 …)

# Версии ассетов для кеш-бастинга (хеш содержимого) — заполняется в main() до рендера.
# Стабильный путь /assets/app.js кешируется браузером; ?v=<hash> меняется только при
# изменении файла и заставляет подхватить новую версию (важно для ежечасных пересборок).
VER = {"css": "", "js": "", "cat": ""}


def _h(s):
    return hashlib.md5(s.encode("utf-8") if isinstance(s, str) else s).hexdigest()[:8]

# перевод категорий для EN
CAT_EN = {"Криптовалюты": "Cryptocurrencies", "Digital currencies": "Digital currencies",
          "Bank accounts and cards": "Bank accounts and cards", "Online banking": "Online banking",
          "Money transfers": "Money transfers", "Cash": "Cash", "Прочее": "Other"}


def cat_name(c, lang):
    return CAT_EN.get(c, c) if lang == "en" else c


# слаги категорийных хабов (/kategoriya/<slug>/)
CAT_SLUG = {"Криптовалюты": "kriptovalyuty", "Digital currencies": "cifrovye-valyuty",
            "Bank accounts and cards": "bankovskie-karty", "Online banking": "onlayn-banking",
            "Money transfers": "denezhnye-perevody", "Cash": "nalichnye", "Прочее": "prochee"}

# уникальные вступления для хаб-страниц категорий (RU/EN)
CAT_INTRO = {
    "Криптовалюты": ("Криптовалюты — цифровые активы в блокчейн-сетях: Bitcoin, Ethereum, стейблкоины (USDT, "
                     "USDC) и десятки других монет. При обмене важны сеть выпуска и её комиссия. Ниже — все "
                     "криптовалюты каталога; на странице каждой собраны курсы всех направлений и калькулятор.",
                     "Cryptocurrencies are digital assets on blockchain networks: Bitcoin, Ethereum, stablecoins "
                     "(USDT, USDC) and dozens more. When exchanging, the issuing network and its fee matter. Below "
                     "are all cryptocurrencies in the catalog; each page has rates for every direction and a calculator."),
    "Digital currencies": ("Электронные платёжные системы и цифровые кошельки: YooMoney, Advanced Cash, Capitalist "
                           "и другие. Ниже — все такие направления каталога с курсами обмена.",
                           "Electronic payment systems and digital wallets: YooMoney, Advanced Cash, Capitalist and "
                           "others. Below are all such directions in the catalog with exchange rates."),
    "Bank accounts and cards": ("Банковские карты и реквизиты: Visa/Mastercard, Мир, СБП, переводы на счёт. Ниже — "
                                "все карточные направления каталога с курсами обмена.",
                                "Bank cards and details: Visa/Mastercard, Mir, SBP, transfers to account. Below are "
                                "all card directions in the catalog with exchange rates."),
    "Online banking": ("Онлайн-банкинг: Сбербанк, Т-Банк, ВТБ, Альфа-Банк и другие банки. Ниже — все банковские "
                       "направления каталога; на странице каждого — курсы обмена и калькулятор.",
                       "Online banking: Sberbank, T-Bank, VTB, Alfa-Bank and other banks. Below are all bank "
                       "directions in the catalog; each page has exchange rates and a calculator."),
    "Money transfers": ("Системы денежных переводов. Ниже — все такие направления каталога с курсами обмена.",
                        "Money transfer systems. Below are all such directions in the catalog with exchange rates."),
    "Cash": ("Наличные в разных валютах. Ниже — все наличные направления каталога; обмен проходит в офисе обменника.",
             "Cash in various currencies. Below are all cash directions in the catalog; the exchange happens in the "
             "exchanger's office."),
    "Прочее": ("Прочие направления каталога.", "Other directions in the catalog."),
}


def cat_page(lang, cat):
    return f"{PREF[lang]}/kategoriya/{CAT_SLUG.get(cat, 'prochee')}/"


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
RATES_GENERATED = 0
_rp = os.path.join(ROOT, "rates.json")
if os.path.exists(_rp):
    try:
        _rj = json.load(open(_rp, encoding="utf-8"))
        RATES = _rj.get("pairs", {})
        RATES_GENERATED = int(_rj.get("generated_at", 0) or 0)
    except (ValueError, OSError):
        RATES = {}


def updated_str(lang):
    """Метка свежести данных курсов (UTC) для отображения на страницах."""
    if not RATES_GENERATED:
        return ""
    dt = datetime.fromtimestamp(RATES_GENERATED, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Обновлено: {dt}" if lang == "ru" else f"Updated: {dt}"


def modified_iso():
    """ISO-дата последнего обновления курсов — для schema dateModified (свежесть)."""
    ts = RATES_GENERATED or int(datetime.now(timezone.utc).timestamp())
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


GLOSSARY = []
_gp = os.path.join(ROOT, "glossary.json")
if os.path.exists(_gp):
    try:
        GLOSSARY = json.load(open(_gp, encoding="utf-8")).get("terms", [])
    except (ValueError, OSError):
        GLOSSARY = []
GLOSSARY_BY = {t["slug"]: t for t in GLOSSARY}


HISTORY = {}
_hp = os.path.join(ROOT, "history.json")
if os.path.exists(_hp):
    try:
        HISTORY = json.load(open(_hp, encoding="utf-8")).get("series", {})
    except (ValueError, OSError):
        HISTORY = {}


def svg_chart(points):
    """Inline-SVG линия динамики (без JS/внешних либ). points=[[date,rate],...]."""
    vals = [p[1] for p in points]
    mn, mx = min(vals), max(vals)
    W, H, pad = 600.0, 120.0, 8.0
    span = (mx - mn) or (mx or 1.0)
    n = len(points)
    def xy(i, v):
        x = pad + (W - 2 * pad) * (i / (n - 1) if n > 1 else 0)
        y = pad + (H - 2 * pad) * (1 - (v - mn) / span)
        return f"{x:.1f},{y:.1f}"
    poly = " ".join(xy(i, v) for i, v in enumerate(vals))
    last_x = pad + (W - 2 * pad)
    last_y = pad + (H - 2 * pad) * (1 - (vals[-1] - mn) / span)
    return (f'<svg class="chart" viewBox="0 0 {W:.0f} {H:.0f}" preserveAspectRatio="none" '
            f'role="img" aria-label="rate chart">'
            f'<polyline fill="none" stroke="#55ff55" stroke-width="2" points="{poly}"/>'
            f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="#ffff55"/></svg>')


# периоды для фильтра роста/падения на /grafiki/ (ключ, дней)
CHART_PERIODS = [("24h", 1), ("7d", 7), ("30d", 30), ("1y", 365), ("3y", 1095), ("5y", 1825), ("10y", 3650)]


def _hist_time(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:00")
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%d")


def _pct_over(pts, days):
    """% изменения цены за последние `days` (база — первая точка в окне; если данных меньше — от старта)."""
    if len(pts) < 2:
        return None
    cutoff = _hist_time(pts[-1][0]) - timedelta(days=days)
    base = None
    for k, v in pts:
        if _hist_time(k) >= cutoff:
            base = v
            break
    if base is None:
        base = pts[0][1]
    if not base:
        return None
    return (pts[-1][1] - base) / base * 100


def mini_spark(points):
    """Лёгкий спарклайн (мини-SVG без осей) для обзорной страницы графиков."""
    vals = [p[1] for p in points]
    mn, mx = min(vals), max(vals)
    span = (mx - mn) or (mx or 1.0)
    W, H = 120.0, 34.0
    n = len(points)
    poly = " ".join(f"{(i / (n - 1) * W if n > 1 else 0):.1f},{(2 + (1 - (v - mn) / span) * (H - 4)):.1f}"
                    for i, v in enumerate(vals))
    color = "#55ff55" if vals[-1] >= vals[0] else "#f55"
    return (f'<svg class="spark" viewBox="0 0 {W:.0f} {H:.0f}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{poly}"/></svg>')


def _usdt_price(slug):
    """Текущая цена валюты в USDT: прямой курс, иначе обратный (USDT→slug) с инверсией."""
    r = rate_of(slug, "tether-trc20")
    if r:
        try:
            v = float(r["rate"])
            if v > 0:
                return v, r.get("count", 0)
        except (ValueError, TypeError):
            pass
    rr = rate_of("tether-trc20", slug)
    if rr:
        try:
            v = float(rr["rate"])
            if v > 0:
                return 1.0 / v, rr.get("count", 0)
        except (ValueError, TypeError, ZeroDivisionError):
            pass
    return None, 0


def render_charts_overview(lang):
    """Обзор рынка по ВСЕМ валютам: спарклайн+цена+изм где есть история; иначе цена/прочерк. SEO-хаб."""
    rows = []
    for slug, info in CUR.items():
        if slug == "tether-trc20":
            continue
        h = HISTORY.get(slug, [])
        price, liq = _usdt_price(slug)
        if len(h) >= 2:
            vals = [p[1] for p in h]
            chg = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] else 0
            per = {pk: _pct_over(h, dys) for pk, dys in CHART_PERIODS}
            rows.append((2, liq, slug, info, vals[-1], chg, h[-90:], per))
        elif price is not None:
            rows.append((1, liq, slug, info, price, None, None, {}))
        else:
            rows.append((0, 0, slug, info, None, None, None, {}))
    if not rows:
        return
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    path = "/grafiki/"
    if lang == "ru":
        title = f"Графики курсов криптовалют — динамика цен | {S['name']}"
        desc = "Графики динамики курсов криптовалют (цена в USDT): изменение, мини-графики по всем монетам. Обновление ежечасно."
        h1, lead = "Графики курсов", f"Динамика цен в USDT по {len(rows)} валютам. Обновляется ежечасно. Нажмите на валюту — полный интерактивный график."
        th = ("Валюта", "Цена (USDT)", "Изм.", "График")
        sorts = [("liq", "По ликвидности"), ("up", "Рост ↑"), ("down", "Падение ↓")]
        plbl = "Изменение за:"
        periods = [("all", "Всё"), ("24h", "24ч"), ("7d", "7д"), ("30d", "30д"),
                   ("1y", "1г"), ("3y", "3г"), ("5y", "5л"), ("10y", "10л")]
    else:
        title = f"Cryptocurrency rate charts — price trends | {S['name']}"
        desc = "Crypto rate charts (price in USDT): change and mini-charts for all coins. Hourly updates."
        h1, lead = "Rate charts", f"Price trends in USDT across {len(rows)} currencies. Hourly updates. Click a currency for the full interactive chart."
        th = ("Currency", "Price (USDT)", "Chg.", "Chart")
        sorts = [("liq", "By liquidity"), ("up", "Gainers ↑"), ("down", "Losers ↓")]
        plbl = "Change over:"
        periods = [("all", "All"), ("24h", "24h"), ("7d", "7d"), ("30d", "30d"),
                   ("1y", "1y"), ("3y", "3y"), ("5y", "5y"), ("10y", "10y")]
    trs = ""
    for _b, _liq, slug, info, price, chg, spark, per in rows:
        price_c = f'<b>{fmt_rate(price)}</b>' if price is not None else '<span class="nd">—</span>'
        if chg is None:
            chg_c = '<span class="nd">—</span>'
        else:
            cls = "up" if chg >= 0 else "down"
            sign = "+" if chg >= 0 else ""
            chg_c = f'<b class="{cls}">{sign}{chg:.1f}%</b>'
        spk_c = mini_spark(spark) if spark else '<span class="nd">—</span>'
        chg_a = "" if chg is None else f"{chg:.4f}"
        cat_k = CAT_SLUG.get(info["category"], "prochee")
        pattrs = "".join(f' data-c{pk}="{("" if per.get(pk) is None else f"{per[pk]:.4f}")}"' for pk, _ in CHART_PERIODS)
        trs += (f'<tr data-liq="{_liq}" data-chg="{chg_a}" data-cat="{cat_k}"{pattrs}><td class="d"><a href="{cpage(lang, slug)}">{info["name"]} <span>{info["ticker"]}</span></a></td>'
                f'<td class="num">{price_c}</td><td class="num chg-cell">{chg_c}</td><td class="spk">{spk_c}</td></tr>')
    sbtns = ""
    for sv, sl in sorts:
        son = ' class="on"' if sv == "liq" else ""
        sbtns += f'<button type="button" data-s="{sv}"{son}>{sl}</button>'
    filts = [("", "Все" if lang == "ru" else "All")] + [(CAT_SLUG[c], cat_name(c, lang)) for c in CATS]
    fbtns = ""
    for fv, fl in filts:
        fon = ' class="on"' if fv == "" else ""
        fbtns += f'<button type="button" data-f="{fv}"{fon}>{fl}</button>'
    pbtns = ""
    for pv, pl in periods:
        pon = ' class="on"' if pv == "all" else ""
        pbtns += f'<button type="button" data-p="{pv}"{pon}>{pl}</button>'
    ld = jsonld({"@context": "https://schema.org", "@type": "CollectionPage", "name": h1,
                 "url": BASE_URL + PREF[lang] + path, "inLanguage": LOCALE[lang], "dateModified": modified_iso()})
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {h1}</nav>
    <h1>{h1} <span class="cnt">{len(rows)}</span></h1><p>{lead}</p>
    <p class="updnote">{updated_str(lang)}</p>
    <div class="rsrange catbar">{fbtns}</div>
    <div class="rsrange sortbar">{sbtns}</div>
    <div class="perrow"><span class="ctllbl">{plbl}</span><span class="rsrange perbar">{pbtns}</span></div>
    <div class="rtbl-wrap"><table class="rtbl marktbl"><thead><tr>
      <th>{th[0]}</th><th>{th[1]}</th><th>{th[2]}</th><th>{th[3]}</th></tr></thead><tbody>{trs}</tbody></table></div>
  </div>
</div>
{ld}
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path, ld) + body)


def currency_chart(slug, info, lang):
    pts = HISTORY.get(slug, [])
    if len(pts) < 2:
        if lang == "ru":
            return (f'<h2 class="news">Динамика цены {info["ticker"]} (USDT)</h2>'
                    f'<p class="updnote">📈 Идёт накопление данных — график появится, когда наберётся история '
                    f'(точек сейчас: {len(pts)}). Обновляется ежедневно.</p>') if pts else ""
        return (f'<h2 class="news">{info["ticker"]} price trend (USDT)</h2>'
                f'<p class="updnote">📈 Collecting data — the chart will appear once history builds up '
                f'(points so far: {len(pts)}). Updated daily.</p>') if pts else ""
    data = pts[-2000:]                      # недавние почасовые + дневные (годы) — для интерактива
    vals = [p[1] for p in data]
    first, last = vals[0], vals[-1]
    chg = (last - first) / first * 100 if first else 0
    sign = "+" if chg >= 0 else ""
    cls = "up" if chg >= 0 else "down"
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    if lang == "ru":
        title = f"Динамика цены {info['ticker']} (USDT)"
        ranges = [("24h", "24ч"), ("7d", "7д"), ("30d", "30д"), ("1y", "1г"),
                  ("3y", "3г"), ("5y", "5л"), ("10y", "10л"), ("all", "Всё")]
        note = (f"1 {info['ticker']} = <b>{fmt_rate(last)}</b> USDT · за период: "
                f'<b class="{cls}">{sign}{chg:.1f}%</b>. Данные BestChange, обновление ежечасно. '
                "Наведите на график — покажет цену и время.")
    else:
        title = f"{info['ticker']} price trend (USDT)"
        ranges = [("24h", "24h"), ("7d", "7d"), ("30d", "30d"), ("1y", "1y"),
                  ("3y", "3y"), ("5y", "5y"), ("10y", "10y"), ("all", "All")]
        note = (f"1 {info['ticker']} = <b>{fmt_rate(last)}</b> USDT · change: "
                f'<b class="{cls}">{sign}{chg:.1f}%</b>. BestChange data, hourly. '
                "Hover the chart to see price and time.")
    # кнопка диапазона появляется, только когда истории хватает на этот период
    def _pt(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:00")
        except ValueError:
            return datetime.strptime(s, "%Y-%m-%d")
    span_days = (_pt(data[-1][0]) - _pt(data[0][0])).total_seconds() / 86400
    DURD = {"24h": 1, "7d": 7, "30d": 30, "1y": 365, "3y": 3 * 365, "5y": 5 * 365, "10y": 10 * 365, "all": 0}
    ranges = [(r, lbl) for r, lbl in ranges if r == "all" or span_days >= DURD[r]]
    btns = ""
    for r, lbl in ranges:
        on = ' class="on"' if r == "all" else ""
        btns += f'<button type="button" data-r="{r}"{on}>{lbl}</button>'
    return (f'<h2 class="news" id="chart">{title}</h2>'
            f'<div class="rschart-wrap" data-ticker="{info["ticker"]}" data-unit="USDT">'
            f'<div class="rsrange">{btns}</div>'
            f'<div class="rschart"><noscript>{svg_chart(pts[-90:])}</noscript></div>'
            f'<div class="rsperiod"></div>'
            f'<div class="rstip" hidden></div>'
            f'<script type="application/json" class="rschart-data">{data_json}</script>'
            f'</div>'
            f'<p class="updnote">{note}</p>')


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

# Высокоинтентные пары: топ-крипта → главные RUB-направления (только где есть реальный курс).
# Дают SEO-страницы под запросы «обменять <крипта> на <банк>/наличные/СБП», без пустышек.
HI_FROM = ["tether-trc20", "bitcoin", "tether-bep20", "tether-erc20", "ethereum",
           "litecoin", "monero", "tron", "usdcoin", "tether-ton"]
HI_TO = ["sberbank", "tinkoff", "sbp", "cash-ruble", "visa-mastercard-rub", "mir",
         "alfaclick", "vtb", "gazprombank", "yoomoney", "raiffeisen-bank", "ozon"]
EXTRA_PAIRS = []
for _f in HI_FROM:
    for _t in HI_TO:
        if _f in CUR and _t in CUR and (_f, _t) not in TOP_SET and RATES.get(f"{_f}>{_t}"):
            EXTRA_PAIRS.append({"from": _f, "to": _t})

# Все пары, для которых генерим страницы (топ + высокоинтентные), с дедупом.
PAIR_PAGES = TOP + EXTRA_PAIRS
_seen = set()
PAIR_PAGES = [p for p in PAIR_PAGES if not ((p["from"], p["to"]) in _seen or _seen.add((p["from"], p["to"])))]
PAIR_SET = {(p["from"], p["to"]) for p in PAIR_PAGES}

# Банковские хабы: «все монеты → конкретный получатель» (крупные RUB-направления).
# Страница /na/<slug>/ агрегирует крипто→этот банк с курсами — высокоинтентный money-лендинг.
BANK_HUB_LIST = ["sberbank", "tinkoff", "sbp", "cash-ruble", "visa-mastercard-rub",
                 "mir", "alfaclick", "vtb", "gazprombank", "yoomoney"]


# Пары для встраиваемого виджета: (ключ, from_slug, to_slug, показ_from, показ_to, url на нашем сайте)
WIDGET_PAIRS = [
    ("usdt-rub", "tether-trc20", "sberbank", "USDT", "RUB", "/na/sberbank/"),
    ("btc-rub", "bitcoin", "sberbank", "BTC", "RUB", "/obmen/bitcoin-sberbank/"),
    ("eth-rub", "ethereum", "sberbank", "ETH", "RUB", "/valuta/ethereum/"),
    ("btc-usdt", "bitcoin", "tether-trc20", "BTC", "USDT", "/obmen/bitcoin-tether-trc20/"),
    ("eth-usdt", "ethereum", "tether-trc20", "ETH", "USDT", "/valuta/ethereum/"),
    ("ton-usdt", "ton", "tether-trc20", "TON", "USDT", "/valuta/ton/"),
    ("trx-usdt", "tron", "tether-trc20", "TRX", "USDT", "/valuta/tron/"),
    ("ltc-usdt", "litecoin", "tether-trc20", "LTC", "USDT", "/valuta/litecoin/"),
]


def _crypto_rate_count(to_slug):
    return sum(1 for fs, _ in GROUPED.get("Криптовалюты", []) if RATES.get(f"{fs}>{to_slug}"))


# хабы, у которых реально ≥5 крипто-направлений (иначе не рендерим — не плодим тонкие)
BANK_HUBS = [b for b in BANK_HUB_LIST if b in CUR and _crypto_rate_count(b) >= 5]
BANK_HUB_SET = set(BANK_HUBS)


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
        "nav_aml": "AML-проверка", "nav_disc": "Раскрытие", "nav_faq": "Вопросы", "nav_glossary": "Словарь", "nav_widget": "Виджеты", "nav_charts": "Графики",
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
        "amount": "Сумма", "approx": "≈ получите", "get_cta": "Получить",
    },
    "en": {
        "nav_monitor": "Monitor", "nav_blog": "Blog", "nav_about": "What is BestChange",
        "nav_aml": "AML check", "nav_disc": "Disclosure", "nav_faq": "FAQ", "nav_glossary": "Glossary", "nav_widget": "Widgets", "nav_charts": "Charts",
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
        "amount": "Amount", "approx": "≈ you get", "get_cta": "Get",
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


def howto_ld(name, steps):
    """HowTo-разметка из списка шагов (теги в тексте вычищаются)."""
    return jsonld({"@context": "https://schema.org", "@type": "HowTo", "name": name,
                   "step": [{"@type": "HowToStep", "position": i + 1,
                             "text": re.sub("<[^>]+>", "", s)} for i, s in enumerate(steps)]})


def itemlist_ld(items):
    """ItemList-разметка: items = [(name, absolute_url), ...]."""
    return jsonld({"@context": "https://schema.org", "@type": "ItemList",
                   "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "url": u}
                                       for i, (n, u) in enumerate(items)]})


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
<link rel="preconnect" href="https://mc.yandex.ru">
<link rel="dns-prefetch" href="https://mc.yandex.ru">
<link rel="preconnect" href="https://www.googletagmanager.com">
<link rel="dns-prefetch" href="https://www.googletagmanager.com">
<link rel="stylesheet" href="/assets/styles.css?v={VER['css']}">
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
    <li><a href="{PREF[lang]}/grafiki/">{tr(lang,'nav_charts')}</a></li>
    <li><a href="{PREF[lang]}/faq/">{tr(lang,'nav_faq')}</a></li>
    <li><a href="{PREF[lang]}/slovar/">{tr(lang,'nav_glossary')}</a></li>
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
                 f'<a href="/vidzhet/">Виджет для сайта</a> · <a href="/redakciya/">О редакции</a> · <a href="/raskrytie/">Раскрытие и дисклеймеры</a> · <a href="/politika/">Политика конфиденциальности</a>')
        fine = ("18+. Информация носит справочный характер, не является рекламой, офертой или финансовой "
                f"рекомендацией. Курсы меняются. © {S['name']} {S['domain']}.<br>"
                f"<span class=\"erid\">Владелец сайта: {S.get('owner_status','')} {S.get('owner','')}, ИНН {S.get('owner_inn','')}.</span>")
    else:
        disc = ("RateScout is an independent rate-monitoring service. We are not an exchange office and do not "
                "process transactions. Links lead to BestChange (a monitor of exchange office rates); through the "
                "affiliate program we may earn a commission. This is not advertising on behalf of BestChange.")
        links = (f'<a href="/en/o-servise/">About</a> · <a href="/en/aml/">AML check</a> · '
                 f'<a href="/en/vidzhet/">Site widget</a> · <a href="/en/redakciya/">Editorial</a> · <a href="/en/raskrytie/">Disclosure</a> · <a href="/en/politika/">Privacy policy</a>')
        fine = ("18+. Information is for reference only and is not advertising, an offer or financial advice. "
                f"Rates change. © {S['name']} {S['domain']}.<br>"
                f"<span class=\"erid\">Site owner: {S.get('owner','')} (self-employed, RU tax ID {S.get('owner_inn','')}).</span>")
    return f"""<div id="footer">
  <div class="disc">{disc}</div>
  <div class="links">{links}</div>
  <div class="fine">{fine}</div>
</div>
</div>
<script src="/assets/catalog.js?v={VER['cat']}"></script>
<script src="/assets/app.js?v={VER['js']}"></script>
</body></html>"""


def outgoing_rates(slug):
    """Карта лучших курсов {to_slug: rate} из данной валюты — для калькулятора на её странице."""
    out = {}
    pref = slug + ">"
    for k, v in RATES.items():
        if k.startswith(pref):
            to = k[len(pref):]
            if to in CUR:
                out[to] = v["rate"]
    return out


def converter_html(lang, preset_from="", rates=None):
    amt = res = rjson = ""
    if rates:
        amt = (f'<label class="amt">{tr(lang,"amount")}'
               f'<input id="cAmt" type="number" min="0" step="any" value="1" inputmode="decimal"></label>')
        res = '<div class="cest" id="cOut"></div>'
        rjson = (f'<script type="application/json" id="convRates" data-owner="{preset_from}">'
                 f'{json.dumps(rates, ensure_ascii=False)}</script>')
    return f"""<div class="conv dosblue dosborder" id="conv" data-from="{preset_from}" data-prefix="{PREF[lang]}" data-open="{'Open' if lang=='en' else 'Открыть'}" data-approx="{tr(lang,'approx')}">
  <h3>{tr(lang,'calc')}</h3>
  <label>{tr(lang,'give')}<select id="cFrom"></select></label>
  <button class="swap" id="cSwap" type="button">{tr(lang,'swap')}</button>
  <label>{tr(lang,'get')}<select id="cTo"></select></label>
  {amt}
  {res}
  <a class="cta" id="cGo" href="https://www.bestchange.ru/?p={REF}" target="_blank" rel="nofollow noopener sponsored">{tr(lang,'find_rate')}</a>
</div>{rjson}"""


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


def related_currencies(slug, info, lang, n=8):
    """Похожие валюты: та же категория; для крипты — приоритет той же сети. Внутренняя перелинковка."""
    cat = info["category"]
    same = [(s, i) for s, i in GROUPED.get(cat, []) if s != slug]
    if not same:
        return ""
    net = _net(info["name"])
    if net:
        same.sort(key=lambda x: (0 if _net(x[1]["name"]) == net else 1, x[1]["name"]))
    picked = same[:n]
    items = "".join(f'<li><a href="{cpage(lang, s)}">{i["name"]} <span>{i["ticker"]}</span></a></li>'
                    for s, i in picked)
    h = "Похожие валюты" if lang == "ru" else "Similar currencies"
    return f'<h2 class="news">{h}</h2><ul class="dlist">{items}</ul>'


def rate_table(slug, info, lang, n=12):
    """Живая таблица лучших курсов направлений валюты: курс + число обменников + резерв."""
    rows = []
    for ts, ti in CUR.items():
        if ts == slug:
            continue
        r = rate_of(slug, ts)
        if not r:
            continue
        rows.append((r.get("count", 0), ts, ti, r))
    if not rows:
        return ""
    rows.sort(key=lambda x: x[0], reverse=True)
    rows = rows[:n]
    if lang == "ru":
        title = f"Лучшие курсы обмена {info['ticker']}"
        h = ("Направление", "Лучший курс", "Обменников", "Резерв, всего")
        note = "Лучший курс среди обменников; резерв — суммарный по направлению. Мониторинг BestChange, обновление ежечасно. " + updated_str(lang)
        openw = "Открыть"
    else:
        title = f"Best {info['ticker']} exchange rates"
        h = ("Direction", "Best rate", "Exchangers", "Total reserve")
        note = "Best rate among exchangers; reserve is the total for the direction. BestChange monitor, hourly updates. " + updated_str(lang)
        openw = "Open"
    trs = ""
    for cnt, ts, ti, r in rows:
        trs += (f'<tr><td class="d"><a href="{bc_link(slug, ts)}" target="_blank" rel="nofollow noopener sponsored">'
                f'→ {ti["name"]} <span class="op">{ti["ticker"]}</span></a></td>'
                f'<td class="num"><b>{fmt_rate(r["rate"])}</b></td>'
                f'<td class="num">{cnt}</td>'
                f'<td class="num">{fmt_rate(r.get("reserve", 0))}</td></tr>')
    return (f'<h2 class="news">{title}</h2>'
            f'<div class="rtbl-wrap"><table class="rtbl"><thead><tr>'
            f'<th>{h[0]}</th><th>{h[1]}</th><th>{h[2]}</th><th>{h[3]}</th></tr></thead>'
            f'<tbody>{trs}</tbody></table></div>'
            f'<p class="updnote">{note}</p>')


# ---------------- страницы ----------------
def render_home(lang):
    total = len(CUR)
    cat_html = ""
    for c in CATS:
        items = "".join(f'<li><a href="{cpage(lang, slug)}">{info["name"]} <span>{info["ticker"]}</span></a></li>'
                        for slug, info in GROUPED.get(c, []))
        cat_html += (f'<h2 class="news"><a href="{cat_page(lang, c)}">{cat_name(c, lang)}</a> '
                     f'<span class="cnt">{len(GROUPED.get(c, []))}</span></h2><ul class="dlist">{items}</ul>')
    ld = jsonld({"@context": "https://schema.org", "@type": "WebSite", "name": S["name"],
                 "url": BASE_URL + PREF[lang] + "/", "inLanguage": LOCALE[lang], "description": S["tagline"]})
    org = jsonld({"@context": "https://schema.org", "@type": "Organization", "name": S["name"],
                  "url": BASE_URL, "logo": f"{BASE_URL}/assets/og-image.png",
                  "email": S.get("owner_email", ""),
                  "contactPoint": {"@type": "ContactPoint", "contactType":
                                   ("customer support" if lang == "en" else "поддержка"),
                                   "email": S.get("owner_email", "")}})
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
      <li><a href="{PREF[lang]}/vidzhet/">{tr(lang,'nav_widget')}</a></li>
      <li><a href="{PREF[lang]}/raskrytie/">{tr(lang,'nav_disc')}</a></li>
    </ul></div>
  </div>
  <div class="clearboth"></div>
</div>
{org}
{footer(lang)}"""
    write(lang, "/", head(lang, title, desc, "/", ld) + body)


def render_buy(slug, info, lang):
    """Страница покупки: все направления «источник → эта валюта» (как получить X) + CTA. SEO/конверсия."""
    name, ticker = info["name"], info["ticker"]
    path = f"/kupit/{slug}/"
    # входящие направления (источник → slug), по популярности
    incoming = []
    for ss, si in CUR.items():
        if ss == slug:
            continue
        r = rate_of(ss, slug)
        if r:
            incoming.append((r.get("count", 0), ss, si, r))
    incoming.sort(key=lambda x: x[0], reverse=True)
    get_src = "bitcoin" if slug == "tether-trc20" else "tether-trc20"
    # таблица топ-способов
    trows = ""
    for cnt, ss, si, r in incoming[:15]:
        trows += (f'<tr><td class="d"><a href="{bc_link(ss, slug)}" target="_blank" rel="nofollow noopener sponsored">'
                  f'{si["ticker"]} <span class="op">{"→ " + ticker}</span></a></td>'
                  f'<td class="num"><b>{fmt_rate(r["rate"])}</b></td><td class="num">{cnt}</td>'
                  f'<td class="num">{fmt_rate(r.get("reserve", 0))}</td></tr>')
    # полный список источников по категориям
    dir_blocks = ""
    for c in CATS:
        li = ""
        for ss, si in GROUPED.get(c, []):
            if ss == slug:
                continue
            r = rate_of(ss, slug)
            if not r:
                continue
            rr = f' <b class="rt">{fmt_rate(r["rate"])}</b>'
            li += (f'<li><a href="{bc_link(ss, slug)}" target="_blank" rel="nofollow noopener sponsored">'
                   f'{si["name"]} <span>{si["ticker"]}</span> → {ticker}{rr}</a></li>')
        if li:
            dir_blocks += f'<h2 class="news">{cat_name(c, lang)} → {ticker}</h2><ul class="dlist">{li}</ul>'
    if lang == "ru":
        title = f"Купить {name} ({ticker}) — где и как получить, курсы | {S['name']}"
        desc = (f"Как купить {name} ({ticker}): все направления обмена на {ticker} с курсами из мониторинга "
                f"BestChange. Получить {ticker} за USDT, рубли, другую крипту.")
        h1 = f"Купить {name}"
        intro = (f"Справочник направлений, где можно <b>получить {name} ({ticker})</b>: обмен из других валют "
                 f"с курсами из мониторинга <b>BestChange</b>. Выберите, чем платите, ниже.")
        tt = ("Отдаёте", "Курс", "Обменников", "Резерв, всего")
        howh = f"Как купить {name}"
        steps = [f"Выберите, что отдаёте, в таблице или списке ниже.",
                 "В BestChange сравните курс, резерв и рейтинг обменников.",
                 f'Проверьте адрес получения {ticker}; для крупной суммы — <a href="{PREF[lang]}/aml/">AML-проверка</a>.',
                 f"Проведите обмен и получите {ticker} на свой кошелёк/счёт."]
        q1, a1 = f"Как выгоднее купить {name}?", f"Сравните направления по курсу и резерву в мониторинге BestChange и учтите комиссию сети. Часто выгодно покупать {ticker} за USDT."
        q2, a2 = f"Где получить {name} за рубли?", f"Выберите направление с рублёвым источником (карта/СБП/наличные) → {ticker} в списке ниже."
        back = f'<a href="{cpage(lang, slug)}">Обмен {name} (продать/все направления) →</a>'
        note = "Лучший курс среди обменников; резерв — суммарный. " + updated_str(lang)
    else:
        title = f"Buy {name} ({ticker}) — where and how to get it, rates | {S['name']}"
        desc = (f"How to buy {name} ({ticker}): all exchange directions to {ticker} with rates from BestChange "
                f"monitoring. Get {ticker} for USDT, rubles or other crypto.")
        h1 = f"Buy {name}"
        intro = (f"A directory of directions where you can <b>get {name} ({ticker})</b>: exchange from other "
                 f"currencies with rates from the <b>BestChange</b> monitor. Choose what you pay with below.")
        tt = ("You send", "Rate", "Exchangers", "Total reserve")
        howh = f"How to buy {name}"
        steps = [f"Choose what you send in the table or list below.",
                 "On BestChange compare rate, reserve and exchanger rating.",
                 f'Check the receiving {ticker} address; for a large amount — an <a href="{PREF[lang]}/aml/">AML check</a>.',
                 f"Complete the exchange and receive {ticker} to your wallet/account."]
        q1, a1 = f"How to buy {name} cheaper?", f"Compare directions by rate and reserve in the BestChange monitor and factor in the network fee. Buying {ticker} for USDT is often favorable."
        q2, a2 = f"Where to get {name} for rubles?", f"Pick a direction with a ruble source (card/SBP/cash) → {ticker} in the list below."
        back = f'<a href="{cpage(lang, slug)}">Exchange {name} (sell / all directions) →</a>'
        note = "Best rate among exchangers; reserve is the total. " + updated_str(lang)
    get_btn = (f'<a class="cta cta-get" href="{bc_link(get_src, slug)}" target="_blank" '
               f'rel="nofollow noopener sponsored">{tr(lang,"get_cta")} {name} →</a>')
    table_html = (f'<div class="rtbl-wrap"><table class="rtbl"><thead><tr>'
                  f'<th>{tt[0]}</th><th>{tt[1]}</th><th>{tt[2]}</th><th>{tt[3]}</th></tr></thead>'
                  f'<tbody>{trows}</tbody></table></div><p class="updnote">{note}</p>') if trows else ""
    faq = jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q1, "acceptedAnswer": {"@type": "Answer", "text": a1}},
        {"@type": "Question", "name": q2, "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", a2)}}]})
    crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": tr(lang, "monitor"), "item": BASE_URL + PREF[lang] + "/"},
        {"@type": "ListItem", "position": 2, "name": h1, "item": BASE_URL + PREF[lang] + path}]})
    crumbs += jsonld({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                      "url": BASE_URL + PREF[lang] + path, "inLanguage": LOCALE[lang], "dateModified": modified_iso()})
    steps_html = "".join(f"<li>{s}</li>" for s in steps)
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {h1}</nav>
    <h1>{h1} <span class="tk">{ticker}</span></h1>
    <p>{intro}</p>
    <p class="getcta">{get_btn}</p>
    {table_html}
    <h2 class="news">{howh}</h2>
    <ol class="steps">{steps_html}</ol>
    {howto_ld(howh, steps)}
    <p class="related">{back}</p>
    {dir_blocks}
    <h2 class="news">{tr(lang,'faq')}</h2>
    <details><summary>{q1}</summary><p>{a1}</p></details>
    <details><summary>{q2}</summary><p>{a2}</p></details>
  </div>
</div>
{faq}{crumbs}
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path) + body)


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
                     f'→ {ti["name"]} <span>{ti["ticker"]}</span>{rr}</a></li>')
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
    crumbs += jsonld({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                      "url": BASE_URL + PREF[lang] + path, "inLanguage": LOCALE[lang],
                      "dateModified": modified_iso()})
    steps_html = "".join(f"<li>{s}</li>" for s in steps)
    get_btn = f'<a class="cta cta-get" href="{PREF[lang]}/kupit/{slug}/">{tr(lang,"get_cta")} {name} →</a>'
    _h = HISTORY.get(slug, [])
    getspark = ""
    if len(_h) >= 2:
        _v = [p[1] for p in _h]
        _chg = (_v[-1] - _v[0]) / _v[0] * 100 if _v[0] else 0
        _cls = "up" if _chg >= 0 else "down"
        _sign = "+" if _chg >= 0 else ""
        _lbl = "Полный график ниже" if lang == "ru" else "Full chart below"
        getspark = (f'<a class="getspark" href="#chart" title="{_lbl}">{mini_spark(_h[-90:])}'
                    f'<span class="chgpill {_cls}">{_sign}{_chg:.1f}%</span></a>')
    hub_cta = ""
    if slug in BANK_HUB_SET:
        hub_cta = (f'<p class="related"><a href="{PREF[lang]}/na/{slug}/">'
                   + (f'→ Обмен криптовалюты на {name} (все монеты)' if lang == "ru"
                      else f'→ Exchange crypto to {name} (all coins)') + '</a></p>')
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {name} <span class="tk">{ticker}</span></nav>
    <h1>{'Exchange' if lang=='en' else 'Обмен'} {name} <span class="tk">{ticker}</span></h1>
    <p>{intro}</p>
    <div class="getcta">{get_btn}{getspark}</div>
    {hub_cta}
    {about_currency(slug, info, lang)}
    {currency_chart(slug, info, lang)}
    {rate_table(slug, info, lang)}
    {popular_block(slug, lang)}
    <h2 class="news">{tr(lang,'directions')} {ticker}</h2>
    {dir_blocks}
    <h2 class="news">{tr(lang,'how_to')} {name}</h2>
    <ol class="steps">{steps_html}</ol>
    {howto_ld(tr(lang,'how_to') + ' ' + name, steps)}
    <h2 class="news">{tr(lang,'faq')}</h2>
    <details><summary>{faq_q1}</summary><p>{faq_a1}</p></details>
    <details><summary>{faq_q2}</summary><p>{faq_a2}</p></details>
    {related_currencies(slug, info, lang)}
  </div>
  <div id="sidebar">
    {converter_html(lang, slug, outgoing_rates(slug))}
    {search_box(lang)}
    <div class="sblock"><h3>{tr(lang,'sections')}</h3><ul>
      <li><a href="{PREF[lang]}/">{tr(lang,'all_cur')}</a></li>
      <li><a href="{PREF[lang]}/aml/">{tr(lang,'nav_aml')}</a></li>
      <li><a href="{PREF[lang]}/o-servise/">{tr(lang,'nav_about')}</a></li>
      <li><a href="{PREF[lang]}/vidzhet/">{tr(lang,'nav_widget')}</a></li>
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
        rev = f'<a href="{pair_url(lang, t, f)}">Обратный обмен: {tN} → {fN}</a> · ' if (t, f) in PAIR_SET else ""
        hub = f'<a href="{PREF[lang]}/na/{t}/">Все монеты → {tN}</a> · ' if t in BANK_HUB_SET else ""
        rel = f'{rev}{hub}<a href="{cpage(lang, f)}">О валюте {fN}</a> · <a href="{cpage(lang, t)}">О валюте {tN}</a>'
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
        rev = f'<a href="{pair_url(lang, t, f)}">Reverse: {tN} → {fN}</a> · ' if (t, f) in PAIR_SET else ""
        hub = f'<a href="{PREF[lang]}/na/{t}/">All coins → {tN}</a> · ' if t in BANK_HUB_SET else ""
        rel = f'{rev}{hub}<a href="{cpage(lang, f)}">About {fN}</a> · <a href="{cpage(lang, t)}">About {tN}</a>'
        q1 = f"What is the {fN} to {tN} rate?"
        a1 = (f"Best value — <b>{fmt_rate(r['rate'])} {tT}</b> per 1 {fT} across {r['count']} exchangers. For reference, it changes." if r else "The rate is confirmed in the BestChange monitor.")
        q2, a2 = "Is it safe?", "The exchange runs in offices from BestChange monitoring with ratings and reserves. For crypto an address AML check is recommended."
    faq = jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q1, "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", a1)}},
        {"@type": "Question", "name": q2, "acceptedAnswer": {"@type": "Answer", "text": a2}}]})
    crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": tr(lang, "monitor"), "item": BASE_URL + PREF[lang] + "/"},
        {"@type": "ListItem", "position": 2, "name": f"{fT} → {tT}", "item": BASE_URL + PREF[lang] + path}]})
    crumbs += jsonld({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                      "url": BASE_URL + PREF[lang] + path, "inLanguage": LOCALE[lang],
                      "dateModified": modified_iso()})
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
    {howto_ld(h_how, steps)}
    <p class="related">{rel} · <a href="{PREF[lang]}/blog/slovar-terminov-obmena/">{tr(lang,'glossary')}</a></p>
    {(lambda ps: (f'<h2 class="news">{("Другие направления " if lang=="ru" else "Other directions for ")+fT}</h2>'
                  f'<ul class="dlist">{"".join(pair_link_li(p, lang) for p in ps)}</ul>') if ps else "")(
        [p for p in popular_involving(f) if not (p["from"]==f and p["to"]==t)][:6])}
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


def blog_page_path(lang, p):
    return f"{PREF[lang]}/blog/" if p == 1 else f"{PREF[lang]}/blog/page/{p}/"


def pager_html(lang, cur, pages):
    if pages <= 1:
        return ""
    parts = []
    if cur > 1:
        parts.append(f'<a class="pg-nav" href="{blog_page_path(lang, cur-1)}" rel="prev">←</a>')
    for p in range(1, pages + 1):
        if p == cur:
            parts.append(f'<span class="pg-cur">{p}</span>')
        else:
            parts.append(f'<a href="{blog_page_path(lang, p)}">{p}</a>')
    if cur < pages:
        parts.append(f'<a class="pg-nav" href="{blog_page_path(lang, cur+1)}" rel="next">→</a>')
    return f'<nav class="pager" aria-label="pagination">{"".join(parts)}</nav>'


def render_blog(lang):
    arts = ARTS[lang]
    if not arts:
        return
    def dsearch(a):
        return (a["title"] + " " + a.get("description", "") + " " + a["slug"]).lower().replace('"', "&quot;")
    # индекс ВСЕХ статей для сквозного поиска (встраивается в каждую страницу блога, ~15 записей)
    index = [{"t": a["title"], "d": a.get("description", ""), "dt": a.get("date", ""),
              "u": f"{PREF[lang]}/blog/{a['slug']}/",
              "k": (a["title"] + " " + a.get("description", "") + " " + a["slug"]).lower()} for a in arts]
    index_script = ('<script type="application/json" id="blogIndex">'
                    + json.dumps(index, ensure_ascii=False).replace("</", "<\\/") + '</script>')
    pages = (len(arts) + BLOG_PER_PAGE - 1) // BLOG_PER_PAGE
    if lang == "ru":
        base_title = f"Блог — гайды по обмену криптовалют и валют | {S['name']}"
        desc = "Статьи и гайды: сети USDT, комиссии, AML-проверка, словарь терминов обмена."
        h1, lead = "Блог", "Справочные материалы и гайды об обмене криптовалют и валют."
    else:
        base_title = f"Blog — crypto and currency exchange guides | {S['name']}"
        desc = "Articles and guides: USDT networks, fees, AML check, exchange glossary."
        h1, lead = "Blog", "Reference materials and guides on crypto and currency exchange."
    for p in range(1, pages + 1):
        path = ("/blog/" if p == 1 else f"/blog/page/{p}/")
        chunk = arts[(p - 1) * BLOG_PER_PAGE: p * BLOG_PER_PAGE]
        cards = "".join(
            f'<li data-search="{dsearch(a)}"><a href="{PREF[lang]}/blog/{a["slug"]}/">{a["title"]}</a>'
            f'<div class="apreview">{a.get("description","")}</div><div class="adate">{a.get("date","")}</div></li>'
            for a in chunk)
        title = base_title if p == 1 else (
            f"Блог, страница {p} | {S['name']}" if lang == "ru" else f"Blog, page {p} | {S['name']}")
        ld = jsonld({"@context": "https://schema.org", "@type": "Blog", "name": f"{S['name']} Blog",
                     "url": f"{BASE_URL}{PREF[lang]}/blog/"})
        ld += (f'\n<link rel="alternate" type="application/rss+xml" '
               f'title="{S["name"]} {"блог" if lang=="ru" else "blog"} RSS" '
               f'href="{PREF[lang]}/blog/rss.xml">')
        if p > 1:
            ld += f'\n<link rel="prev" href="{blog_page_path(lang, p-1)}">'
        if p < pages:
            ld += f'\n<link rel="next" href="{blog_page_path(lang, p+1)}">'
        pageinfo = "" if p == 1 else (f' <span class="pg-of">— страница {p} из {pages}</span>' if lang == "ru"
                                      else f' <span class="pg-of">— page {p} of {pages}</span>')
        body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / <a href="{PREF[lang]}/blog/">{h1}</a></nav>
    <h1>{h1}{pageinfo}</h1><p>{lead}</p>
    <div id="blogsearch" class="dosblue dosborder">
      <h3>{tr(lang,'blog_search_ph').rstrip('…')}</h3>
      <input id="bq" type="search" placeholder="{tr(lang,'blog_search_ph')}" autocomplete="off" aria-label="{tr(lang,'blog_search_ph')}">
    </div>
    <ul class="bloglist" id="bloglist">{cards}</ul>
    <p id="bnores" class="related" hidden>{tr(lang,'blog_noresults')}</p>
    {pager_html(lang, p, pages)}
    {index_script}
  </div>
</div>
{ld}
{footer(lang)}"""
        write(lang, path, head(lang, title, desc, path, ld) + body)


def render_rss(lang):
    arts = ARTS[lang]
    if not arts:
        return
    base = BASE_URL + PREF[lang]
    self_url = f"{base}/blog/rss.xml"
    ttl = f"{S['name']} — блог" if lang == "ru" else f"{S['name']} — Blog"
    dsc = ("Гайды по обмену криптовалют и валют." if lang == "ru"
           else "Guides on crypto and currency exchange.")
    items = ""
    for a in arts:
        try:
            y, m, d = (int(x) for x in a.get("date", "").split("-"))
            pub = format_datetime(datetime(y, m, d, tzinfo=timezone.utc))
        except (ValueError, TypeError):
            pub = ""
        url = f"{base}/blog/{a['slug']}/"
        items += (f"<item><title>{xml_escape(a['title'])}</title>"
                  f"<link>{url}</link><guid isPermaLink=\"true\">{url}</guid>"
                  + (f"<pubDate>{pub}</pubDate>" if pub else "")
                  + f"<description>{xml_escape(a.get('description',''))}</description></item>")
    rss = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
           f'<title>{xml_escape(ttl)}</title><link>{base}/blog/</link>'
           f'<description>{xml_escape(dsc)}</description><language>{LOCALE[lang]}</language>'
           f'<atom:link href="{self_url}" rel="self" type="application/rss+xml"/>'
           f'{items}</channel></rss>')
    full = os.path.join(DIST, (PREF[lang] + "/blog/rss.xml").strip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8").write(rss)


def render_article(a, lang):
    path = f"/blog/{a['slug']}/"
    title = f"{a['title']} | {S['name']}"
    desc = a.get("description", "")
    art_ld = jsonld({"@context": "https://schema.org", "@type": "Article", "headline": a["title"],
                     "description": desc, "datePublished": a.get("date", ""),
                     "dateModified": a.get("modified", a.get("date", "")), "inLanguage": LOCALE[lang],
                     "author": {"@type": "Organization", "name": S["name"]},
                     "publisher": {"@type": "Organization", "name": S["name"],
                                   "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/assets/og-image.png"}},
                     "mainEntityOfPage": BASE_URL + PREF[lang] + path})
    back = "← All articles" if lang == "en" else "← Все статьи"
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / <a href="{PREF[lang]}/blog/">{tr(lang,'nav_blog')}</a> / {a['title']}</nav>
    <article class="post"><div class="adate">{'Опубликовано' if lang=='ru' else 'Published'}: {a.get('date','')} · <a href="{PREF[lang]}/redakciya/">{'Редакция ' if lang=='ru' else 'Editorial · '}{S['name']}</a></div>{a['html']}</article>
    <p><a href="{PREF[lang]}/blog/">{back}</a></p>
  </div>
</div>
{art_ld}
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path) + body)


FAQ_ITEMS = {
    "ru": [
        ("Какая сеть USDT самая дешёвая для перевода?",
         "Обычно TRC20 (TRON) — низкая и стабильная комиссия сети. BEP20 (BNB Smart Chain) тоже дешёвый. "
         "ERC20 (Ethereum) дороже, комиссия зависит от загрузки сети. Сеть отправителя и получателя должна совпадать."),
        ("Сколько идёт перевод USDT?",
         "В сети TRC20 перевод обычно приходит за 1–5 минут после подтверждений. Скорость зависит от сети и её загрузки, "
         "а также от числа подтверждений, которое требует получатель или обменник."),
        ("Что такое резерв обменника?",
         "Резерв — сколько валюты доступно у обменника по конкретному направлению прямо сейчас. Если резерв меньше вашей "
         "суммы, обмен не пройдёт или займёт время. Резерв смотрят вместе с курсом и рейтингом."),
        ("Чем обменник отличается от биржи?",
         "Обменник проводит операцию по фиксированному курсу и резерву — быстро и без регистрации ордеров. Биржа — это "
         "торговая площадка со стаканом заявок, где цену формируют покупатели и продавцы. Для разового обмена обычно берут обменник."),
        ("Как выбрать лучший курс обмена?",
         "Смотрите не только на верхний курс, но и на резерв, рейтинг и отзывы обменника, а также лимиты и комиссию сети. "
         "Слишком выгодный курс иногда означает маленький резерв или скрытые условия. Сравнить помогает мониторинг BestChange."),
        ("Что такое AML-проверка криптоадреса?",
         "AML-проверка оценивает связь адреса или транзакции с мошенничеством, даркнетом и санкциями. Её делают до приёма "
         "или обмена крупной суммы, чтобы снизить риск получить «грязные» монеты и блокировку средств."),
        ("Безопасен ли обмен криптовалюты через обменник?",
         "Риск снижается, если выбирать обменник с высоким рейтингом, историей и достаточным резервом из мониторинга, а для "
         "криптовалюты делать AML-проверку адреса. Гарантий не даёт никто — решение об обмене вы принимаете самостоятельно."),
        ("Что такое СБП и при чём тут обмен?",
         "СБП — Система быстрых платежей Банка России: мгновенные переводы между банками по номеру телефона. Многие обменники "
         "выдают рубли через СБП — это быстро и удобно; учитывайте лимиты вашего банка."),
    ],
    "en": [
        ("Which USDT network is the cheapest for transfers?",
         "Usually TRC20 (TRON) — a low, stable network fee. BEP20 (BNB Smart Chain) is also cheap. ERC20 (Ethereum) is "
         "pricier and its fee depends on network load. The sender's and recipient's network must match."),
        ("How long does a USDT transfer take?",
         "On TRC20 a transfer usually arrives within 1–5 minutes after confirmations. Speed depends on the network and its "
         "load, and on how many confirmations the recipient or exchanger requires."),
        ("What is an exchanger's reserve?",
         "Reserve is how much currency an exchanger has available for a given direction right now. If the reserve is smaller "
         "than your amount, the exchange won't go through or will take time. Check reserve together with the rate and rating."),
        ("How is an exchanger different from an exchange?",
         "An exchanger completes the operation at a fixed rate and reserve — fast and without placing orders. An exchange is "
         "a trading venue with an order book where buyers and sellers set the price. For a one-off swap people usually pick an exchanger."),
        ("How do I choose the best exchange rate?",
         "Look not only at the top rate but also at the exchanger's reserve, rating and reviews, plus limits and the network "
         "fee. A rate that's too good can mean a small reserve or hidden terms. The BestChange monitor helps compare."),
        ("What is a crypto address AML check?",
         "An AML check assesses an address or transaction for links to fraud, darknet and sanctions. It's done before "
         "receiving or exchanging a large amount to reduce the risk of getting 'dirty' coins and frozen funds."),
        ("Is exchanging crypto through an exchanger safe?",
         "Risk is lower if you pick an exchanger with a high rating, history and sufficient reserve from a monitor, and do an "
         "address AML check for crypto. No one guarantees anything — you decide to exchange on your own."),
        ("What is SBP and how does it relate to exchanging?",
         "SBP is Russia's Faster Payments System: instant transfers between banks by phone number. Many exchangers pay out "
         "rubles via SBP — fast and convenient; mind your bank's limits."),
    ],
}


def render_faq(lang):
    items = FAQ_ITEMS[lang]
    path = "/faq/"
    if lang == "ru":
        title = f"Частые вопросы об обмене криптовалют и валют | {S['name']}"
        desc = "Ответы на частые вопросы: сети USDT и комиссии, резерв, AML-проверка, СБП, как выбрать обменник и лучший курс."
        h1, lead = "Частые вопросы", "Короткие ответы на популярные вопросы об обмене криптовалют и валют."
    else:
        title = f"Frequently asked questions about crypto and currency exchange | {S['name']}"
        desc = "Answers to common questions: USDT networks and fees, reserve, AML check, SBP, how to choose an exchanger and the best rate."
        h1, lead = "Frequently asked questions", "Short answers to popular questions about crypto and currency exchange."
    qa = "".join(f'<details><summary>{q}</summary><p>{a}</p></details>' for q, a in items)
    faq_ld = jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]})
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {h1}</nav>
    <h1>{h1}</h1><p>{lead}</p>
    {qa}
  </div>
</div>
{faq_ld}
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path, faq_ld) + body)


def render_category(cat, lang):
    slug = CAT_SLUG.get(cat, "prochee")
    path = f"/kategoriya/{slug}/"
    curs = GROUPED.get(cat, [])
    if not curs:
        return
    cname = cat_name(cat, lang)
    intro = CAT_INTRO.get(cat, ("", ""))[0 if lang == "ru" else 1]
    items = "".join(f'<li><a href="{cpage(lang, s)}">{i["name"]} <span>{i["ticker"]}</span></a></li>'
                    for s, i in curs)
    if lang == "ru":
        title = f"{cname} — обмен: курсы и все направления ({len(curs)}) | {S['name']}"
        desc = f"{cname} для обмена: {len(curs)} направлений, курсы из мониторинга BestChange, калькулятор, все направления обмена."
        h1 = f"Обмен: {cname}"
        q1, a1 = f"Сколько {cname.lower()} доступно для обмена?", f"В каталоге {len(curs)} направлений категории «{cname}». На странице каждого — курсы всех направлений обмена."
        listh = f"Все направления категории «{cname}»"
    else:
        title = f"{cname} — exchange: rates and all directions ({len(curs)}) | {S['name']}"
        desc = f"{cname} for exchange: {len(curs)} directions, rates from BestChange monitoring, calculator, all exchange directions."
        h1 = f"Exchange: {cname}"
        q1, a1 = f"How many {cname.lower()} are available to exchange?", f"The catalog has {len(curs)} directions in the “{cname}” category. Each page lists rates for all exchange directions."
        listh = f"All directions in “{cname}”"
    faq_ld = jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q1, "acceptedAnswer": {"@type": "Answer", "text": a1}}]})
    crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": tr(lang, "monitor"), "item": BASE_URL + PREF[lang] + "/"},
        {"@type": "ListItem", "position": 2, "name": cname, "item": BASE_URL + PREF[lang] + path}]})
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {cname}</nav>
    <h1>{h1} <span class="cnt">{len(curs)}</span></h1>
    <div class="dosblue dosborder">{intro}</div>
    <h2 class="news">{listh}</h2>
    <ul class="dlist">{items}</ul>
    <h2 class="news">{tr(lang,'faq')}</h2>
    <details><summary>{q1}</summary><p>{a1}</p></details>
  </div>
</div>
{faq_ld}{crumbs}{itemlist_ld([(i["name"], BASE_URL + cpage(lang, s)) for s, i in curs])}
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path) + body)


def _gterm(t, lang):
    return t["ru"] if lang == "ru" else t["en"]


def _gdef(t, lang):
    return t["def_ru"] if lang == "ru" else t["def_en"]


def render_widget_page(lang):
    """Страница /vidzhet/ — галерея виджетов (курс + конвертер): код для вставки + живое демо."""
    path = "/vidzhet/"
    def esc(c):
        return c.replace("<", "&lt;").replace(">", "&gt;")
    code_rate = ('<div class="ratescout-widget" data-pair="usdt-rub"></div>\n'
                 '<script src="' + BASE_URL + '/widget.js" async></script>')
    code_conv = ('<div class="ratescout-widget" data-widget="converter"></div>\n'
                 '<script src="' + BASE_URL + '/widget.js" async></script>')
    pairs_list = ", ".join(f"<code>{k}</code>" for k, *_ in WIDGET_PAIRS)
    if lang == "ru":
        title = f"Виджеты курсов и конвертер для сайта — бесплатно | {S['name']}"
        desc = "Бесплатные встраиваемые виджеты для сайта: живой курс обмена и мини-конвертер криптовалют. Вставьте код — обновляется автоматически."
        h1 = "Виджеты для вашего сайта"
        lead = ("Разместите на своём сайте живой курс или мини-конвертер обмена — обновляются автоматически, "
                "бесплатно. Достаточно вставить код в HTML страницы.")
        t_rate, t_conv, h_pairs, h_how = "Виджет курса", "Виджет-конвертер (ввод суммы)", "Доступные пары (data-pair)", "Как это работает"
        t_cfg, cfg_lead, l_give, l_get = "Конструктор виджета — любая пара", "Выберите любую пару из каталога проекта — получите готовый код и предпросмотр.", "Отдаю", "Получаю"
        how = ["Скопируйте код нужного виджета и вставьте в HTML страницы.",
               "Курс: <code>data-pair</code> (популярная) или <code>data-from</code>+<code>data-to</code> (любая пара). Конвертер: <code>data-widget=\"converter\"</code>.",
               "Скрипт сам подтянет актуальные курсы и обновит виджет.",
               "Несколько виджетов на странице — вставьте несколько блоков <code>div</code>."]
    else:
        title = f"Rate and converter widgets for your site — free | {S['name']}"
        desc = "Free embeddable widgets for your site: a live exchange rate and a mini crypto converter. Paste the code — updates automatically."
        h1 = "Widgets for your website"
        lead = ("Put a live rate or a mini exchange converter on your site — they update automatically, for free. "
                "Just paste the code into your page's HTML.")
        t_rate, t_conv, h_pairs, h_how = "Rate widget", "Converter widget (amount input)", "Available pairs (data-pair)", "How it works"
        t_cfg, cfg_lead, l_give, l_get = "Widget builder — any pair", "Pick any pair from the project catalog — get ready code and a preview.", "From", "To"
        how = ["Copy the code of the widget you want and paste it into your page's HTML.",
               "Rate: <code>data-pair</code> (popular) or <code>data-from</code>+<code>data-to</code> (any pair). Converter: <code>data-widget=\"converter\"</code>.",
               "The script pulls current rates and updates the widget.",
               "For several widgets on a page — add several <code>div</code> blocks."]
    how_html = "".join(f"<li>{s}</li>" for s in how)
    demo_style = "padding:14px;background:#0d0d0d;border:1px solid #333;margin:0 0 12px"
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {h1}</nav>
    <h1>{h1}</h1><p>{lead}</p>

    <h2 class="news">{t_cfg}</h2>
    <p>{cfg_lead}</p>
    <div class="conv dosblue dosborder" style="max-width:420px">
      <label>{l_give}<select id="cfgFrom"></select></label>
      <label>{l_get}<select id="cfgTo"></select></label>
    </div>
    <div style="{demo_style}"><div id="cfgPreview"></div></div>
    <pre class="code-embed"><code id="cfgCode"></code></pre>
    <script>
    (function(){{
      var fromS=document.getElementById('cfgFrom'),toS=document.getElementById('cfgTo'),
          prev=document.getElementById('cfgPreview'),code=document.getElementById('cfgCode');
      if(!fromS)return;
      var CARD="font:13px/1.4 system-ui,Arial,sans-serif;display:inline-block;border:1px solid #d0d5dd;border-radius:8px;padding:10px 14px;background:#fff;color:#111;min-width:210px";
      var LBL="font-size:11px;color:#667085;text-transform:uppercase;letter-spacing:.04em";
      var BIG="font-size:20px;font-weight:700;margin:2px 0";
      var LINK="color:#0a66c2;text-decoration:none;font-weight:600";
      var ATTR="display:block;margin-top:6px;font-size:11px;color:#98a2b3;text-decoration:none";
      function num(v){{v=parseFloat(String(v).replace(/\\s/g,''));return isNaN(v)?0:v;}}
      function fmt(v){{if(v>=1000)return v.toLocaleString('ru-RU',{{maximumFractionDigits:0}});if(v>=1)return v.toLocaleString('ru-RU',{{maximumFractionDigits:2}});return v.toFixed(6).replace(/0+$/,'').replace(/\\.$/,'');}}
      fetch('/widget-rates.json').then(function(r){{return r.json();}}).then(function(d){{
        var cur=d.cur,slugs=Object.keys(cur).sort(function(a,b){{return cur[a].n.localeCompare(cur[b].n);}});
        var opts=slugs.map(function(s){{return '<option value="'+s+'">'+cur[s].n+' ('+cur[s].t+')</option>';}}).join('');
        fromS.innerHTML=opts;toS.innerHTML=opts;
        if(cur['bitcoin'])fromS.value='bitcoin';if(cur['sberbank'])toS.value='sberbank';
        function upd(){{
          var f=fromS.value,t=toS.value,cf=cur[f],ct=cur[t],r=d.rates[f]&&d.rates[f][t];
          var rate=r?fmt(num(r)):'—';
          prev.innerHTML='<div style="'+CARD+'"><div style="'+LBL+'">'+cf.t+' → '+ct.t+'</div>'+
            '<div style="'+BIG+'">1 '+cf.t+' = '+rate+' '+ct.t+'</div>'+
            '<a href="{BASE_URL}/valuta/'+f+'/" target="_blank" rel="noopener" style="'+LINK+'">Обменять →</a>'+
            '<a href="{BASE_URL}/" target="_blank" rel="noopener" style="'+ATTR+'">Курсы: RateScout</a></div>';
          code.textContent='<div class="ratescout-widget" data-from="'+f+'" data-to="'+t+'"></div>\\n<script src="{BASE_URL}/widget.js" async><\\/script>';
        }}
        fromS.addEventListener('change',upd);toS.addEventListener('change',upd);upd();
      }}).catch(function(){{}});
    }})();
    </script>

    <h2 class="news">{t_conv}</h2>
    <div style="{demo_style}"><div class="ratescout-widget" data-widget="converter"></div></div>
    <pre class="code-embed"><code>{esc(code_conv)}</code></pre>

    <h2 class="news">{h_pairs}</h2>
    <p class="related">{pairs_list}</p>
    <h2 class="news">{h_how}</h2>
    <ol class="steps">{how_html}</ol>
    <script src="/widget.js" async></script>
  </div>
</div>
{footer(lang)}"""
    write(lang, path, head(lang, title, desc, path) + body)


def render_glossary(lang):
    if not GLOSSARY:
        return
    terms = sorted(GLOSSARY, key=lambda t: _gterm(t, lang).lower())
    # индекс /slovar/
    lidx = "".join(f'<li><a href="{PREF[lang]}/slovar/{t["slug"]}/">{_gterm(t, lang)}</a>'
                   f'<div class="apreview">{_gdef(t, lang)[:110]}…</div></li>' for t in terms)
    if lang == "ru":
        it, idesc = "Словарь терминов обмена криптовалют и валют", "Понятные определения терминов обмена: курс, резерв, спред, сеть, комиссия, AML, KYC, стейблкоин, эскроу и другие."
        ih1, ilead = "Словарь терминов", "Короткие понятные определения терминов, которые встречаются при обмене криптовалют и валют."
    else:
        it, idesc = "Glossary of crypto and currency exchange terms", "Clear definitions of exchange terms: rate, reserve, spread, network, fee, AML, KYC, stablecoin, escrow and more."
        ih1, ilead = "Glossary", "Short, clear definitions of the terms you meet when exchanging crypto and currencies."
    ild = jsonld({"@context": "https://schema.org", "@type": "DefinedTermSet", "name": ih1,
                  "url": f"{BASE_URL}{PREF[lang]}/slovar/"})
    ibody = f"""{header(lang, "/slovar/")}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {ih1}</nav>
    <h1>{ih1} <span class="cnt">{len(terms)}</span></h1><p>{ilead}</p>
    <ul class="bloglist">{lidx}</ul>
  </div>
</div>
{ild}
{footer(lang)}"""
    write(lang, "/slovar/", head(lang, f"{it} | {S['name']}", idesc, "/slovar/", ild) + ibody)
    # страницы терминов
    for t in GLOSSARY:
        term, dfn, path = _gterm(t, lang), _gdef(t, lang), f"/slovar/{t['slug']}/"
        see = [GLOSSARY_BY[s] for s in t.get("see", []) if s in GLOSSARY_BY]
        see_html = ("".join(f'<li><a href="{PREF[lang]}/slovar/{s["slug"]}/">{_gterm(s, lang)}</a></li>' for s in see))
        seeh = ("См. также" if lang == "ru" else "See also")
        allh = ("Все термины" if lang == "ru" else "All terms")
        title = f"{term} — что это простыми словами | {S['name']}" if lang == "ru" else f"{term} — meaning explained | {S['name']}"
        desc = (dfn[:155]).rsplit(" ", 1)[0] + "…"
        dt_ld = jsonld({"@context": "https://schema.org", "@type": "DefinedTerm", "name": term,
                        "description": dfn, "inDefinedTermSet": f"{BASE_URL}{PREF[lang]}/slovar/",
                        "url": BASE_URL + PREF[lang] + path})
        crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": tr(lang, "monitor"), "item": BASE_URL + PREF[lang] + "/"},
            {"@type": "ListItem", "position": 2, "name": ("Словарь" if lang == "ru" else "Glossary"), "item": BASE_URL + PREF[lang] + "/slovar/"},
            {"@type": "ListItem", "position": 3, "name": term, "item": BASE_URL + PREF[lang] + path}]})
        body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / <a href="{PREF[lang]}/slovar/">{'Словарь' if lang=='ru' else 'Glossary'}</a> / {term}</nav>
    <h1>{term}</h1>
    <div class="dosblue dosborder">{dfn}</div>
    {f'<h2 class="news">{seeh}</h2><ul class="dlist">{see_html}</ul>' if see_html else ''}
    <p class="related"><a href="{PREF[lang]}/slovar/">← {allh}</a> · <a href="{PREF[lang]}/faq/">{tr(lang,'nav_faq')}</a> · <a href="{PREF[lang]}/">{tr(lang,'all_cur')}</a></p>
  </div>
</div>
{dt_ld}{crumbs}
{footer(lang)}"""
        write(lang, path, head(lang, title, desc, path) + body)


def render_editorial(lang):
    """Страница «О редакции» — сигналы доверия (E-E-A-T) для YMYL-ниши."""
    owner = S.get("owner", "")
    email = S.get("owner_email", "")
    if lang == "ru":
        title = "О редакции RateScout — кто ведёт сайт и как мы работаем"
        desc = "Редакция RateScout: независимый справочник курсов обмена. Принципы, источники данных, обновление и контакты."
        body = f"""<h1>О редакции RateScout</h1>
<p><b>RateScout</b> — независимый информационный справочник курсов обмена криптовалют и валют. Мы не обменный
   пункт и не проводим операции: наша задача — собрать и понятно показать данные, чтобы вы приняли решение сами.</p>
<h2>Как мы работаем</h2>
<ul>
  <li><b>Источник данных</b> — мониторинг обменных пунктов <a href="{PREF[lang]}/o-servise/">BestChange</a>:
      курсы, резервы и число обменников. Курсы на сайте обновляются <b>ежечасно</b>.</li>
  <li><b>Нейтральность.</b> Мы не оцениваем обменники субъективно и не даём финансовых рекомендаций — только справочные данные.</li>
  <li><b>Прозрачность.</b> Ссылки на обмен ведут в BestChange; по партнёрской программе мы можем получать
      вознаграждение (<a href="{PREF[lang]}/raskrytie/">раскрытие</a>).</li>
  <li><b>Актуальность.</b> Гайды и справочные страницы поддерживаются в актуальном состоянии; на страницах
      курсов указано время последнего обновления.</li>
</ul>
<h2>Для кого это</h2>
<p>Для тех, кто обменивает криптовалюту и валюты и хочет быстро сориентироваться в курсах, сетях, комиссиях и
   безопасности (включая <a href="{PREF[lang]}/blog/chto-takoe-aml-proverka/">AML-проверку</a>).</p>
<h2>Владелец и контакты</h2>
<p>Владелец сайта: {S.get('owner_status','')} <b>{owner}</b>, ИНН {S.get('owner_inn','')}. Вопросы, уточнения,
   сообщения об ошибках в данных — на <a href="mailto:{email}">{email}</a>. Мы за обратную связь: если заметили
   неточность в курсе или тексте — напишите, поправим.</p>
<p class="related"><a href="{PREF[lang]}/raskrytie/">Раскрытие и дисклеймеры</a> ·
   <a href="{PREF[lang]}/politika/">Политика конфиденциальности</a></p>"""
        crumb = "О редакции"
    else:
        title = "About the RateScout editorial team — who runs the site and how"
        desc = "RateScout editorial team: an independent rate directory. Principles, data sources, updates and contacts."
        body = f"""<h1>About the RateScout editorial team</h1>
<p><b>RateScout</b> is an independent directory of crypto and currency exchange rates. We are not an exchange
   office and do not process transactions: our job is to collect and clearly present data so you can decide yourself.</p>
<h2>How we work</h2>
<ul>
  <li><b>Data source</b> — the <a href="{PREF[lang]}/o-servise/">BestChange</a> exchange monitor: rates,
      reserves and exchanger counts. Rates on the site update <b>hourly</b>.</li>
  <li><b>Neutrality.</b> We don't rate exchangers subjectively and don't give financial advice — reference data only.</li>
  <li><b>Transparency.</b> Exchange links lead to BestChange; through the affiliate program we may earn a
      commission (<a href="{PREF[lang]}/raskrytie/">disclosure</a>).</li>
  <li><b>Freshness.</b> Guides and reference pages are kept current; rate pages show the last update time.</li>
</ul>
<h2>Who it's for</h2>
<p>For anyone exchanging crypto and currencies who wants to quickly navigate rates, networks, fees and safety
   (including an <a href="{PREF[lang]}/blog/chto-takoe-aml-proverka/">AML check</a>).</p>
<h2>Owner and contacts</h2>
<p>Site owner: <b>{owner}</b> (self-employed, RU tax ID {S.get('owner_inn','')}). Questions, corrections and
   data-error reports — at <a href="mailto:{email}">{email}</a>. We welcome feedback: spotted an inaccuracy in a
   rate or text? Let us know and we'll fix it.</p>
<p class="related"><a href="{PREF[lang]}/raskrytie/">Disclosure</a> ·
   <a href="{PREF[lang]}/politika/">Privacy policy</a></p>"""
        crumb = "Editorial"
    render_page(lang, "redakciya", title, desc, body, crumb)


def render_bank_hub(to_slug, lang):
    ti = CUR.get(to_slug)
    if not ti:
        return
    name, tT = ti["name"], ti["ticker"]
    # все крипто-валюты с курсом → этот получатель, по популярности
    rows = []
    for fs, fi in GROUPED.get("Криптовалюты", []):
        r = rate_of(fs, to_slug)
        if r:
            rows.append((r.get("count", 0), fs, fi, r))
    if len(rows) < 5:
        return
    rows.sort(key=lambda x: x[0], reverse=True)
    path = f"/na/{to_slug}/"
    if lang == "ru":
        title = f"Обмен криптовалюты на {name} — курсы и все монеты ({len(rows)}) | {S['name']}"
        desc = (f"Обмен криптовалюты на {name}: {len(rows)} направлений, лучшие курсы из мониторинга BestChange. "
                f"USDT, Bitcoin, Ethereum и другие монеты на {name}. Калькулятор, AML-подсказки.")
        intro = (f"Собраны направления обмена криптовалюты на <b>{name}</b> с лучшими курсами из мониторинга "
                 f"<b>BestChange</b>. Выберите монету ниже — откроется список обменников по направлению.")
        h1 = f"Обмен криптовалюты на {name}"
        th = ("Монета", "Лучший курс", "Обменников", "Резерв, всего")
        openw, howh = "Открыть", f"Как обменять крипту на {name}"
        steps = [f"Выберите монету для обмена на {name} в таблице.",
                 "В BestChange сравните курс, резерв и рейтинг обменников.",
                 f'Для крипто — сделайте <a href="{PREF[lang]}/aml/">AML-проверку адреса</a>.',
                 f"Проведите обмен и получите средства на {name}."]
        note = "Лучший курс среди обменников; резерв — суммарный по направлению. " + updated_str(lang)
        q1 = f"Как обменять USDT на {name}?"
        a1 = f"Выберите направление USDT → {name} в таблице, сравните обменники в BestChange по курсу и резерву и проведите обмен."
        guide = f'<a href="{PREF[lang]}/blog/kak-obmenyat-usdt-na-rubli/">Пошаговый гайд по выводу в рубли</a>'
    else:
        title = f"Exchange crypto to {name} — rates and all coins ({len(rows)}) | {S['name']}"
        desc = (f"Exchange crypto to {name}: {len(rows)} directions, best rates from BestChange monitoring. "
                f"USDT, Bitcoin, Ethereum and other coins to {name}. Calculator, AML tips.")
        intro = (f"Directions to exchange crypto to <b>{name}</b> with the best rates from the <b>BestChange</b> "
                 f"monitor. Pick a coin below — the exchanger list for that direction opens.")
        h1 = f"Exchange crypto to {name}"
        th = ("Coin", "Best rate", "Exchangers", "Total reserve")
        openw, howh = "Open", f"How to exchange crypto to {name}"
        steps = [f"Pick a coin to exchange to {name} in the table.",
                 "On BestChange compare rate, reserve and exchanger rating.",
                 f'For crypto — do an <a href="{PREF[lang]}/aml/">address AML check</a>.',
                 f"Complete the exchange and receive funds to {name}."]
        note = "Best rate among exchangers; reserve is the total for the direction. " + updated_str(lang)
        q1 = f"How to exchange USDT to {name}?"
        a1 = f"Pick the USDT → {name} direction in the table, compare exchangers on BestChange by rate and reserve, and complete the exchange."
        guide = f'<a href="{PREF[lang]}/blog/kak-obmenyat-usdt-na-rubli/">Step-by-step cash-out guide</a>'
    trs = ""
    for cnt, fs, fi, r in rows:
        trs += (f'<tr><td class="d"><a href="{bc_link(fs, to_slug)}" target="_blank" rel="nofollow noopener sponsored">'
                f'{fi["name"]} <span>{fi["ticker"]}</span></a></td>'
                f'<td class="num"><b>{fmt_rate(r["rate"])}</b></td><td class="num">{cnt}</td>'
                f'<td class="num">{fmt_rate(r.get("reserve", 0))}</td></tr>')
    faq_ld = jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q1, "acceptedAnswer": {"@type": "Answer", "text": a1}}]})
    crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": tr(lang, "monitor"), "item": BASE_URL + PREF[lang] + "/"},
        {"@type": "ListItem", "position": 2, "name": h1, "item": BASE_URL + PREF[lang] + path}]})
    crumbs += jsonld({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                      "url": BASE_URL + PREF[lang] + path, "inLanguage": LOCALE[lang], "dateModified": modified_iso()})
    steps_html = "".join(f"<li>{s}</li>" for s in steps)
    body = f"""{header(lang, path)}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <nav class="crumbs"><a href="{PREF[lang]}/">{tr(lang,'monitor')}</a> / {h1}</nav>
    <h1>{h1} <span class="cnt">{len(rows)}</span></h1>
    <div class="dosblue dosborder">{intro}</div>
    <div class="rtbl-wrap"><table class="rtbl"><thead><tr>
      <th>{th[0]}</th><th>{th[1]}</th><th>{th[2]}</th><th>{th[3]}</th></tr></thead><tbody>{trs}</tbody></table></div>
    <p class="updnote">{note}</p>
    <h2 class="news">{howh}</h2>
    <ol class="steps">{steps_html}</ol>
    {howto_ld(howh, steps)}
    <p class="related">{guide} · <a href="{cpage(lang, to_slug)}">{'О ' if lang=='ru' else 'About '}{name}</a></p>
    <h2 class="news">{tr(lang,'faq')}</h2>
    <details><summary>{q1}</summary><p>{a1}</p></details>
  </div>
</div>
{faq_ld}{crumbs}{itemlist_ld([(fi["name"], BASE_URL + cpage(lang, fs)) for _c, fs, fi, _r in rows])}
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


def build_catalog_js():
    cur = {slug: {"n": i["name"], "t": i["ticker"], "c": i["category"]} for slug, i in CUR.items()}
    return "window.__CATALOG__=" + json.dumps({"order": CATS, "cur": cur}, ensure_ascii=False) + \
           ";window.__REF__=" + json.dumps(REF) + ";"


def write_catalog_js(js):
    open(os.path.join(DIST, "assets", "catalog.js"), "w", encoding="utf-8").write(js)


def render_404():
    """Своя 404 (GitHub Pages отдаёт /404.html при отсутствии страницы). Пути абсолютные."""
    lang = "ru"
    pop = ["bitcoin", "tether-trc20", "ethereum", "litecoin", "tron"]
    pop_li = "".join(f'<li><a href="{cpage(lang, s)}">{CUR[s]["name"]} <span>{CUR[s]["ticker"]}</span></a></li>'
                     for s in pop if s in CUR)
    body = f"""{header(lang, "/404")}
<div id="main">
  <div id="content" style="float:none;width:100%">
    <h1>404 — страница не найдена</h1>
    <div class="dosblue dosborder">Похоже, такой страницы нет или она переехала. Ниже — куда пойти дальше.
      <br><span style="color:#cfe">Page not found — see the links below or go to the
      <a href="/en/">English version</a>.</span></div>
    <h2 class="news">Куда пойти</h2>
    <ul class="dlist">
      <li><a href="/">Главная — каталог курсов</a></li>
      <li><a href="/blog/">Блог — гайды по обмену</a></li>
      <li><a href="/faq/">Частые вопросы</a></li>
      <li><a href="/kategoriya/kriptovalyuty/">Все криптовалюты</a></li>
      <li><a href="/na/sberbank/">Обмен крипты на Сбербанк</a></li>
      <li><a href="/o-servise/">Что такое BestChange</a></li>
    </ul>
    <h2 class="news">Популярные валюты</h2>
    <ul class="dlist">{pop_li}</ul>
  </div>
</div>
{footer(lang)}"""
    html = head(lang, f"404 — страница не найдена | {S['name']}", "Страница не найдена.", "/404") + body
    open(os.path.join(DIST, "404.html"), "w", encoding="utf-8").write(html)


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
        items += [u_entry(pr + f"/kupit/{s}/", "hourly", "0.6") for s in CUR]
        items += [u_entry(pr + f"/obmen/{p['from']}-{p['to']}/", "hourly", "0.8") for p in PAIR_PAGES]
        if ARTS[lg]:
            items.append(u_entry(pr + "/blog/", "weekly", "0.7"))
            _bpages = (len(ARTS[lg]) + BLOG_PER_PAGE - 1) // BLOG_PER_PAGE
            items += [u_entry(pr + f"/blog/page/{p}/", "weekly", "0.5") for p in range(2, _bpages + 1)]
            items += [u_entry(pr + f"/blog/{a['slug']}/", "monthly", "0.6") for a in ARTS[lg]]
        items += [u_entry(pr + f"/kategoriya/{CAT_SLUG[c]}/", "weekly", "0.7") for c in CATS]
        items += [u_entry(pr + f"/na/{b}/", "hourly", "0.8") for b in BANK_HUBS]
        items.append(u_entry(pr + "/faq/", "monthly", "0.6"))
        items.append(u_entry(pr + "/vidzhet/", "monthly", "0.5"))
        items.append(u_entry(pr + "/grafiki/", "hourly", "0.7"))
        if GLOSSARY:
            items.append(u_entry(pr + "/slovar/", "weekly", "0.6"))
            items += [u_entry(pr + f"/slovar/{t['slug']}/", "monthly", "0.5") for t in GLOSSARY]
        items += [u_entry(pr + f"/{u}/", "monthly", "0.4") for u in ("o-servise", "aml", "raskrytie", "politika", "redakciya")]
    open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(items) + "\n</urlset>")
    open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"
        f"# LLM guidance: {BASE_URL}/llms.txt\n")
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
    # IndexNow: ключ-файл (публичный, не секрет) для мгновенной переиндексации Яндекс/Bing
    open(os.path.join(DIST, INDEXNOW_KEY + ".txt"), "w").write(INDEXNOW_KEY)
    write_llms()
    write_widget()


def write_llms():
    """llms.txt (llmstxt.org) — карта сайта для AI-систем/ответных движков."""
    B = BASE_URL
    pop = [s for s in ["bitcoin", "tether-trc20", "ethereum", "tether-erc20", "tether-bep20",
                       "litecoin", "monero", "tron", "usdcoin", "tether-ton"] if s in CUR]
    lines = [
        f"# {S['name']} — справочник курсов обмена криптовалют и валют",
        "",
        f"> Независимый справочник курсов обмена криптовалют и валют по данным мониторинга обменных пунктов "
        f"BestChange. Не обменный пункт: данные справочные, курсы обновляются ежечасно. Языки: RU ({B}/) и EN ({B}/en/).",
        "",
        "## Основные разделы",
        f"- [Главная — каталог курсов]({B}/): {len(CUR)} валют по категориям, живые курсы и калькулятор.",
        f"- [Частые вопросы (FAQ)]({B}/faq/): сети USDT, комиссии, AML, резерв, СБП, обменник vs биржа.",
        f"- [О редакции]({B}/redakciya/): кто ведёт сайт, источники данных, обновление, контакты.",
        f"- [Что такое BestChange]({B}/o-servise/): как устроен мониторинг обменников.",
        f"- [AML-проверка криптоадреса]({B}/aml/): зачем и как.",
        "",
        "## Категории валют",
    ]
    for c in CATS:
        n = len(GROUPED.get(c, []))
        if n:
            lines.append(f"- [{cat_name(c,'ru')}]({B}/kategoriya/{CAT_SLUG[c]}/): {n} направлений.")
    lines += ["", "## Популярные валюты"]
    for s in pop:
        lines.append(f"- [{CUR[s]['name']} ({CUR[s]['ticker']})]({B}/valuta/{s}/)")
    lines += ["", "## Обмен крипты на банки/получателей"]
    for b in BANK_HUBS:
        lines.append(f"- [Обмен криптовалюты на {CUR[b]['name']}]({B}/na/{b}/)")
    lines += ["", "## Блог (гайды)"]
    for a in ARTS["ru"]:
        lines.append(f"- [{a['title']}]({B}/blog/{a['slug']}/): {a.get('description','')}")
    lines += ["", "## Данные и фиды",
              f"- Sitemap: {B}/sitemap.xml",
              f"- RSS блога: {B}/blog/rss.xml",
              f"- Английская версия: {B}/en/", ""]
    open(os.path.join(DIST, "llms.txt"), "w", encoding="utf-8").write("\n".join(lines))


def write_widget():
    """Встраиваемый виджет курсов: widget-data.json (данные) + widget.js (скрипт для чужих сайтов)."""
    pairs = {}
    for key, f, t, df, dt, url in WIDGET_PAIRS:
        r = rate_of(f, t)
        if r:
            pairs[key] = {"from": df, "to": dt, "rate": fmt_rate(r["rate"]), "url": BASE_URL + url}
    data = {"updated": updated_str("en").replace("Updated: ", ""), "base": BASE_URL, "pairs": pairs}
    open(os.path.join(DIST, "widget-data.json"), "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False))
    src = open(os.path.join(ROOT, "widget.src.js"), encoding="utf-8").read()
    open(os.path.join(DIST, "widget.js"), "w", encoding="utf-8").write(src.replace("{{BASE}}", BASE_URL))
    # полная карта курсов для режима «любая пара»/конвертер (тянется только когда нужно)
    nested = {}
    for k, v in RATES.items():
        f, t = k.split(">", 1)
        if f in CUR and t in CUR:
            nested.setdefault(f, {})[t] = v["rate"]
    curmap = {s: {"n": i["name"], "t": i["ticker"]} for s, i in CUR.items()}
    open(os.path.join(DIST, "widget-rates.json"), "w", encoding="utf-8").write(
        json.dumps({"updated": data["updated"], "cur": curmap, "rates": nested},
                   ensure_ascii=False, separators=(",", ":")))


def copy_assets():
    dst = os.path.join(DIST, "assets")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(ROOT, "assets"), dst)


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    # версии ассетов (кеш-бастинг) — до рендера, чтобы попали в head/footer
    catjs = build_catalog_js()
    VER["css"] = _h(open(os.path.join(ROOT, "assets", "styles.css"), encoding="utf-8").read())
    VER["js"] = _h(open(os.path.join(ROOT, "assets", "app.js"), encoding="utf-8").read())
    VER["cat"] = _h(catjs)
    for lang in LANGS:
        render_home(lang)
        for slug, info in CUR.items():
            render_currency(slug, info, lang)
            render_buy(slug, info, lang)
        compliance_pages(lang)
        for _c in CATS:
            render_category(_c, lang)
        for _b in BANK_HUBS:
            render_bank_hub(_b, lang)
        render_editorial(lang)
        render_glossary(lang)
        render_charts_overview(lang)
        render_widget_page(lang)
        render_faq(lang)
        render_blog(lang)
        render_rss(lang)
        for a in ARTS[lang]:
            render_article(a, lang)
        for p in PAIR_PAGES:
            render_pair(p["from"], p["to"], lang)
    render_404()
    static_files()
    copy_assets()
    write_catalog_js(catjs)
    print(f"✅ dist/: {LANGS} × (главная + {len(CUR)} валют + {len(TOP)} пар + {1+len(ARTS['ru'])} блог + 4 инфо) + sitemap/robots")
    print(f"   asset ver: css={VER['css']} js={VER['js']} cat={VER['cat']}")


if __name__ == "__main__":
    main()
