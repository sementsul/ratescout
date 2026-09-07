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

APP_KEY = os.environ.get("OK_APP_KEY") or "CDCNOHMGDIHBABABA"
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
