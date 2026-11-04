# -*- coding: utf-8 -*-
"""Запис відповідей API: читання, запис, пакування, розбір тіла. Формат — `tools/api-recorder/FORMAT.md`, версія 1.

Запис — тека з `recording.json` (маніфест, упорядкований перелік обмінів) і файлами `NNNN.json` (один обмін на файл).
Тіло відповіді — байтами в Base64 (кодування — частина даних, рекордер його не змінює).

**Пакет (`pack`/`unpack`)** — той самий запис в одному JSON-файлі, для макета тестового розширення (один макет — один
запис): `{"format": "smp-api-recording-pack", "formatVersion": 1, "manifest": <recording.json>,
"exchanges": {"0001.json": <обмін>, ...}}`. Об'єкти — дослівно ті самі, що лежать у теці, тож `unpack(pack(x))` дає
записану теку без втрат (тест у `tests/test_api_recording.py`).
"""
import base64
import json
import os
import re
from decimal import Decimal
from urllib.parse import parse_qsl

FORMAT = 'smp-api-recording'
EXCHANGE_FORMAT = 'smp-api-exchange'
PACK_FORMAT = 'smp-api-recording-pack'
VERSION = 1
STATES = ('ok', 'incomplete', 'aborted', 'error', 'interrupted', 'leak-detected')
FAILURE_KINDS = ('timeout', 'network', 'other')
HEADER_WHITELIST_RX = re.compile(r'^(content-type|retry-after|date|x-rate-limit-.*|x-ratelimit-.*|ratelimit-.*)$')


class FormatError(ValueError):
    """Запис порушує FORMAT.md."""


class NotJson(ValueError):
    """Тіло відповіді не є JSON (наприклад, HTML проксі)."""


def _dumps(obj, indent=None):
    return json.dumps(obj, ensure_ascii=False, indent=indent, sort_keys=False)


def make_exchange(seq, scenario, request, response=None, failure=None, started='2026-10-15T09:00:00.000Z',
                  duration_ms=10):
    """Обмін у форматі FORMAT.md. `request` = {method, host, path, query}; `response` = {status, headers, body(bytes)}
    або None; `failure` = {kind, text} або None. Рівно одне з response / failure."""
    if (response is None) == (failure is None):
        raise FormatError('обмін має або response, або failure')
    ex = {'format': EXCHANGE_FORMAT, 'formatVersion': VERSION, 'seq': seq, 'scenario': scenario,
          'startedUtc': started, 'durationMs': duration_ms,
          'request': {'method': request.get('method', 'GET'), 'host': request['host'], 'path': request['path'],
                      'query': request.get('query', '')}}
    if response is not None:
        body = response['body']
        ex['response'] = {'status': response['status'],
                          'headers': [[k.lower(), v] for k, v in response.get('headers', [])],
                          'bodyLength': len(body), 'bodyBase64': base64.b64encode(body).decode('ascii')}
        ex['failure'] = None
    else:
        ex['response'] = None
        ex['failure'] = {'kind': failure['kind'], 'text': failure['text']}
    return ex


def make_manifest(bank, run_label, exchanges, state='ok', note='', started='2026-10-15T09:00:00.000Z',
                  finished='2026-10-15T09:00:05.000Z', recorder='synthetic'):
    return {'format': FORMAT, 'formatVersion': VERSION, 'recorderVersion': recorder, 'bank': bank, 'runLabel': run_label,
            'startedUtc': started, 'finishedUtc': finished, 'state': state, 'note': note,
            'exchanges': [{'seq': e['seq'], 'file': '%04d.json' % e['seq'], 'scenario': e['scenario'],
                           'status': (e['response']['status'] if e['response'] else None),
                           'failure': (e['failure']['kind'] if e['failure'] else None)} for e in exchanges]}


class Recording:
    def __init__(self, manifest, exchanges):
        self.manifest = manifest
        self.exchanges = exchanges          # у порядку маніфесту (seq)
        self.validate()

    # ------------------------------------------------------------------ перевірка формату
    def validate(self):
        m = self.manifest
        if m.get('format') != FORMAT or m.get('formatVersion') != VERSION:
            raise FormatError('маніфест: format/formatVersion')
        if m.get('bank') not in ('privat', 'mono-corp', 'mono-fop'):
            raise FormatError('маніфест: bank')
        if m.get('state') not in STATES:
            raise FormatError('маніфест: state')
        listed = m.get('exchanges', [])
        if [e['seq'] for e in listed] != [e['seq'] for e in self.exchanges]:
            raise FormatError('маніфест: порядок обмінів не збігається з файлами')
        for i, e in enumerate(self.exchanges):
            if e.get('format') != EXCHANGE_FORMAT or e.get('formatVersion') != VERSION:
                raise FormatError('обмін %d: format' % e.get('seq', i))
            if 'headers' in e.get('request', {}):
                raise FormatError('обмін %d: у запиті не може бути заголовків' % e['seq'])
            if e['request'].get('method') != 'GET':
                raise FormatError('обмін %d: метод не GET' % e['seq'])
            r, f = e.get('response'), e.get('failure')
            if (r is None) == (f is None):
                raise FormatError('обмін %d: рівно одне з response / failure' % e['seq'])
            if r is not None:
                body = base64.b64decode(r['bodyBase64'], validate=True)
                if len(body) != r['bodyLength']:
                    raise FormatError('обмін %d: bodyLength' % e['seq'])
                for k, _ in r['headers']:
                    if k != k.lower() or not HEADER_WHITELIST_RX.match(k):
                        raise FormatError('обмін %d: заголовок поза білим списком: %s' % (e['seq'], k))
            else:
                if f.get('kind') not in FAILURE_KINDS:
                    raise FormatError('обмін %d: failure.kind' % e['seq'])

    # ------------------------------------------------------------------ тека
    @classmethod
    def from_dir(cls, path):
        with open(os.path.join(path, 'recording.json'), encoding='utf-8') as f:
            manifest = json.load(f)
        exchanges = []
        for entry in manifest['exchanges']:
            with open(os.path.join(path, entry['file']), encoding='utf-8') as f:
                exchanges.append(json.load(f))
        return cls(manifest, exchanges)

    def to_dir(self, path):
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, 'recording.json'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(_dumps(self.manifest, 1) + '\n')
        for e in self.exchanges:
            with open(os.path.join(path, '%04d.json' % e['seq']), 'w', encoding='utf-8', newline='\n') as f:
                f.write(_dumps(e, 1) + '\n')

    # ------------------------------------------------------------------ пакет
    def pack(self):
        pk = {'format': PACK_FORMAT, 'formatVersion': VERSION, 'manifest': self.manifest,
              'exchanges': {'%04d.json' % e['seq']: e for e in self.exchanges}}
        return _dumps(pk, 1) + '\n'

    @classmethod
    def unpack(cls, text):
        pk = json.loads(text)
        if pk.get('format') != PACK_FORMAT or pk.get('formatVersion') != VERSION:
            raise FormatError('пакет: format')
        exchanges = [pk['exchanges'][entry['file']] for entry in pk['manifest']['exchanges']]
        return cls(pk['manifest'], exchanges)

    @property
    def bank(self):
        return self.manifest['bank']


# ---------------------------------------------------------------------- розбір обміну
def body_bytes(ex):
    r = ex['response']
    return base64.b64decode(r['bodyBase64']) if r else b''


def header(ex, name):
    r = ex['response']
    if not r:
        return None
    for k, v in r['headers']:
        if k == name.lower():
            return v
    return None


def charset_of(ex):
    ct = header(ex, 'content-type') or ''
    m = re.search(r'charset\s*=\s*([\w\-]+)', ct, re.I)
    return (m.group(1).lower() if m else 'utf-8')


def body_text(ex):
    """Тіло як текст за `charset` із content-type (`cp1251`, `utf8`/`utf-8`); без charset — UTF-8."""
    cs = charset_of(ex)
    cs = {'utf8': 'utf-8', 'cp1251': 'cp1251', 'windows-1251': 'cp1251'}.get(cs, cs)
    return body_bytes(ex).decode(cs)


def body_json(ex):
    """Тіло як JSON (числа з дробом — Decimal). Не JSON -> NotJson."""
    try:
        return json.loads(body_text(ex), parse_float=Decimal)
    except (ValueError, LookupError) as e:       # UnicodeDecodeError і JSONDecodeError — підкласи ValueError
        raise NotJson(str(e))


def query_pairs(ex):
    return parse_qsl(ex['request']['query'], keep_blank_values=True)


_STATEMENT_RX = re.compile(r'^/(?:personal/statement|ext/v1/statement)/([^/]+)/(\d+)/(\d+)$')


def statement_window(ex):
    """(ідентифікатор рахунку, from, to) із шляху запиту виписки monobank; інакше None."""
    m = _STATEMENT_RX.match(ex['request']['path'])
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m else None
