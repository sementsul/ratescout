#!/usr/bin/env python3
"""Автопостинг видео из репо my-many/promo на стену VK-группы: один ролик за запуск.
Подпись ЧЕРЕДУЕТСЯ: пост про ratescout.ru → следующий про my-many.ru → и по кругу.

Токен/группа — ТОЛЬКО из окружения (GitHub Secrets):
  VK_USER_TOKEN — ПОЛЬЗОВАТЕЛЬСКИЙ токен с правами video/wall (community-токен видео грузить не может),
                  бессрочный (implicit + offline). VK_GROUP_ID — числовой id группы (без минуса).
Ролики — из GitHub (my-many/promo): список через API, файл по raw. Опубликованные — в vk_posted.json
(коммитит воркфлоу). Тексты — VK_CAPTION_RS / VK_CAPTION_MM (или дефолт). DRY_RUN=1 — не публикует.
Запуск раз в 2 дня (vk-videos.yml). Порядок роликов не важен — берём первый непубликованный по имени.
"""
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid

TOKEN = os.environ.get("VK_USER_TOKEN")
GROUP = os.environ.get("VK_GROUP_ID")
DRY = os.environ.get("DRY_RUN") == "1"
API = "https://api.vk.com/method/"
V = "5.199"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REPO = "sementsul/my-many"
FOLDER = "promo"
STATE = "vk_posted.json"

# Подписи чередуются по номеру поста (чётный — ratescout, нечётный — my-many). Можно переопределить env.
CAP_RS = (os.environ.get("VK_CAPTION_RS") or "").strip() or (
    "Мониторинг курсов обмена и обменников — RateScout.\n"
    "Лучший курс на обмен крипты и валюты в одном месте: https://ratescout.ru/?p=1116359\n\n"
    "#обмен #криптовалюта #курсывалют #ratescout")
CAP_MM = (os.environ.get("VK_CAPTION_MM") or "").strip() or (
    "MyMany — база выгодных цепочек обмена (арбитраж).\n"
    "Зарабатывай на разнице курсов, всё посчитано: https://my-many.ru/\n\n"
    "#арбитраж #обмен #криптовалюта #mymany")


def caption_for(n):
    return CAP_RS if n % 2 == 0 else CAP_MM


def vk(method, params):
    p = dict(params)
    p["access_token"] = TOKEN
    p["v"] = V
    req = urllib.request.Request(API + method, data=urllib.parse.urlencode(p).encode(),
                                 method="POST", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    if "error" in res:
        raise RuntimeError(res["error"].get("error_msg", res["error"]))
    return res["response"]


def gh_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def list_videos():
    items = gh_get(f"https://api.github.com/repos/{REPO}/contents/{FOLDER}")
    vids = [(i["name"], i["download_url"]) for i in items
            if i.get("type") == "file" and i["name"].lower().endswith((".mp4", ".mov", ".webm", ".m4v"))]
    vids.sort(key=lambda x: x[0])
    return vids


def load_posted():
    try:
        return set(json.load(open(STATE, encoding="utf-8")).get("posted", []))
    except Exception:                            # noqa: BLE001
        return set()


def upload_video(path, caption):
    saved = vk("video.save", {"group_id": GROUP, "name": "RateScout", "description": caption,
                              "wallpost": 0, "is_private": 0, "repeat": 0})
    owner, vid, up = saved["owner_id"], saved["video_id"], saved["upload_url"]
    boundary = uuid.uuid4().hex
    with open(path, "rb") as f:
        data = f.read()
    body = (f"--{boundary}\r\n".encode()
            + b'Content-Disposition: form-data; name="video_file"; filename="v.mp4"\r\n'
            + b"Content-Type: video/mp4\r\n\r\n" + data + b"\r\n"
            + f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(up, data=body, headers={
        "Content-Type": "multipart/form-data; boundary=" + boundary, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        r.read()
    return f"video{owner}_{vid}"


def main():
    vids = list_videos()
    posted = load_posted()
    nxt = next(((n, u) for (n, u) in vids if n not in posted), None)
    print(f"видео всего: {len(vids)}, опубликовано: {len(posted)}")
    if not nxt:
        print("все ролики опубликованы — нечего постить.")
        return 0
    name, url = nxt
    caption = caption_for(len(posted))           # чередуем по числу уже опубликованных
    who = "ratescout.ru" if len(posted) % 2 == 0 else "my-many.ru"
    print(f"следующий ролик: {name}\nпро домен: {who}\nподпись:\n{caption}\n")
    if DRY or not TOKEN or not GROUP:
        print("СУХОЙ ПРОГОН — не публикую." if DRY else "VK_USER_TOKEN/VK_GROUP_ID не заданы — сухой прогон.")
        json.dump({"total": len(vids), "posted": len(posted), "next": name, "domain": who, "caption": caption},
                  open("vk_dryrun.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 0
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r, \
            open(tmp.name, "wb") as f:
        f.write(r.read())
    att = upload_video(tmp.name, caption)
    vk("wall.post", {"owner_id": "-" + str(GROUP), "from_group": 1, "message": caption, "attachments": att})
    posted.add(name)
    json.dump({"posted": sorted(posted)}, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"✅ опубликовано ({who}): {name} ({att})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
