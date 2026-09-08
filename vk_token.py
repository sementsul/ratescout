#!/usr/bin/env python3
"""Общий helper авторизации VK для постеров (vk_daily.py, vk_video_post.py).

Свежий VK ID access-токен (vk1.a…, TTL ~1ч) из «вечного» refresh — как blogger_daily.py для Blogger.
Токен СООБЩЕСТВА фото/видео на стену грузить не умеет, нужен пользовательский; VK ID access живёт ~1ч,
поэтому храним refresh (VK_REFRESH_TOKEN + VK_DEVICE_ID) и меняем его на свежий access на каждом запуске.

Секреты (env):
  VK_REFRESH_TOKEN — «вечный» refresh из vk_id_bootstrap.py
  VK_DEVICE_ID     — device_id из того же bootstrap
  VK_CLIENT_ID     — id приложения VK ID (по умолчанию 54178608)
  VK_REFRESH_OUT   — путь к файлу: если VK ID ротирует refresh, новый пишется сюда (workflow сохранит в секрет)
"""
import json
import os
import urllib.parse
import urllib.request

VK_ID_TOKEN = "https://id.vk.com/oauth2/auth"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def fresh_user_token():
    """Свежий access-токен из VK_REFRESH_TOKEN+VK_DEVICE_ID. None — если refresh-секретов нет.

    Кидает RuntimeError, если VK ID не вернул access_token (истёкший/битый refresh — видно в логе).
    При ротации refresh (VK вернул новый) пишет его в файл VK_REFRESH_OUT — workflow сохранит в секрет.
    """
    refresh = os.environ.get("VK_REFRESH_TOKEN")
    device = os.environ.get("VK_DEVICE_ID")
    if not (refresh and device):
        return None
    client_id = os.environ.get("VK_CLIENT_ID", "54760537")   # тот же app, что выдал refresh (иначе refresh не примут)
    client_secret = os.environ.get("VK_CLIENT_SECRET")       # нужен, если приложение «Веб-сайт» (confidential client)
    out = os.environ.get("VK_REFRESH_OUT")
    params = {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id,
              "device_id": device, "scope": "video photos wall groups"}
    if client_secret:
        params["client_secret"] = client_secret
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(VK_ID_TOKEN, data=data,
                                 headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    tok = res.get("access_token")
    if not tok:
        raise RuntimeError(f"VK ID refresh не дал access_token: {str(res)[:200]}")
    new_refresh = res.get("refresh_token")
    if new_refresh and new_refresh != refresh and out:        # ротация → отдать новый на сохранение
        try:
            with open(out, "w", encoding="utf-8") as f:
                f.write(new_refresh)
            print("ℹ️ VK ID refresh ротировался — новый передан workflow на сохранение в секрет.")
        except Exception as e:                                # noqa: BLE001
            print(f"⚠️ refresh ротировался, но записать новый не смог ({e}) — завтра может протухнуть.")
    return tok
