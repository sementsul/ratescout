#!/usr/bin/env python3
"""Приём статей блога через Telegram-бота (без сервера — опрос getUpdates по расписанию).

Ты пересылаешь боту в личку либо готовый .md, либо просто текст (первая строка = заголовок).
Скрипт (workflow по cron) забирает новые сообщения, создаёт articles/<slug>.md, САМ ставит дату выхода
(следующий слот дрипа: +9 дней к последней запланированной статье, если release не задан явно), и коммитит.
Обложка сгенерится при сборке из заголовка. Бот отвечает подтверждением с датой выхода.

Безопасность: принимаем ТОЛЬКО от владельца (chat_id == ALLOWED_CHAT). Прочее игнорируем.
Секреты/настройки — из окружения: TELEGRAM_TOKEN, ALLOWED_CHAT (= ALERT_CHAT_ID владельца).
Без токена — сухой прогон. Offset (что уже обработано) хранится в .intake_offset.json в репо.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ALLOWED = str(os.environ.get("ALLOWED_CHAT") or os.environ.get("ALERT_CHAT_ID") or "").strip()
ART_DIR = os.path.join(ROOT, "articles")
OFFSET_FILE = os.path.join(ROOT, ".intake_offset.json")
DRIP_DAYS = 9

TRANSLIT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
            "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
            "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "shch",
            "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}


def slugify(text):
    text = "".join(TRANSLIT.get(c, c) for c in (text or "").lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text or "statya")[:60].strip("-")


def api(method, **params):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST" if data else "GET"),
                                timeout=60) as r:
        return json.load(r)


def download_file(file_id):
    fp = api("getFile", file_id=file_id)["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{TOKEN}/{fp}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8", "ignore")


def read_offset():
    try:
        return int(json.load(open(OFFSET_FILE, encoding="utf-8")).get("offset", 0))
    except (OSError, ValueError):
        return 0


def existing_release_dates():
    out = []
    for fn in os.listdir(ART_DIR):
        if not fn.endswith(".md"):
            continue
        m = re.search(r"release:\s*(\d{4}-\d{2}-\d{2})", open(os.path.join(ART_DIR, fn), encoding="utf-8").read())
        if m:
            out.append(datetime.strptime(m.group(1), "%Y-%m-%d").date())
    return out


def next_release(taken):
    """Следующий свободный слот дрипа: +9 дней к самой поздней запланированной (или сегодня)."""
    today = datetime.now(timezone.utc).date()
    base = max(existing_release_dates() + list(taken) + [today])
    return base + timedelta(days=DRIP_DAYS)


def parse_frontmatter(raw):
    meta, body = {}, raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = parts[2]
    return meta, body.strip()


def make_description(body):
    for para in body.split("\n\n"):
        if para.lstrip().startswith("#"):          # пропускаем заголовки
            continue
        p = re.sub(r"[#*_>`\[\]]", "", para).strip()
        if p and not p.startswith("!"):
            return (p[:157] + "…") if len(p) > 158 else p
    return "Статья блога RateScout."


def build_article(raw, fallback_title, taken):
    meta, body = parse_frontmatter(raw)
    title = meta.get("title") or fallback_title or (body.splitlines()[0].lstrip("# ").strip() if body else "Статья")
    # убрать первую строку тела, если она дублирует заголовок (обычный текст: 1-я строка = заголовок)
    body = body.strip()
    lines = body.splitlines()
    if lines and lines[0].lstrip("# ").strip() == title:
        body = "\n".join(lines[1:]).strip()
    if not body.startswith("#"):                    # гарантируем ровно один H1 = заголовок
        body = f"# {title}\n\n{body}"
    slug = meta.get("slug") or slugify(title)
    # уникальность слага
    base_slug, i = slug, 2
    while os.path.exists(os.path.join(ART_DIR, f"{slug}.md")):
        slug = f"{base_slug}-{i}"; i += 1
    desc = meta.get("description") or make_description(body)
    rel = meta.get("release")
    if rel and re.match(r"\d{4}-\d{2}-\d{2}", rel):
        release = rel[:10]
    else:
        release = next_release(taken).isoformat()
    fm = (f"---\ntitle: {title}\ndescription: {desc}\nslug: {slug}\n"
          f"date: {release}\nrelease: {release}\n---\n")
    open(os.path.join(ART_DIR, f"{slug}.md"), "w", encoding="utf-8").write(fm + body.strip() + "\n")
    return slug, title, release


def main():
    if not TOKEN or not ALLOWED:
        print("TELEGRAM_TOKEN/ALLOWED_CHAT не заданы — сухой прогон, приём не выполнялся.")
        return 0
    offset = read_offset()
    try:
        upd = api("getUpdates", offset=offset + 1, timeout=0, allowed_updates=json.dumps(["message"]))
    except Exception as e:                         # noqa: BLE001
        print(f"getUpdates: ошибка {e}")
        return 0
    results = upd.get("result", [])
    created, max_uid, taken = [], offset, []
    for u in results:
        max_uid = max(max_uid, u["update_id"])
        msg = u.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat != ALLOWED:
            continue                               # чужие сообщения — игнор
        doc = msg.get("document")
        try:
            if doc and (doc.get("file_name", "").endswith((".md", ".txt"))):
                raw = download_file(doc["file_id"])
                fb = os.path.splitext(doc.get("file_name", ""))[0]
                slug, title, release = build_article(raw, fb, taken)
            elif msg.get("text"):
                if len(msg["text"].strip()) < 200:     # защита: короткое сообщение — не статья
                    api("sendMessage", chat_id=ALLOWED,
                        text="Это похоже на короткое сообщение, а не статью. Пришли полный текст "
                             "(первая строка — заголовок) или файлом .md.")
                    continue
                slug, title, release = build_article(msg["text"], None, taken)
            else:
                api("sendMessage", chat_id=ALLOWED,
                    text="Пришли статью текстом (первая строка — заголовок) или файлом .md")
                continue
        except Exception as e:                     # noqa: BLE001
            api("sendMessage", chat_id=ALLOWED, text=f"⚠️ Не смог принять статью: {str(e)[:120]}")
            continue
        taken.append(datetime.strptime(release, "%Y-%m-%d").date())
        created.append((slug, title, release))
        d = datetime.strptime(release, "%Y-%m-%d").strftime("%d.%m.%Y")
        api("sendMessage", chat_id=ALLOWED, text=f"✅ Принято: «{title}»\nВыйдет {d}. Слаг: {slug}")

    json.dump({"offset": max_uid}, open(OFFSET_FILE, "w", encoding="utf-8"))
    print(f"обработано сообщений: {len(results)}, создано статей: {len(created)}, offset={max_uid}")
    for slug, title, release in created:
        print(f"  + {slug} (release {release})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
