#!/usr/bin/env python3
"""Ежедневная сводка Cloudflare-аналитики по my-many.ru → Telegram (админ-чат).

Секреты (env, в коде их нет):
  CF_ANALYTICS_TOKEN  — Cloudflare API-токен с правом Analytics · Read
  TELEGRAM_TOKEN      — токен бота (уже используется другими воркфлоу)
  ALERT_CHAT_ID       — чат для админ-уведомлений
  CF_ZONE             — Zone ID (по умолчанию — my-many.ru)
Без CF-токена — стоп (нечего запрашивать). Без TG-секретов — сухой прогон (печатает сводку, не шлёт).

Данные: Cloudflare GraphQL Analytics API, набор httpRequests1dGroups (доступен и на бесплатном плане):
запросы/просмотры/уникальные/угрозы/трафик + разбивка по странам. Рефереры тут не отдаются (платные измерения).
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


def build_query(since, until):
    return ('{ viewer { zones(filter: {zoneTag: "%s"}) {'
            '  httpRequests1dGroups(limit: 3, filter: {date_geq: "%s", date_leq: "%s"}, orderBy: [date_DESC]) {'
            '    dimensions { date }'
            '    uniq { uniques }'
            '    sum { requests pageViews cachedRequests bytes threats'
            '          countryMap { clientCountryName requests } }'
            '  } } } }') % (ZONE, since, until)


def cf_query(since, until):
    body = json.dumps({"query": build_query(since, until)}).encode()
    req = urllib.request.Request(GQL, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {CF_TOKEN}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:          # тело ответа CF содержит детали ошибки
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


def main():
    if not CF_TOKEN:
        print("CF_ANALYTICS_TOKEN не задан — нечем запросить аналитику. Стоп.")
        return 0
    today = datetime.now(timezone.utc).date()
    since = (today - timedelta(days=2)).isoformat()
    until = today.isoformat()
    data = cf_query(since, until)
    if data.get("errors"):
        print("CF GraphQL вернул ошибки:", json.dumps(data["errors"], ensure_ascii=False))
        return 1
    zones = (data.get("data") or {}).get("viewer", {}).get("zones", [])
    groups = zones[0]["httpRequests1dGroups"] if zones else []
    if not groups:
        print("Нет данных по зоне за период. Возможные причины: неверный Zone ID, у токена нет Analytics·Read "
              "на эту зону, либо DNS домена НЕ проксируется (серое облако) → CF не видит запросы.")
        print("Сырой ответ CF:", json.dumps(data, ensure_ascii=False)[:800])
        return 0
    # берём вчерашний ПОЛНЫЙ день (сегодня частичный); если вчера нет — самый свежий
    yday = (today - timedelta(days=1)).isoformat()
    g = next((x for x in groups if x["dimensions"]["date"] == yday), groups[0])
    date = g["dimensions"]["date"]
    s = g["sum"]
    uniq = g["uniq"]["uniques"]
    total = s.get("requests") or 1
    countries = sorted(s.get("countryMap", []), key=lambda c: c["requests"], reverse=True)[:5]
    ctry = " · ".join(f"{c['clientCountryName']} {round(100 * c['requests'] / total)}%" for c in countries) or "—"
    text = (f"📊 my-many.ru — {date}\n"
            f"👥 Уникальных: {uniq}\n"
            f"📈 Запросов: {s['requests']} · просмотров: {s['pageViews']}\n"
            f"🌍 Топ страны: {ctry}\n"
            f"🛡 Угроз: {s['threats']} · трафик: {human_bytes(s['bytes'])}")
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
        print(f"\nTG HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}")
        return 1
    except Exception as e:                      # noqa: BLE001
        print(f"\nошибка отправки в TG: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
