# -*- coding: utf-8 -*-
"""Оракул, режим «за назвою»: незалежні читачі форматів банківських виписок -> список Op.
Колонки CSV/XLS/DBF/XML знаходяться за назвою (CSV/XLS — за заголовком, норм. через norm_name).
Це не емуляція старої обробки (її розкладки за номерами колонок — у legacy.py), а друга, незалежна
лінія розбору: збіг двох ліній доводить, що розкладка прочитала саме те поле, яке названо.
Жоден читач не друкує значення полів.
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from decimal import Decimal

from .util import (DBF_PRODUCT, Op, cur_norm, q2, norm_name, parse_amount, parse_date, read_csv_rows, read_dbf,
                   read_text_lines)
from .biff import xls_table


# =====================================================================
# 1. CSV/XLS-таблиці з заголовком, колонки за назвою
# =====================================================================
# Таблиця синонімів: канонічне поле -> варіанти назв (всі пропускаються через norm_name,
# тому латинська i / кирилична і, регістр, зайві пробіли й лапки не мають значення).
SYN_IFOBS = {
    'own_edrpou': ['ЄДРПОУ', 'Код', 'ЕГРПОУ'],
    'own_mfo':    ['МФО', 'Код ID НБУ'],
    'own_name':   ['Плательщик'],
    'own_acc':    ['Рахунок', 'Счет'],
    'currency':   ['Валюта'],
    'op_date':    ['Дата операції', 'Дата операции'],
    'op_code':    ['Код операції', 'Код операции'],
    'cp_mfo':     ['МФО банка', 'МФО банку', 'Код ID НБУ надавача', 'МФО контрагента'],
    'cp_bank':    ['Назва банка', 'Надавач платіжних послуг', 'Название банка'],
    'cp_acc':     ['Рахунок кореспондента', 'Счет корреспондента'],
    'cp_edrpou':  ['ЄДРПОУ кореспондента', 'ЕГРПОУ корреспондента'],
    'cp_name':    ['Кореспондент', 'Корреспондент'],
    'doc_no':     ['Номер документа', 'Документ'],
    'doc_date':   ['Дата документа'],
    'debit':      ['Дебет'],
    'credit':     ['Кредит'],
    'purpose':    ['Призначення платежу', 'Назначение платежа'],
    'cover':      ['Гривневе покриття', 'Гривневое покрытие'],
}
SYN_ALFA = {
    'own_acc_old': ['Наш рахунок'],
    'own_acc':    ['Наш IBAN'],
    'direction':  ['Операція'],
    'cp_acc_old': ['Рахунок'],
    'cp_acc':     ['IBAN'],
    'cp_mfo':     ['МФО банку'],
    'cp_name':    ['Найменування контрагента'],
    'cp_edrpou':  ['Код контрагента'],
    'purpose':    ['Призначення платежу'],
    'op_date':    ['Дата проведення'],
    'doc_no':     ['Номер документа'],
    'amount':     ['Сума'],
    'currency':   ['Валюта'],
    'op_time':    ['Час проведення'],
    'doc_date':   ['Дата документа'],
    'arch_date':  ['Дата архівування'],
    'own_edrpou': ['ід.код', 'Ід.код'],
    'own_name':   ['Найменування'],
    'own_mfo':    ['МФО'],
}
SYN_UKRGAZ = {
    'op_date': ['DATA_VYP'], 'own_mfo': ['MFO'], 'own_acc_old': ['AC'], 'own_edrpou': ['OKPO'], 'own_name': ['NAME'],
    'doc_no': ['ND'], 'doc_date': ['DATA_D'], 'dk': ['DK'], 'cp_mfo': ['MFO_KOR'], 'cp_acc_old': ['AC_KOR'],
    'cp_edrpou': ['OKPO_KOR'], 'cp_name': ['NAME_KOR'], 'cur_alpha': ['CUR_CODE'], 'cur_tag': ['CUR_TAG'],
    'amount': ['SUM_PD_NOM'], 'amount_eq': ['SUM_PD_EQ'], 'purpose': ['PURPOSE'],
    'in_rst': ['IN_RST_NO'], 'out_rst': ['OUT_RST_NO'], 'db_sum': ['DB_SUM_NOM'], 'cr_sum': ['CR_SUM_NOM'],
    'own_acc': ['DB_IBAN'], 'cp_acc': ['CR_IBAN'],
}


def build_index(header, syn):
    """-> (idx: канон -> номер колонки, missing: список канонів без колонки, dup: канони з >1 збігом)."""
    nh = [norm_name(h) for h in header]
    idx, dup = {}, []
    for k, names in syn.items():
        for n in names:
            nn = norm_name(n)
            hits = [i for i, h in enumerate(nh) if h == nn]
            if hits:
                if len(hits) > 1:
                    dup.append(k)
                idx[k] = hits[0]
                break
    missing = [k for k in syn if k not in idx]
    return idx, missing, dup


def _g(row, idx, k):
    i = idx.get(k)
    return '' if i is None or i >= len(row) else (row[i] if row[i] is not None else '')


def _s(x):
    return str(x).strip() if x is not None else ''


FEE_CODES = {'ukrsib': {'06'}, 'nbu': {'5'}, 'procredit': {'T_F'}}


def detect_ifobs_profile(raw_header, rows_codes):
    joined = ';'.join(raw_header)
    if re.search(r'[а-яіїє]i|i[а-яіїє]', joined):   # латинська i поруч з кирилицею (УкрСиб)
        return 'ukrsib'
    if 'Код ID НБУ' in joined:
        return 'nbu'
    if any(re.match(r'^T_', c or '') for c in rows_codes):
        return 'procredit'
    if 'Дата операции' in joined:
        return 'alfa_fop'
    if 'Документ' in raw_header and 'Номер документа' not in raw_header:
        return 'aval'
    return 'ifobs'


def read_ifobs(src):
    """iFOBS-подібний CSV із заголовком (ПроКредит, Аваль, УкрСиб, Універсал, Восток, Акорд, Альфа ФОП)."""
    header, rows, cm = read_csv_rows(src)
    meta = {'rows_total': len(rows), 'csv': cm, 'header_cols': len(header), 'fail': Counter(), 'flags': Counter()}
    idx, missing, dup = build_index(header, SYN_IFOBS)
    meta['missing'] = missing
    meta['dup'] = dup
    prof = detect_ifobs_profile(header, [_g(r, idx, 'op_code') for r in rows])
    meta['profile'] = prof
    ops = []
    for n, r in enumerate(rows, 2):
        o = Op(fmt='ifobs:' + prof, src_row=n)
        o.date, o.time = parse_date(_s(_g(r, idx, 'op_date')))
        o.doc_date, _ = parse_date(_s(_g(r, idx, 'doc_date')))
        o.doc_no = _s(_g(r, idx, 'doc_no'))
        db, cr = parse_amount(_g(r, idx, 'debit')), parse_amount(_g(r, idx, 'credit'))
        dbp = db is not None and db != 0
        crp = cr is not None and cr != 0
        if dbp and crp:
            o.flags.append('debit_and_credit'); amount = None
        elif dbp:
            o.direction, amount = 'out', db
        elif crp:
            o.direction, amount = 'in', cr
        else:
            o.flags.append('no_amount'); amount = None
        if amount is not None and amount < 0:
            o.flags.append('negative_amount'); amount = abs(amount)
        o.amount = amount
        o.own_acc, o.own_edrpou, o.own_mfo = _s(_g(r, idx, 'own_acc')), _s(_g(r, idx, 'own_edrpou')), _s(_g(r, idx, 'own_mfo'))
        o.cp_acc, o.cp_edrpou, o.cp_mfo = _s(_g(r, idx, 'cp_acc')), _s(_g(r, idx, 'cp_edrpou')), _s(_g(r, idx, 'cp_mfo'))
        o.cp_name, o.cp_bank = _s(_g(r, idx, 'cp_name')), _s(_g(r, idx, 'cp_bank'))
        o.purpose = _s(_g(r, idx, 'purpose'))
        o.currency = cur_norm(_g(r, idx, 'currency'))
        o.op_code = _s(_g(r, idx, 'op_code'))
        if prof in FEE_CODES:
            o.fee_by_code = o.op_code in FEE_CODES[prof]
        # знаковість «гривневого покриття» (лише довідково для перевірки напряму)
        cv = parse_amount(_g(r, idx, 'cover'))
        if cv is not None and cv < 0:
            o.flags.append('cover_negative')
        if o.date is None or o.amount is None or o.direction is None:
            meta['fail']['date' if o.date is None else ('amount_dir')] += 1
        ops.append(o)
    return ops, meta


def _alfa_from_rows(header, rows, fmt):
    idx, missing, dup = build_index(header, SYN_ALFA)
    meta = {'rows_total': len(rows), 'header_cols': len(header), 'fail': Counter(), 'missing': missing, 'dup': dup, 'profile': 'alfa_tov'}
    ops = []
    for n, r in enumerate(rows, 2):
        o = Op(fmt=fmt, src_row=n)
        o.date, o.time = parse_date(_s(_g(r, idx, 'op_date')))
        t = _s(_g(r, idx, 'op_time'))
        if t:
            m = re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?$', t)
            if m:
                o.time = '%02d:%s:%s' % (int(m.group(1)), m.group(2), m.group(3) or '00')
        o.doc_date, _ = parse_date(_s(_g(r, idx, 'doc_date')))
        o.doc_no = _s(_g(r, idx, 'doc_no'))
        a = parse_amount(_g(r, idx, 'amount'))
        if a is not None and a < 0:
            o.flags.append('negative_amount'); a = abs(a)
        o.amount = a
        d = norm_name(_s(_g(r, idx, 'direction')))
        o.direction = {'дебет': 'out', 'кредит': 'in'}.get(d)
        o.own_acc = _s(_g(r, idx, 'own_acc')) or _s(_g(r, idx, 'own_acc_old'))
        o.own_edrpou = _s(_g(r, idx, 'own_edrpou')).split('.')[0]
        o.own_mfo = _s(_g(r, idx, 'own_mfo')).split('.')[0]
        o.cp_acc = _s(_g(r, idx, 'cp_acc')) or _s(_g(r, idx, 'cp_acc_old'))
        o.cp_edrpou = _s(_g(r, idx, 'cp_edrpou')).split('.')[0]
        o.cp_mfo = _s(_g(r, idx, 'cp_mfo')).split('.')[0]
        o.cp_name = _s(_g(r, idx, 'cp_name'))
        o.purpose = _s(_g(r, idx, 'purpose'))
        o.currency = cur_norm(_g(r, idx, 'currency'))
        if o.date is None or o.amount is None or o.direction is None:
            meta['fail']['row'] += 1
        ops.append(o)
    return ops, meta


def read_alfa_csv(src):
    header, rows, cm = read_csv_rows(src)
    ops, meta = _alfa_from_rows(header, rows, 'alfa_tov:csv')
    meta['csv'] = cm
    return ops, meta


def read_alfa_xls(src):
    header, rows, xm = xls_table(src)
    ops, meta = _alfa_from_rows(header, rows, 'alfa_tov:xls')
    meta['xls'] = xm
    return ops, meta


# =====================================================================
# 2. УкрГаз
# =====================================================================
def read_ukrgaz(src):
    header, rows, cm = read_csv_rows(src)
    idx, missing, dup = build_index(header, SYN_UKRGAZ)
    meta = {'rows_total': len(rows), 'csv': cm, 'missing': missing, 'dup': dup, 'fail': Counter(), 'profile': 'ukrgaz'}
    ops = []
    bal = {'in': set(), 'out': set(), 'dbsum': set(), 'crsum': set()}
    for n, r in enumerate(rows, 2):
        o = Op(fmt='ukrgaz', src_row=n)
        o.date, _ = parse_date(_s(_g(r, idx, 'op_date')))
        o.doc_date, _ = parse_date(_s(_g(r, idx, 'doc_date')))
        o.doc_no = _s(_g(r, idx, 'doc_no'))
        o.amount = parse_amount(_g(r, idx, 'amount'))
        dk = _s(_g(r, idx, 'dk'))
        o.op_code = dk                      # напрям тимчасово у op_code; значення DK->in/out вирішує fix_ukrgaz_direction
        o.own_acc = _s(_g(r, idx, 'own_acc'))
        o.own_edrpou, o.own_mfo = _s(_g(r, idx, 'own_edrpou')), _s(_g(r, idx, 'own_mfo'))
        o.cp_acc = _s(_g(r, idx, 'cp_acc'))
        o.cp_edrpou, o.cp_mfo = _s(_g(r, idx, 'cp_edrpou')), _s(_g(r, idx, 'cp_mfo'))
        o.cp_name = _s(_g(r, idx, 'cp_name'))
        o.purpose = _s(_g(r, idx, 'purpose'))
        o.currency = cur_norm(_g(r, idx, 'cur_alpha') or _g(r, idx, 'cur_tag'))
        if re.search(r'[Ee]\+\d', _s(_g(r, idx, 'cp_acc_old'))):
            o.flags.append('cp_acc_old_exponent')
        bal['in'].add(_s(_g(r, idx, 'in_rst'))); bal['out'].add(_s(_g(r, idx, 'out_rst')))
        bal['dbsum'].add(_s(_g(r, idx, 'db_sum'))); bal['crsum'].add(_s(_g(r, idx, 'cr_sum')))
        ops.append(o)
    meta['balances'] = bal
    # напрям: з балансового рівняння (див. balance_check), а не з коду — тут лише зберігаємо DK
    return ops, meta


def ukrgaz_balance(ops, meta, debit_dk):
    """Перевірка: вхідний + надходження − списання = вихідний, за гіпотезою «DK==debit_dk — списання»."""
    bal = meta['balances']
    if any(len(v) != 1 for v in bal.values()):
        return None
    vin, vout = parse_amount(next(iter(bal['in']))), parse_amount(next(iter(bal['out'])))
    dbs, crs = parse_amount(next(iter(bal['dbsum']))), parse_amount(next(iter(bal['crsum'])))
    deb = sum((o.amount for o in ops if o.op_code == debit_dk), Decimal(0))
    cre = sum((o.amount for o in ops if o.op_code != debit_dk), Decimal(0))
    return {'eq_balance': q2(vin + cre - deb) == q2(vout), 'eq_turn_db': q2(deb) == q2(dbs), 'eq_turn_cr': q2(cre) == q2(crs)}


def apply_ukrgaz_direction(ops, debit_dk):
    for o in ops:
        o.direction = 'out' if o.op_code == debit_dk else 'in'


# =====================================================================
# 3. ОТП: текст фіксованої ширини (.dat/.txt), два покоління
# =====================================================================
# Межі полів [початок, кінець) 0-based. Виведено зіставленням з DBF тих самих виписок (probe_dat/probe_txt).
OTP_OLD = dict(width=660, mfo_db=(0, 9), rr_db=(9, 28), iban_db=(28, 57), mfo_cr=(57, 66), rr_k=(66, 85), iban_k=(85, 114),
               flag=(114, 115), amount=(115, 131), kind=(131, 133), doc_no=(133, 143), cur=(143, 146),
               dat=(146, 152), dat_pr=(152, 158), name_d=(158, 196), name_k=(196, 234), purpose=(234, 394),
               okpo_db=(459, 473), okpo_cr=(473, 487), bank_id=(487, 496), dat_end=(654, 660))
OTP_NEW = dict(width=1191, mfo_db=(0, 9), rr_db=(9, 28), iban_db=(28, 57), mfo_cr=(57, 66), rr_k=(66, 85), iban_k=(85, 114),
               flag=(114, 115), amount=(115, 131), kind=(131, 133), doc_no=(133, 168), cur=(168, 171),
               dat=(171, 177), dat_pr=(177, 183), name_d=(183, 323), name_k=(323, 463), purpose=(463, 883),
               okpo_db=(948, 983), okpo_cr=(983, 1018), bank_id=(1018, 1027), dat_end=(1185, 1191))


def read_otp_dat(src):
    lines, nul = read_text_lines(src)
    lines = [l for l in lines if l.strip() != '']
    widths = Counter(len(l) for l in lines)
    meta = {'rows_total': len(lines), 'widths': dict(widths), 'nul': nul, 'fail': Counter(), 'profile': 'otp_fixed'}
    ops = []
    for n, l in enumerate(lines, 1):
        lay = OTP_NEW if len(l) == 1191 else OTP_OLD if len(l) == 660 else None
        if lay is None:
            meta['fail']['unknown_width'] += 1
            continue
        f = lambda k: l[lay[k][0]:lay[k][1]].strip()
        o = Op(fmt='otp:dat%d' % lay['width'], src_row=n)
        yy, yp = f('dat'), f('dat_end')   # дата операції = кінець рядка (збігається з DAT_PR у DBF у 233/233; [dat_pr] розходиться у 2 з 233)
        o.doc_date, _ = parse_date('20' + yy) if len(yy) == 6 and yy.isdigit() else (None, None)
        o.date, _ = parse_date('20' + yp) if len(yp) == 6 and yp.isdigit() else (None, None)
        o.doc_no = f('doc_no')
        a = parse_amount(f('amount'))
        o.amount = None if a is None else a / 100
        fl = f('flag')
        o.direction = {'0': 'out', '1': 'in'}.get(fl)         # див. звіт: 0=дебет(списання), 1=кредит(надходження)
        o.op_code = f('kind')
        # власна сторона визначається напрямом: списання -> платник власний, надходження -> одержувач
        sides = (('iban_db', 'okpo_db', 'mfo_db', 'name_d'), ('iban_k', 'okpo_cr', 'mfo_cr', 'name_k'))
        own, cp = (sides[0], sides[1]) if o.direction == 'out' else (sides[1], sides[0])
        o.own_acc, o.own_edrpou, o.own_mfo = f(own[0]), f(own[1]), f(own[2])
        o.cp_acc, o.cp_edrpou, o.cp_mfo, o.cp_name = f(cp[0]), f(cp[1]), f(cp[2]), f(cp[3])
        o.purpose = f('purpose')
        o.currency = cur_norm(f('cur'))
        o.bank_id = f('bank_id')
        if o.date is None or o.amount is None or o.direction is None:
            meta['fail']['row'] += 1
        ops.append(o)
    return ops, meta


# =====================================================================
# 4. DBF
# =====================================================================
def _read_dbf_named(src):
    """Розбір «за назвою» представляє ПРОДУКТ: контейнер ЗаписиDBF (модель 'product': NUL -> апостроф, справа
    лише пробіли, фізична нумерація) і далі те, що робить модуль формату зі значеннями (.strip() — СокрЛП).
    Старій обробці відповідає legacy.py (модель 'legacy')."""
    fields, recs, dm = read_dbf(src, model=DBF_PRODUCT)
    recs = [{k: v.strip() for k, v in r.items()} for r in recs]
    return fields, recs, dm


def read_dbf_oschad(src):
    fields, recs, dm = _read_dbf_named(src)
    low = lambda r: {k.lower(): v for k, v in r.items()}
    meta = {'rows_total': len(recs), 'dbf': dm, 'fields': [f[0] for f in fields], 'fail': Counter(), 'profile': 'oschad_dbf'}
    ops = []
    for n, r0 in enumerate(recs, 1):
        r = low(r0)
        o = Op(fmt='dbf:oschad', src_row=dm['numbers'][n - 1])
        o.date, _ = parse_date(r.get('dt'))
        o.doc_no = r.get('ndoc', '')
        o.amount = parse_amount(r.get('summa'))
        o.direction = {'0': 'out', '1': 'in'}.get(r.get('dk', '').strip())
        o.own_acc, o.own_edrpou, o.own_mfo = r.get('acccli', ''), r.get('okpocli', ''), r.get('mfocli', '')
        o.cp_acc, o.cp_edrpou, o.cp_mfo, o.cp_name, o.cp_bank = r.get('acccor', ''), r.get('okpocor', ''), r.get('mfocor', ''), r.get('namecor', ''), r.get('bankcor', '')
        o.purpose = r.get('nazn', '')
        o.currency = cur_norm(r.get('val', ''))
        o.bank_id = r.get('uetr', '')
        if o.date is None or o.amount is None or o.direction is None:
            meta['fail']['row'] += 1
        ops.append(o)
    return ops, meta


def read_dbf_ndoc(src, debit_operat='1', own_side='by_operat', fmt='dbf:ndoc'):
    """DBF n_doc…tim_pr (Універсал: lowercase, ОТП: UPPERCASE + IBAN_DB/IBAN_K).
    OPERAT: debit_operat — значення «списання». own_side: 'by_operat' (ОТП: власний боком платника при списанні)
    або 'db' (Універсал: власний завжди в *_db)."""
    fields, recs, dm = _read_dbf_named(src)
    names = [f[0].lower() for f in fields]
    meta = {'rows_total': len(recs), 'dbf': dm, 'fields': names, 'fail': Counter(), 'profile': 'ndoc_dbf'}
    has_iban = 'iban_db' in names
    ops = []
    for n, r0 in enumerate(recs, 1):
        r = {k.lower(): v for k, v in r0.items()}
        o = Op(fmt=fmt, src_row=dm['numbers'][n - 1])
        o.date, _ = parse_date(r.get('dat_pr') or r.get('dat'))
        d1, _ = parse_date(r.get('dat'))
        o.doc_date = d1
        t = r.get('tim_pr', '')
        o.time = t if re.fullmatch(r'\d{2}:\d{2}:\d{2}', t or '') else None
        o.doc_no = r.get('n_doc', '')
        a = parse_amount(r.get('sum'))
        o.amount = a
        op = r.get('operat', '').strip()
        o.op_code = op
        o.direction = ('out' if op == debit_operat else 'in') if op in ('1', '2') else None
        db = dict(acc=r.get('iban_db') if has_iban else r.get('rr_db'), edr=r.get('okpo_db'), mfo=r.get('mfo_db'), name=r.get('naim_d'))
        cr = dict(acc=r.get('iban_k') if has_iban else r.get('rr_k'), edr=r.get('okpo_cr'), mfo=r.get('mfo_cr'), name=r.get('naim_k'))
        if own_side == 'db' or o.direction == 'out':
            own, cp = db, cr
        else:
            own, cp = cr, db
        o.own_acc, o.own_edrpou, o.own_mfo = own['acc'] or '', own['edr'] or '', own['mfo'] or ''
        o.cp_acc, o.cp_edrpou, o.cp_mfo, o.cp_name = cp['acc'] or '', cp['edr'] or '', cp['mfo'] or '', cp['name'] or ''
        o.purpose = (r.get('prizn', '') + ' ' + r.get('prizn_end', '')).strip() if 'prizn_end' in r else (r.get('prizn', '') + (' ' + r['prizn2'] if r.get('prizn2') else '')).strip()
        o.currency = cur_norm(r.get('kod_val', ''))
        if o.date is None or o.amount is None or o.direction is None:
            meta['fail']['row'] += 1
        ops.append(o)
    return ops, meta


# =====================================================================
# 5. XML ROWDATA/ROW (Південний, ОТП; Сбер ідентичний)
# =====================================================================
def read_xml_rowdata(src, scale=Decimal(100)):
    b = open(src, 'rb').read() if isinstance(src, str) else src
    root = ET.fromstring(b)
    rows = list(root.iter('ROW'))
    meta = {'rows_total': len(rows), 'root': root.tag, 'fail': Counter(), 'profile': 'xml_rowdata', 'attrs': Counter()}
    ops = []
    for n, e in enumerate(rows, 1):
        a = e.attrib
        meta['attrs'].update(a.keys())
        o = Op(fmt='xml:rowdata', src_row=n)
        o.doc_no = a.get('DOCUMENTNO', '')
        o.doc_date, _ = parse_date(a.get('DOCUMENTDATE'))
        bk = a.get('BOOKEDDATE', '')
        o.date, _ = parse_date(bk[:8]) if bk else (None, None)
        if o.date is None:
            o.date = o.doc_date
        m = re.match(r'^\d{8}T(\d{2}):(\d{2}):(\d{2})', bk)
        o.time = '%s:%s:%s' % m.groups() if m else None
        s = parse_amount(a.get('SUMMA'))
        o.amount = None if s is None else s / scale
        o.direction = {'0': 'out', '1': 'in'}.get(a.get('OPERATIONID'))
        o.own_acc = a.get('IBAN') or a.get('ACCOUNTNO', '')
        o.own_edrpou, o.own_mfo = a.get('IDENTIFYCODE', ''), a.get('BANKID', '')
        o.cp_acc = a.get('CORRIBAN') or a.get('CORRACCOUNTNO', '')
        o.cp_edrpou, o.cp_mfo = a.get('CORRIDENTIFYCODE', ''), a.get('CORRBANKID', '')
        o.cp_name, o.cp_bank = a.get('CORRCONTRAGENTSNAME', ''), a.get('CORRBANKNAME', '')
        o.purpose = (a.get('PLATPURPOSE', '') or '').replace('\n', ' ').strip()
        o.currency = cur_norm(a.get('CURRSYMBOLCODE') or a.get('CURRENCYID', ''))
        o.bank_id = a.get('DATAVERSION', '')
        o.op_code = a.get('DOCUMENTTYPEID', '')
        if o.date is None or o.amount is None or o.direction is None:
            meta['fail']['row'] += 1
        ops.append(o)
    return ops, meta
