#!/usr/bin/env python3
"""Тянет поисковые фразы из Яндекс.Метрики (ym:s:searchPhrase по визитам) → metrika.json.

Официальный Metrika API, тем же YANDEX_OAUTH_TOKEN, что и отчёт (нужен доступ Метрики у токена).
Это реальные фразы, по которым на сайт приходили из поиска (по сессиям). Бесплатно/надёжно.
Секреты — только из окружения. Сбой — тихо пропускаем.
🔶 Яндекс часто скрывает часть фраз («не определено») — их отфильтровываем.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("YANDEX_OAUTH_TOKEN")
COUNTER = os.environ.get("YANDEX_METRIKA_COUNTER") or "111586112"
MET = "https://api-metrika.yandex.net/stat/v1/data"
_HIDE = {"не определено", "(not set)", "(none)", "not set", "—", ""}


def _junk(q):
    """Отсеять не-запросы: URL/путь/бренд (прямые заходы Метрика пишет как URL сайта)."""
    ql = q.lower().strip()
    if not ql or ql in _HIDE:
        return True
    if ql.startswith(("http", "www.", "/")):
        return True
    return "ratescout" in ql


def main():
    if not TOKEN:
        print("нет YANDEX_OAUTH_TOKEN — пропускаю"); return 0
    params = {
        "ids": COUNTER, "metrics": "ym:s:visits", "dimensions": "ym:s:searchPhrase",
        "date1": "30daysAgo", "date2": "yesterday", "sort": "-ym:s:visits", "limit": "30", "accuracy": "full",
    }
    try:
        req = urllib.request.Request(MET + "?" + urllib.parse.urlencode(params),
                                     headers={"Authorization": f"OAuth {TOKEN}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"Яндекс.Метрика: ошибка {e} — пропускаю"); return 0

    phrases = []
    for r in data.get("data", []):
        try:
            name = (r["dimensions"][0].get("name") or "").strip()
            visits = r["metrics"][0]
        except (KeyError, IndexError, TypeError):
            continue
        if _junk(name):
            continue
        phrases.append({"q": name, "visits": int(visits or 0)})
    json.dump({"generated_at": int(time.time()), "phrases": phrases},
              open(os.path.join(ROOT, "metrika.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"metrika.json: {len(phrases)} фраз")
    return 0


if __name__ == "__main__":
    sys.exit(main())
