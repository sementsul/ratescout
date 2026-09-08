#!/usr/bin/env python3
"""Автопостинг дневной сводки на стену VK-группы (тот же daily.json, что у Telegram/Дзена).

Токен и id группы — ТОЛЬКО из окружения (GitHub Secrets), в коде их нет:
  VK_TOKEN     — токен сообщества с правом «Стена» (Управление сообществом → API → создать токен)
  VK_GROUP_ID  — числовой id сообщества (без минуса)
Без секретов — сухой прогон (печатает текст, не публикует). Запуск раз в день (vk.yml).

Картинка: график прикрепляем ССЫЛКОЙ (attachments=URL) — VK сам рисует карточку-превью.
Почему не загружаем фото напрямую: для photos.getWallUploadServer нужен ПОЛЬЗОВАТЕЛЬСКИЙ токен с scope
photos, а VK для новых приложений больше не выдаёт бессрочный (offline) user-токен (живёт 24ч) — для крона
без участия человека это не годится. Токен же СООБЩЕСТВА (VK_TOKEN) не протухает, но фото грузить не умеет,
зато принимает ссылку-вложение. Поэтому — ссылка-карточка. (см. UC-73a в docs/ratescout.usecases.md)
"""
import json
import os
import sys
import urllib.parse
import urllib.request

VK_TOKEN = os.environ.get("VK_TOKEN")
VK_GROUP = os.environ.get("VK_GROUP_ID")
SRC = os.environ.get("DAILY_JSON_URL", "https://ratescout.ru/daily.json")
API = "https://api.vk.com/method/"
V = "5.199"


def vk(method, params, token=None):
    p = dict(params)
    p["access_token"] = token or VK_TOKEN
    p["v"] = V
    # POST в теле, а не в URL — иначе длинное сообщение даёт 414 Request-URI Too Large
    req = urllib.request.Request(API + method, data=urllib.parse.urlencode(p).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=40) as r:
        res = json.load(r)
    if "error" in res:
        raise RuntimeError(res["error"].get("error_msg", res["error"]))
    return res["response"]


def main():
    try:
        with urllib.request.urlopen(SRC, timeout=30) as r:
            d = json.load(r)
    except Exception as e:                       # noqa: BLE001
        print(f"не удалось получить {SRC}: {e}")
        return 0
    if not d.get("has_data"):
        print("нет данных за сутки — публикация пропущена")
        return 0
    msg = d["caption"]
    if d.get("full_list"):                       # полный список всех валют текстом (у VK лимит ~16000)
        msg = msg + "\n\n" + d["full_list"]
        if len(msg) > 15800:
            msg = msg[:15800] + "\n…полный список: " + d.get("url", "")
    if not VK_TOKEN or not VK_GROUP:
        print("VK_TOKEN/VK_GROUP_ID не заданы — сухой прогон (не публикую).\n--- пост ---")
        print(msg)
        return 0
    att = ""
    if d.get("image"):
        att = d["image"]                     # график прикрепляем ССЫЛКОЙ — VK нарисует карточку-превью
        print(f"картинка: прикрепляю ссылкой-карточкой → {att}")
    print(f"длина сообщения VK: {len(msg)} символов (со списком, если full_list есть)")
    params = {"owner_id": "-" + str(VK_GROUP), "from_group": 1, "message": msg}
    if att:
        params["attachments"] = att          # URL-вложение: community-токен это умеет, фото-загрузка не нужна
    try:
        res = vk("wall.post", params)
        print(f"опубликовано, post_id={res.get('post_id')}")
        return 0
    except Exception as e:                        # noqa: BLE001
        print(f"ошибка публикации в VK: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
