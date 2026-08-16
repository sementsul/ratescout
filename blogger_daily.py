#!/usr/bin/env python3
"""Автопостинг дневной сводки в Blogger (Google Blogger API v3).

Секреты (GitHub Secrets), в коде их нет:
  BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN  — OAuth Desktop-приложения (scope blogger)
  BLOGGER_BLOG_ID  — числовой id блога
Refresh-токен получается один раз (OAuth Playground), дальше CI сам меняет его на access-токен.
Без секретов — сухой прогон (печатает заголовок/HTML, не публикует).
"""
import html
import json
import os
import sys
import urllib.parse
import urllib.request

CID = os.environ.get("BLOGGER_CLIENT_ID")
CSEC = os.environ.get("BLOGGER_CLIENT_SECRET")
RTOK = os.environ.get("BLOGGER_REFRESH_TOKEN")
BLOG = os.environ.get("BLOGGER_BLOG_ID")
SRC = os.environ.get("DAILY_JSON_URL", "https://ratescout.ru/daily.json")


def access_token():
    data = urllib.parse.urlencode({"client_id": CID, "client_secret": CSEC,
                                   "refresh_token": RTOK, "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token",
                                                       data=data, method="POST"), timeout=30) as r:
        return json.load(r)["access_token"]


def build_html(d):
    cap = html.escape(d.get("caption", "")).replace("\n", "<br>")
    img = f'<p><img src="{html.escape(d["image"])}" alt="Крипторынок за сутки" /></p>' if d.get("image") else ""
    parts = [img, f"<p>{cap}</p>"]
    if d.get("full_list"):
        fl = html.escape(d["full_list"]).replace("\n", "<br>")
        parts.append(f"<h3>Все валюты — цена USDT · изм.24ч · обменников</h3><p>{fl}</p>")
    return "".join(parts)


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
    title = d.get("title", "RateScout — крипторынок")
    if not all([CID, CSEC, RTOK, BLOG]):
        print("Blogger-секреты не заданы — сухой прогон.\n--- заголовок ---")
        print(title)
        return 0
    body = json.dumps({"kind": "blogger#post", "title": title, "content": build_html(d)}).encode()
    req = urllib.request.Request(f"https://www.googleapis.com/blogger/v3/blogs/{BLOG}/posts/",
                                 data=body, method="POST",
                                 headers={"Authorization": f"Bearer {access_token()}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            res = json.load(r)
        print("опубликовано:", res.get("url"))
        return 0
    except Exception as e:                        # noqa: BLE001
        print(f"ошибка публикации в Blogger: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
