#!/usr/bin/env python3
"""Автопостинг ВК Клипов из репо my-many/promo: один ролик за запуск (ТОЛЬКО видео).
Очередь КРУГОВАЯ (после последнего → первый). Подпись ЧЕРЕДУЕТСЯ ratescout.ru / my-many.ru.

Флоу: shortVideo.create (group_id, description) → {upload_url} → POST mp4 полем `video_file`.
Токен — VK_USER_TOKEN (клипы грузит пользовательский). Секреты: VK_USER_TOKEN, VK_GROUP_ID, GH_PAT.
Состояние — vk_clip_posted.json {"last","count"} (коммит воркфлоу). DRY_RUN=1 — не публикует.
"""
import json
import os
import urllib.request

import vk_video_post as vv     # переиспуем vk(), gh_get(), download(), _multipart(), list_media(), VID_EXT

DRY = os.environ.get("DRY_RUN") == "1"
STATE = "vk_clip_posted.json"


def videos():
    return [(n, u) for n, u in vv.list_media() if n.lower().endswith(vv.VID_EXT)]


def load_state():
    try:
        d = json.load(open(STATE, encoding="utf-8"))
    except Exception:                            # noqa: BLE001
        return None, 0
    return d.get("last"), int(d.get("count", 0))


def upload_clip(path, upload_url):
    with open(path, "rb") as f:
        data = f.read()
    b, body = vv._multipart("video_file", "clip.mp4", "video/mp4", data)   # только файл, без прочих полей
    req = urllib.request.Request(upload_url, data=body, headers={
        "Content-Type": "multipart/form-data; boundary=" + b, "User-Agent": vv.UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main():
    vids = videos()
    if not vids:
        print("в promo нет видео.")
        return 0
    names = [n for n, _ in vids]
    last, count = load_state()
    idx = (names.index(last) + 1) % len(names) if last in names else 0
    force = os.environ.get("FORCE_NAME")
    if force and force in names:
        idx = names.index(force)
    name, url = vids[idx]
    caption = vv.caption_for(count)
    who = "ratescout.ru" if count % 2 == 0 else "my-many.ru"
    print(f"видео всего: {len(vids)} | клип #{count} | след.[{idx}]: {name} | домен: {who}")
    print(f"подпись:\n{caption}\n")
    if DRY or not vv.TOKEN or not vv.GROUP:
        print("СУХОЙ ПРОГОН — не публикую." if DRY else "VK_USER_TOKEN/VK_GROUP_ID не заданы — сухой прогон.")
        json.dump({"total": len(vids), "count": count, "next": name, "domain": who, "caption": caption},
                  open("vk_clip_dryrun.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 0
    try:
        cr = vv.vk("shortVideo.create", {"group_id": vv.GROUP, "name": "RateScout", "description": caption})
        up = upload_clip(vv.download(url, ".mp4"), cr["upload_url"])
        if not force:
            json.dump({"last": name, "count": count + 1}, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
        res = {"ok": True, "posted": name, "domain": who,
               "owner_id": cr.get("owner_id"), "video_id": cr.get("video_id"), "upload_resp": up,
               "forced": bool(force)}
        print(f"✅ клип опубликован ({who}): {name}")
    except Exception as e:                       # noqa: BLE001
        res = {"ok": False, "error": str(e), "next": name}
        print(f"❌ ошибка публикации клипа: {e}")
    json.dump(res, open("vk_clip_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
