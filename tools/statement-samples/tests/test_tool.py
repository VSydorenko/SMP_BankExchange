# -*- coding: utf-8 -*-
"""Тести інструменту зразків. Дані лише синтетичні (вигадані тут); сирих зразків немає.

Запуск (з теки tools/statement-samples):  python -P -m unittest discover -s tests
`-P`, а не `-I`: python-stdnum стоїть у користувацькому site-packages, який `-I` вимикає.

Валідатор кодів незалежний від генератора: генератор рахує контрольні суми власним кодом
(sslib/gen.py), а перевіряє їх бібліотека python-stdnum (`stdnum.iban`, `stdnum.ua.edrpou`,
`stdnum.ua.rntrc`) та опубліковані приклади з реєстру IBAN (SWIFT, ISO 13616) і з документації
python-stdnum до відповідних модулів."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdnum import iban as sn_iban
from stdnum.ua import edrpou as sn_edrpou, rntrc as sn_rntrc

from sslib import checks, containers, gen, legacy
from sslib.util import split_csv_quoted

# Опубліковані приклади (джерела в коментарях): IBAN registry (SWIFT): приклади для UA, GB, DE.
IBAN_REGISTRY = ['UA213223130000026007233566001', 'GB82WEST12345698765432', 'DE89370400440532013000']
# python-stdnum, docstring stdnum/ua/edrpou.py і stdnum/ua/rntrc.py
EDRPOU_EXAMPLE, EDRPOU_BAD = '32855961', '32855968'
RNTRC_EXAMPLE, RNTRC_BAD = '1759013776', '1759013770'


class GeneratorsAgainstIndependentValidator(unittest.TestCase):
    def test_published_iban_examples_reproduced(self):
        for v in IBAN_REGISTRY:
            self.assertTrue(sn_iban.is_valid(v))
            # власний генератор відтворює опубліковані контрольні цифри
            self.assertEqual(gen.iban_check_digits(v[:2], v[4:]), v[2:4])

    def test_published_edrpou_rnokpp_examples_reproduced(self):
        self.assertTrue(sn_edrpou.is_valid(EDRPOU_EXAMPLE))
        self.assertFalse(sn_edrpou.is_valid(EDRPOU_BAD))
        self.assertEqual(gen.edrpou_check_digit(EDRPOU_EXAMPLE[:7]), EDRPOU_EXAMPLE[7])
        self.assertTrue(sn_rntrc.is_valid(RNTRC_EXAMPLE))
        self.assertFalse(sn_rntrc.is_valid(RNTRC_BAD))
        self.assertEqual(gen.rnokpp_check_digit(RNTRC_EXAMPLE[:9]), RNTRC_EXAMPLE[9])

    def test_validator_can_fail(self):
        # контроль: валідатор відхиляє значення з псованою контрольною цифрою
        self.assertFalse(sn_iban.is_valid('UA223223130000026007233566001'))
        self.assertFalse(sn_edrpou.is_valid('12345678') and sn_edrpou.is_valid('12345679'))

    def test_generated_codes_valid_for_all_weight_branches(self):
        rng = random.Random(1)
        seen_345, seen_other, seen_recalc = 0, 0, 0
        for _ in range(20000):
            p = ''.join(rng.choice('0123456789') for _ in range(7))
            if p[0] == '0':
                continue
            c = gen.edrpou_check_digit(p)
            self.assertTrue(sn_edrpou.is_valid(p + c), p + c)
            seen_345 += p[0] in '345'
            seen_other += p[0] not in '345'
        for _ in range(20000):
            p = ''.join(rng.choice('0123456789') for _ in range(9))
            self.assertTrue(sn_rntrc.is_valid(p + gen.rnokpp_check_digit(p)))
        self.assertGreater(seen_345, 100)
        self.assertGreater(seen_other, 100)

    def test_fakes_codes_and_accounts(self):
        f = gen.Fakes(rng=random.Random(2))
        for raw in ('32855961', '12345678', '10000000'):
            v = f.code(raw)
            self.assertEqual(len(v), 8)
            self.assertNotEqual(v, raw)
            self.assertTrue(sn_edrpou.is_valid(v))
            self.assertEqual(f.code(raw), v)                      # одна заміна на значення
        v = f.code('1759013776')
        self.assertEqual(len(v), 10)
        self.assertTrue(sn_rntrc.is_valid(v))
        ib = f.account('UA213223130000026007233566001')
        self.assertTrue(sn_iban.is_valid(ib))
        self.assertEqual(ib[4:10], '322313')                    # код банку (МФО) зберігається
        self.assertNotEqual(ib[10:], '0000026007233566001')
        # зв'язок «IBAN <-> старий номер рахунку»: одна й та сама заміна ядра
        old = f.account('26007233566001')
        self.assertEqual(ib[10:].lstrip('0'), old)
        self.assertEqual(len(old), 14)

    def test_phrases_classify_back(self):
        for cat, phrases in gen.PHRASES.items():
            for p in phrases + gen.SHORT[cat]:
                self.assertEqual(gen.category(p), cat, p)
                self.assertEqual(p, p.lower())                    # жодного слова з великої літери


class CsvAndDeviations(unittest.TestCase):
    def test_quote_splitting_case_kinds(self):
        f = split_csv_quoted('a;"b;c";"d ""e"" f";')
        self.assertEqual([v for _, v, _ in f], ['a', 'b;c', 'd "e" f', ''])
        self.assertEqual([q for _, _, q in f], [False, True, True, False])
        self.assertEqual(legacy.dev1_split_quoted('x;"p;q";y'), ['x', 'p;q', 'y'])

    def test_deviation_2_unparsed_values(self):
        with self.assertRaises(legacy.BadValue):
            legacy.dev2_amount('1 234,56')
        with self.assertRaises(legacy.BadValue):
            legacy.dev2_date('32.13.2020')
        self.assertEqual(legacy.dev2_currency('UAH'), '980')
        self.assertEqual(legacy.dev2_currency(''), '')
        with self.assertRaises(legacy.BadValue):
            legacy.dev2_currency('XXX')
        self.assertEqual(legacy.dev2_sens_fop_currency('322313'), '')

    def test_old_mode_zero_amount_vs_expected_error(self):
        row = ['12345675', '322313', 'UA213223130000026007233566001', 'UAH', '15.03.2024 10:30', '', '300528', 'Bank',
               'UA573052800000026009467410469', '32855961', 'Name', '77', '15.03.2024', '', 'x', 'text', '']
        row[14] = 'abc'
        self.assertEqual(legacy.lay_A(list(row), False)['amount'], 0)   # стара обробка: 0
        with self.assertRaises(legacy.BadValue):
            legacy.lay_A(list(row), True)                               # очікуване: помилка значення


HEADER = ('ЄДРПОУ;МФО;Рахунок;Валюта;Дата операції;Код операції;МФО банка;Назва банка;Рахунок кореспондента;'
          'ЄДРПОУ кореспондента;Кореспондент;Номер документа;Дата документа;Дебет;Кредит;Призначення платежу;'
          'Гривневе покриття')


def synthetic_csv():
    """Вигаданий iFOBS-подібний CSV: усе значення згенеровано тут і не відповідає жодній реальній особі."""
    f = gen.Fakes(rng=random.Random(5))
    own_acc = f.account('UA213223130000026007233566001')
    rows = [HEADER]
    cps = [('Zorryk Company', '41234563', 'UA573052800000026009467410469'),
           ('Plum Trade', '31234561', 'UA693052800000026001234567890')]
    for i in range(6):
        name, code, acc = cps[i % 2]
        rows.append(';'.join([f.code('32855961'), '322313', own_acc, 'UAH', '15.03.2024 1%d:30' % i, '', '300528',
                              '"Test Bank"', f.account(acc), f.code(code), '"%s ""%s"""' % (name, name[:4]),
                              str(100 + i), '15.03.2024', '' if i % 2 else '%d.50' % (200 + i),
                              '%d.00' % (300 + i) if i % 2 else '', '"Purchase; of goods invoice %d%d"' % (50000 + i, 7),
                              '1.00']))
    return ('\r\n'.join(rows) + '\r\n').encode('cp1251')


SPEC = dict(container='csv', schema='ifobs', layout='A', named='ifobs', accepted=True, id='T', take_rows=None)
CFG = dict(allowed_words=['ТОВ'], verbatim_texts=[])
CRLF = b'\r\n'


class ChecksCanFail(unittest.TestCase):
    def setUp(self):
        self.raw = synthetic_csv()
        self.f = gen.Fakes(rng=random.Random(9), forbidden_words=['zorryk', 'plum', 'test'])
        self.anon = containers.walk(SPEC, self.raw, self.f.apply)
        self.issued = self.f.m['issued']

    def test_clean_anon_passes_all(self):
        self.assertTrue(checks.check_a(SPEC, self.raw, self.anon, CFG, self.issued)['ok'])
        self.assertTrue(checks.check_b(SPEC, self.raw, self.anon)['ok'])
        self.assertTrue(checks.check_c(SPEC, SPEC, self.raw, self.anon, self.f)['ok'])

    def test_a_control_on_raw_has_hits(self):
        r = checks.check_a(SPEC, self.raw, self.raw, CFG, self.issued, control=True)
        self.assertTrue(r['ok'])
        self.assertGreater(r['hits_lexemes'], 0)

    def test_a_catches_leaked_name(self):
        bank = b'"' + self.f.apply('BANKNAME', 'Test Bank').encode('cp1251') + b'"'
        self.assertIn(bank, self.anon)
        leaked = self.anon.replace(bank, b'"Zorryk Company"', 1)
        r = checks.check_a(SPEC, self.raw, leaked, CFG, self.issued)
        self.assertFalse(r['ok'])
        self.assertGreater(r['hits_lexemes'], 0)

    def test_a_catches_leaked_number_from_purpose(self):
        # сирий номер із призначення (50000) підмішано в призначення першого рядка даних (поле у лапках)
        fake = self.f.apply('PURPOSE', 'Purchase; of goods invoice 500007').encode('cp1251')
        self.assertIn(fake, self.anon)
        r = checks.check_a(SPEC, self.raw, self.anon.replace(fake, b'oplata 500007', 1), CFG, self.issued)
        self.assertFalse(r['ok'])

    def test_a_catches_unmapped_code_pattern(self):
        # 8-цифрове число поза мапою й поза збереженими полями -> шаблонний пошук
        bank = b'"' + self.f.apply('BANKNAME', 'Test Bank').encode('cp1251') + b'"'
        r = checks.check_a(SPEC, self.raw, self.anon.replace(bank, b'"87654321"', 1), CFG, self.issued)
        self.assertFalse(r['ok'])
        self.assertGreater(r['pattern']['unexplained'], 0)

    def test_b_catches_changed_structure(self):
        lines = self.anon.split(b'\r\n')
        broken = b'\r\n'.join(lines[:3] + [lines[3] + b';extra'] + lines[4:])
        with self.assertRaises(containers.SchemaError):
            checks.check_b(SPEC, self.raw, broken)         # зайва колонка без класифікації не проходить
        no_tail = CRLF.join(lines[:3] + [lines[3].replace(b'"', b'', 2)] + lines[4:])
        self.assertFalse(checks.check_b(SPEC, self.raw, no_tail)['ok'])   # зникли лапки
        short = b'\r\n'.join(lines[:-2]) + b'\r\n'
        self.assertFalse(checks.check_b(SPEC, self.raw, short)['ok'])

    def test_b_catches_bad_checksum(self):
        f = self.f
        some = [v for v in f.m['issued'] if len(v) == 8][0]
        bad = some[:-1] + str((int(some[-1]) + 1) % 10)
        broken = self.anon.replace(some.encode(), bad.encode())
        self.assertFalse(checks.check_b(SPEC, self.raw, broken)['ok'])

    def test_c_catches_changed_amount(self):
        text = self.anon.decode('cp1251').replace('301.00', '999.00').replace('200.50', '999.50')
        self.assertNotEqual(text.encode('cp1251'), self.anon)
        r = checks.check_c(SPEC, SPEC, self.raw, text.encode('cp1251'), self.f)
        self.assertFalse(r['ok'])

    def test_c_catches_unreplaced_field(self):
        # сирий код контрагента лишився -> розбір «замінене» бачить, що значення не вигадане
        r = checks.check_c(SPEC, SPEC, self.raw, self.raw, self.f)
        self.assertFalse(r['ok'])


if __name__ == '__main__':
    unittest.main()
