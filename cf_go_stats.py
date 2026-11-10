#!/usr/bin/env python3
"""Воронка партнёрских переходов через /go/bestchange: сколько прошло проверку, сколько нет.

Данные — из Workers Analytics Engine (биндинг ANALYTICS у воркера ratescout-go).
Считаем только то, что ДОШЛО до воркера: запросы, которые Cloudflare отбил
челленджем, в воркер не попадают, поэтому «сколько всего проверок выдано» видно
только в Cloudflare (Security → Events, фильтр по пути /go/bestchange).

Секреты (env, в коде их нет):
  CF_API_TOKEN   — Cloudflare API-токен с правом Account · Analytics · Read
  CF_ACCOUNT_ID  — ID аккаунта (32 hex-символа)
  CF_AE_DATASET  — имя датасета, по умолчанию go_router

Примеры:
  py -3 cf_go_stats.py --days 7
  py -3 cf_go_stats.py --days 1 --json
  py -3 cf_go_stats.py --dry-run
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

SQL_API = "https://api.cloudflare.com/client/v4/accounts/{acc}/analytics_engine/sql"

# Как называются события (см. track() в worker/go-router.js) и что они значат
EVENTS = {
    "gate_js": "показан JS-гейт (капчи нет)",
    "gate_turnstile": "показана капча Turnstile",
    "pass_clearance": "прошёл проверку Cloudflare",
    "pass_turnstile": "прошёл Turnstile",
    "fail_turnstile": "не прошёл Turnstile",
    "tag": "выдана метка (переход с p=)",
    "no_tag_js": "переход без метки (js=1)",
    "no_tag_bad": "переход без метки (плохие параметры)",
    "rate_limited": "отсечён лимитом по IP",
}
PASS_EVENTS = ("pass_clearance", "pass_turnstile")


def sql(dataset: str, days: int) -> str:
    return (
        "SELECT toDate(timestamp) AS day, blob1 AS event, count() AS n "
        f"FROM {dataset} "
        f"WHERE timestamp > NOW() - INTERVAL '{int(days)}' DAY "
        "GROUP BY day, event ORDER BY day DESC, n DESC"
    )


def query(token: str, account: str, statement: str) -> list:
    body = json.dumps({"query": statement}).encode()
    req = urllib.request.Request(
        SQL_API.format(acc=account),
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload.get("data") or []


def build_table(rows: list) -> dict:
    """{day: {event: count}}"""
    table: dict = {}
    for row in rows:
        day = str(row.get("day", ""))[:10]
        event = row.get("event", "")
        table.setdefault(day, {})[event] = int(row.get("n", 0) or 0)
    return table


def print_report(table: dict, days: int) -> None:
    if not table:
        print("Данных нет. Проверьте биндинг ANALYTICS и что воркер задеплоен с новым кодом.")
        return

    print("%-11s %12s %11s %10s %7s" % ("день", "прошли", "с меткой", "без метки", "лимит"))
    print("-" * 56)

    total: dict = {}
    for day in sorted(table, reverse=True):
        ev = table[day]
        first_pass = sum(ev.get(e, 0) for e in PASS_EVENTS)   # первый клик прошёл проверку
        tagged = ev.get("tag", 0) + first_pass                # все переходы с p=
        notag = ev.get("no_tag_js", 0) + ev.get("no_tag_bad", 0) + ev.get("fail_turnstile", 0)
        limited = ev.get("rate_limited", 0)
        print("%-11s %12d %11d %10d %7d" % (day, first_pass, tagged, notag, limited))
        for k, v in (("pass", first_pass), ("tagged", tagged),
                     ("notag", notag), ("limited", limited)):
            total[k] = total.get(k, 0) + v

    print("-" * 56)
    print("%-11s %12d %11d %10d %7d" % ("всего", total["pass"], total["tagged"],
                                        total["notag"], total["limited"]))

    handled = total["tagged"] + total["notag"] + total["limited"]
    if handled:
        print("\nДоля переходов с меткой: %.1f%% (%d из %d дошедших до воркера)"
              % (100.0 * total["tagged"] / handled, total["tagged"], handled))

    print("\n«прошли» — первый клик, для которого Cloudflare/Turnstile выдал пропуск.")
    print("Дальше человек ходит по cookie, каждый такой клик считается в «с меткой».")
    print("\nЧего здесь нет: сколько проверок выдал сам Cloudflare — в них попадают и те,")
    print("кто до воркера не дошёл. Это видно в Security → Events, фильтр:")
    print("  URI Path starts with /go/bestchange, Action = Managed Challenge")


def main() -> int:
    ap = argparse.ArgumentParser(description="Воронка /go/bestchange из Analytics Engine")
    ap.add_argument("--days", type=int, default=7, help="за сколько дней (по умолчанию 7)")
    ap.add_argument("--dataset", default=os.environ.get("CF_AE_DATASET", "go_router"))
    ap.add_argument("--json", action="store_true", help="вывести сырые строки JSON")
    ap.add_argument("--dry-run", action="store_true", help="напечатать SQL и выйти")
    args = ap.parse_args()

    statement = sql(args.dataset, args.days)
    if args.dry_run:
        print(statement)
        return 0

    token = os.environ.get("CF_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID")
    if not token or not account:
        print("Нужны CF_API_TOKEN (Account · Analytics · Read) и CF_ACCOUNT_ID.", file=sys.stderr)
        return 2

    try:
        rows = query(token, account, statement)
    except urllib.error.HTTPError as e:
        print(f"Cloudflare ответил {e.code}: {e.read().decode()[:400]}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка запроса: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    table = build_table(rows)
    print_report(table, args.days)

    # Подсказка про «сколько всего выдано», если хочется сравнить
    unknown = sorted({r.get("event") for r in rows} - set(EVENTS))
    if unknown:
        print("\nНеизвестные события (обновите EVENTS): " + ", ".join(map(str, unknown)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())