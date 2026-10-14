# -*- coding: utf-8 -*-
"""Оракул, режим «за розкладкою»: емуляція `ЗаповнитиСтроку` нинішніх обробок `epf/src` (ЗаполнитьСтроку).

Це НЕ запуск 1С. Прийняті припущення про платформу (не перевірені тут) — у PLATFORM_ASSUMPTIONS.
Два режими виходу:
  * «стара обробка» (mode='old')   — емуляція як є, з усіма особливостями й дефектами;
  * «очікуване»     (mode='expected') — стара + п'ять відступів плану 03 (Global Constraints), кожен —
    окрема іменована функція `dev1_…` … `dev5_…`. Будь-який інший відступ — питання планувальнику.

Кожен рядок результату — `Row`: номер у джерелі, статус, розібране (`r`) і помилки значень.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from .util import (CUR, CUR_NUM, DBF_LEGACY, cur_norm, parse_date, q2, read_dbf, read_text_lines, split_csv_quoted, ws)

PLATFORM_ASSUMPTIONS = [
    'КодировкаТекста.ANSI = cp1251 (залежить від машини)',
    'Число("1234.56") і Число("1234,56") обидва дають число; Число("") = 0; пробіл усередині числа -> помилка',
    'Сред(s, 0, n) трактується як Сред(s, 1, n)',
    'Дата("дд.мм.рррр г:хх:сс") приймає годину з однією цифрою; будь-який інший зіпсований рядок = помилка',
    'СтрЧислоСтрок("a;b;") враховує порожній хвіст (3 рядки)',
    'NUL усередині рядка файлу вилучається при читанні',
]

MODES = ('old', 'expected')


class Skip(Exception):
    """Рядок, який стара обробка пропускає (порожній код у першій колонці)."""


class BadValue(Exception):
    """Нерозібране значення (відступ 2): поле + сире значення."""

    def __init__(self, what, raw):
        super().__init__(what)
        self.what = what
        self.raw = raw


@dataclass
class Row:
    n: int                          # номер у джерелі (з одиниці): рядок файлу / запис DBF / елемент XML
    status: str                     # ok | skip | exc_num | exc_date | exc_index | bad
    r: Optional[dict] = None
    errors: list = field(default_factory=list)   # [(що, сире_значення)]


# ----------------------------------------------------------------- допоміжні, «як у 1С»
def mid(s, start, ln):
    if start < 1:
        start = 1
    return s[start - 1:start - 1 + ln]


def sl(x):
    return (x or '').strip()


def num1c(s):
    t = (s or '').strip()
    if t == '':
        return Decimal(0)
    if not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?', t):
        raise ValueError('num')
    return Decimal(t.replace(',', '.'))


def date1c(s):
    """'дд.мм.рррр[ г:хх[:сс]]' -> datetime; інакше ValueError('date')."""
    t = (s or '').strip()
    m = re.fullmatch(r'(\d{2})\.(\d{2})\.(\d{4})(?: (\d{1,2}):(\d{2})(?::(\d{2}))?)?', t)
    if not m:
        raise ValueError('date')
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                        int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0))
    except ValueError:
        raise ValueError('date')


def split_old(line):
    """Розбиття як у старій обробці (Акорд:100-124): `;` -> ПС, склейка частин у лапках без
    повернення `;` і без зняття лапок."""
    parts = line.split(';')
    res, cur, cont = [], '', False
    for p in parts:
        cur = (cur + p) if cont else p
        if p[:1] == '"' and p[-1:] != '"':
            cont = True
        if cont and p[-1:] == '"':
            cont = False
        if not cont:
            res.append(cur)
    return res


# ----------------------------------------------------------------- відступи 1–5 (кожен — окрема функція)
def dev1_split_quoted(line):
    """Відступ 1. CSV з лапками: лапки знімаються, `;` усередині лапок не рве поле, подвоєна лапка —
    одна лапка."""
    return [v for _, v, _ in split_csv_quoted(line)]


def dev2_amount(raw, allow_zero_on_error=False):
    """Відступ 2. Нерозібрана сума — помилка значення (BadValue), а не 0."""
    try:
        return num1c(raw)
    except ValueError:
        raise BadValue('amount', raw)


def dev2_date(raw_for_parse, raw_shown=None):
    """Відступ 2. Нерозібрана дата — помилка значення (BadValue), а не порожня дата й не втрата рядка."""
    try:
        return date1c(raw_for_parse)
    except ValueError:
        raise BadValue('date', raw_shown if raw_shown is not None else raw_for_parse)


def dev2_currency(raw):
    """Відступ 2. Валюта в контракті — числовий код ISO 4217 з трьох цифр або порожня. Буквений код
    перетворюється на числовий. Невідомий код — помилка значення."""
    t = (raw or '').strip()
    if t == '':
        return ''
    if re.fullmatch(r'\d{3}', t):
        return t
    c = CUR_NUM.get(t.upper())
    if c:
        return c
    raise BadValue('currency', raw)


def dev2_sens_fop_currency(raw_from_mfo_column):
    """Відступ 2 (окремий випадок). «Валюта» Сенсу-ФОП береться старим кодом з колонки МФО; це не
    валюта -> порожня валюта (= валюта рахунку)."""
    return ''


def dev3_foreign_accounts(rows, our_accounts):
    """Відступ 3. Рядки чужих рахунків не відкидаються мовчки, а йдуть у діагностику.
    -> {рахунок: [номери рядків у джерелі]} для рахунків, яких немає в our_accounts."""
    out = {}
    for row in rows:
        if row.status != 'ok':
            continue
        r = row.r
        a = (r['payer'] if r['dir'] == 'out' else r['recv'])[0]
        if a not in our_accounts:
            out.setdefault(a, []).append(row.n)
    return out


ENCODINGS = {}   # формат -> кодування, яке заявляє читач (ОписаниеЧитателя().Кодировка)


def dev4_reader_encoding(kind):
    """Відступ 4. Кодування заявляє читач, а не «ANSI» в коді розбору. У всіх файлових форматах етапу —
    windows-1251 (для XML — ще й декларація в самому файлі)."""
    return 'cp1251'


def dev5_oschad_no_temp_file():
    """Відступ 5. Ощад: жодного переміщення файлу користувача у фіксований тимчасовий файл.
    Оракул читає DBF із пам'яті, тож цей відступ у розборі нічого не змінює — функція існує, щоб
    відступ був названий і щоб тест 1С міг перевіряти саме його (інваріант: вхідний файл не чіпається)."""
    return True


# ----------------------------------------------------------------- розкладки
# Кожна розкладка: f -> dict. У режимі 'expected' нерозібране значення піднімає BadValue.
def _amount(raw, expected, tolerant=False):
    """tolerant — розкладка A: стара обробка при помилці суми пише 0 (і мовчить)."""
    if expected:
        return dev2_amount(raw)
    try:
        return num1c(raw)
    except ValueError:
        if tolerant:
            return Decimal(0)
        raise


def _date(raw, expected, shown=None):
    if expected:
        return dev2_date(raw, shown)
    return date1c(raw)


def _cur(raw, expected):
    return dev2_currency(raw) if expected else raw


def lay_A(f, expected=False):
    """Акорд, БанкВосток, Райффайзен, Універсал (сімейство A)."""
    if sl(f[0]) == '':
        raise Skip()
    r = {}
    r['num'] = sl(f[11])
    d = sl(f[4])
    ds = mid(d, 1, 2) + '.' + mid(d, 4, 2) + '.' + mid(d, 7, 4) + ' ' + mid(d, 12, 5) + ':00'
    r['date'] = _date(ds, expected, d)
    s = sl(f[13]).replace('.', ',').replace(' ', '')
    if s == '':
        s = sl(f[14]).replace('.', ',').replace(' ', '')
    r['amount'] = _amount(s, expected, tolerant=True)
    out = sl(f[14]).replace('.', ',').replace(' ', '') == ''
    own = (sl(f[2]), sl(f[0]), sl(f[1]))
    cp = (sl(f[8]), sl(f[9]), sl(f[6]), sl(f[10]))
    r['dir'] = 'out' if out else 'in'
    if out:
        r['payer'] = own + ('',); r['recv'] = cp
    else:
        r['recv'] = own + ('',); r['payer'] = cp
    r['cur'] = _cur(sl(f[3]), expected)
    r['purpose'] = sl(f[15])
    return r


def _a2(f, us, expected):
    r = {}
    r['num'] = sl(f[11])
    d = sl(f[4])
    tail = (d[-5:] + ':00') if us else d[-8:]
    r['date'] = _date(mid(d, 1, 2) + '.' + mid(d, 4, 2) + '.' + mid(d, 7, 4) + ' ' + tail, expected, d)
    raw_a = sl(f[13]) if sl(f[13]) != '' else sl(f[14])
    r['amount'] = _amount(raw_a, expected)
    out = sl(f[13]) != ''
    r['dir'] = 'out' if out else 'in'
    mf = (lambda i, j: sl(mid(f[i], 5, 6))) if us else (lambda i, j: sl(f[j]))
    own = (sl(f[2]), sl(f[0]), mf(2, 1))
    cp = (sl(f[8]), sl(f[9]), mf(8, 6), sl(f[10]))
    if out:
        r['payer'] = own + ('',); r['recv'] = cp
    else:
        r['recv'] = own + ('',); r['payer'] = cp
    r['cur'] = '' if us else _cur(sl(f[3]), expected)
    r['purpose'] = sl(f[15])
    return r


def lay_A2_procredit(f, expected=False):
    return _a2(f, False, expected)


def lay_A2_ukrsib(f, expected=False):
    return _a2(f, True, expected)


def lay_ukrgaz(f, expected=False):
    if sl(f[0]) == '':
        raise Skip()
    r = {}
    r['num'] = sl(f[5])
    d = sl(f[0])
    r['date'] = _date(mid(d, 1, 2) + '.' + mid(d, 4, 2) + '.' + mid(d, 7, 4) + ' 00:09:00', expected, d)
    s = sl(f[17]).replace('.', ',').replace(' ', '')
    r['amount'] = _amount(s, expected, tolerant=True)
    out = sl(f[7]) == '2'
    r['dir'] = 'out' if out else 'in'
    own = (sl(f[29]), sl(f[3]), sl(f[1]), '')
    cp = (sl(f[30]), sl(f[10]), sl(f[8]), sl(f[11]))
    if out:
        r['payer'], r['recv'] = own, cp
    else:
        r['recv'], r['payer'] = own, cp
    r['cur'] = _cur(sl(f[16]), expected)
    r['purpose'] = sl(f[19])
    return r


def lay_sens(f, expected=False):
    r = {}
    if len(sl(f[0])) > 10:       # «Юр. особа»: Альфа 19 колонок
        r['branch'] = 'tov'
        r['num'] = sl(f[10])
        d = sl(f[14])
        r['date'] = _date(mid(d, 1, 2) + '.' + mid(d, 4, 2) + '.' + mid(d, 7, 4) + ' ' + sl(f[13]), expected, d)
        r['amount'] = _amount(sl(f[11]).replace('.', ',').replace(' ', ''), expected)
        out = sl(f[2]) != 'Кредит'
        own = (sl(f[1]), sl(f[16]), sl(f[18]), '')
        cp = (sl(f[4]), sl(f[7]), sl(f[5]), sl(f[6]))
        r['cur'] = _cur(sl(f[12]), expected)
        r['purpose'] = sl(f[8])
    else:                         # «ФОП»: Альфа ФОП, 17 колонок
        r['branch'] = 'fop'
        r['num'] = sl(f[11])
        d = sl(f[0])
        r['date'] = _date(mid(d, 1, 2) + '.' + mid(d, 4, 2) + '.' + mid(d, 7, 4), expected, d)
        raw_a = sl(f[13]) if sl(f[13]) != '0' else sl(f[14])
        r['amount'] = _amount(raw_a, expected)
        out = sl(f[13]) != '0'
        own = (sl(f[4]), sl(f[1]), sl(f[3]), '')
        cp = (sl(f[8]), sl(f[9]), sl(f[6]), sl(f[10]))
        r['cur'] = dev2_sens_fop_currency(sl(f[3])) if expected else sl(f[3])
        r['purpose'] = sl(f[15])
    r['dir'] = 'out' if out else 'in'
    if out:
        r['payer'], r['recv'] = own, cp
    else:
        r['recv'], r['payer'] = own, cp
    return r


def lay_otp(l, expected=False):
    r = {}
    r['num'] = sl(mid(l, 132, 11))
    ds = mid(l, 1190, 2) + '.' + mid(l, 1188, 2) + '.20' + mid(l, 1186, 2)
    if expected:
        r['date'] = dev2_date(ds, mid(l, 1186, 6))
    else:
        try:
            r['date'] = date1c(ds)
        except ValueError:                 # стара обробка тут дати не має, але рядок не губить
            r['date'] = None
            r['date_bad'] = True
    r['amount'] = _amount(mid(l, 117, 16), expected) / 100
    # «1» -> надходження (за коментарем в коді — «исходящий», але сума йде в «Поступило»)
    r['dir'] = 'in' if sl(mid(l, 115, 1)) == '1' else 'out'
    r['payer'] = (sl(mid(l, 29, 29)), sl(mid(l, 976, 14)), sl(mid(l, 0, 10)), sl(mid(l, 185, 138)))
    r['recv'] = (sl(mid(l, 86, 29)), sl(mid(l, 1005, 14)), sl(mid(l, 58, 9)), sl(mid(l, 324, 138)))
    r['cur'] = None
    r['purpose'] = sl(mid(l, 464, 500))
    return r


def lay_oschad(d, expected=False):
    r = {}
    r['num'] = sl(d.get('ndoc'))
    raw = d.get('dt', '')
    r['date'] = None
    pd = parse_date(raw)[0]
    if pd is None:
        if expected:
            raise BadValue('date', raw)
        raise ValueError('date')
    r['date'] = datetime(pd.year, pd.month, pd.day)
    raw_a = d.get('summa', '').replace(' ', '').replace('\xa0', '')
    r['amount'] = _amount(raw_a, expected)
    out = int(sl(d.get('dk') or '0')) == 0
    r['dir'] = 'out' if out else 'in'
    own = (sl(d.get('acccli')), sl(d.get('okpocli')), sl(d.get('mfocli')), '')
    cp = (sl(d.get('acccor')), sl(d.get('okpocor')), sl(d.get('mfocor')), sl(d.get('namecor')))
    if out:
        r['payer'], r['recv'] = own, cp
    else:
        r['recv'], r['payer'] = own, cp
    r['cur'] = _cur(sl(d.get('val')), expected)
    r['purpose'] = (d.get('nazn') or '').strip()
    return r


def lay_pivd(a, expected=False):
    r = {}
    r['num'] = a.get('DOCUMENTNO', '')
    dd = a.get('DOCUMENTDATE', '')
    ds = mid(dd, 7, 2) + '.' + mid(dd, 5, 2) + '.' + mid(dd, 1, 4) + ' ' + mid(a.get('BOOKEDDATE', ''), 10, 8)
    r['date'] = _date(ds.strip(), expected, dd)
    r['amount'] = _amount(a.get('SUMMA', ''), expected) / 100
    out = a.get('OPERATIONID') == '0'
    r['dir'] = 'out' if out else 'in'
    own = (sl(a.get('IBAN')), sl(a.get('IDENTIFYCODE')), sl(a.get('BANKID')), '')
    cp = (sl(a.get('CORRIBAN')), sl(a.get('CORRIDENTIFYCODE')), sl(a.get('CORRBANKID')), sl(a.get('CORRCONTRAGENTSNAME')))
    if out:
        r['payer'], r['recv'] = own, cp
    else:
        r['recv'], r['payer'] = own, cp
    r['cur'] = _cur(a.get('CURRENCYID', ''), expected)
    r['purpose'] = (a.get('PLATPURPOSE', '') or '').replace('\n', ' ').strip()
    return r


# назва розкладки -> (функція, вид контейнера, ім'я «обробки-еталона»)
LAYOUTS = {
    'A': (lay_A, 'csv', 'Акорд/БанкВосток/Райффайзен/Універсал'),
    'A2_procredit': (lay_A2_procredit, 'csv', 'ПроКредит'),
    'A2_ukrsib': (lay_A2_ukrsib, 'csv', 'УкрСиб'),
    'ukrgaz': (lay_ukrgaz, 'csv', 'УкрГаз'),
    'sens': (lay_sens, 'csv', 'Сенс'),
    'otp': (lay_otp, 'lines', 'ОТП'),
    'oschad': (lay_oschad, 'dbf', 'Ощад'),
    'pivd': (lay_pivd, 'xml', 'Південний'),
}


# ----------------------------------------------------------------- запуск на файлі
def _run(lay, f, n, expected, status_list):
    try:
        r = lay(f, expected)
        status_list.append(Row(n, 'ok', r))
    except Skip:
        status_list.append(Row(n, 'skip'))
    except IndexError:
        status_list.append(Row(n, 'exc_index'))
    except BadValue as e:
        status_list.append(Row(n, 'bad', None, [(e.what, e.raw)]))
    except ValueError as e:
        status_list.append(Row(n, 'exc_' + str(e)))


def emulate(data, layout, mode='old', skip_first=True):
    """data — bytes файлу (для XML — також); layout — ключ LAYOUTS. -> список Row."""
    expected = mode == 'expected'
    lay, kind, _ = LAYOUTS[layout]
    enc = dev4_reader_encoding(kind) if expected else 'cp1251'
    res = []
    if kind == 'csv':
        lines, _ = read_text_lines(data, enc)
        split = dev1_split_quoted if expected else split_old
        for n, l in enumerate(lines, 1):
            if l.strip() == '' or (skip_first and n == 1):
                continue
            _run(lay, split(l), n, expected, res)
    elif kind == 'lines':
        lines, _ = read_text_lines(data, enc)
        for n, l in enumerate(lines, 1):
            if l.strip() == '':
                continue
            _run(lay, l, n, expected, res)
    elif kind == 'dbf':
        dev5_oschad_no_temp_file()
        # Модель старої обробки (XBase): обрізання на першому NUL, вилучені пропущені.
        fields, recs, _ = read_dbf(data, model=DBF_LEGACY, enc=enc)
        for n, r0 in enumerate(recs, 1):
            _run(lay, {k.lower(): v for k, v in r0.items()}, n, expected, res)
    elif kind == 'xml':
        root = ET.fromstring(data)
        for n, e in enumerate(root.iter('ROW'), 1):
            _run(lay, e.attrib, n, expected, res)
    else:
        raise ValueError(kind)
    return res


# ----------------------------------------------------------------- порівняння з розбором «за назвою»
KEY_FIELDS = ('номер', 'дата(=операції)', 'сума', 'напрям', 'рах.платника', 'рах.одержувача')


def compare(emu, ops):
    """Порівняння по рядках (однаковий порядок і кількість у обох списках, крім skip).
    -> (статуси, збіги по полях, всього по полях, рядків з усіма ключовими полями, кількість пар, збої ключових)."""
    from collections import Counter
    st = Counter(x.status for x in emu)
    fld, tot, keyfail = Counter(), Counter(), Counter()
    allkey = 0
    o_iter = iter(ops)
    pairs = []
    for x in emu:
        if x.status == 'skip':
            next(o_iter, None)
            continue
        o = next(o_iter, None)
        if o is None:
            break
        pairs.append((x, o))
    for x, o in pairs:
        if x.status != 'ok':
            continue
        r = x.r
        pay = (o.own_acc, o.own_edrpou, o.own_mfo, '') if o.direction == 'out' else (o.cp_acc, o.cp_edrpou, o.cp_mfo, o.cp_name)
        rec = (o.cp_acc, o.cp_edrpou, o.cp_mfo, o.cp_name) if o.direction == 'out' else (o.own_acc, o.own_edrpou, o.own_mfo, '')
        rd = r['date'].date() if r['date'] else None
        checks = {
            'номер': ws(r['num']) == ws(o.doc_no),
            'дата(=операції)': rd == o.date,
            'дата(=документа)': rd == o.doc_date,
            'сума': q2(r['amount']) == q2(o.amount),
            'напрям': r['dir'] == o.direction,
            'рах.платника': ws(r['payer'][0]) == ws(pay[0]),
            'код платника': ws(r['payer'][1]) == ws(pay[1]),
            'МФО платника': ws(r['payer'][2]) == ws(pay[2]) if ws(pay[2]) or ws(r['payer'][2]) else True,
            'рах.одержувача': ws(r['recv'][0]) == ws(rec[0]),
            'код одержувача': ws(r['recv'][1]) == ws(rec[1]),
            'МФО одержувача': ws(r['recv'][2]) == ws(rec[2]) if ws(rec[2]) or ws(r['recv'][2]) else True,
            'призначення': ws(r['purpose']) == ws(o.purpose),
            'призначення (ігн. лапки)': ws(r['purpose']).replace('"', '') == ws(o.purpose).replace('"', ''),
            'призначення (ігн. лапки і «;»)': ws(r['purpose']).replace('"', '').replace(';', '') == ws(o.purpose).replace('"', '').replace(';', ''),
            'призначення містить «;»': ';' in o.purpose,
        }
        if r.get('cur') is not None:
            checks['валюта'] = cur_norm(r['cur']) == o.currency
        if o.direction == 'out' and len(r['recv']) > 3:
            checks['назва контрагента'] = ws(r['recv'][3]) == ws(o.cp_name)
            checks['назва контрагента (ігн. лапки)'] = ws(r['recv'][3]).replace('"', '') == ws(o.cp_name).replace('"', '')
        elif o.direction == 'in' and len(r['payer']) > 3:
            checks['назва контрагента'] = ws(r['payer'][3]) == ws(o.cp_name)
            checks['назва контрагента (ігн. лапки)'] = ws(r['payer'][3]).replace('"', '') == ws(o.cp_name).replace('"', '')
        for k, v in checks.items():
            tot[k] += 1
            fld[k] += int(v)
        if all(checks[k] for k in KEY_FIELDS):
            allkey += 1
        else:
            for k in KEY_FIELDS:
                if not checks[k]:
                    keyfail[k] += 1
    return st, fld, tot, allkey, len(pairs), keyfail
