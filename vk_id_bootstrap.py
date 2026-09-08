#!/usr/bin/env python3
"""VK ID (OAuth 2.1) — получить «вечный» refresh-токен для авто-постинга фото/видео в ВК.
Почти без ручной возни: сам откроет браузер, сам поймает токен через локальный колбэк и (если есть gh)
сам запишет секреты VK_REFRESH_TOKEN / VK_DEVICE_ID в репозиторий. От тебя — только «залогиниться + Разрешить».

🔴 ЗАПУСКАТЬ ЛОКАЛЬНО, на своём компьютере:  python3 vk_id_bootstrap.py
   НЕ через бота/`!` (токены печатаются/сохраняются только у тебя, не в чат).

Перед запуском (ОДИН раз) — в dev.vk.com у приложения (по умолч. 54178608):
   • приложение включено;
   • в «Доверенные redirect URI» добавь ровно:  http://localhost:8890/
   Если приложение — VK Mini App и localhost там не принимается («Ошибка загрузки» остаётся) —
   заведи новое приложение типа «Веб-сайт»/standalone, добавь тот же redirect и запусти с VK_CLIENT_ID=<новый id>.

Настройки через env (по желанию):
   VK_CLIENT_ID (по умолч. 54178608), VK_BOOTSTRAP_PORT (8890), GH_REPO (sementsul/ratescout)
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

CLIENT_ID = os.environ.get("VK_CLIENT_ID", "54178608")
PORT = int(os.environ.get("VK_BOOTSTRAP_PORT", "8890"))
REDIRECT = f"http://localhost:{PORT}/"
SCOPE = "video photos wall groups"
AUTH = "https://id.vk.com/authorize"
TOKEN = "https://id.vk.com/oauth2/auth"
REPO = os.environ.get("GH_REPO", "sementsul/ratescout")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_captured = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.urlparse(self.path).query
        for k, v in urllib.parse.parse_qs(q).items():
            _captured[k] = v[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h2>Готово. Можно закрыть вкладку и вернуться в терминал.</h2>".encode())

    def log_message(self, *a):     # тихо
        return


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


def set_secret(name, val):
    """Пишем секрет через gh CLI (если установлен и залогинен). True — успех."""
    try:
        subprocess.run(["gh", "secret", "set", name, "--repo", REPO, "--body", val],
                       check=True, capture_output=True)
        return True
    except Exception:              # noqa: BLE001 — gh нет/не залогинен/нет прав
        return False


def main():
    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_hex(8)
    url = AUTH + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": CLIENT_ID, "scope": SCOPE,
        "redirect_uri": REDIRECT, "state": state,
        "code_challenge": challenge, "code_challenge_method": "s256"})

    print(f"\nredirect_uri для приложения (должен быть в «Доверенные redirect URI»): {REDIRECT}")
    try:
        srv = http.server.HTTPServer(("127.0.0.1", PORT), _Handler)
    except OSError as e:
        print(f"\n❌ Не занять порт {PORT} ({e}). Задай другой: VK_BOOTSTRAP_PORT=8891 python3 vk_id_bootstrap.py")
        return
    print("\nОткрываю браузер — залогинься под админом группы и нажми «Разрешить»…")
    if not webbrowser.open(url):
        print("Не удалось открыть браузер. Открой ссылку вручную:\n\n" + url + "\n")
    else:
        print("Если не открылось — вот ссылка вручную:\n\n" + url + "\n")

    print("Жду ответ VK на", REDIRECT, "…")
    while "code" not in _captured and "error" not in _captured:
        srv.handle_request()
    srv.server_close()

    if "code" not in _captured:
        print("\n❌ VK вернул ошибку:", json.dumps(_captured, ensure_ascii=False)[:400])
        print("Проверь: приложение включено и redirect_uri", REDIRECT, "добавлен в доверенные.")
        return
    if _captured.get("state") != state:
        print("\n❌ state не совпал — прерываю (возможная подмена).")
        return
    code = _captured["code"]
    device_id = _captured.get("device_id", "")
    if not device_id:
        print("\n❌ VK не прислал device_id в колбэке — не смогу обновлять токен. Проверь тип приложения.")
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

    # пытаемся записать секреты сами (gh CLI); иначе — печатаем для ручного добавления
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
