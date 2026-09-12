#!/usr/bin/env python3
"""Статистика показов в VK ОРД (ЕРИР) по данным Яндекс.Метрики — ежемесячный крон.

Официальные документы:
- VK ORD API, раздел «API статистики»: POST /v1/statistics, первичный ключ
  (creative_external_id + pad_external_id + месяц); статистика за месяц подаётся
  в течение 30 дней после конца месяца. Без денег — только shows_count
  (пример «создание статистики без денег» из cookbook).
- Yandex Metrica Reports API: GET https://api-metrika.yandex.net/stat/v1/data
  с метрикой ym:s:pageviews (показы страниц счётчика).

Логика:
- Период по умолчанию — прошлый календарный месяц (ORD_MONTH=YYYY-MM переопределяет).
- shows_count = сумма ym:s:pageviews счётчика за период (целое число).
- DRY_RUN=1 — только читает Метрику и печатает payload, ничего не отправляет.
- ORD_SANDBOX=1 — тестовый контур https://api-sandbox.ord.vk.com (в ЕРИР не уходит).

Секреты — только из окружения, в лог не печатаются:
  ORD_API_TOKEN (Bearer-ключ из ord.vk.com/keys), YANDEX_OAUTH_TOKEN,
  YANDEX_METRIKA_COUNTER (по умолчанию 111586112),
  ORD_CREATIVE_ID, ORD_PAD_ID (external_id из кабинета ОРД).
"""
import calendar
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

MET = 'https://api-metrika.yandex.net/stat/v1/data'
ORD_PROD = 'https://api.ord.vk.com'
ORD_SANDBOX = 'https://api-sandbox.ord.vk.com'


def mask(s):
    s = s or ''
    return (s[:4] + '...' + s[-4:]) if len(s) > 12 else '***'


OUT = {}  # для GITHUB_OUTPUT (месяц/показы — их подхватит TG-уведомление)


def emit_outputs():
    path = os.environ.get('GITHUB_OUTPUT', '')
    if not path:
        return
    with open(path, 'a', encoding='utf-8') as f:
        for k in ('ord_month', 'ord_shows', 'ord_shows_mm'):
            f.write(f'{k}={OUT.get(k, "")}\n')


def http_json(url, token=None, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {'User-Agent': 'ratescout-ord/1.0'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method='POST' if payload is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def prev_month(today=None):
    today = today or dt.date.today()
    first = today.replace(day=1)
    last_prev = first - dt.timedelta(days=1)
    return last_prev.year, last_prev.month


def metrika_pageviews(token, counter, d1, d2, host=None):
    params = {'ids': counter, 'metrics': 'ym:s:pageviews',
              'date1': d1, 'date2': d2, 'accuracy': 'full'}
    if host:
        params['filters'] = f"EXISTS(ym:pv:URL=@'{host}')"
    try:
        data = http_json(MET + '?' + urllib.parse.urlencode(params), token=token,
                         payload=None)
    except Exception as e:  # noqa: BLE001
        print(f'ERROR metrika: {e}')
        return None
    totals = data.get('totals') or []
    if totals:
        return int(float(totals[0] or 0))
    rows = data.get('data') or []
    if rows:
        return int(sum(float(r.get('metrics', [0])[0] or 0) for r in rows))
    print('ERROR metrika: пустой ответ без totals/data')
    return None


def main():
    ord_token = os.environ.get('ORD_API_TOKEN', '')
    ya_token = os.environ.get('YANDEX_OAUTH_TOKEN', '')
    counter = os.environ.get('YANDEX_METRIKA_COUNTER', '') or '111586112'
    creative = os.environ.get('ORD_CREATIVE_ID', '') or '85bcklvevfc-1k28ihvhd'
    pad = os.environ.get('ORD_PAD_ID', '') or '1ggont56t70-1k28j2dhf'
    pad_mm = os.environ.get('ORD_PAD_MM', '') or 'i3rkh4d6kfg-1k28pbbqm'
    mm_host = os.environ.get('ORD_MM_HOST', '') or 'my-many.ratescout.ru'
    sandbox = os.environ.get('ORD_SANDBOX', '') == '1'
    dry = os.environ.get('DRY_RUN', '') == '1'
    month_arg = os.environ.get('ORD_MONTH', '')

    if not ord_token:
        print('ERROR: нет ORD_API_TOKEN — пропускаю (добавьте в Secrets)');
        return 2
    if not ya_token:
        print('ERROR: нет YANDEX_OAUTH_TOKEN — пропускаю');
        return 2

    if month_arg:
        year, month = (int(x) for x in month_arg.split('-'))
    else:
        year, month = prev_month()
    last_day = calendar.monthrange(year, month)[1]
    d1 = f'{year:04d}-{month:02d}-01'
    d2 = f'{year:04d}-{month:02d}-{last_day:02d}'
    month_key = f'{year:04d}-{month:02d}-01'
    OUT['ord_month'] = f'{year:04d}-{month:02d}'

    shows = metrika_pageviews(ya_token, counter, d1, d2)
    if shows is None:
        print('ERROR: не удалось получить pageviews — ничего не отправляю');
        return 1
    OUT['ord_shows'] = shows
    print(f'metrika counter={counter} period={d1}..{d2} pageviews={shows}')

    shows_mm = metrika_pageviews(ya_token, counter, d1, d2, host=mm_host)
    if shows_mm is None:
        print('ERROR: не удалось получить pageviews поддомена — ничего не отправляю');
        return 1
    OUT['ord_shows_mm'] = shows_mm
    print(f'metrika host={mm_host} pageviews={shows_mm}')

    items = [{'creative_external_id': creative, 'pad_external_id': pad,
              'shows_count': shows,
              'date_start_actual': d1, 'date_end_actual': d2},
             {'creative_external_id': creative, 'pad_external_id': pad_mm,
              'shows_count': shows_mm,
              'date_start_actual': d1, 'date_end_actual': d2}]
    print(f'ord base={"sandbox" if sandbox else "prod"} '
          f'creative={creative} pads=[{pad}, {pad_mm}] month={month_key} (токены скрыты)')

    if dry:
        print('DRY_RUN=1 — payload (без отправки):')
        print(json.dumps({'items': items}, ensure_ascii=False))
        return 0

    base = ORD_SANDBOX if sandbox else ORD_PROD
    try:
        resp = http_json(base + '/v1/statistics',
                         token=ord_token, payload={'items': items})
    except Exception as e:  # noqa: BLE001
        print(f'ERROR ord POST /v1/statistics: {e}');
        return 1
    print('ord response:', json.dumps(resp, ensure_ascii=False)[:500])

    try:
        chk = http_json(base + '/v1/statistics/list?' + urllib.parse.urlencode(
            {'months': month_key, 'creative_external_ids': creative,
             'pad_external_ids': f'{pad},{pad_mm}', 'limit': 10}), token=ord_token)
    except Exception as e:  # noqa: BLE001
        print(f'WARN verify list failed: {e}');
        return 0
    got = {it.get('pad_external_id') for it in chk.get('items', [])}
    print(f'verify: найдено записей за месяц: {len(chk.get("items", []))}')
    for p, label in ((pad, 'ratescout'), (pad_mm, 'mymany')):
        if p in got:
            print(f'verify ok [{label}]: запись есть')
        else:
            print(f'WARN verify [{label}]: запись за месяц не найдена (проверьте позже статус ЕРИР)')
    return 0


if __name__ == '__main__':
    code = main()
    try:
        emit_outputs()
    except Exception:  # noqa: BLE001
        pass
    sys.exit(code)
