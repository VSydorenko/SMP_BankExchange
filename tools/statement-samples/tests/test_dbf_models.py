# -*- coding: utf-8 -*-
"""Дві моделі читання DBF (sslib.util.read_dbf): модель продукту й модель старої обробки (XBase).

Дані синтетичні, вигадані тут. ОДИН файл містить NUL посеред поля, NUL у кінці поля після ведучого
пробілу й вилучений запис посередині: на ньому дві моделі дають різні, наперед відомі результати.

Запуск (з теки tools/statement-samples):  python -P -m unittest discover -s tests
"""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sslib.util import DBF_LEGACY, DBF_PRODUCT, read_dbf


def build_dbf(fields, records):
    """Збирає dBase III вручну. fields: [(ім'я, довжина)] (усі типу C); records: [(вилучений?, [байти поля...])]."""
    hlen = 32 + 32 * len(fields) + 1
    rlen = 1 + sum(ln for _, ln in fields)
    out = bytearray(b'\x03\x7c\x0a\x0e')
    out += struct.pack('<IHH', len(records), hlen, rlen)
    out += b'\x00' * 20
    for name, ln in fields:
        out += name.encode('ascii').ljust(11, b'\x00') + b'C' + b'\x00' * 4 + bytes([ln % 256, ln // 256]) + b'\x00' * 14
    out += b'\x0d'
    for deleted, values in records:
        out += b'*' if deleted else b' '
        for (_, ln), v in zip(fields, values):
            out += v.ljust(ln, b' ')
    out += b'\x1a'
    return bytes(out)


FIELDS = [('A', 10), ('B', 6)]
# 1: NUL посеред поля A; 2: вилучений; 3: ведучий пробіл, NUL у кінці перед добивкою.
DATA = build_dbf(FIELDS, [
    (False, [b'ab\x00cd', b'one']),
    (True, [b'zz', b'two']),
    (False, [b' x\x00', b'  y']),
])


class TwoDbfModels(unittest.TestCase):
    def test_product_model_nul_to_apostrophe_physical_numbers(self):
        fields, recs, meta = read_dbf(DATA, model=DBF_PRODUCT, enc='cp1251')
        self.assertEqual(recs, [{'A': "ab'cd", 'B': 'one'}, {'A': " x'", 'B': '  y'}])
        self.assertEqual(meta['numbers'], [1, 3])          # вилучений другий запис номер займає
        self.assertEqual(meta['deleted'], 1)

    def test_legacy_model_truncates_at_first_nul_ordinal_numbers(self):
        fields, recs, meta = read_dbf(DATA, model=DBF_LEGACY, enc='cp1251')
        self.assertEqual(recs, [{'A': 'ab', 'B': 'one'}, {'A': 'x', 'B': 'y'}])
        self.assertEqual(meta['numbers'], [1, 2])          # внутрішній порядковий номер, не фізичний
        self.assertEqual(meta['deleted'], 1)

    def test_models_differ_on_the_same_file(self):
        _, product, _ = read_dbf(DATA, model=DBF_PRODUCT, enc='cp1251')
        _, legacy, _ = read_dbf(DATA, model=DBF_LEGACY, enc='cp1251')
        self.assertNotEqual(product, legacy)

    def test_product_model_keeps_leading_and_strips_only_trailing_spaces(self):
        data = build_dbf([('A', 8)], [(False, [b'  ab  '])])
        _, recs, _ = read_dbf(data, model=DBF_PRODUCT, enc='cp1251')
        self.assertEqual(recs, [{'A': '  ab'}])

    def test_model_is_mandatory_and_validated(self):
        with self.assertRaises(TypeError):
            read_dbf(DATA)                                  # без моделі — помилка, не значення за замовчуванням
        with self.assertRaises(ValueError):
            read_dbf(DATA, model='xbase')


if __name__ == '__main__':
    unittest.main()
