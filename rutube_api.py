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

BASE = "https://rutube.ru/api"   # username = email аккаунта (телефон token_auth не принимает; нужен пароль RuTube, не Яндекс ID)
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


def _phone_variants(u):
    """Разные написания одного логина/телефона (RuTube придирчив к формату)."""
    digits = "".join(c for c in u if c.isdigit())
    out = [u]
    if digits:
        out += ["+" + digits, digits]
        if digits.startswith("7") and len(digits) == 11:
            out.append("8" + digits[1:])          # 8XXXXXXXXXX
            out.append("+7" + digits[1:])
        if digits.startswith("8") and len(digits) == 11:
            out.append("+7" + digits[1:])
            out.append("7" + digits[1:])
    seen, uniq = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def auth(verbose=False):
    """Поле — `username` (подтверждено пробой). Перебираем написания логина + form/json."""
    global _token
    tries = []
    for uname in _phone_variants(USER):
        for as_json in (True, False):
            code, d = _req("POST", "/accounts/token_auth/",
                           {"username": uname, "password": PASS}, as_json=as_json)
            tok = d.get("token") if isinstance(d, dict) else None
            tries.append({"username": uname, "json": as_json, "code": code,
                          "got_token": bool(tok), "resp": None if tok else d})
            if tok:
                _token = tok
                return tok, {"username": uname, "json": as_json, "tries": tries}
    return None, {"tries": tries}


def add_video(url, title, description, token=None, category_id=13, is_hidden=False):
    """Создаёт видео из URL (RuTube качает сам). Возвращает (code, resp)."""
    token = token or _token
    snd = {"url": url, "title": title[:99], "description": description,
           "category_id": category_id, "is_hidden": is_hidden}
    return _req("POST", "/video/", snd, token=token)
