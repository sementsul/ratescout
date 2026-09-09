#!/usr/bin/env python3
"""Автопостинг дневной сводки на стену VK-группы (тот же daily.json, что у Telegram/Дзена).

Секреты (GitHub Secrets), в коде их нет:
  VK_TOKEN      — токен СООБЩЕСТВА с правом «Стена» (для wall.post от имени группы)
  VK_USER_TOKEN — ПОЛЬЗОВАТЕЛЬСКИЙ токен с правом photos (грузит фото на стену; сообщество это не умеет).
                  Бессрочный — получен через доверенное приложение (Kate Mobile, client_id 2685278, scope …offline),
                  т.к. у своих приложений VK offline убрал, а VK ID даёт только «логин» без photos/wall.
  VK_GROUP_ID   — числовой id сообщества (без минуса)
Без VK_TOKEN/VK_GROUP_ID — сухой прогон (печатает текст). Запуск раз в день (vk.yml).

Картинку (daily-24h.png) грузим photos.getWallUploadServer ПОЛЬЗОВАТЕЛЬСКИМ токеном → wall.post с attachments=photo…
от имени сообщества. Нет user-токена / фото не загрузилось → пост уходит текстом (не роняем).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid

VK_TOKEN = os.environ.get("VK_TOKEN")          # сообщество — для wall.post
VK_USER = os.environ.get("VK_USER_TOKEN")      # пользовательский — для загрузки ФОТО (сообщество не умеет)
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


def upload_photo(img, tok):
    """Грузим фото на стену сообщества ПОЛЬЗОВАТЕЛЬСКИМ токеном (у него есть photos). Возвращает 'photo<owner>_<id>'."""
    up = vk("photos.getWallUploadServer", {"group_id": VK_GROUP}, token=tok)
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\n".encode()
            + b'Content-Disposition: form-data; name="photo"; filename="d.png"\r\n'
            + b"Content-Type: image/png\r\n\r\n" + img + b"\r\n"
            + f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(up["upload_url"], data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=90) as r:
        ur = json.load(r)
    # upload-сервер при неудаче отдаёт photo:"[]" (не исключение) — ловим явно, иначе saveWallPhoto вернёт мусор
    if not isinstance(ur, dict) or str(ur.get("photo", "")) in ("", "[]"):
        raise RuntimeError(f"upload-сервер вернул без фото: {str(ur)[:200]}")
    saved = vk("photos.saveWallPhoto", {"group_id": VK_GROUP, "server": ur["server"],
                                        "photo": ur["photo"], "hash": ur["hash"]}, token=tok)[0]
    return f'photo{saved["owner_id"]}_{saved["id"]}'


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
        if not VK_USER:
            print("❗ нет VK_USER_TOKEN — фото не загрузить (сообщество фото на стену не умеет). Пост уйдёт текстом.")
        else:
            for attempt in range(1, 4):          # 3 попытки: отсекаем разовые сбои сети/Flood control
                try:
                    img = urllib.request.urlopen(d["image"], timeout=90).read()
                    att = upload_photo(img, VK_USER)
                    print(f"✅ фото загружено (попытка {attempt}): {att}")
                    break
                except Exception as e:           # noqa: BLE001
                    print(f"❗ фото не загрузилось (попытка {attempt}/3): {type(e).__name__}: {e}")
                    if attempt < 3:
                        time.sleep(5)
            if not att:
                print("❗❗ фото так и не прикрепилось — пост уйдёт ТОЛЬКО ТЕКСТОМ (причина — в строках ❗ выше).")

    print(f"длина сообщения VK: {len(msg)} символов (со списком, если full_list есть)")
    params = {"owner_id": "-" + str(VK_GROUP), "from_group": 1, "message": msg}
    if att:
        params["attachments"] = att
    try:
        res = vk("wall.post", params)
        print(f"опубликовано{'' if att else ' (без фото)'}, post_id={res.get('post_id')}")
        return 0
    except Exception as e:                        # noqa: BLE001
        print(f"ошибка публикации в VK: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
