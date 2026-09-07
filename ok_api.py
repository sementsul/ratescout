#!/usr/bin/env python3
"""OK.ru (Одноклассники) API-клиент — СЕССИОННЫЙ режим (вечный session_key), без OAuth/EXTERNAL.

Секреты из env: OK_SESSION_KEY, OK_SESSION_SECRET, OK_GROUP_ID. Публичное: OK_APP_KEY (application key).
Подпись OK (session): sig = md5( concat(отсортированные 'k=v', КРОМЕ session_key и sig) + session_secret_key ).
Если OK вернёт ошибку подписи — пробуем вариант с session_key в базе (SIG_INCLUDE_SK=1).
"""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

APP_KEY = os.environ.get("OK_APP_KEY", "CDCNOHMGDIHBABABA")
# session_key/секрет кладём в существующие секреты OK_ACCESS_TOKEN / OK_APP_SECRET (fallback-имена)
SESSION_KEY = os.environ.get("OK_SESSION_KEY") or os.environ.get("OK_ACCESS_TOKEN", "")
SESSION_SECRET = os.environ.get("OK_SESSION_SECRET") or os.environ.get("OK_APP_SECRET", "")
GROUP = os.environ.get("OK_GROUP_ID", "")
INCLUDE_SK = os.environ.get("SIG_INCLUDE_SK") == "1"
API = "https://api.ok.ru/fb.do"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def call(method, **params):
    """Подписанный сессионный вызов OK API. Бросает RuntimeError на error_code."""
    p = {k: ("" if v is None else str(v)) for k, v in params.items()}
    p["application_key"] = APP_KEY
    p["method"] = method
    p["format"] = "json"
    sign = dict(p)
    if INCLUDE_SK:
        sign["session_key"] = SESSION_KEY
    base = "".join(f"{k}={sign[k]}" for k in sorted(sign))
    sig = _md5(base + SESSION_SECRET)
    q = dict(p)
    q["sig"] = sig
    q["session_key"] = SESSION_KEY
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
