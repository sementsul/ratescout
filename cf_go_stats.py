#!/usr/bin/env python3
"""Воронка партнёрских переходов через /go/bestchange + отправка в Telegram.

Данные — Workers Analytics Engine (биндинг ANALYTICS у воркера ratescout-go).
Считается только то, что ДОШЛО до воркера: запросы, которым Cloudflare выдал
challenge, до него не доходят. Сколько проверок выдано всего — видно в
Cloudflare → Security → Events (фильтр по пути /go/bestchange).

Секреты (env, в коде их нет):
  CF_API_TOKEN    Cloudflare API-токен: Account · Account Analytics · Read
  CF_ACCOUNT_ID   ID аккаунта (32 hex-символа)
  CF_AE_DATASET   датасет, по умолчанию go_router
  TG_TOKEN        токен бота (или TELEGRAM_TOKEN)
  TG_CHAT         chat_id получателя (или ALERT_CHAT_ID)

Примеры:
  py -3 cf_go_stats.py --days 7
  py -3 cf_go_stats.py --days 1 --json
  py -3 cf_go_stats.py --discover              # кто бот и какие у него чаты
  py -3 cf_go_stats.py --days 1 --tg           # отчёт в Telegram
  py -3 cf_go_stats.py --days 1 --tg --print-only
"""
import argparse
import html
import json
import os
import sys
import urllib.error
import urllib.request

SQL_API = "https://api.cloudflare.com/client/v4/accounts/{acc}/analytics_engine/sql"
TG_API = "https://api.telegram.org/bot{token}/{method}"

# События из track() в worker/go-router.js
EVENTS = {
    "gate_js": "показан JS-гейт",
    "gate_turnstile": "показана капча Turnstile",
    "pass_clearance": "прошёл проверку Cloudflare",
    "pass_turnstile": "прошёл Turnstile",
    "fail_turnstile": "не прошёл Turnstile",
    "tag": "переход с меткой (по cookie)",
    "no_tag_js": "переход без метки (js=1)",
    "no_tag_bad": "переход без метки (плохие параметры)",
    "rate_limited": "отсечён лимитом по IP",
}
PASS = ("pass_clearance", "pass_turnstile")
FAIL = ("no_tag_js", "no_tag_bad", "fail_turnstile")
MAX_TG = 3800


# ───────────────────────────── Cloudflare ──────────────────────────────
def sql_events(ds: str, days: int) -> str:
    return (
        "SELECT blob1 AS event, SUM(_sample_interval) AS n "
        f"FROM {ds} WHERE timestamp > NOW() - INTERVAL '{days}' DAY GROUP BY event"
    )


def sql_days(ds: str, days: int) -> str:
    return (
        "SELECT formatDateTime(toStartOfInterval(timestamp, INTERVAL '1' DAY), '%Y-%m-%d') AS day, "
        "blob1 AS event, SUM(_sample_interval) AS n "
        f"FROM {ds} WHERE timestamp > NOW() - INTERVAL '{days}' DAY GROUP BY day, event"
    )


def sql_dim(ds: str, days: int, expr: str) -> str:
    return (
        f"SELECT {expr} AS dim, blob1 AS event, SUM(_sample_interval) AS n "
        f"FROM {ds} WHERE timestamp > NOW() - INTERVAL '{days}' DAY GROUP BY dim, event"
    )


def sql_asn(ds: str, days: int) -> str:
    return (
        "SELECT blob5 AS org, double2 AS asn, blob1 AS event, SUM(_sample_interval) AS n "
        f"FROM {ds} WHERE timestamp > NOW() - INTERVAL '{days}' DAY GROUP BY org, asn, event"
    )


def resolve_account(token: str) -> str:
    """Если CF_ACCOUNT_ID не задан — берём единственный аккаунт токена."""
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode())
    accounts = payload.get("result") or []
    if len(accounts) == 1:
        return accounts[0]["id"]
    if not accounts:
        raise RuntimeError("токен не видит ни одного аккаунта Cloudflare")
    raise RuntimeError(
        "аккаунтов несколько — задайте CF_ACCOUNT_ID вручную: "
        + ", ".join(f"{a['name']}={a['id']}" for a in accounts)
    )


def query(token: str, account: str, statement: str) -> list:
    # Analytics Engine SQL API принимает сам текст запроса, без JSON-обёртки.
    req = urllib.request.Request(
        SQL_API.format(acc=account),
        data=statement.encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload.get("data") or []


def collect(token: str, account: str, ds: str, days: int) -> dict:
    try:
        return {
            "events": query(token, account, sql_events(ds, days)),
            "days": query(token, account, sql_days(ds, days)),
            "country": query(token, account, sql_dim(ds, days, "blob3")),
            "lang": query(token, account, sql_dim(ds, days, "blob2")),
            "host": query(token, account, sql_dim(ds, days, "blob4")),
            "asn": query(token, account, sql_asn(ds, days)),
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        low = body.lower()
        # Датасета ещё нет (воркер не задеплоен или не было ни одного события) —
        # это не ошибка, а «данных пока нет».
        if "does not exist" in low or "unknown table" in low or "no such table" in low:
            return {"events": [], "days": [], "country": [], "lang": [], "host": [], "asn": []}
        raise RuntimeError(f"HTTP {e.code}: {body.strip()[:400] or 'пустой ответ'}") from None


# ───────────────────────────── свёртка ─────────────────────────────────
def num(row: dict) -> int:
    return int(float(row.get("n") or 0))


def count_by(rows: list, key: str) -> dict:
    """{значение: {событие: n}}"""
    out: dict = {}
    for row in rows:
        out.setdefault(str(row.get(key, "")), {})[str(row.get("event", ""))] = num(row)
    return out


def funnel(events: dict) -> dict:
    passed = sum(events.get(e, 0) for e in PASS)
    tagged = events.get("tag", 0) + passed
    notag = sum(events.get(e, 0) for e in FAIL)
    limited = events.get("rate_limited", 0)
    gate = events.get("gate_js", 0) + events.get("gate_turnstile", 0)
    reach = tagged + notag + limited
    return {
        "passed": passed,
        "tagged": tagged,
        "notag": notag,
        "limited": limited,
        "gate": gate,
        "reach": reach,
        "tag_share": (100.0 * tagged / reach) if reach else 0.0,
        "pass_share": (100.0 * passed / reach) if reach else 0.0,
    }


def pct(part: int, total: int) -> str:
    return f"{100.0 * part / total:.0f}%" if total else "—"


def dim_rows(rows: list, key: str, limit: int = 12) -> list:
    """[{имя, прошли, метка, без метки, всего}] по убыванию «всего»."""
    out = []
    for name, ev in count_by(rows, key).items():
        passed = sum(ev.get(e, 0) for e in PASS)
        tagged = ev.get("tag", 0) + passed
        notag = sum(ev.get(e, 0) for e in FAIL)
        out.append({
            "name": name,
            "passed": passed,
            "tagged": tagged,
            "notag": notag,
            "total": tagged + notag + ev.get("rate_limited", 0),
        })
    out.sort(key=lambda r: (-r["total"], r["name"]))
    return out[:limit]


def asn_rows(rows: list, limit: int = 12) -> list:
    grouped: dict = {}
    for row in rows:
        org = str(row.get("org") or "").strip() or "—"
        asn = int(float(row.get("asn") or 0))
        key = f"{org} (AS{asn})" if asn else org
        grouped.setdefault(key, {})[str(row.get("event", ""))] = num(row)
    out = []
    for name, ev in grouped.items():
        passed = sum(ev.get(e, 0) for e in PASS)
        tagged = ev.get("tag", 0) + passed
        notag = sum(ev.get(e, 0) for e in FAIL)
        out.append({"name": name, "passed": passed, "tagged": tagged, "notag": notag,
                    "total": tagged + notag + ev.get("rate_limited", 0)})
    out.sort(key=lambda r: (-r["total"], r["name"]))
    return out[:limit]


# ───────────────────────────── вывод ───────────────────────────────────
def render_text(data: dict, days: int) -> str:
    f = funnel({r["event"]: num(r) for r in data["events"]})
    lines = [
        f"/go/bestchange за {days} дн.",
        "=" * 62,
        f"пришли на воркер   {f['reach']:>7}",
        f"прошли проверку    {f['passed']:>7}  {pct(f['passed'], f['reach'])}",
        f"с меткой           {f['tagged']:>7}  {pct(f['tagged'], f['reach'])}",
        f"без метки          {f['notag']:>7}",
        f"лимит по IP        {f['limited']:>7}",
        f"показан гейт       {f['gate']:>7}",
        "",
        "по дням:",
    ]
    by_day = count_by(data["days"], "day")
    for day in sorted(by_day, reverse=True):
        fd = funnel(by_day[day])
        lines.append(f"  {day}  прошли {fd['passed']:>5}  метка {fd['tagged']:>5}  "
                     f"б/м {fd['notag']:>4}  лимит {fd['limited']:>3}")
    for title, key, limit in (("страны", "country", 10), ("языки", "lang", 6),
                              ("хосты", "host", 4)):
        rows = dim_rows(data[key], "dim", limit)
        if not rows:
            continue
        lines.append(f"\n{title}:")
        for r in rows:
            lines.append(f"  {r['name'][:24]:<24} всего {r['total']:>5}  прошли {r['passed']:>5}  "
                         f"метка {r['tagged']:>5}  б/м {r['notag']:>4}")
    rows = asn_rows(data["asn"], 10)
    if rows:
        lines.append("\nASN (кто стучится):")
        for r in rows:
            lines.append(f"  {r['name'][:40]:<40} всего {r['total']:>5}  прошли {r['passed']:>5}")
    return "\n".join(lines)


def pre(text: str) -> str:
    return f"<pre>{html.escape(text)}</pre>"


def render_tg(data: dict, days: int) -> list:
    """Части сообщения: Telegram не принимает больше 4096 символов."""
    f = funnel({r["event"]: num(r) for r in data["events"]})

    funnel_txt = "\n".join([
        f"пришли на воркер   {f['reach']:>7}",
        f"прошли проверку    {f['passed']:>7}  {pct(f['passed'], f['reach'])}",
        f"с меткой           {f['tagged']:>7}  {pct(f['tagged'], f['reach'])}",
        f"без метки          {f['notag']:>7}",
        f"лимит по IP        {f['limited']:>7}",
        f"показан гейт       {f['gate']:>7}",
    ])

    by_day = count_by(data["days"], "day")
    day_lines = []
    for day in sorted(by_day, reverse=True)[:14]:
        fd = funnel(by_day[day])
        day_lines.append(
            f"{day[5:]}  прошли {fd['passed']:>4}  метка {fd['tagged']:>4}  "
            f"б/м {fd['notag']:>3}  лим {fd['limited']:>2}"
        )

    parts = [
        f"📊 <b>/go/bestchange</b> · {days} дн.\n\n<b>Итого</b>\n{pre(funnel_txt)}",
        "<b>По дням</b>\n" + pre("\n".join(day_lines) if day_lines else "нет данных"),
    ]

    for title, key, limit in (("Страны", "country", 12), ("Языки", "lang", 6),
                              ("Хосты", "host", 4)):
        rows = dim_rows(data[key], "dim", limit)
        if not rows:
            continue
        body = "\n".join(
            f"{r['name'][:12]:<12} {r['total']:>5}  метка {r['tagged']:>5} "
            f"({pct(r['tagged'], r['total'])})"
            for r in rows
        )
        parts.append(f"<b>{title}</b> · всего / с меткой\n" + pre(body))

    rows = asn_rows(data["asn"], 12)
    if rows:
        body = "\n".join(
            f"{r['name'][:34]:<34} {r['total']:>4} {pct(r['tagged'], r['total']):>5}"
            for r in rows
        )
        parts.append("<b>ASN</b> · запросы / доля с меткой\n" + pre(body))

    parts.append(
        "<i>«прошли проверку» — первый клик, которому Cloudflare выдал пропуск; дальше "
        "человек ходит по cookie. Сколько проверок выдано всего (включая тех, кто не дошёл "
        "до воркера) — Security → Events, фильтр /go/bestchange.</i>"
    )

    out, buf = [], ""
    for part in parts:
        if buf and len(buf) + 2 + len(part) > MAX_TG:
            out.append(buf)
            buf = part
        else:
            buf = f"{buf}\n\n{part}" if buf else part
    if buf:
        out.append(buf)
    return out


# ───────────────────────────── Telegram ────────────────────────────────
def tg_call(token: str, method: str, payload: dict) -> dict:
    req = urllib.request.Request(
        TG_API.format(token=token, method=method),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def tg_send(token: str, chat: str, parts: list) -> int:
    sent = 0
    for part in parts:
        resp = tg_call(token, "sendMessage", {
            "chat_id": chat,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if not resp.get("ok"):
            raise RuntimeError(resp.get("description", "Telegram отказал"))
        sent += 1
    return sent


def discover(token: str) -> int:
    me = tg_call(token, "getMe", {})
    if not me.get("ok"):
        print("Токен не принят Telegram: " + json.dumps(me, ensure_ascii=False), file=sys.stderr)
        return 1
    bot = me["result"]
    print(f"бот: @{bot.get('username')} — {bot.get('first_name')} (id {bot.get('id')})")

    upd = tg_call(token, "getUpdates", {"limit": 20})
    chats = {}
    for item in upd.get("result") or []:
        msg = item.get("message") or item.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            chats[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
    if chats:
        print("найдены чаты (годятся для TG_CHAT):")
        for cid, title in chats.items():
            print(f"  {cid}\t{title}")
    else:
        print("чатов нет: напишите боту /start в Telegram и повторите --discover")
    return 0


# ───────────────────────────── main ────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Воронка /go/bestchange → консоль и Telegram")
    ap.add_argument("--days", type=int, default=7, help="за сколько дней (по умолчанию 7)")
    ap.add_argument("--dataset", default=os.environ.get("CF_AE_DATASET", "go_router"))
    ap.add_argument("--json", action="store_true", help="сырые строки JSON")
    ap.add_argument("--dry-run", action="store_true", help="только напечатать SQL")
    ap.add_argument("--discover", action="store_true", help="показать бота и его чаты")
    ap.add_argument("--tg", action="store_true", help="отправить отчёт в Telegram")
    ap.add_argument("--chat", default=os.environ.get("TG_CHAT") or os.environ.get("ALERT_CHAT_ID"),
                    help="chat_id получателя (по умолчанию TG_CHAT/ALERT_CHAT_ID)")
    ap.add_argument("--print-only", action="store_true",
                    help="печатать в консоль, даже если отчёт уходит в TG")
    args = ap.parse_args()

    tg_token = os.environ.get("TG_TOKEN") or os.environ.get("TELEGRAM_TOKEN")

    if args.discover:
        if not tg_token:
            print("Нужен TG_TOKEN (или TELEGRAM_TOKEN).", file=sys.stderr)
            return 2
        return discover(tg_token)

    if args.dry_run:
        for q in (sql_events(args.dataset, args.days), sql_days(args.dataset, args.days),
                  sql_dim(args.dataset, args.days, "blob3"), sql_asn(args.dataset, args.days)):
            print(q + ";\n")
        return 0

    cf_token = os.environ.get("CF_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID")
    if not cf_token:
        print("Нужен CF_API_TOKEN с правом Account · Account Analytics · Read.", file=sys.stderr)
        return 2

    def notify_error(text: str) -> None:
        """Ошибку тоже видно в Telegram — иначе тихо сломается и никто не заметит."""
        if args.tg and tg_token and args.chat:
            try:
                tg_send(tg_token, args.chat, [f"⚠️ <b>/go/bestchange</b>: {html.escape(text)}"])
            except Exception:  # noqa: BLE001
                pass

    try:
        if not account:
            account = resolve_account(cf_token)
        data = collect(cf_token, account, args.dataset, args.days)
    except urllib.error.HTTPError as e:
        err = f"Cloudflare ответил {e.code}: {e.read().decode()[:300]}"
        print(err, file=sys.stderr)
        notify_error(err)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка запроса: {e}", file=sys.stderr)
        notify_error(f"ошибка запроса: {e}")
        return 1

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    total = sum(num(r) for r in data["events"])
    if total == 0:
        # Пусто бывает до первого клика после деплоя — не шлём таблицу из нулей.
        msg = (f"📊 <b>/go/bestchange</b> · {args.days} дн.\n\n"
               "Данных пока нет: счётчик ещё не получал событий "
               "(нужен деплой воркера с биндингом <code>ANALYTICS</code> "
               "и хотя бы один переход по партнёрской ссылке).")
        print(msg.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
        if args.tg:
            if not tg_token or not args.chat:
                print("Для --tg нужны TG_TOKEN и TG_CHAT (или --chat).", file=sys.stderr)
                return 2
            try:
                tg_send(tg_token, args.chat, [msg])
            except Exception as e:  # noqa: BLE001
                print(f"Telegram: {e}", file=sys.stderr)
                return 1
        return 0

    if args.print_only or not args.tg:
        print(render_text(data, args.days))

    if args.tg:
        if not tg_token or not args.chat:
            print("Для --tg нужны TG_TOKEN и TG_CHAT (или --chat).", file=sys.stderr)
            return 2
        try:
            parts = render_tg(data, args.days)
            n = tg_send(tg_token, args.chat, parts)
            print(f"\nотправлено в Telegram: {n} сообщение(й), чат {args.chat}")
        except Exception as e:  # noqa: BLE001
            print(f"Telegram: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())