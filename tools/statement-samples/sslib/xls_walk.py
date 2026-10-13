# -*- coding: utf-8 -*-
"""Обхід XLS (BIFF8): підміна значень на місці зі збереженням довжини й кодування рядків.

Роль комірки — за заголовком першого рядка (схема `alfa`). Рядки живуть у таблиці спільних рядків (SST):
кожен рядок SST отримує роль із комірок, що на нього посилаються (конфлікт KEEP/чутливе — помилка).
Числові комірки чутливих ролей (напр. ід.код числом) підміняються на місці як double.
"""
import struct

from . import biff
from .schema import KEEP, CSV_ROLES
from .util import norm_name

BLANK_CH = '\x01'


class XlsError(Exception):
    pass


def _analyse(data, spec):
    x = biff.read_xls(data)
    roles_map = CSV_ROLES[spec['schema']]
    hdr = x['header']
    col_role = {}
    for c, h in enumerate(hdr):
        n = norm_name(str(h))
        if n == '':
            continue
        if n not in roles_map:
            raise XlsError('невідома колонка XLS: %r' % n[:40])
        col_role[c] = roles_map[n]
    sst_roles = {}
    header_idx = set()
    num_cells = []
    for (r, c), cell in x['cells'].items():
        if r == 0:
            if cell[0] == 'sst':
                header_idx.add(cell[1])
            continue
        role = col_role.get(c)
        if role is None:
            raise XlsError('комірка в колонці без класифікації')
        if cell[0] == 'sst':
            sst_roles.setdefault(cell[1], set()).add(role)
        elif cell[0] == 'num':
            num_cells.append((r, c, role, cell[1]))
    return x, col_role, sst_roles, header_idx, num_cells


def _resolve_role(roles):
    non = sorted(r for r in roles if r != KEEP)
    if non and KEEP in roles:
        raise XlsError('рядок SST спільний для KEEP і чутливої колонки')
    if len(non) > 1:
        # однакове значення в різних чутливих колонках (напр. рахунок і код): беремо першу за алфавітом
        return non[0]
    return non[0] if non else KEEP


def _patch(buf, entry_map, stream_off, raw):
    for i, bt in enumerate(raw):
        buf[entry_map(stream_off + i)] = bt


def walk_xls(data, spec, fn, blank=False):
    x, col_role, sst_roles, header_idx, num_cells = _analyse(data, spec)
    ole, ent = x['ole'], x['entry']
    f2o = ole.stream_to_file(ent)
    buf = bytearray(data)
    for idx, s in enumerate(x['sst']):
        if idx in header_idx and idx not in sst_roles:
            continue
        roles = sst_roles.get(idx)
        if roles is None:
            role = 'SCRAMBLE'          # рядок SST без комірок
        else:
            role = _resolve_role(roles)
        if role == KEEP and not blank:
            continue
        text = s.text
        if text == '':
            continue
        if blank:
            new = BLANK_CH * len(text)
        else:
            new = fn(role, text, 'sst')
            new = new[:len(text)].ljust(len(text))
        pos = 0
        for off, nbytes, high in s.char_spans:
            n = nbytes // (2 if high else 1)
            part = new[pos:pos + n]
            pos += n
            try:
                raw = part.encode('utf-16le') if high else part.encode('latin-1')
            except UnicodeEncodeError:
                raise XlsError('вигадане значення не вміщується в 8-бітний рядок XLS')
            _patch(buf, f2o, off, raw)
    for r, c, role, v in num_cells:
        if role == KEEP and not blank:
            continue
        rid, off = x['cellpos'][(r, c)]
        if rid != 0x0203:
            raise XlsError('числова комірка не у записі NUMBER')
        if blank:
            raw = struct.pack('<d', 0.0)
        else:
            old = str(int(v)) if v == int(v) else repr(v)
            new = fn(role, old, 'num')
            raw = struct.pack('<d', float(new))
        _patch(buf, f2o, off, raw)
    if blank:
        # числові KEEP-комірки теж гасимо в скелеті
        for (r, c), cell in x['cells'].items():
            if r > 0 and cell[0] == 'num' and col_role.get(c) == KEEP:
                rid, off = x['cellpos'][(r, c)]
                if rid == 0x0203:
                    _patch(buf, f2o, off, struct.pack('<d', 0.0))
    return bytes(buf)


def fields_xls(data, spec):
    x, col_role, sst_roles, header_idx, num_cells = _analyse(data, spec)
    sens, keep = [], []
    for idx, s in enumerate(x['sst']):
        if idx in header_idx and idx not in sst_roles:
            continue
        role = _resolve_role(sst_roles[idx]) if idx in sst_roles else 'SCRAMBLE'
        (keep if role == KEEP else sens).append((role, s.text, 'sst'))
    for r, c, role, v in num_cells:
        t = str(int(v)) if v == int(v) else repr(v)
        (keep if role == KEEP else sens).append((role, t, 'num'))
    return sens, keep


def structure_xls(data, spec):
    x = biff.read_xls(data)
    return [str(h) for h in x['header']]
