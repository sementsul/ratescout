#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube Shorts раз в 3 дня: вертикальное видео (1080×1920) из дневного дайджеста.

Что делает: берёт daily.json с боевого сайта → 3 кадра Pillow (обложка / топ роста /
топ падения, везде пометка «справочно, не рекомендация») → склейка ffmpeg
(zoompan, ~12 сек, H.264) → заливка на YouTube через resumable upload (только urllib).

Аккуратно для YouTube/ФинНадзора: только факты (тикеры и % из мониторинга),
никаких призывов и обещаний доходности; в описании — дисклеймер + 18+.

Секреты (GitHub Secrets), в коде их нет:
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN — OAuth Desktop-приложения
    со scope https://www.googleapis.com/auth/youtube.upload
    (refresh получается один раз в OAuth Playground, дальше скрипт меняет его сам)
Без секретов или с DRY_RUN=1 — сухой прогон: собирает yt_shorts.mp4 локально,
печатает название/описание, не заливает.

Зависимости: Pillow + бинарник ffmpeg (в CI ubuntu-latest он предустановлен;
путь можно переопределить переменной FFMPEG_BIN).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

SRC = os.environ.get("DAILY_JSON_URL", "https://ratescout.ru/daily.json")
CID = os.environ.get("YT_CLIENT_ID")
CSEC = os.environ.get("YT_CLIENT_SECRET")
RTOK = os.environ.get("YT_REFRESH_TOKEN")
DRY = os.environ.get("DRY_RUN", "")
FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
OUT = os.environ.get("YT_OUT", "yt_shorts.mp4")

W, H = 1080, 1920
FPS, SEC_PER = 30, 4
BG, FG, GREEN, RED, MUT = (11, 11, 11), (235, 235, 235), (85, 255, 85), (255, 95, 95), (150, 150, 150)


def _font(bold, size):
    from PIL import ImageFont
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in ("/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/",
              "/usr/share/fonts/TTF/", "C:/Windows/Fonts/"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def parse_movers(cap):
    """Из caption daily.json: ([(тикер, +%)], [(тикер, -%)])."""
    gain, loss, mode = [], [], None
    for ln in cap.split("\n"):
        s = ln.strip()
        if s.startswith("📈"):
            mode = gain
            continue
        if s.startswith("📉"):
            mode = loss
            continue
        if mode is not None and s.startswith("•"):
            m = re.match(r"•\s*(\S+)\s+([+-]?\d+(?:\.\d+)?)%", s)
            if m:
                mode.append((m.group(1), float(m.group(2))))
    return gain[:5], loss[:5]


def frame(draw_list, title, date):
    """Кадр 1080×1920: заголовок + строки + дисклеймер. draw_list: [(текст, цвет)]."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, 16, H], fill=(0, 209, 143))
    fb, fh, fr, ff = _font(True, 84), _font(True, 68), _font(True, 62), _font(False, 36)
    dr.text((70, 150), "RateScout", font=fb, fill=(85, 255, 255))
    dr.text((70, 280), title, font=fh, fill=FG)
    dr.text((70, 390), date, font=ff, fill=MUT)
    dr.rectangle([70, 480, W - 70, 484], fill=(35, 44, 64))
    y = 580
    for text, col in draw_list:
        dr.text((90, y), text, font=fr, fill=col)
        y += 170
    dr.text((70, H - 230), "Курсы справочные.", font=ff, fill=MUT)
    dr.text((70, H - 165), "Не является рекомендацией. 18+.", font=ff, fill=MUT)
    dr.text((70, H - 100), "ratescout.ru", font=ff, fill=(0, 209, 143))
    return img


def build_video(gain, loss, date, out):
    from PIL import Image  # noqa: F401
    tmp = tempfile.mkdtemp(prefix="ytshorts")
    frames = [
        frame([(f"{t}  +{p:.1f}%", GREEN) for t, p in gain[:3]], "Крипторынок", date),
        frame([(f"▲ {t}  +{p:.1f}%", GREEN) for t, p in gain], "Топ роста", date),
        frame([(f"▼ {t}  {p:.1f}%", RED) for t, p in loss], "Топ падения", date),
    ]
    pngs = []
    for i, im in enumerate(frames):
        p = os.path.join(tmp, f"f{i}.png")
        im.save(p)
        pngs.append(p)
    # zoompan-сегменты + xfade-склейка
    n = len(pngs)
    fc, filt = [], []
    for i, p in enumerate(pngs):
        fc += ["-loop", "1", "-t", str(SEC_PER), "-i", p]
        # d=1: один выходной кадр на входной (иначе zoompan размножит кадры);
        # зум прогрессирует через счётчик on по всей длине сегмента.
        filt.append(f"[{i}:v]scale=1440:2560,zoompan=z='1+0.08*on/{FPS*SEC_PER}':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
                    f"s=1080x1920:fps={FPS},format=yuv420p[v{i}]")
    chained, off = "[v0]", SEC_PER
    for i in range(1, n):
        filt.append(f"{chained}[v{i}]xfade=transition=fade:duration=0.5:offset={off - 0.5}[x{i}]")
        chained, off = f"[x{i}]", off + SEC_PER - 0.5
    cmd = [FFMPEG, "-y"] + fc + ["-filter_complex", ";".join(filt),
                                 "-map", chained, "-c:v", "libx264", "-preset", "veryfast",
                                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise SystemExit("ffmpeg не собрал видео")
    print(f"видео готово: {out} ({os.path.getsize(out)//1024} КБ)")


def access_token():
    data = urllib.parse.urlencode({"client_id": CID, "client_secret": CSEC,
                                   "refresh_token": RTOK, "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token",
                                                       data=data, method="POST"), timeout=30) as r:
        return json.load(r)["access_token"]


def upload(path, title, desc):
    size = os.path.getsize(path)
    token = access_token()
    meta = {"snippet": {"title": title[:100], "description": desc[:5000],
                        "tags": ["криптовалюта", "курс биткоина", "crypto", "shorts"],
                        "categoryId": "28"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    q = urllib.parse.urlencode({"uploadType": "resumable", "part": "snippet,status"})
    req = urllib.request.Request(
        f"https://www.googleapis.com/upload/youtube/v3/videos?{q}",
        data=json.dumps(meta).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"})
    with urllib.request.urlopen(req, timeout=60) as r:
        session = r.headers.get("Location")
    if not session:
        raise SystemExit("YouTube не дал upload-сессию")
    with open(path, "rb") as f:
        blob = f.read()
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(
                session, data=blob, method="PUT",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Length": str(size), "Content-Type": "video/mp4"})
            with urllib.request.urlopen(req, timeout=300) as r:
                vid = json.load(r)["id"]
            print(f"залито: https://www.youtube.com/shorts/{vid}")
            return vid
        except Exception as e:                            # noqa: BLE001
            print(f"попытка {attempt}: {str(e)[:150]}")
    raise SystemExit(1)


def main():
    with urllib.request.urlopen(SRC, timeout=30) as r:
        d = json.load(r)
    if not d.get("has_data"):
        print("нет данных — пропуск")
        return 0
    gain, loss = parse_movers(d.get("caption", ""))
    if not (gain or loss):
        print("не разобрал движения — пропуск")
        return 0
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})", d.get("caption", ""))
    date = m.group(1) if m else ""
    top = gain[0] if gain else loss[0]
    title = f"Крипта: {top[0]} {'+' if top[1] >= 0 else ''}{top[1]:.1f}% · {date} #shorts"
    desc = (d.get("caption", "").split("📢")[0].strip()
            + "\n\nКурсы справочные, не являются финансовой рекомендацией. 18+."
            + "\nОбзор и графики: https://ratescout.ru/obzor/sutki/"
            + "\n#crypto #shorts")
    build_video(gain, loss, date, OUT)
    if DRY or not all([CID, CSEC, RTOK]):
        print("--- title ---")
        print(title)
        print("--- desc ---")
        print(desc)
        print("сухой прогон: заливка пропущена")
        return 0
    upload(OUT, title, desc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
