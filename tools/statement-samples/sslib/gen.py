# -*- coding: utf-8 -*-
"""Генератори вигаданих значень для знеособлення: коди з правильною контрольною сумою, IBAN, слова,
призначення. Усе випадкове (SystemRandom); детермінованої заміни хешем немає. Мапа «реальне -> вигадане»
живе лише в об'єкті Fakes і зберігається користувачем у `temp/` (гітігноровано).

Контрольні суми тут рахуються власним кодом; валідуються вони НЕЗАЛЕЖНО — бібліотекою python-stdnum
(`stdnum.iban`, `stdnum.ua.edrpou`, `stdnum.ua.rntrc`) у перевірках і тестах інструменту.
"""
import random
import re

from .util import ws

UKR_C = 'бвгдзклмнпрстфхцчшжщ'
UKR_V = 'аеиіоуяюєї'
LAT_C = 'bcdfghklmnprstvz'
LAT_V = 'aeiou'
UKR_UP = 'АБВГДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЮЯ'
LAT_UP = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
WORD_RX = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]+(?:['’ʼ][A-Za-zА-Яа-яІіЇїЄєҐґ]+)*")
LATIN_RX = re.compile(r'[A-Za-z]')

# Категорії призначень і словник вигаданих фраз (малими літерами: жодного слова з великої літери).
CATEGORIES = [
    ('fee', re.compile(r'коміс|комис|commission')),
    ('tax', re.compile(r'податк|пдв|єсв|єдин\w+ внес|військов|збір|збор|подат|налог|ндс')),
    ('salary', re.compile(r'заробітн|зарплат|аванс|відпуск|лікарнян|відрядж|зарабо')),
    ('interest', re.compile(r'відсотк|процент|депозит|овердрафт')),
    ('services', re.compile(r'послуг|робіт|робот|ремонт|оренд|абонент|доставк|надан|обслуговуван|консульт')),
    ('goods', re.compile(r'товар|продукц|постачан|поставк|накладн|рахунок|рахунку|рах\.|рах-|оплата за')),
]
PHRASES = {
    'fee': ['комісія банку за обслуговування рахунку', 'комісія за виконання платіжної операції',
            'комісія за переказ коштів згідно тарифів', 'комісія за ведення рахунку за період'],
    'tax': ['сплата податку за період згідно декларації', 'єдиний податок за звітний період',
            'сплата військового збору за період', 'податок на додану вартість згідно рахунку'],
    'salary': ['виплата заробітної плати за період', 'аванс з заробітної плати за місяць',
               'виплата відпускних згідно наказу', 'заробітна плата за звітний місяць'],
    'interest': ['відсотки за користування коштами за період', 'нарахування відсотків за залишком коштів',
                 'відсотки за депозитом згідно угоди'],
    'services': ['оплата за надані послуги згідно договору', 'оплата послуг за звітний період',
                 'оплата за виконані роботи згідно акту', 'оренда приміщення за місяць згідно договору'],
    'goods': ['оплата за товар згідно рахунку', 'оплата за продукцію згідно накладної',
              'оплата за поставлений товар згідно договору', 'передоплата за товар згідно рахунку'],
    'other': ['платіж згідно договору', 'оплата згідно угоди', 'переказ коштів згідно домовленості'],
}
SHORT = {'fee': ['комісія банку', 'комісія за переказ'], 'tax': ['сплата податку', 'єдиний податок'],
         'salary': ['заробітна плата', 'аванс за місяць'], 'interest': ['відсотки за період', 'відсотки'],
         'services': ['оплата послуг', 'оплата робіт'], 'goods': ['оплата товару', 'оплата за товар'],
         'other': ['платіж', 'оплата']}
CONTROL = '\x00\n\r\t'
CONTROL_NO_NUL = '\n\r\t'


def category(text):
    t = text.casefold()
    for name, rx in CATEGORIES:
        if rx.search(t):
            return name
    return 'other'


# ----------------------------------------------------------------- контрольні суми (власний код)
def edrpou_check_digit(first7):
    """ЄДРПОУ: ваги 1..7 (для кодів, що починаються з 3,4,5: 7,1,2,3,4,5,6); якщо залишок 10 — ваги +2."""
    w = [1, 2, 3, 4, 5, 6, 7]
    if first7[0] in '345':
        w = [7, 1, 2, 3, 4, 5, 6]
    s = sum(a * int(d) for a, d in zip(w, first7))
    if s % 11 < 10:
        return str(s % 11)
    w = [a + 2 for a in w]
    s = sum(a * int(d) for a, d in zip(w, first7))
    return str(s % 11 % 10)


def rnokpp_check_digit(first9):
    """РНОКПП (ІПН): ваги -1,5,7,9,4,6,10,5,7; (сума mod 11) mod 10."""
    w = (-1, 5, 7, 9, 4, 6, 10, 5, 7)
    return str((sum(a * int(d) for a, d in zip(w, first9)) % 11) % 10)


def iban_check_digits(country, bban):
    """ISO 13616 / ISO 7064 mod 97-10: контрольні цифри для country + bban."""
    s = bban + country + '00'
    n = int(''.join(str(int(c, 36)) for c in s))
    return '%02d' % (98 - n % 97)


class Fakes:
    def __init__(self, rng=None, forbidden_words=(), forbidden_numbers=(), allowed_words=()):
        self.rng = rng or random.SystemRandom()
        self.forbidden_words = {w.casefold() for w in forbidden_words}
        self.forbidden_numbers = set(forbidden_numbers)
        self.allowed = set(allowed_words)
        self.m = {'code': {}, 'core': {}, 'word': {}, 'text': {}, 'scramble': {}, 'issued': []}
        self._issued = set()
        self.used_words = set()
        self._ident_used = set()

    # ----- персистентність
    def dump(self):
        return self.m

    def load(self, m):
        self.m = m
        self._issued = set(m.get('issued', []))
        self.used_words = {v.casefold() for v in m['word'].values()}
        self._ident_used = set(m.get('ident', {}).values())

    # ----- цифри
    def _digits(self, n, first_nonzero=False):
        s = ''.join(self.rng.choice('0123456789') for _ in range(n))
        if first_nonzero and n and s[0] == '0':
            s = self.rng.choice('123456789') + s[1:]
        return s

    def _text_digits(self, n):
        """Цифри всередині тексту (назва, призначення): числа з 5+ цифр реєструються як видані."""
        s = self._digits(n)
        if n >= 5 and s not in self._issued:
            self._issued.add(s)
            self.m['issued'].append(s)
        return s

    def _fresh_number(self, make, raw):
        for _ in range(10000):
            v = make()
            if v != raw and v not in self.forbidden_numbers:
                return v
        raise RuntimeError('не вдалося підібрати вигадане число')

    # ----- коди ЄДРПОУ / ІПН
    def code(self, value):
        v = value.strip()
        if v in self.m['code']:
            return self.m['code'][v]
        if re.fullmatch(r'\d{8}', v):
            def mk():
                p = self._digits(7, True)
                return p + edrpou_check_digit(p)
        elif re.fullmatch(r'\d{10}', v):
            def mk():
                p = '%05d' % self.rng.randint(18000, 40000) + self._digits(4)
                return p + rnokpp_check_digit(p)
        elif re.fullmatch(r'\d+', v):
            def mk():
                return self._digits(len(v), len(v) > 1)
        else:
            return self.scramble(v)
        out = self._fresh_number(mk, v)
        self.m['code'][v] = out
        return out

    # ----- рахунки
    def _core(self, stripped):
        if stripped in self.m['core']:
            return self.m['core'][stripped]
        n = len(stripped)

        def mk():
            return stripped[:4] + self._digits(n - 4) if n > 4 else self._digits(n)
        out = self._fresh_number(mk, stripped)
        self.m['core'][stripped] = out
        return out

    def account(self, value):
        v = value.strip()
        if re.fullmatch(r'UA\d{27}', v):
            bank, core = v[4:10], v[10:]
            st = core.lstrip('0')
            new = self._core(st).rjust(len(core), '0') if st else core
            bban = bank + new
            return 'UA' + iban_check_digits('UA', bban) + bban
        if re.fullmatch(r'\d+', v):
            st = v.lstrip('0')
            if not st:
                return v
            return '0' * (len(v) - len(st)) + self._core(st)
        return self.scramble(v)

    # ----- загальне перемішування (форма зберігається)
    def scramble(self, value):
        v = value
        if v in self.m['scramble']:
            return self.m['scramble'][v]
        out = []
        for ch in v:
            if ch.isdigit():
                out.append(self.rng.choice('0123456789'))
            elif ch.isalpha():
                if LATIN_RX.match(ch):
                    pool = LAT_UP if ch.isupper() else LAT_UP.lower()
                else:
                    pool = UKR_UP if ch.isupper() else UKR_UP.lower()
                out.append(self.rng.choice(pool))
            else:
                out.append(ch)
        res = ''.join(out)
        self.m['scramble'][v] = res
        return res

    # ----- слова й назви
    def _make_word(self, template):
        n = len(template)
        latin = bool(LATIN_RX.match(template[0]))
        C, V = (LAT_C, LAT_V) if latin else (UKR_C, UKR_V)
        for _ in range(1000):
            w = []
            start_c = self.rng.random() < 0.7
            for i in range(n):
                w.append(self.rng.choice(C if (i % 2 == 0) == start_c else V))
            s = ''.join(w)
            if template.isupper() and len(template) > 1:
                s = s.upper()
            elif template[0].isupper():
                s = s[0].upper() + s[1:]
            if s.casefold() not in self.forbidden_words and s.casefold() not in self.used_words:
                return s
        raise RuntimeError('не вдалося підібрати вигадане слово')

    def word(self, w):
        if w in self.allowed:
            return w
        # односимвольні (ініціали): випадкова велика літера того ж письма
        if len(w) == 1:
            pool = LAT_UP if LATIN_RX.match(w) else UKR_UP
            return self.rng.choice(pool)
        k = self._shape(w) + ':' + w.casefold()
        if k in self.m['word']:
            return self.m['word'][k]
        fake = self._make_word(w)
        self.used_words.add(fake.casefold())
        self.m['word'][k] = fake
        return fake

    @staticmethod
    def _shape(w):
        return 'U' if (w.isupper() and len(w) > 1) else ('T' if w[0].isupper() else 'l')

    def name(self, text):
        """Назва/ПІБ: слова замінюються вигаданими тієї ж довжини й регістру; юр. форми з allowed лишаються;
        лапки, розділові знаки й пробіли зберігаються; цифри перемішуються. Результат кешується за
        ws(текст), тож однакова назва в різних форматах однієї виписки дає однакову заміну."""
        key = 'name:' + ws(text)
        if key in self.m['text']:
            return self.m['text'][key]
        out = WORD_RX.sub(lambda m: self.word(m.group(0)), text)
        out = re.sub(r'\d+', lambda m: self._text_digits(len(m.group(0))), out)
        self.m['text'][key] = out
        return out

    # ----- призначення
    def _brand(self):
        return self._make_word(chr(0x410) + chr(0x430) * self.rng.randint(4, 7))

    def _phrase(self, cat, n):
        pool = [p for p in PHRASES[cat] + SHORT[cat] if len(p) <= max(n, 13)]
        return self.rng.choice(pool or [min(SHORT[cat], key=len)])

    def purpose(self, core):
        key = ws(core)
        if key in self.m['text']:
            return self.m['text'][key]
        cat = category(core)
        segs = core.split(';')
        out = []
        for seg in segs:
            body = seg.strip()
            lead = seg[:len(seg) - len(seg.lstrip())]
            trail = seg[len(seg.rstrip()):]
            if body == '':
                out.append(seg)
            elif re.fullmatch(r'[\d\W_]*', body):
                out.append(lead + re.sub(r'\d{5,}', lambda m: self._text_digits(len(m.group(0))), body) + trail)
            else:
                out.append(lead + self._phrase(cat, len(body)) + trail)
        res = ';'.join(out)
        # лапки: пари зберігаються (вигадана торгова назва), непарна лапка — як є
        nq = core.count('"')
        for _ in range(nq // 2):
            res = res.rstrip() + ' "' + self._brand() + '"'
        if nq % 2:
            res += '"'
        for o, c in (('«', '»'),):
            for _ in range(min(core.count(o), core.count(c))):
                res = res.rstrip() + ' ' + o + self._brand() + c
        # керівні символи (NUL, переноси) — на тих самих відносних позиціях
        res = self._restore_controls(core, res, CONTROL_NO_NUL)
        self.m['text'][key] = res
        return res

    @staticmethod
    def _restore_controls(raw, fake, chars=CONTROL):
        ctl = [(i, ch) for i, ch in enumerate(raw) if ch in chars]
        if not ctl:
            return fake
        out = list(fake)
        for i, ch in reversed(ctl):
            pos = min(len(out), int(round(i / max(len(raw), 1) * len(out))))
            out.insert(pos, ch)
        return ''.join(out)

    def doctype(self, core):
        key = 'doctype:' + core.casefold()
        if key not in self.m['text']:
            n = sum(1 for k in self.m['text'] if k.startswith('doctype:')) + 1
            self.m['text'][key] = 'вид документа %d' % n
        return self.m['text'][key]

    # ----- ідентифікатори (записи відповідей API) і числа з тексту JSON
    HEX_LOWER = '0123456789abcdef'
    HEX_UPPER = '0123456789ABCDEF'

    def _ident_shape(self, raw):
        """Випадкове значення тієї самої форми: цифра -> цифра, літера -> літера того ж регістру й письма, решта (розділювачі,
        зірочки, `=`) лишається. Рядок, що складається лише з hex-символів (UUID, GUID), лишається hex. Перша цифра
        ненульова, якщо була ненульовою."""
        alnum = [c for c in raw if c.isalnum()]
        hex_lower = bool(alnum) and all(c in self.HEX_LOWER for c in alnum) and any(c.isalpha() for c in alnum)
        hex_upper = bool(alnum) and all(c in self.HEX_UPPER for c in alnum) and any(c.isalpha() for c in alnum)
        out, first_digit = [], True
        for ch in raw:
            if ch.isdigit():
                pool = '123456789' if (first_digit and ch != '0') else '0123456789'
                first_digit = False
                out.append(self.rng.choice(pool))
            elif ch.isalpha():
                if hex_lower:
                    out.append(self.rng.choice('abcdef'))
                elif hex_upper:
                    out.append(self.rng.choice('ABCDEF'))
                elif LATIN_RX.match(ch):
                    out.append(self.rng.choice(LAT_UP if ch.isupper() else LAT_UP.lower()))
                else:
                    out.append(self.rng.choice(UKR_UP if ch.isupper() else UKR_UP.lower()))
            else:
                out.append(ch)
        return ''.join(out)

    def ident(self, value, refs=()):
        """Ідентифікатор (операції, запису, сторінки, рахунку банку): вигаданий тієї самої форми й довжини; одне значення --
        одна заміна на весь прогін, різні значення -- різні заміни. Якщо значення починається з одного з `refs` (REF
        ПриватБанку, з якого починається ідентифікатор операції), заміна починається із заміни цього `ref`: зв'язок
        «починається з» зберігається."""
        v = value
        table = self.m.setdefault('ident', {})
        if v in table:
            return table[v]
        if not any(c.isalnum() for c in v):
            return v
        pref = next((r for r in sorted(refs, key=len, reverse=True) if r and len(v) > len(r) and v.startswith(r)), None)
        for _ in range(1000):
            if pref:
                new = self.ident(pref, refs) + self._ident_shape(v[len(pref):])
            else:
                new = self._ident_shape(v)
            if new != v and new not in self._ident_used:
                break
        else:
            raise RuntimeError('не вдалося підібрати вигаданий ідентифікатор')
        self._ident_used.add(new)
        table[v] = new
        return new

    def number(self, token):
        """Число з тексту JSON (ціле чи з дробом, можливо зі знаком): та сама кількість цифр і розділювачі на місці, цифри
        випадкові, ціла частина без провідного нуля, якщо його не було; одне значення -- одна заміна."""
        table = self.m.setdefault('number', {})
        if token in table:
            return table[token]
        digits = sum(1 for c in token if c.isdigit())
        for _ in range(1000):
            new = self._ident_shape(token) if digits else token
            new = ''.join(ch if not ch.isalpha() else token[i] for i, ch in enumerate(new))     # 'e'/'E' експоненти лишаються
            if new != token or digits < 2:
                break
        table[token] = new
        return new

    # ----- диспетчер
    def apply(self, role, text, key=None):
        """Замінити значення поля ролі `role`. Початкові/кінцеві пробіли зберігаються."""
        core = text.strip()
        if core == '':
            return text
        lead = text[:len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        f = {'CODE': self.code, 'ACC': self.account, 'NAME': self.name, 'BANKNAME': self.name,
             'PURPOSE': self.purpose, 'SCRAMBLE': self.scramble, 'GAP': self.scramble,
             'DOCTYPE': self.doctype}[role]
        if role in ('NAME', 'BANKNAME', 'PURPOSE') and '\x00' in core:
            new = self._restore_controls(core, f(core.replace('\x00', '')), '\x00')
        else:
            new = f(core)
        if role in ('CODE', 'ACC', 'SCRAMBLE', 'GAP') and new not in self._issued:
            self._issued.add(new)
            self.m['issued'].append(new)
        return lead + new + trail

    def lookup(self, role, text):
        """Очікуване вигадане значення для перевірки (в): мапа вже заповнена, тож це читання."""
        return self.apply(role, text)
