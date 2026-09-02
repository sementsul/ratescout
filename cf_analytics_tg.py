#!/usr/bin/env python3
"""Ежедневная сводка Cloudflare-аналитики по my-many.ru → Telegram (админ-чат).

Секреты (env, в коде их нет):
  CF_ANALYTICS_TOKEN  — Cloudflare API-токен с правом Zone · Analytics · Read
  TELEGRAM_TOKEN      — токен бота
  ALERT_CHAT_ID       — чат для админ-уведомлений
  CF_ZONE             — Zone ID (по умолчанию — my-many.ru)
Без CF-токена — стоп. Без TG-секретов — сухой прогон (печатает сводку, не шлёт).

Базовая сводка: httpRequests1dGroups (запросы/уники/страны). Детализация ботов: httpRequestsAdaptiveGroups
(топ User-Agent / путей / сетей-ASN / кодов ответа) — данные сэмплированные (оценка), best-effort.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

ZONE = os.environ.get("CF_ZONE", "5d667f50b12ae3337cc9533f185a34f9")  # my-many.ru
CF_TOKEN = os.environ.get("CF_ANALYTICS_TOKEN")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TG_CHAT = os.environ.get("ALERT_CHAT_ID")
GQL = "https://api.cloudflare.com/client/v4/graphql"

# Известные дата-центровые/бот-сети (для читаемости ASN)
ASN_NAMES = {
    13335: "Cloudflare", 16509: "AWS", 14618: "AWS", 15169: "Google", 396982: "Google Cloud",
    16276: "OVH", 24940: "Hetzner", 14061: "DigitalOcean", 20473: "Vultr", 63949: "Linode",
    45102: "Alibaba", 132203: "Tencent", 8075: "Microsoft", 51167: "Contabo", 39572: "AdvancedHosting",
    212238: "Datacamp", 9009: "M247", 60068: "Datacamp", 208046: "HZ-Hosting", 210644: "AEZA",
}


def gql(query):
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(GQL, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {CF_TOKEN}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        print(f"HTTP {e.code} от Cloudflare API. Тело ответа:\n{detail}")
        raise


def human_bytes(n):
    n = float(n or 0)
    for u in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.0f} ПБ"


def basic_query(since, until):
    return ('{ viewer { zones(filter: {zoneTag: "%s"}) {'
            '  httpRequests1dGroups(limit: 3, filter: {date_geq: "%s", date_leq: "%s"}, orderBy: [date_DESC]) {'
            '    dimensions { date } uniq { uniques }'
            '    sum { requests pageViews cachedRequests bytes threats'
            '          countryMap { clientCountryName requests } }'
            '  } } } }') % (ZONE, since, until)


def detail_query(since_dt, until_dt):
    flt = 'filter: {datetime_geq: "%s", datetime_leq: "%s"}' % (since_dt, until_dt)

    def blk(alias, dims):
        return (f'{alias}: httpRequestsAdaptiveGroups(limit: 6, {flt}, orderBy: [count_DESC]) '
                f'{{ count dimensions {{ {dims} }} }}')

    return ('{ viewer { zones(filter: {zoneTag: "%s"}) { '
            + blk("ua", "userAgent")
            + blk("paths", "clientRequestPath")
            + blk("asn", "clientAsn")
            + blk("status", "edgeResponseStatus")
            + ' } } }') % ZONE


def asn_label(n):
    return f"AS{n} ({ASN_NAMES[n]})" if n in ASN_NAMES else f"AS{n}"


def clip(s, n):
    s = (s or "").replace("\n", " ").strip()
    return s[:n] + "…" if len(s) > n else s


def build_detail_text(since_dt, until_dt):
    """Возвращает блок детализации ботов или '' при недоступности (best-effort)."""
    try:
        d = gql(detail_query(since_dt, until_dt))
        if d.get("errors"):
            return f"\n🤖 Детализация недоступна: {clip(json.dumps(d['errors'], ensure_ascii=False), 120)}"
        z = d["data"]["viewer"]["zones"][0]
        ua = "; ".join(f"{clip(g['dimensions']['userAgent'], 32)}×{g['count']}" for g in z["ua"][:4]) or "—"
        paths = "; ".join(f"{clip(g['dimensions']['clientRequestPath'], 24)}×{g['count']}" for g in z["paths"][:5]) or "—"
        asn = "; ".join(f"{asn_label(g['dimensions']['clientAsn'])}×{g['count']}" for g in z["asn"][:4]) or "—"
        status = " ".join(f"{g['dimensions']['edgeResponseStatus']}:{g['count']}" for g in z["status"][:6]) or "—"
        return (f"\n🤖 Кто ходит (24ч, оценка):\n"
                f"• UA: {ua}\n• Пути: {paths}\n• Сети: {asn}\n• Ответы: {status}")
    except Exception as e:                       # noqa: BLE001
        return f"\n🤖 Детализация недоступна: {clip(str(e), 120)}"


def main():
    if not CF_TOKEN:
        print("CF_ANALYTICS_TOKEN не задан — нечем запросить аналитику. Стоп.")
        return 0
    today = datetime.now(timezone.utc).date()
    data = gql(basic_query((today - timedelta(days=2)).isoformat(), today.isoformat()))
    if data.get("errors"):
        print("CF GraphQL вернул ошибки:", json.dumps(data["errors"], ensure_ascii=False))
        return 1
    zones = (data.get("data") or {}).get("viewer", {}).get("zones", [])
    groups = zones[0]["httpRequests1dGroups"] if zones else []
    if not groups:
        print("Нет данных по зоне за период. Проверь Zone ID, право Analytics·Read и что DNS проксируется.")
        print("Сырой ответ CF:", json.dumps(data, ensure_ascii=False)[:800])
        return 0
    yday = (today - timedelta(days=1)).isoformat()
    g = next((x for x in groups if x["dimensions"]["date"] == yday), groups[0])
    date = g["dimensions"]["date"]
    s = g["sum"]
    total = s.get("requests") or 1
    countries = sorted(s.get("countryMap", []), key=lambda c: c["requests"], reverse=True)[:5]
    ctry = " · ".join(f"{c['clientCountryName']} {round(100 * c['requests'] / total)}%" for c in countries) or "—"
    text = (f"📊 my-many.ru — {date}\n"
            f"👥 Уникальных: {g['uniq']['uniques']}\n"
            f"📈 Запросов: {s['requests']} · просмотров: {s['pageViews']}\n"
            f"🌍 Топ страны: {ctry}\n"
            f"🛡 Угроз: {s['threats']} · трафик: {human_bytes(s['bytes'])}")
    # детализация ботов за последние 24 часа
    now = datetime.now(timezone.utc)
    text += build_detail_text((now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                              now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    print(text)
    if not (TG_TOKEN and TG_CHAT):
        print("\n(TELEGRAM_TOKEN/ALERT_CHAT_ID не заданы — сухой прогон, не отправляю)")
        return 0
    tg = json.dumps({"chat_id": TG_CHAT, "text": text, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=tg, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30)
        print("\n✅ отправлено в Telegram")
        return 0
    except urllib.error.HTTPError as e:
        print(f"\nTG HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
        return 1
    except Exception as e:                       # noqa: BLE001
        print(f"\nошибка отправки в TG: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
