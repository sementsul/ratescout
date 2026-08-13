#!/usr/bin/env python3
"""Тянет курсы BestChange из публичного дампа базы и кладёт в rates.json.

Источник по умолчанию: http://api.bestchange.ru/info.zip (БЕЗ ключа) — bm_rates.dat/bm_cy.dat.
Формат bm_rates.dat (cp1251, ';'):
  id_from ; id_to ; id_exchanger ; rate_from ; rate_to ; reserve ; ...
«Сколько получаем за 1 отдаваемого» = rate_to / rate_from. Лучший курс = максимум по обменникам.

ID валют в дампе совпадают с currencies.json (те же id из clk()).

🔴 Ключ (BESTCHANGE_API_KEY) для базовых курсов НЕ нужен и в дамп не отправляется.
   Если задан BESTCHANGE_RATES_URL — берём его (партнёрский эндпоинт), иначе публичный дамп.

Выход: rates.json {"generated_at": ts, "pairs": {"<from_slug>>​<to_slug>": {"rate","count","reserve"}}}
"""
import io
import json
import os
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = "http://api.bestchange.ru/info.zip"


def id2slug():
    cat = json.load(open(os.path.join(ROOT, "currencies.json"), encoding="utf-8"))
    return {info["id"]: slug for slug, info in cat["currencies"].items()}


def download(url, key=None):
    if key:
        url = url.replace("{key}", key)
    req = urllib.request.Request(url, headers={"User-Agent": "RateScout/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def rates_dat_from(raw):
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = next((n for n in z.namelist() if n.endswith("bm_rates.dat")), None)
        if not name:
            raise SystemExit("❌ в архиве нет bm_rates.dat")
        return z.read(name)
    except zipfile.BadZipFile:
        return raw   # уже сам .dat


def fmt(v):
    if v == 0:
        return "0"
    return f"{v:.6g}"


def build_pairs(rates_bytes, i2s):
    text = rates_bytes.decode("cp1251", "replace")
    agg = {}   # (fid,tid) -> [best_gpg, count, reserve_sum]
    for line in text.splitlines():
        p = line.split(";")
        if len(p) < 6:
            continue
        try:
            fid, tid = int(p[0]), int(p[1])
            rf, rt = float(p[3]), float(p[4])
            reserve = float(p[5]) if p[5] else 0.0
        except ValueError:
            continue
        if rf <= 0:
            continue
        gpg = rt / rf                      # получаем за 1 отдаваемого
        a = agg.get((fid, tid))
        if a is None:
            agg[(fid, tid)] = [gpg, 1, reserve]
        else:
            a[1] += 1
            a[2] += reserve
            if gpg > a[0]:
                a[0] = gpg
    pairs = {}
    for (fid, tid), (gpg, cnt, res) in agg.items():
        fs, ts = i2s.get(fid), i2s.get(tid)
        if fs and ts:
            pairs[f"{fs}>{ts}"] = {"rate": fmt(gpg), "count": cnt, "reserve": fmt(res)}
    return pairs


def main():
    key = os.environ.get("BESTCHANGE_API_KEY") or None
    url = os.environ.get("BESTCHANGE_RATES_URL") or DEFAULT_URL
    raw = download(url, key)
    pairs = build_pairs(rates_dat_from(raw), id2slug())
    out = {"generated_at": int(time.time()), "pairs": pairs}
    json.dump(out, open(os.path.join(ROOT, "rates.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"✅ rates.json: направлений {len(pairs)} (источник: {'партнёрский' if os.environ.get('BESTCHANGE_RATES_URL') else 'публичный дамп'})")


if __name__ == "__main__":
    main()
