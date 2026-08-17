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
COVER_DIR = os.path.join(ROOT, "article_covers")      # кастомные обложки <slug>.png (используются build.py)
PENDING_COVER = os.path.join(COVER_DIR, "_pending.png")
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


def download_bytes(file_id):
    fp = api("getFile", file_id=file_id)["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{TOKEN}/{fp}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def download_file(file_id):
    return download_bytes(file_id).decode("utf-8", "ignore")


def save_cover(img_bytes, slug):
    os.makedirs(COVER_DIR, exist_ok=True)
    open(os.path.join(COVER_DIR, f"{slug}.png"), "wb").write(img_bytes)


def read_state():
    try:
        return json.load(open(OFFSET_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


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


def _is_image_doc(doc):
    return bool(doc) and (str(doc.get("mime_type", "")).startswith("image/")
                          or doc.get("file_name", "").lower().endswith((".png", ".jpg", ".jpeg", ".webp")))


def main():
    if not TOKEN or not ALLOWED:
        print("TELEGRAM_TOKEN/ALLOWED_CHAT не заданы — сухой прогон, приём не выполнялся.")
        return 0
    state = read_state()
    offset = int(state.get("offset", 0))
    pending = bool(state.get("pending_cover"))         # обложка ждёт статью (файл _pending.png)
    try:
        upd = api("getUpdates", offset=offset + 1, timeout=0, allowed_updates=json.dumps(["message"]))
    except Exception as e:                         # noqa: BLE001
        print(f"getUpdates: ошибка {e}")
        return 0
    results = upd.get("result", [])
    created, covers, max_uid, taken = [], 0, offset, []
    last_slug = None                               # последняя статья без обложки — к ней приклеим следующее фото

    def _accept(raw, fb):
        """Создать статью, приклеить отложенную обложку, ответить. Возвращает slug."""
        nonlocal pending, covers, last_slug
        slug, title, release = build_article(raw, fb, taken)
        taken.append(datetime.strptime(release, "%Y-%m-%d").date())
        cover_note = ""
        if pending and os.path.exists(PENDING_COVER):
            os.replace(PENDING_COVER, os.path.join(COVER_DIR, f"{slug}.png"))
            pending = False; covers += 1; cover_note = " (с обложкой)"; last_slug = None
        else:
            last_slug = slug                       # ждём фото следующим сообщением
        created.append((slug, title, release))
        d = datetime.strptime(release, "%Y-%m-%d").strftime("%d.%m.%Y")
        api("sendMessage", chat_id=ALLOWED, text=f"✅ Принято: «{title}»{cover_note}\nВыйдет {d}. Слаг: {slug}")
        return slug

    for u in results:
        max_uid = max(max_uid, u["update_id"])
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id", "")) != ALLOWED:
            continue                               # чужие сообщения — игнор
        doc = msg.get("document")
        photo = msg.get("photo")
        caption = (msg.get("caption") or "").strip()
        try:
            if photo or _is_image_doc(doc):
                file_id = photo[-1]["file_id"] if photo else doc["file_id"]
                img = download_bytes(file_id)
                if len(caption) >= 200:            # фото + статья в подписи — обложка сразу к ней
                    slug = _accept(caption, None)
                    save_cover(img, slug); covers += 1; last_slug = None
                    api("sendMessage", chat_id=ALLOWED, text=f"🖼️ Обложка прикреплена к «{slug}».")
                elif last_slug:                    # фото после статьи — к последней принятой
                    save_cover(img, last_slug); covers += 1
                    api("sendMessage", chat_id=ALLOWED, text=f"🖼️ Обложка прикреплена к «{last_slug}».")
                    last_slug = None
                else:                              # обложка вперёд статьи — откладываем
                    os.makedirs(COVER_DIR, exist_ok=True)
                    open(PENDING_COVER, "wb").write(img); pending = True
                    api("sendMessage", chat_id=ALLOWED, text="🖼️ Обложку сохранил — приложу к следующей статье.")
            elif doc and doc.get("file_name", "").endswith((".md", ".txt")):
                _accept(download_file(doc["file_id"]), os.path.splitext(doc.get("file_name", ""))[0])
            elif msg.get("text"):
                if len(msg["text"].strip()) < 200:
                    api("sendMessage", chat_id=ALLOWED,
                        text="Это похоже на короткое сообщение, а не статью. Пришли полный текст "
                             "(первая строка — заголовок) или файлом .md.")
                    continue
                _accept(msg["text"], None)
            else:
                api("sendMessage", chat_id=ALLOWED,
                    text="Пришли статью текстом/файлом .md, а обложку — картинкой.")
        except Exception as e:                     # noqa: BLE001
            api("sendMessage", chat_id=ALLOWED, text=f"⚠️ Не смог обработать сообщение: {str(e)[:120]}")
            continue

    json.dump({"offset": max_uid, "pending_cover": pending}, open(OFFSET_FILE, "w", encoding="utf-8"))
    print(f"обработано: {len(results)}, статей: {len(created)}, обложек: {covers}, offset={max_uid}, pending={pending}")
    for slug, title, release in created:
        print(f"  + {slug} (release {release})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
