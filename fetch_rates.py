#!/usr/bin/env python3
"""Тянет курсы BestChange по партнёрскому API и кладёт в rates.json.

🔴 БЕЗОПАСНОСТЬ: ключ читается ТОЛЬКО из окружения (BESTCHANGE_API_KEY) — из GitHub Secret
в раннере Actions. В код, в rates.json и в опубликованный сайт ключ НЕ попадает.
Запускается на этапе СБОРКИ (CI), не в браузере.

Формат курсов BestChange — «экспорт» (ZIP с bm_*.dat, разделитель ';'):
  bm_rates.dat: id_from;id_to;id_exchanger;rate;reserve;...
Мы берём ЛУЧШИЙ курс на пару (id_from,id_to) + число обменников + суммарный резерв,
маппим id→slug по currencies.json и пишем rates.json:
  {"generated_at": <ts>, "pairs": {"<from_slug>>​<to_slug>": {"rate": "..","count": N,"reserve": ".."}}}

Эндпоинт партнёрского экспорта задаётся в BESTCHANGE_RATES_URL (из партнёрских доков bestchange.app),
ключ подставляется в него ({key}) — точный URL зависит от аккаунта, поэтому берём из окружения, не хардкодим.
"""
import io
import json
import os
import sys
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def id_to_slug():
    cat = json.load(open(os.path.join(ROOT, "currencies.json"), encoding="utf-8"))
    return {info["id"]: slug for slug, info in cat["currencies"].items()}


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "RateScout/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse_rates(raw):
    """raw — ZIP с bm_rates.dat/bm_exch.dat ИЛИ сам bm_rates.dat (bytes)."""
    data = None
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = next((n for n in z.namelist() if n.endswith("rates.dat")), None)
        if name:
            data = z.read(name)
    except zipfile.BadZipFile:
        data = raw
    if data is None:
        raise SystemExit("❌ в экспорте не найден bm_rates.dat")
    text = data.decode("utf-8", "replace")
    best = {}   # (from_id,to_id) -> {rate,count,reserve_sum}
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) < 5:
            continue
        try:
            fid, tid = int(parts[0]), int(parts[1])
            rate = float(parts[3])
            reserve = float(parts[4]) if parts[4] else 0.0
        except ValueError:
            continue
        k = (fid, tid)
        b = best.setdefault(k, {"rate": rate, "count": 0, "reserve": 0.0})
        b["count"] += 1
        b["reserve"] += reserve
        if rate > b["rate"]:      # «лучший» = максимум получаемого (упрощённо; уточнить направление сортировки)
            b["rate"] = rate
    return best


def main():
    load_env()
    key = os.environ.get("BESTCHANGE_API_KEY")
    url_tpl = os.environ.get("BESTCHANGE_RATES_URL")
    if not key:
        raise SystemExit("❌ нет BESTCHANGE_API_KEY (локально — в .env; в CI — GitHub Secret)")
    if not url_tpl:
        raise SystemExit("❌ нет BESTCHANGE_RATES_URL — задай URL экспорта из партнёрских доков "
                          "(bestchange.app), с плейсхолдером {key}. Ключ подставится из окружения.")
    url = url_tpl.replace("{key}", key)

    raw = download(url)
    best = parse_rates(raw)
    i2s = id_to_slug()

    pairs = {}
    for (fid, tid), b in best.items():
        fs, ts = i2s.get(fid), i2s.get(tid)
        if not fs or not ts:
            continue
        pairs[f"{fs}>{ts}"] = {
            "rate": f"{b['rate']:.6g}",
            "count": b["count"],
            "reserve": f"{b['reserve']:.0f}",
        }
    out = {"generated_at": int(time.time()), "pairs": pairs}
    json.dump(out, open(os.path.join(ROOT, "rates.json"), "w", encoding="utf-8"), ensure_ascii=False)
    # ключ НЕ логируем и НЕ пишем
    print(f"✅ rates.json: пар {len(pairs)} (обновлено)")


if __name__ == "__main__":
    main()
