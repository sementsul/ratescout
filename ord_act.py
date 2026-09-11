#!/usr/bin/env python3
"""Ежемесячный акт в VK ОРД (ЕРИР) по договору с рекламодателем.

Официальные документы (VK ORD API):
- «Создать полный акт (v3)»: PUT /v3/invoice/{external_id} с полной
  детализацией (разаллокация по изначальному договору + креативы + площадки)
  уходит в ЕРИР сразу. С ?draft=true — остаётся черновиком.
- «Пример создания акта с неявным связыванием со статистикой»: если
  статистика уже подана отдельно (наш ord_stats.py), в акте достаточно
  перечислить креативы изначального договора.
- Акт подаётся в течение 30 дней после месяца счёта. Крон — 5-го числа.

Показы берутся из Яндекс.Метрики (ym:s:pageviews), как в ord_stats.py.
Сумму акта скрипт сам знать не может — источники по приоритету:
  1) ORD_AMOUNT (+ ORD_VAT_RATE) из окружения / inputs workflow;
  2) файл ord-amounts.json в корне репо: {"2026-08": {"including_vat": "1000", "vat_rate": "0"}};
  3) нет суммы → черновик НЕ создаём, шлём TG-напоминание (result=need_amount).

Секреты — только из окружения, в лог не печатаются:
  ORD_API_TOKEN, YANDEX_OAUTH_TOKEN, YANDEX_METRIKA_COUNTER (default 111586112),
  ORD_CONTRACT_ID, ORD_CREATIVE_ID, ORD_PAD_ID.
Режимы: DRY_RUN=1 (только payload), ORD_SANDBOX=1 (песочница, не ЕРИР),
ORD_MONTH=YYYY-MM (по умолчанию прошлый месяц).
"""
import calendar
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP

MET = 'https://api-metrika.yandex.net/stat/v1/data'
ORD_PROD = 'https://api.ord.vk.com'
ORD_SANDBOX = 'https://api-sandbox.ord.vk.com'
ROOT = os.path.dirname(os.path.abspath(__file__))

OUT = {}


def emit_outputs():
    path = os.environ.get('GITHUB_OUTPUT', '')
    if not path:
        return
    with open(path, 'a', encoding='utf-8') as f:
        for k in ('ord_month', 'ord_shows', 'ord_amount', 'ord_result'):
            f.write(f'{k}={OUT.get(k, "")}\n')


def q2(x):
    return str(Decimal(str(x)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def http_json(url, token=None, payload=None, method=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {'User-Agent': 'ratescout-ord/1.0'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method or ('PUT' if payload is not None else 'GET'))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def split_vat(including, rate):
    inc = Decimal(str(including))
    r = Decimal(str(rate or '0'))
    if r == 0:
        return q2(inc), '0', '0.00', '0.00'
    excl = (inc / (1 + r / 100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return q2(inc), q2(r), str(excl), q2(inc - excl)


def metrika_pageviews(token, counter, d1, d2):
    params = {'ids': counter, 'metrics': 'ym:s:pageviews',
              'date1': d1, 'date2': d2, 'accuracy': 'full'}
    try:
        data = http_json(MET + '?' + urllib.parse.urlencode(params), token=token)
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


def load_amount(year, month):
    """Сумма акта: env ORD_AMOUNT/ORD_VAT_RATE → ord-amounts.json → None."""
    env_amt = os.environ.get('ORD_AMOUNT', '').strip()
    if env_amt:
        return env_amt, os.environ.get('ORD_VAT_RATE', '0').strip() or '0'
    key = f'{year:04d}-{month:02d}'
    fp = os.path.join(ROOT, 'ord-amounts.json')
    if os.path.exists(fp):
        try:
            data = json.load(open(fp, encoding='utf-8'))
            row = data.get(key) or {}
            if row.get('including_vat'):
                return str(row['including_vat']), str(row.get('vat_rate', '0'))
        except Exception as e:  # noqa: BLE001
            print(f'WARN ord-amounts.json: {e}')
    return None, None


def main():
    ord_token = os.environ.get('ORD_API_TOKEN', '')
    ya_token = os.environ.get('YANDEX_OAUTH_TOKEN', '')
    counter = os.environ.get('YANDEX_METRIKA_COUNTER', '') or '111586112'
    contract = os.environ.get('ORD_CONTRACT_ID', '') or '0p9kbpb88ks-1k28icnp8'
    creative = os.environ.get('ORD_CREATIVE_ID', '') or '85bcklvevfc-1k28ihvhd'
    pad = os.environ.get('ORD_PAD_ID', '') or '1ggont56t70-1k28j2dhf'
    sandbox = os.environ.get('ORD_SANDBOX', '') == '1'
    dry = os.environ.get('DRY_RUN', '') == '1'
    month_arg = os.environ.get('ORD_MONTH', '')

    if not ord_token:
        print('ERROR: нет ORD_API_TOKEN'); return 2
    if not ya_token:
        print('ERROR: нет YANDEX_OAUTH_TOKEN'); return 2

    today = dt.date.today()
    if month_arg:
        year, month = (int(x) for x in month_arg.split('-'))
    else:
        first = today.replace(day=1)
        prev = first - dt.timedelta(days=1)
        year, month = prev.year, prev.month
    last_day = calendar.monthrange(year, month)[1]
    d1 = f'{year:04d}-{month:02d}-01'
    d2 = f'{year:04d}-{month:02d}-{last_day:02d}'
    OUT['ord_month'] = f'{year:04d}-{month:02d}'

    shows = metrika_pageviews(ya_token, counter, d1, d2)
    if shows is None:
        print('ERROR: не удалось получить pageviews — акт не создаю');
        return 1
    OUT['ord_shows'] = shows
    print(f'metrika counter={counter} period={d1}..{d2} pageviews={shows}')

    including, vat_rate = load_amount(year, month)
    if not including:
        OUT['ord_result'] = 'need_amount'
        print(f'NEED_AMOUNT: нет суммы за {OUT["ord_month"]} — '
              'укажите ORD_AMOUNT (или ord-amounts.json) и перезапустите; '
              'в ЕРИР ничего не отправлено');
        return 0
    inc, rate, excl, vat = split_vat(including, vat_rate)
    OUT['ord_amount'] = inc
    per_event = q2(Decimal(inc) / shows) if shows else '0.00'
    ext_id = f'act-ratescout-{year:04d}{month:02d}'
    serial = f'RS-{year:04d}{month:02d}'
    act_date = today.isoformat()

    payload = {
        'contract_external_id': contract,
        'date': act_date,
        'serial': serial,
        'date_start': d1,
        'date_end': d2,
        'amount': {'services': {'including_vat': inc, 'vat_rate': rate,
                                'excluding_vat': excl, 'vat': vat}},
        'client_role': 'advertiser',
        'contractor_role': 'publisher',
        'items': [{
            'contract_external_id': contract,
            'amount': {'including_vat': inc, 'vat_rate': rate,
                       'excluding_vat': excl, 'vat': vat},
            'creatives': [{
                'creative_external_id': creative,
                'platforms': [{
                    'pad_external_id': pad,
                    'shows_count': shows,
                    'invoice_shows_count': shows,
                    'amount': {'including_vat': inc, 'vat_rate': rate,
                               'excluding_vat': excl, 'vat': vat},
                    'amount_per_event': per_event,
                    'date_start_planned': d1,
                    'date_end_planned': d2,
                    'date_start_actual': d1,
                    'date_end_actual': d2,
                    'pay_type': 'other',
                }],
            }],
        }],
    }
    base = ORD_SANDBOX if sandbox else ORD_PROD
    print(f'ord base={"sandbox" if sandbox else "prod"} act={ext_id} '
          f'serial={serial} amount={inc} (токены скрыты)')

    if dry:
        OUT['ord_result'] = 'dry'
        print('DRY_RUN=1 — payload (без отправки):')
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    try:
        resp = http_json(f'{base}/v3/invoice/{ext_id}', token=ord_token,
                         payload=payload, method='PUT')
    except Exception as e:  # noqa: BLE001
        OUT['ord_result'] = 'fail'
        print(f'ERROR ord PUT /v3/invoice: {e}');
        return 1
    print('ord response:', json.dumps(resp, ensure_ascii=False)[:500])

    try:
        chk = http_json(f'{base}/v3/invoice/{ext_id}', token=ord_token)
        print('verify act:', json.dumps(chk, ensure_ascii=False)[:300])
    except Exception as e:  # noqa: BLE001
        print(f'WARN verify GET failed: {e}')
    OUT['ord_result'] = 'sent'
    print(f'SENT act {ext_id} month={OUT["ord_month"]} shows={shows} amount={inc}')
    return 0


if __name__ == '__main__':
    code = main()
    try:
        emit_outputs()
    except Exception:  # noqa: BLE001
        pass
    sys.exit(code)
