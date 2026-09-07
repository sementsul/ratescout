#!/usr/bin/env python3
"""VK ID (OAuth 2.1) — получить refresh-токен для авто-постинга видео в ВК.

🔴 ЗАПУСКАТЬ ЛОКАЛЬНО, на своём компьютере:  python3 vk_id_bootstrap.py
   НЕ через бота/`!` (иначе токен попадёт в чат). Токены печатаются только на твой экран.

Что делает: генерит PKCE, печатает ссылку авторизации VK ID, ждёт URL после редиректа,
меняет code на токены, показывает refresh_token + device_id для секретов
VK_REFRESH_TOKEN / VK_DEVICE_ID, и проверяет, ротируется ли refresh при обновлении.

Перед запуском: в dev.vk.com у приложения 54178608 добавь «Доверенный redirect URI»:
   https://oauth.vk.com/blank.html
и убедись, что приложение включено.
"""
import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
import urllib.error

CLIENT_ID = "54178608"
REDIRECT = "https://oauth.vk.com/blank.html"
SCOPE = "video photos wall groups"          # VK ID — через пробел
AUTH = "https://id.vk.com/authorize"
TOKEN = "https://id.vk.com/oauth2/auth"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def post(data):
    req = urllib.request.Request(TOKEN, data=urllib.parse.urlencode(data).encode(),
                                 headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode("utf-8", "replace")}


def main():
    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_hex(8)
    url = AUTH + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": CLIENT_ID, "scope": SCOPE,
        "redirect_uri": REDIRECT, "state": state,
        "code_challenge": challenge, "code_challenge_method": "s256"})
    print("\n1) Открой в браузере (залогинься под админом группы):\n\n" + url + "\n")
    print("2) Нажми «Разрешить». Тебя перекинет на", REDIRECT + "?code=...&device_id=...")
    print("   Скопируй ВЕСЬ URL из адресной строки.\n")
    red = input("3) Вставь сюда этот URL и нажми Enter:\n> ").strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(red).query)
    code = q.get("code", [""])[0]
    device_id = q.get("device_id", [""])[0]
    if not code or not device_id:
        print("\n❌ В URL нет code/device_id. Проверь, что скопировал полный адрес после редиректа.")
        return
    r = post({"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
              "client_id": CLIENT_ID, "device_id": device_id, "redirect_uri": REDIRECT, "state": state})
    if "refresh_token" not in r:
        print("\n❌ Обмен не удался:", json.dumps(r, ensure_ascii=False)[:500])
        return
    refresh = r["refresh_token"]
    print("\n✅ Токены получены. access живёт", r.get("expires_in"), "сек.")
    # проверка ротации: обновим и посмотрим, поменялся ли refresh_token
    r2 = post({"grant_type": "refresh_token", "refresh_token": refresh, "client_id": CLIENT_ID,
               "device_id": device_id, "scope": SCOPE})
    rotated = ("refresh_token" in r2 and r2["refresh_token"] != refresh)
    latest = r2.get("refresh_token", refresh)
    print("\n=== ДОБАВЬ СЕКРЕТЫ в репозиторий sementsul/ratescout (Settings → Secrets → Actions): ===")
    print("VK_REFRESH_TOKEN =", latest)
    print("VK_DEVICE_ID     =", device_id)
    print("\nrefresh ротируется:", "ДА (постер будет сам сохранять новый)" if rotated
          else "нет (можно хранить статично)")
    if "_body" in r2:
        print("(тест-обновление вернуло:", r2.get("_body", "")[:200], ")")


if __name__ == "__main__":
    main()
