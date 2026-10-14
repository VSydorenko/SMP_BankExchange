# -*- coding: utf-8 -*-
"""Корпус сирих зразків: узагальнені мітки замість імен файлів (імена містять назви клієнтів і ПІБ).

Шляхи задаються масками папок/розширень. Назв клієнтів у масках немає: теку клієнта описано як
`* - Виписки банка`. Файли `settings*` у теках API-банків виключаються явно (не відкриваються).
"""
import glob
import os
import zipfile
from collections import Counter

from . import named
from .util import sniff

EXCLUDE_PREFIXES = ('settings',)      # будь-який файл з таким початком імені (регістр не важить) не береться


def _excluded(path):
    return os.path.basename(path).lower().startswith(EXCLUDE_PREFIXES)


def build(root):
    """-> список (мітка, шлях, ключ_читача). Мітки не містять особистих даних."""
    R = []

    def g(pat, recursive=False):
        return sorted(p for p in glob.glob(os.path.join(root, pat), recursive=recursive)
                      if os.path.isfile(p) and not _excluded(p))

    def add(prefix, paths, key):
        for i, p in enumerate(paths, 1):
            R.append(('%s#%d' % (prefix, i), p, key))

    client = '* - Виписки банка'
    add('Аваль', g('Банк Аваль*/*.csv'), 'ifobs')
    for i, p in enumerate(g('Банк АльфаБанк_ТОВ*/**/*', True), 1):
        R.append(('АльфаТОВ#%d' % i, p, 'alfa_xls' if sniff(p) == 'xls' else 'alfa_csv'))
    add('АльфаФОП', g('Банк АльфаБанк_ФОП*/*.csv'), 'ifobs')
    add('Восток', g('Банк Восток/*.csv'), 'ifobs')
    add('ПроКредит', g('Банк ПроКредитБанк*/**/*.csv', True), 'ifobs')
    add('УкрСиб', g('Банк УкрСибБанк*/*.csv'), 'ifobs')
    add('Універсал-csv', g('Банк Універсал*/*.csv'), 'ifobs')
    add('Універсал-dbf', g('Банк Універсал*/*.dbf'), 'dbf_univ')
    add('УкрГаз', g('Банк УкрГазБанк*/*.csv'), 'ukrgaz')
    add('Ощад', g('Банк ОщадБанк*/*.Dbf') + g('Банк ОщадБанк*/Старі файли/*.Dbf'), 'dbf_oschad')
    add('Південний', g('Банк Південний*/*.xml'), 'xml')
    otp = 'Банк ОТП (файли загрузки)'
    for label, name, key in (('ОТП-170521-txt', '170521 txt.txt', 'otp_dat'),
                             ('ОТП-170521-xls', '170521.xls', 'alfa_xls'),
                             ('ОТП-170521-dbf.zip', '170521 dbf.zip', 'zip_dbf_otp'),
                             ('ОТП-170521-xml.zip', '170521 xml.zip', 'zip_xml')):
        R.append((label, os.path.join(root, otp, name), key))
    one = lambda pat: (g(pat) or [None])[0]
    for label, pat, key in (('Кл-Акорд', client + '/АкордБанк*.csv', 'ifobs'),
                            ('Кл-ОТП-dat-660', client + '/ОТП 200123.dat', 'otp_dat'),
                            ('Кл-ОТП-dat-1191', client + '/ОТП нова виписка/030423.dat', 'otp_dat'),
                            ('Кл-ОТП-dbf', client + '/ОТП нова виписка/230331.dbf', 'dbf_otp')):
        p = one(pat)
        if p:
            R.append((label, p, key))
    add('Кл-Ощад', g(client + '/Ощад*.Dbf'), 'dbf_oschad')
    return R


def read_any(path, key):
    if key == 'ifobs':
        return named.read_ifobs(path)
    if key == 'alfa_csv':
        return named.read_alfa_csv(path)
    if key == 'alfa_xls':
        return named.read_alfa_xls(path)
    if key == 'ukrgaz':
        return named.read_ukrgaz(path)
    if key == 'otp_dat':
        return named.read_otp_dat(path)
    if key == 'dbf_oschad':
        return named.read_dbf_oschad(path)
    if key == 'dbf_univ':
        return named.read_dbf_ndoc(path, own_side='db', fmt='dbf:univ')
    if key == 'dbf_otp':
        return named.read_dbf_ndoc(path)
    if key == 'xml':
        return named.read_xml_rowdata(path)
    if key in ('zip_dbf_otp', 'zip_xml'):
        z = zipfile.ZipFile(path)
        ops = []
        m = {'rows_total': 0, 'fail': Counter(), 'members': 0, 'profile': key}
        for nm in sorted(z.namelist()):
            if nm.lower().endswith(('.dbf', '.xml')):
                o2, m2 = named.read_dbf_ndoc(z.read(nm)) if key == 'zip_dbf_otp' else named.read_xml_rowdata(z.read(nm))
                for o in o2:
                    o.flags.append('member:' + nm)
                ops += o2
                m['rows_total'] += m2['rows_total']
                m['fail'] += m2['fail']
                m['members'] += 1
        return ops, m
    raise ValueError(key)


def fix_ukrgaz(d):
    ops, meta = d['ops'], d['meta']
    res = {dk: named.ukrgaz_balance(ops, meta, dk) for dk in ('1', '2')}
    ok = [dk for dk, r in res.items() if r and all(r.values())]
    meta['balance_tests'] = res
    if len(ok) == 1:
        named.apply_ukrgaz_direction(ops, ok[0])
        meta['debit_dk'] = ok[0]


def load_all(root):
    out = {}
    for label, path, key in build(root):
        ops, meta = read_any(path, key)
        out[label] = dict(path=path, key=key, ops=ops, meta=meta)
        if key == 'ukrgaz':
            fix_ukrgaz(out[label])
    return out


def read_any_bytes(data, key):
    """Те саме, що read_any, але для вмісту файлу в пам'яті (не для zip-ключів)."""
    if key.startswith('zip_'):
        raise ValueError(key)
    return read_any(data, key)
