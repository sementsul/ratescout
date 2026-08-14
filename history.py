#!/usr/bin/env python3
"""Накопление истории курсов RateScout → history.json (для графиков на страницах валют).

Один снимок В ДЕНЬ на валюту: «цена в USDT» = лучший курс `slug → tether-trc20`
(сколько USDT за 1 единицу). Отслеживаем валюты, у которых такой курс есть (в основном крипта).
history.json коммитится обратно в репозиторий в CI — так точки накапливаются между запусками.

Формат history.json:
  {"generated_at": <ts>, "unit": "USDT",
   "series": {"<slug>": [["YYYY-MM-DD", <rate:float>], ...]}}
Точки — по одной на дату (повторный запуск в тот же день перезаписывает значение), хранятся последние KEEP.
"""
import json
import os
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
USDT = "tether-trc20"        # опорная валюта (стейблкоин ≈ доллар)
KEEP = 120                   # хранить последние N дней на серию

def _load(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return default


def main():
    cur = _load(os.path.join(ROOT, "currencies.json"), {"currencies": {}})["currencies"]
    rates = _load(os.path.join(ROOT, "rates.json"), {}).get("pairs", {})
    hist = _load(os.path.join(ROOT, "history.json"), {"unit": "USDT", "series": {}})
    series = hist.get("series", {})
    today = date.today().isoformat()

    added = 0
    for slug in cur:
        if slug == USDT:
            continue
        r = rates.get(f"{slug}>{USDT}")
        if not r:
            continue
        try:
            val = float(r["rate"])
        except (KeyError, ValueError, TypeError):
            continue
        if val <= 0:
            continue
        pts = series.get(slug, [])
        if pts and pts[-1][0] == today:      # точка за сегодня уже есть — один снимок в день
            continue
        pts.append([today, val]); added += 1
        series[slug] = pts[-KEEP:]

    if added == 0 and os.path.exists(os.path.join(ROOT, "history.json")):
        print(f"история: за {today} уже записано — файл не меняю (нет лишних коммитов)")
        return
    hist = {"generated_at": int(datetime.now(timezone.utc).timestamp()),
            "unit": "USDT", "series": series}
    json.dump(hist, open(os.path.join(ROOT, "history.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"история: серий {len(series)}, новых точек за {today}: {added}")


if __name__ == "__main__":
    main()
