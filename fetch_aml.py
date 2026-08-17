#!/usr/bin/env python3
"""Тянет санкционный список крипто-адресов OFAC → aml-sanctions.json (для клиентского AML-чека).

Источник — публичный поддерживаемый репозиторий 0xB10C (адреса из списка OFAC SDN, по сетям).
Читаем через GitHub API с токеном (Accept: raw) — надёжно, без 429 на raw.githubusercontent в CI.
Аггрегируем адреса всех сетей в один список. Это ОФИЦИАЛЬНЫЙ санкционный список — факт, не скоринг.
Сбой сети — пропускаем эту сеть (лог), но не роняем весь список. Ephemeral (.gitignore), обновляется каждую сборку.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = "0xB10C/ofac-sanctioned-digital-currency-addresses"
API = f"https://api.github.com/repos/{REPO}/contents/sanctioned_addresses_{{}}.txt?ref=lists"
# все реальные сети из ветки lists (крупные: XBT/ETH/TRX/USDT + мелкие)
CHAINS = ["XBT", "ETH", "TRX", "USDT", "USDC", "XMR", "LTC", "BCH", "DASH", "ZEC",
          "SOL", "ARB", "BSC", "ETC", "BSV", "BTG", "XRP", "XVG"]
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def fetch(chain):
    headers = {"Accept": "application/vnd.github.raw", "User-Agent": "RateScout-AML"}
    if TOKEN:
        headers["Authorization"] = f"token {TOKEN}"
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(API.format(chain), headers=headers), timeout=60) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 404:
                break
            time.sleep(2 * (attempt + 1))
        except Exception as e:                     # noqa: BLE001
            last = str(e)[:60]
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(last or "fail")


def main():
    addrs, ok, per = set(), 0, {}
    for ch in CHAINS:
        try:
            got = [ln.strip() for ln in fetch(ch).splitlines() if ln.strip() and not ln.startswith("#")]
            got = [a for a in got if len(a) >= 20]
            per[ch] = len(got)
            addrs.update(got)
            ok += 1
        except Exception as e:                     # noqa: BLE001
            print(f"OFAC {ch}: пропуск ({e})")
        time.sleep(0.5)
    out = os.path.join(ROOT, "aml-sanctions.json")
    json.dump({"updated": int(time.time()), "count": len(addrs), "addresses": sorted(addrs)},
              open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"aml-sanctions.json: {len(addrs)} адресов из {ok}/{len(CHAINS)} сетей "
          f"(XBT={per.get('XBT', 0)}, ETH={per.get('ETH', 0)}, TRX={per.get('TRX', 0)}, USDT={per.get('USDT', 0)})")
    if len(addrs) < 300:
        print("⚠️ подозрительно мало адресов — часть сетей не загрузилась")
    return 0


if __name__ == "__main__":
    sys.exit(main())
