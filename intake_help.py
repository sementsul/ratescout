#!/usr/bin/env python3
"""Разовая отправка инструкции по публикации статей в личку владельцу (для закрепа в чате с ботом).

Секреты — ТОЛЬКО из окружения: TELEGRAM_TOKEN, ALLOWED_CHAT (=ALERT_CHAT_ID). Без них — печатает текст.
Запуск — вручную (intake-help.yml). Закрепляет пользователь сам.
"""
import os
import sys
import urllib.parse
import urllib.request

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT = os.environ.get("ALLOWED_CHAT") or os.environ.get("ALERT_CHAT_ID")

TEXT = (
    "📌 <b>Как публиковать статьи через этого бота</b>\n\n"
    "<b>1. Отправить статью</b> — одним из способов:\n"
    "• <b>Текстом:</b> первая строка — заголовок, дальше тело (минимум ~200 символов).\n"
    "• <b>Файлом .md</b> — можно с полем <code>release:</code> и заголовком.\n\n"
    "<b>2. Обложка (по желанию)</b> — картинкой:\n"
    "• фото <b>с подписью</b> = обложка + статья в подписи; или\n"
    "• фото <b>до/после</b> сообщения со статьёй — приклею к ней.\n"
    "• не пришлёшь — обложка сгенерится из заголовка.\n\n"
    "<b>3. Дата выхода</b>\n"
    "• По умолчанию статья встаёт в <b>конец очереди</b> (запас на будущее).\n"
    "• Нужно раньше — добавь первой строкой:\n"
    "  <code>release: 2026-09-01</code>\n\n"
    "<b>Что ответит бот:</b>\n"
    "<code>✅ Принято: «Заголовок»\nВыйдет ДД.ММ.ГГГГ. Слаг: …</code>\n\n"
    "Дальше всё само: в свой день статья публикуется на сайте, попадает в Дзен "
    "и анонсируется в Telegram/ВК/Mastodon. Приём — раз в ~30 минут.\n\n"
    "⚠️ Короткие сообщения (менее ~200 символов) статьёй не считаются."
)


def main():
    if not TOKEN or not CHAT:
        print("TELEGRAM_TOKEN/ALLOWED_CHAT не заданы — вот текст:\n\n" + TEXT)
        return 0
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": TEXT, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data, method="POST"), timeout=30) as r:
            import json
            ok = json.load(r).get("ok")
        print("инструкция отправлена — закрепи её в чате" if ok else "ошибка ответа Telegram")
    except Exception as e:                          # noqa: BLE001
        print(f"ошибка отправки: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
