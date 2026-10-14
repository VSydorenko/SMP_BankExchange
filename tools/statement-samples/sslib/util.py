# -*- coding: utf-8 -*-
"""Спільні утиліти інструменту зразків виписок. Жодна функція не друкує значення полів."""
import re
import struct
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

ENC = 'cp1251'

# Латинські двійники кирилиці (УкрСиб пише «операцiї» з латинською i).
_CONF = str.maketrans({'i': 'і', 'a': 'а', 'c': 'с', 'e': 'е', 'o': 'о', 'p': 'р', 'x': 'х', 'y': 'у', 'ё': 'е', 'I': 'і'})


def norm_name(s):
    """Нормалізація назви колонки: регістр, латиниця-двійники -> кирилиця, пробіли, лапки."""
    s = (s or '').replace('﻿', '').replace('"', '').strip().lower()
    s = re.sub(r'\s+', ' ', s)
    return s.translate(_CONF)


def ws(s):
    return re.sub(r'\s+', ' ', (s or '').replace('\xa0', ' ')).strip()


@dataclass
class Op:
    fmt: str = ''
    src_row: int = 0
    date: Optional[date] = None
    time: Optional[str] = None
    doc_no: str = ''
    doc_date: Optional[date] = None
    amount: Optional[Decimal] = None
    direction: Optional[str] = None      # 'in' / 'out'
    own_acc: str = ''
    own_edrpou: str = ''
    own_mfo: str = ''
    cp_acc: str = ''
    cp_edrpou: str = ''
    cp_mfo: str = ''
    cp_name: str = ''
    cp_bank: str = ''
    purpose: str = ''
    currency: str = ''
    bank_id: str = ''
    op_code: str = ''
    fee_by_code: Optional[bool] = None
    flags: list = field(default_factory=list)


CUR = {'980': 'UAH', '978': 'EUR', '840': 'USD', '985': 'PLN', '826': 'GBP', '643': 'RUB'}
CUR_NUM = {v: k for k, v in CUR.items()}


def cur_norm(s):
    s = (s or '').strip()
    return CUR.get(s, s.upper())


def q2(d):
    return None if d is None else d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def parse_amount(s):
    """'1 234,56' / '1234.56' / '60000' -> Decimal або None. Мінус не знімається."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return Decimal(repr(s)) if isinstance(s, float) else Decimal(s)
    t = str(s).replace('\xa0', '').replace(' ', '').strip()
    if t == '':
        return None
    if ',' in t and '.' in t:
        if t.rfind(',') > t.rfind('.'):
            t = t.replace('.', '').replace(',', '.')
        else:
            t = t.replace(',', '')
    else:
        t = t.replace(',', '.')
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


_DRE = [
    (re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$'), 'dmy'),
    (re.compile(r'^(\d{4})\.(\d{2})\.(\d{2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$'), 'ymd'),
    (re.compile(r'^(\d{4})-(\d{2})-(\d{2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$'), 'ymd'),
    (re.compile(r'^(\d{4})(\d{2})(\d{2})$'), 'ymd'),
]


def parse_date(s):
    """-> (date, 'hh:mm:ss' | None) або (None, None)"""
    if s is None:
        return None, None
    if isinstance(s, (date, datetime)):
        return (s.date() if isinstance(s, datetime) else s), None
    t = str(s).strip()
    for rx, k in _DRE:
        m = rx.match(t)
        if m:
            g = m.groups()
            try:
                d = date(int(g[2]), int(g[1]), int(g[0])) if k == 'dmy' else date(int(g[0]), int(g[1]), int(g[2]))
            except ValueError:
                return None, None
            tm = None
            if len(g) > 3 and g[3] is not None:
                tm = '%02d:%s:%s' % (int(g[3]), g[4], g[5] or '00')
            return d, tm
    return None, None


def iban_ok(s):
    s = (s or '').strip().upper()
    if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{1,30}', s):
        return False
    r = s[4:] + s[:4]
    n = ''.join(str(int(c, 36)) for c in r)
    return int(n) % 97 == 1


def is_ua_iban_shape(s):
    return bool(re.fullmatch(r'UA\d{27}', (s or '').strip().upper()))


FEE_RX = re.compile(r'коміс|комис|commission', re.I)


def fee_text(s):
    return bool(FEE_RX.search(s or ''))


def mask(s):
    """Маска значення для звітів: цифри -> #, латиниця -> a, кирилиця -> я."""
    s = re.sub(r'\d', '#', s or '')
    s = re.sub(r'[A-Za-z]', 'a', s)
    s = re.sub(r'[А-Яа-яІіЇїЄєҐґ]', 'я', s)
    return s


# ---- декодування ----
def read_text_lines(path_or_bytes, enc=ENC):
    """-> (рядки без порожнього хвоста, кількість NUL-байтів). NUL з тексту вилучаються."""
    b = open(path_or_bytes, 'rb').read() if isinstance(path_or_bytes, str) else path_or_bytes
    nul = b.count(b'\x00')
    t = b.decode(enc, errors='replace').replace('\x00', '')
    lines = t.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    return lines, nul


def sniff(path_or_bytes):
    b = open(path_or_bytes, 'rb').read(8) if isinstance(path_or_bytes, str) else path_or_bytes[:8]
    if b[:4] == b'\xd0\xcf\x11\xe0':
        return 'xls'
    if b[:2] == b'PK':
        return 'zip'
    if b[:1] == b'\x03':
        return 'dbf'
    if b.lstrip()[:5] == b'<?xml':
        return 'xml'
    return 'text'


def split_csv_quoted(line, delim=';'):
    """Розбір одного рядка CSV за правилами RFC 4180: -> список (сирий_текст, значення, у_лапках).
    Лапка всередині поля в лапках подвоюється. Поле без початкової лапки береться дослівно."""
    out = []
    i, n = 0, len(line)
    while True:
        if i < n and line[i] == '"':
            j = i + 1
            val = []
            while j < n:
                if line[j] == '"':
                    if j + 1 < n and line[j + 1] == '"':
                        val.append('"')
                        j += 2
                        continue
                    break
                val.append(line[j])
                j += 1
            k = j + 1          # після закривальної лапки
            # хвіст між закривальною лапкою і роздільником (у зразках — порожній)
            e = line.find(delim, k)
            e = n if e < 0 else e
            tail = line[k:e]
            out.append((line[i:e], ''.join(val) + tail, True))
            i = e
        else:
            e = line.find(delim, i)
            e = n if e < 0 else e
            out.append((line[i:e], line[i:e], False))
            i = e
        if i >= n:
            break
        i += 1               # пропустити роздільник
        if i == n:           # рядок закінчився роздільником -> порожнє поле
            out.append(('', '', False))
            break
    return out


def read_csv_rows(path_or_bytes, enc=ENC, delim=';'):
    """-> (header, rows, meta). Рядки розбираються за RFC 4180 (відступ 1: лапки знімаються)."""
    lines, nul = read_text_lines(path_or_bytes, enc)
    meta = {'nul': nul, 'trail_extra': 0, 'short': 0, 'long': 0}
    lines = [l for l in lines if l.strip() != '']
    if not lines:
        return [], [], meta
    allrows = [[v for _, v, _ in split_csv_quoted(l, delim)] for l in lines]
    header = [h.strip() for h in allrows[0]]
    n = len(header)
    rows = []
    for r in allrows[1:]:
        if len(r) > n:
            if all(x.strip() == '' for x in r[n:]):
                meta['trail_extra'] += 1
            else:
                meta['long'] += 1
            r = r[:n]
        if len(r) < n:
            meta['short'] += 1
            r = r + [''] * (n - len(r))
        rows.append(r)
    return header, rows, meta


# ---- DBF ----
def dbf_layout(b):
    """-> (fields[(name,type,len,dec)], nrec, hlen, rlen). Довжина символьного поля 16-бітна."""
    nrec = struct.unpack('<I', b[4:8])[0]
    hlen, rlen = struct.unpack('<HH', b[8:12])
    fields = []
    pos = 32
    while b[pos] != 0x0D:
        name = b[pos:pos + 11].split(b'\x00')[0].decode('ascii', 'replace')
        t = chr(b[pos + 11])
        ln = b[pos + 16]
        dc = b[pos + 17]
        if t == 'C':
            ln = ln + dc * 256
        fields.append((name, t, ln, dc))
        pos += 32
    return fields, nrec, hlen, rlen


# Дві моделі читання DBF. Кожен виклик read_dbf МУСИТЬ назвати модель (параметр model без значення за
# замовчуванням): модель продукту й модель старої обробки відрізняються, і підміна однієї іншою мовчки
# змінює результат.
#
# 'product' — контейнер ЗаписиDBF продукту (СМП_ЧтениеВыписокОбщее): байти поля декодуються кодуванням
#   enc; NUL (код 0) -> апостроф (довжина не змінюється); справа знімаються лише пробіли (код 32), ліві
#   пробіли й усі інші символи лишаються; вилучені записи пропускаються, але нумерація фізична
#   (meta['numbers'][i] — номер запису у файлі з одиниці, вилучені його займають).
# 'legacy'  — старі обробки (XBase, вимір у журналі прогонів плану 03, задача 4): значення поля
#   обрізається на ПЕРШОМУ NUL; вилучені записи пропускаються; номера запису для людини XBase не дає,
#   meta['numbers'] — внутрішній порядковий номер серед невилучених (з продуктом не зіставляти).
#   Подальше .strip() з обох боків — це СокрЛП, який старі обробки застосовують самі (розкладки в
#   legacy.py), а не властивість XBase (XBase віддає значення з добивкою).
DBF_PRODUCT = 'product'
DBF_LEGACY = 'legacy'
DBF_MODELS = (DBF_PRODUCT, DBF_LEGACY)


def dbf_value(raw, enc, model):
    text = raw.decode(enc, errors='replace')
    if model == DBF_PRODUCT:
        return text.replace('\x00', "'").rstrip(' ')
    if model == DBF_LEGACY:
        return text.split('\x00', 1)[0].strip()
    raise ValueError('невідома модель DBF: %r (допустимі: %s)' % (model, ', '.join(DBF_MODELS)))


def read_dbf(path_or_bytes, *, model, enc=ENC):
    """-> (fields, recs, meta). model — 'product' або 'legacy' (обов'язково, див. вище).
    meta: nrec_hdr, deleted, rlen, numbers (номер запису для кожного елемента recs), model."""
    if model not in DBF_MODELS:
        raise ValueError('невідома модель DBF: %r (допустимі: %s)' % (model, ', '.join(DBF_MODELS)))
    b = open(path_or_bytes, 'rb').read() if isinstance(path_or_bytes, str) else path_or_bytes
    fields, nrec, hlen, rlen = dbf_layout(b)
    recs = []
    numbers = []
    deleted = 0
    for i in range(nrec):
        rec = b[hlen + i * rlen: hlen + (i + 1) * rlen]
        if len(rec) < rlen:
            break
        if rec[0:1] == b'*':
            deleted += 1
            continue
        p = 1
        d = {}
        for name, t, ln, dc in fields:
            d[name] = dbf_value(rec[p:p + ln], enc, model)
            p += ln
        recs.append(d)
        numbers.append(i + 1 if model == DBF_PRODUCT else len(recs))
    return fields, recs, {'nrec_hdr': nrec, 'deleted': deleted, 'rlen': rlen, 'numbers': numbers, 'model': model}
