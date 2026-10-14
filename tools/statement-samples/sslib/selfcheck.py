# -*- coding: utf-8 -*-
"""Самоперевірка оракула на сирих зразках (крок 1): розкладки старих обробок проти розбору «за назвою»,
перехресні звірки ОТП, масштаб SUMMA. Друкує лише кількості. Код виходу 1, якщо розбіжність із
очікуваними числами `40-oracle.md` (EXPECT)."""
import os
import re
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal

from . import corpus, legacy, named
from .util import q2, ws, read_text_lines

# (обробка, розкладка, мітки) -> очікуване з 40-oracle.md розд. 2: (рядків, прочитано, усі ключові вірні)
CASES = [
    ('Акорд (A)', 'A', lambda D: ['Кл-Акорд']),
    ('БанкВосток (A)', 'A', lambda D: ['Восток#1']),
    ('Універсал (A)', 'A', lambda D: [k for k in D if k.startswith('Універсал-csv')]),
    ('ПроКредит (A2)', 'A2_procredit', lambda D: [k for k in D if k.startswith('ПроКредит')]),
    ('УкрСиб (A2)', 'A2_ukrsib', lambda D: [k for k in D if k.startswith('УкрСиб')]),
    ('УкрГаз (B)', 'ukrgaz', lambda D: [k for k in D if k.startswith('УкрГаз')]),
    ('Сенс (C, юр.особа)', 'sens', lambda D: [k for k in D if k.startswith('АльфаТОВ') and D[k]['key'] == 'alfa_csv']),
    ('Сенс (C, ФОП)', 'sens', lambda D: [k for k in D if k.startswith('АльфаФОП')]),
    ('ОТП (D) 1191', 'otp', lambda D: ['Кл-ОТП-dat-1191']),
    ('ОТП (D) 660', 'otp', lambda D: ['Кл-ОТП-dat-660', 'ОТП-170521-txt']),
    ('Ощад (E)', 'oschad', lambda D: [k for k in D if k.startswith('Ощад') or k.startswith('Кл-Ощад')]),
    ('Південний (F)', 'pivd', lambda D: [k for k in D if k.startswith('Південний')]),
]
# очікувано: (всього рядків, прочитано без винятку, усі ключові вірні) — 40-oracle.md, розд. 1–2
EXPECT = {
    'Акорд (A)': (17, 17, 17), 'БанкВосток (A)': (2, 2, 2), 'Універсал (A)': (82, 82, 82),
    'ПроКредит (A2)': (373, 373, 373), 'УкрСиб (A2)': (231, 231, 231), 'УкрГаз (B)': (7, 7, 7),
    'Сенс (C, юр.особа)': (231, 231, 176), 'Сенс (C, ФОП)': (37, 37, 37),
    'ОТП (D) 1191': (15, 15, 0), 'Ощад (E)': (221, 221, 221), 'Південний (F)': (113, 113, 106),
}


def _data(D, label):
    return open(D[label]['path'], 'rb').read()


def run_layouts(D, log):
    bad = 0
    for name, lay, sel in CASES:
        labels = sel(D)
        S, F, T, ak, npairs = Counter(), Counter(), Counter(), 0, 0
        for l in labels:
            emu = legacy.emulate(_data(D, l), lay, 'old')
            st, fld, tot, a, n, kf = legacy.compare(emu, D[l]['ops'])
            S += st; F += fld; T += tot; ak += a; npairs += n
        rows = sum(S.values())
        log('%s: файлів %d, рядків %d, статуси %s, усі ключові вірні %d з %d' % (name, len(labels), rows, dict(S), ak, S.get('ok', 0)))
        if name in EXPECT:
            exp = EXPECT[name]
            got = (rows, S.get('ok', 0), ak)
            if got != exp:
                bad += 1
                log('  РОЗБІЖНІСТЬ: очікувано %s, отримано %s' % (exp, got))
    return bad


def _members(path, ext):
    z = zipfile.ZipFile(path)
    return [(nm, z.read(nm)) for nm in sorted(z.namelist()) if nm.lower().endswith(ext)]


def _match(A, B, keyf):
    idx = defaultdict(list)
    for b in B:
        idx[keyf(b)].append(b)
    pairs, ua = [], []
    for a in A:
        lst = idx.get(keyf(a))
        if lst:
            pairs.append((a, lst.pop(0)))
        else:
            ua.append(a)
    return pairs, ua, [b for l in idx.values() for b in l]


FIELDS = [
    ('напрям', lambda o: o.direction), ('дата', lambda o: o.date), ('дата док.', lambda o: o.doc_date),
    ('сума', lambda o: q2(o.amount)), ('валюта', lambda o: o.currency), ('власний рах.', lambda o: o.own_acc),
    ('рах.контрагента', lambda o: o.cp_acc), ('ЄДРПОУ власн.', lambda o: o.own_edrpou),
    ('ЄДРПОУ контр.', lambda o: o.cp_edrpou), ('МФО контр.', lambda o: o.cp_mfo),
    ('назва контр.', lambda o: ws(o.cp_name)), ('призначення', lambda o: ws(o.purpose)),
]


def field_matches(pairs, fields=FIELDS):
    return {n: sum(1 for a, b in pairs if f(a) == f(b)) for n, f in fields}


def run_crosschecks(D, root, log):
    """Звірки ОТП 233/233 (xls=dbf=xml), масштаб SUMMA, txt ⊇ 233, пара .dat↔.dbf 15/15. -> кількість розбіжностей."""
    bad = 0
    otp = os.path.join(root, 'Банк ОТП (файли загрузки)')
    xls = D['ОТП-170521-xls']['ops']
    dbf = D['ОТП-170521-dbf.zip']['ops']
    key = lambda o: (ws(o.doc_no), q2(o.amount), o.currency)
    # масштаб SUMMA
    for scale, want in ((Decimal(100), 233), (Decimal(1), 0)):
        xml = []
        for nm, b in _members(os.path.join(otp, '170521 xml.zip'), '.xml'):
            xml += named.read_xml_rowdata(b, scale=scale)[0]
        p, _, _ = _match(xls, xml, lambda o: (ws(o.doc_no), q2(o.amount)))
        log('SUMMA/%s: пар з XLS %d (очікувано %d)' % (scale, len(p), want))
        bad += len(p) != want
    xml = []
    for nm, b in _members(os.path.join(otp, '170521 xml.zip'), '.xml'):
        xml += named.read_xml_rowdata(b)[0]
    pxd, _, _ = _match(xls, dbf, key)
    pxx, _, _ = _match(xls, xml, key)
    pdx, _, _ = _match(dbf, xml, key)
    for title, pairs in (('xls↔dbf', pxd), ('xls↔xml', pxx), ('dbf↔xml', pdx)):
        fm = field_matches(pairs)
        log('%s: пар %d; поля, де збіг < пар: %s' % (title, len(pairs), {k: v for k, v in fm.items() if v != len(pairs)}))
        bad += len(pairs) != 233 or any(v != len(pairs) for v in fm.values())
    # txt (599) ⊇ 233
    txt = D['ОТП-170521-txt']['ops']
    ptx, ua, _ = _match(dbf, txt, lambda o: (q2(o.amount), o.own_acc, o.cp_acc, ws(o.doc_no), o.date))
    fm = field_matches(ptx, [f for f in FIELDS if f[0] not in ('дата док.', 'ЄДРПОУ власн.')])
    log('dbf(233)↔txt(599): пар %d, без пари в dbf %d; не повні збіги: %s' % (len(ptx), len(ua), {k: v for k, v in fm.items() if v != len(ptx)}))
    bad += len(ptx) != 233
    # пара .dat↔.dbf 15/15
    dat, dbf1 = D['Кл-ОТП-dat-1191']['ops'], D['Кл-ОТП-dbf']['ops']
    pairs = list(zip(dat, dbf1))
    fm = field_matches(pairs)
    log('ОТП .dat1191↔.dbf: пар %d (рядок до рядка); не повні збіги: %s' % (len(pairs), {k: v for k, v in fm.items() if v != len(pairs)}))
    bad += len(pairs) != 15 or any(v != 15 for v in fm.values())
    return bad


def run_counts(D, log):
    """Кількості розібрано/усього за таблицею 40-oracle.md розд. 1 (по групах)."""
    exp = {'Аваль': [9], 'АльфаФОП': [37], 'Восток': [2], 'ПроКредит': [43 + 158 + 158 + 14], 'УкрСиб': [13 + 81 + 33 + 36 + 67 + 1],
           'Універсал-csv': [5 + 25 + 25 + 27], 'Універсал-dbf': [27], 'УкрГаз': [7], 'Південний': [113],
           'Ощад': [14 + 179 + 4], 'Кл-Ощад': [24]}
    bad = 0
    for pref, (n,) in exp.items():
        tot = sum(len(v['ops']) for k, v in D.items() if k.startswith(pref + '#') or k == pref)
        fails = sum(sum(v['meta'].get('fail', {}).values()) for k, v in D.items() if k.startswith(pref + '#') or k == pref)
        log('%s: розібрано %d (очікувано %d), збоїв %d' % (pref, tot, n, fails))
        bad += tot != n or fails != 0
    alfa = [k for k in D if k.startswith('АльфаТОВ')]
    tot = sum(len(D[k]['ops']) for k in alfa)
    log('АльфаТОВ (CSV+XLS): розібрано %d (очікувано %d)' % (tot, 82 + 82 + 37 + 30 + 28 + 5 + 9 + 11))
    bad += tot != 82 + 82 + 37 + 30 + 28 + 5 + 9 + 11
    for k, want in (('ОТП-170521-txt', 599), ('Кл-ОТП-dat-660', 386), ('Кл-ОТП-dat-1191', 15), ('Кл-ОТП-dbf', 15),
                    ('ОТП-170521-xls', 233), ('ОТП-170521-dbf.zip', 233), ('ОТП-170521-xml.zip', 233), ('Кл-Акорд', 17)):
        n = len(D[k]['ops'])
        log('%s: розібрано %d (очікувано %d)' % (k, n, want))
        bad += n != want
    return bad


def run(root, log=print):
    D = corpus.load_all(root)
    log('файлів у корпусі: %d' % len(D))
    bad = run_counts(D, log)
    log('--- розкладки старих обробок проти розбору за назвою ---')
    bad += run_layouts(D, log)
    log('--- перехресні звірки ---')
    bad += run_crosschecks(D, root, log)
    # УкрГаз: баланс
    ug = [v for k, v in D.items() if k.startswith('УкрГаз')]
    for v in ug:
        bt = v['meta'].get('balance_tests', {})
        ok = {dk: bool(r) and all(r.values()) for dk, r in bt.items()}
        log('УкрГаз баланс: DK=1 списання %s, DK=2 списання %s; визначено %s' % (ok.get('1'), ok.get('2'), v['meta'].get('debit_dk')))
        bad += not (ok.get('2') and not ok.get('1'))
    log('РОЗБІЖНОСТЕЙ: %d' % bad)
    return bad
