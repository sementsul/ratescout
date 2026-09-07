#!/usr/bin/env python3
"""OK.ru (Одноклассники) API-клиент — схема «ВЕЧНОГО access_token» (внешнее OAuth-приложение).

apiok выдаёт пару: вечный access_token + session_secret_key. Подпись:
    sig = md5( concat(отсортированные 'k=v', КРОМЕ access_token и sig) + session_secret_key )
в запрос кладём access_token + application_key + sig. НЕ путать с обычным OAuth
(там было бы md5(access_token+application_secret_key)) — здесь секрет = session_secret_key.

env: OK_ACCESS_TOKEN (вечный токен), OK_APP_SECRET (session_secret_key), OK_GROUP_ID.
Публичное: OK_APP_KEY (application key). Секреты — только из GitHub Secrets, в коде их нет.
"""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

APP_KEY = os.environ.get("OK_APP_KEY") or "CNGHOCOGDIHBABABA"   # RateScout (внешнее), app_id 512005105260
TOKEN = os.environ.get("OK_ACCESS_TOKEN", "")
SESSION_SECRET = os.environ.get("OK_APP_SECRET", "")   # именно session_secret_key
GROUP = os.environ.get("OK_GROUP_ID", "")
API = "https://api.ok.ru/fb.do"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def call(method, **params):
    """Подписанный вызов OK API (вечный токен). Бросает RuntimeError на error_code."""
    p = {k: ("" if v is None else str(v)) for k, v in params.items()}
    p["application_key"] = APP_KEY
    p["method"] = method
    p["format"] = "json"
    base = "".join(f"{k}={p[k]}" for k in sorted(p))    # без access_token и sig
    sig = _md5(base + SESSION_SECRET)
    q = dict(p)
    q["access_token"] = TOKEN
    q["sig"] = sig
    req = urllib.request.Request(API, data=urllib.parse.urlencode(q).encode(),
                                 method="POST", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
    try:
        d = json.loads(raw)
    except Exception:                            # noqa: BLE001
        return {"_raw": raw[:400]}
    if isinstance(d, dict) and d.get("error_code"):
        raise RuntimeError(f"OK {d.get('error_code')}: {d.get('error_msg')}")
    return d


def _multipart(fields):
    """fields: list of (name, filename|None, ctype|None, data-bytes|str). Возвращает (boundary, body)."""
    import uuid
    b = uuid.uuid4().hex
    out = b""
    for name, filename, ctype, data in fields:
        head = f'--{b}\r\nContent-Disposition: form-data; name="{name}"'
        if filename:
            head += f'; filename="{filename}"'
        head += "\r\n"
        if ctype:
            head += f"Content-Type: {ctype}\r\n"
        head += "\r\n"
        out += head.encode() + (data if isinstance(data, bytes) else str(data).encode()) + b"\r\n"
    out += f"--{b}--\r\n".encode()
    return b, out


def _upload(url, fields):
    b, body = _multipart(fields)
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "multipart/form-data; boundary=" + b, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:                            # noqa: BLE001
        return {"_raw": raw[:400]}


def upload_photo(img_bytes, gid=None):
    """Грузит фото в группу, возвращает token для mediatopic."""
    gid = gid or GROUP
    up = call("photosV2.getUploadUrl", gid=gid, count=1)
    pid = up["photo_ids"][0]
    resp = _upload(up["upload_url"], [(pid, "p.jpg", "image/jpeg", img_bytes)])
    return resp["photos"][pid]["token"]


def upload_video(path, name="RateScout", gid=None):
    """Грузит видео в группу, возвращает video_id."""
    gid = gid or GROUP
    sz = os.path.getsize(path)
    up = call("video.getUploadUrl", gid=gid, file_name=name, file_size=sz)
    with open(path, "rb") as f:
        _upload(up["upload_url"], [("file", name + ".mp4", "video/mp4", f.read())])
    return up["video_id"]


def post_group(text, photo_token=None, video_id=None, gid=None):
    """Публикует пост в ленту группы через mediatopic.post."""
    gid = gid or GROUP
    media = [{"type": "text", "text": text}]
    if photo_token:
        media.append({"type": "photo", "list": [{"id": photo_token}]})
    if video_id:
        media.append({"type": "movie", "list": [{"id": video_id}]})   # рабочий формат (проверено пробником)
    return call("mediatopic.post", type="GROUP_THEME", gid=gid,
                attachment=json.dumps({"media": media}, ensure_ascii=False))
