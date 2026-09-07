#!/usr/bin/env python3
"""RuTube (неофициальный) API-клиент: авторизация по логину/паролю → токен, загрузка видео по URL.

Флоу (из community-класса rutubex, API недокументирован — может меняться):
  POST /api/accounts/token_auth/  {login|username|phone, password}  → {"token": ...}
  POST /api/video/  {url, title, description, ...}  (RuTube САМ качает видео по url)  → {video_id/id, ...}
Заголовок авторизации: `Authorization: Token <token>`.

env: RUTUBE_USER (логин/телефон), RUTUBE_PASS (пароль) — только из GitHub Secrets.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://rutube.ru/api"
USER = os.environ.get("RUTUBE_USER", "")
PASS = os.environ.get("RUTUBE_PASS", "")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_token = None


def _req(method, path, data=None, token=None, as_json=False):
    url = BASE + path
    headers = {"User-Agent": UA, "Accept": "application/json"}
    body = None
    if data is not None:
        if as_json:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        else:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Token " + token
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            code = r.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        code = e.code
    try:
        return code, json.loads(raw)
    except Exception:                            # noqa: BLE001
        return code, {"_raw": raw[:400]}


def auth(verbose=False):
    """Перебирает варианты полей/кодировки, возвращает (token, meta) или (None, попытки)."""
    global _token
    tries = []
    for fields in ({"login": USER, "password": PASS},
                   {"username": USER, "password": PASS},
                   {"phone": USER, "password": PASS}):
        for as_json in (True, False):
            code, d = _req("POST", "/accounts/token_auth/", fields, as_json=as_json)
            tok = d.get("token") if isinstance(d, dict) else None
            tries.append({"field": list(fields)[0], "json": as_json, "code": code,
                          "got_token": bool(tok), "resp": None if tok else d})
            if tok:
                _token = tok
                return tok, {"field": list(fields)[0], "json": as_json, "tries": tries}
    return None, {"tries": tries}


def add_video(url, title, description, token=None, category_id=13, is_hidden=False):
    """Создаёт видео из URL (RuTube качает сам). Возвращает (code, resp)."""
    token = token or _token
    snd = {"url": url, "title": title[:99], "description": description,
           "category_id": category_id, "is_hidden": is_hidden}
    return _req("POST", "/video/", snd, token=token)
