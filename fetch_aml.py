#!/usr/bin/env python3
"""Тянет санкционный список крипто-адресов OFAC → aml-sanctions.json (для клиентского AML-чека).

Источник — публичный поддерживаемый репозиторий 0xB10C (адреса из списка OFAC SDN, по сетям).
Аггрегируем адреса нескольких сетей в один список. Это ОФИЦИАЛЬНЫЙ санкционный список — факт, не скоринг.
Сбой сети — пишем пустой список (чекер работает: валидация формата + эксплорер, но с пометкой «список недоступен»).
Ephemeral (в .gitignore), обновляется каждую сборку. Ключ не нужен.
"""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = "https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/lists/sanctioned_addresses_{}.txt"
CHAINS = ["XBT", "ETH", "TRX", "LTC", "BCH", "XMR", "DASH", "ZEC", "ARB", "BSC", "USDT", "USDC"]


def fetch(chain):
    req = urllib.request.Request(BASE.format(chain), headers={"User-Agent": "RateScout-AML"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "ignore")


def main():
    addrs = set()
    got = 0
    for ch in CHAINS:
        try:
            for line in fetch(ch).splitlines():
                a = line.strip()
                if a and not a.startswith("#") and len(a) >= 20:
                    addrs.add(a)
            got += 1
        except Exception as e:                     # noqa: BLE001
            print(f"OFAC {ch}: пропуск ({str(e)[:60]})")
        time.sleep(1)                              # вежливо к GitHub raw
    out = os.path.join(ROOT, "aml-sanctions.json")
    json.dump({"updated": int(time.time()), "count": len(addrs), "addresses": sorted(addrs)},
              open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"aml-sanctions.json: {len(addrs)} адресов из {got}/{len(CHAINS)} сетей")
    return 0


if __name__ == "__main__":
    sys.exit(main())
