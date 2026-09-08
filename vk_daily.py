#!/usr/bin/env python3
"""Автопостинг дневной сводки на стену VK-группы (тот же daily.json, что у Telegram/Дзена).

Токен и id группы — ТОЛЬКО из окружения (GitHub Secrets), в коде их нет:
  VK_TOKEN     — токен сообщества с правами «Стена» и «Фотографии» (Управление сообществом → API → создать токен)
  VK_GROUP_ID  — числовой id сообщества (без минуса)
Без секретов — сухой прогон (печатает текст, не публикует). Запуск раз в день (vk.yml).

VK wall-посты не поддерживают инлайн-кнопки — поэтому это текст (со ссылками) + картинка.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid

VK_TOKEN = os.environ.get("VK_TOKEN")
VK_USER = os.environ.get("VK_USER_TOKEN")     # пользовательский — умеет грузить ФОТО (сообщество не может)
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


def upload_photo(img):
    tok = VK_USER or VK_TOKEN                  # фото грузим пользовательским токеном (сообщество не умеет)
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
    # upload-сервер при неудаче отдаёт photo:"[]" (не исключение) — ловим явно, иначе saveWallPhoto молча вернёт мусор
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
        # какой токен реально пойдёт на загрузку фото (ловит случай «вечный токен лежит не в VK_USER_TOKEN»)
        if VK_USER:
            print("фото: гружу пользовательским VK_USER_TOKEN")
        else:
            print("❗ VK_USER_TOKEN ПУСТ → фолбэк на VK_TOKEN (токен СООБЩЕСТВА фото на стену грузить НЕ умеет). "
                  "Вечный пользовательский токен должен лежать в секрете VK_USER_TOKEN.")
        for attempt in range(1, 4):              # 3 попытки: отсекаем разовые сбои сети/upload-сервера
            try:
                img = urllib.request.urlopen(d["image"], timeout=90).read()
                att = upload_photo(img)
                print(f"✅ фото загружено (попытка {attempt}): {att}")
                break
            except Exception as e:               # noqa: BLE001
                print(f"❗ фото не загрузилось (попытка {attempt}/3): {type(e).__name__}: {e}")
                if attempt < 3:
                    time.sleep(2)
        if not att:
            print("❗❗ фото так и не прикрепилось — пост уйдёт ТОЛЬКО ТЕКСТОМ. Причина — в строках ❗ выше.")
    print(f"длина сообщения VK: {len(msg)} символов (со списком, если full_list есть)")
    params = {"owner_id": "-" + str(VK_GROUP), "from_group": 1, "message": msg}
    if att:                                  # фото только если реально загрузилось (нужен user-токен);
        params["attachments"] = att          # иначе просто текст — VK сам сделает превью из первой ссылки
    try:
        res = vk("wall.post", params)
        print(f"опубликовано, post_id={res.get('post_id')}")
        return 0
    except Exception as e:                        # noqa: BLE001
        print(f"ошибка публикации в VK: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
