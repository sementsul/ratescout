#!/usr/bin/env python3
"""OK.ru (Одноклассники) API-клиент: подписанные вызовы + загрузка фото/видео + пост в группу.

Секреты из env: OK_ACCESS_TOKEN, OK_APP_SECRET, OK_GROUP_ID. Публичные (можно зашить): OK_APP_KEY/OK_APP_ID.
Подпись OK: sig = md5( concat(отсортированные 'k=v', КРОМЕ access_token и sig) + md5(access_token + app_secret) ).
"""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

APP_ID = os.environ.get("OK_APP_ID", "512003337250")
APP_KEY = os.environ.get("OK_APP_KEY", "CDCNOHMGDIHBABABA")
APP_SECRET = os.environ.get("OK_APP_SECRET", "")
TOKEN = os.environ.get("OK_ACCESS_TOKEN", "")
GROUP = os.environ.get("OK_GROUP_ID", "")
API = "https://api.ok.ru/fb.do"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def call(method, **params):
    """Подписанный вызов OK API. Бросает RuntimeError на error_code."""
    p = {k: ("" if v is None else str(v)) for k, v in params.items()}
    p["application_key"] = APP_KEY
    p["method"] = method
    p["format"] = "json"
    base = "".join(f"{k}={p[k]}" for k in sorted(p))          # без access_token и sig
    sig = _md5(base + _md5(TOKEN + APP_SECRET))
    q = dict(p)
    q["sig"] = sig
    q["access_token"] = TOKEN
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
