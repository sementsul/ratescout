#!/usr/bin/env python3
"""VK ID (OAuth 2.1 + PKCE) — получить «вечный» refresh-токен для авто-постинга фото/видео в ВК.

Заточен под ТЕРМИНАЛ без браузера и без проброшенных портов: НИКАКОГО локального сервера/колбэка.
Схема — копипаст:
  1) скрипт печатает ссылку авторизации;
  2) открываешь её в браузере НА ЛЮБОМ устройстве (телефон/другой ПК), логинишься под админом группы,
     жмёшь «Разрешить»;
  3) VK перебросит на страницу-заглушку — её адрес будет вида
        https://oauth.vk.com/blank.html?code=...&device_id=...&state=...
     СКОПИРУЙ этот адрес целиком и вставь обратно в терминал;
  4) скрипт меняет code→refresh и (если есть gh) сам пишет секреты VK_REFRESH_TOKEN/VK_DEVICE_ID,
     иначе печатает их у тебя на экране (в чат НЕ кидай).

Запуск:  python3 vk_id_bootstrap.py

Перед запуском (ОДИН раз) в dev.vk.com у приложения (по умолч. 54178608):
   • приложение включено;
   • в «Доверенные redirect URI» добавь РОВНО тот адрес, что в VK_REDIRECT (по умолч. https://oauth.vk.com/blank.html).
   Если приложение — VK Mini App и заглушку не принимает («Ошибка загрузки») — заведи приложение типа
   «Веб-сайт»/standalone, добавь туда этот redirect и запусти с VK_CLIENT_ID=<новый id>.

Настройки через env (по желанию):
   VK_CLIENT_ID (54178608), VK_REDIRECT (https://oauth.vk.com/blank.html), GH_REPO (sementsul/ratescout)
"""
import base64
import hashlib
import json
import os
import secrets
import subprocess
import urllib.error
import urllib.parse
import urllib.request

CLIENT_ID = os.environ.get("VK_CLIENT_ID", "54178608")
REDIRECT = os.environ.get("VK_REDIRECT", "https://oauth.vk.com/blank.html")
SCOPE = "video photos wall groups"
AUTH = "https://id.vk.com/authorize"
TOKEN = "https://id.vk.com/oauth2/auth"
REPO = os.environ.get("GH_REPO", "sementsul/ratescout")
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


def parse_pasted(text):
    """Из вставленного адреса (или голых параметров) достаём code/device_id/state."""
    text = text.strip()
    q = text.split("?", 1)[1] if "?" in text else text
    q = q.replace("#", "&")                       # на случай, если параметры во фрагменте
    return {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}


def set_secret(name, val):
    """Пишем секрет через gh CLI (если установлен и залогинен). True — успех."""
    try:
        subprocess.run(["gh", "secret", "set", name, "--repo", REPO, "--body", val],
                       check=True, capture_output=True)
        return True
    except Exception:                             # noqa: BLE001 — gh нет/не залогинен/нет прав
        return False


def main():
    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_hex(8)
    url = AUTH + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": CLIENT_ID, "scope": SCOPE,
        "redirect_uri": REDIRECT, "state": state,
        "code_challenge": challenge, "code_challenge_method": "s256"})

    print("\n=== VK ID: получение refresh-токена (копипаст, без портов) ===")
    print(f"redirect_uri (должен быть в «Доверенные redirect URI» приложения): {REDIRECT}\n")
    print("1) Открой ЭТУ ссылку в браузере (телефон/любой ПК), войди под админом группы и нажми «Разрешить»:\n")
    print(url + "\n")
    print("2) После «Разрешить» VK перебросит на страницу-заглушку — скопируй её АДРЕС ЦЕЛИКОМ")
    print("   (в нём будут code= и device_id=) и вставь сюда.\n")

    pasted = input("Вставь адрес (или строку с code=...&device_id=...): ").strip()
    p = parse_pasted(pasted)
    code = p.get("code")
    device_id = p.get("device_id", "")
    if not code:
        print("\n❌ В том, что вставлено, нет параметра code. Скопируй адрес заглушки целиком и попробуй снова.")
        return
    if p.get("state") and p["state"] != state:
        print("\n❌ state не совпал — прерываю (возможная подмена/чужая ссылка).")
        return
    if not device_id:
        print("\n❌ Нет device_id в адресе — без него токен не обновить. Проверь тип приложения (нужен не Mini App).")
        return

    r = post({"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
              "client_id": CLIENT_ID, "device_id": device_id, "redirect_uri": REDIRECT, "state": state})
    if "refresh_token" not in r:
        print("\n❌ Обмен code→токены не удался:", json.dumps(r, ensure_ascii=False)[:500])
        return
    refresh = r["refresh_token"]
    print("\n✅ Токены получены. access живёт", r.get("expires_in"), "сек.")

    # тест ротации: обновим один раз и посмотрим, поменялся ли refresh
    r2 = post({"grant_type": "refresh_token", "refresh_token": refresh, "client_id": CLIENT_ID,
               "device_id": device_id, "scope": SCOPE})
    rotated = ("refresh_token" in r2 and r2["refresh_token"] != refresh)
    latest = r2.get("refresh_token", refresh)

    # пробуем записать секреты сами (gh CLI); иначе — печатаем для ручного добавления
    ok_r = set_secret("VK_REFRESH_TOKEN", latest)
    ok_d = set_secret("VK_DEVICE_ID", device_id)
    print()
    if ok_r and ok_d:
        print(f"✅ Секреты VK_REFRESH_TOKEN и VK_DEVICE_ID записаны в репозиторий {REPO} автоматически (gh).")
    else:
        print("gh не сработал (не установлен/не залогинен/нет прав). Добавь секреты ВРУЧНУЮ")
        print(f"(GitHub → {REPO} → Settings → Secrets and variables → Actions):")
        print("  VK_REFRESH_TOKEN =", latest)
        print("  VK_DEVICE_ID     =", device_id)
    print("\nrefresh ротируется:", "ДА (постер сам сохраняет новый через шаг workflow)" if rotated
          else "нет (можно хранить статично)")
    print("\nГотово. Запусти Actions → «VK daily digest» — в посте должна появиться картинка.")


if __name__ == "__main__":
    main()
