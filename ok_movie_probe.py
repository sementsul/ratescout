#!/usr/bin/env python3
"""Разовый пробник: как правильно прикрепить ВИДЕО в mediatopic.post OK-группы.
Заливает один ролик (movieId), затем пробует разные форматы media-элемента и пишет,
какой OK принял. Результат — ok_movie_probe.json. Запускается временным шагом ok-probe.yml.
"""
import json
import os
import time

import ok_api
import ok_video_post as ov

NAME = os.environ.get("FORCE_NAME", "5trr__10_.mp4")


def main():
    media = dict(ov.list_media())
    if NAME not in media:
        json.dump({"error": f"нет {NAME}"}, open("ok_movie_probe.json", "w"))
        return 0
    path = ov.download(media[NAME], ".mp4")
    vid = ok_api.upload_video(path, name="RateScout")
    out = {"movieId": vid, "movieId_type": type(vid).__name__}
    try:
        vid_int = int(vid)
    except Exception:                            # noqa: BLE001
        vid_int = vid
    time.sleep(20)                               # дать OK время начать обработку видео
    variants = {
        "movie_movieId_str": {"type": "movie", "movieId": str(vid)},
        "movie_movieId_int": {"type": "movie", "movieId": vid_int},
        "video_list_id": {"type": "video", "list": [{"id": vid}]},
        "movie_list_id": {"type": "movie", "list": [{"id": vid}]},
        "movie_id": {"type": "movie", "id": vid},
        "video_id": {"type": "video", "id": vid},
    }
    out["tries"] = {}
    for k, el in variants.items():
        try:
            r = ok_api.call("mediatopic.post", type="GROUP_THEME", gid=ok_api.GROUP,
                            attachment=json.dumps({"media": [
                                {"type": "text", "text": "тест видео OK"}, el]}, ensure_ascii=False))
            out["tries"][k] = {"ok": True, "resp": r}
        except Exception as e:                   # noqa: BLE001
            out["tries"][k] = {"ok": False, "err": str(e)}
    json.dump(out, open("ok_movie_probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
