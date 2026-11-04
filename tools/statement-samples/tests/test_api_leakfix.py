# -*- coding: utf-8 -*-
"""Контроль знеособлення ролі ID у полях KEEP (раунд run3): значення DLR / REF, що стоїть підрядком у NUM_DOC ПриватБанку, замінюється тією ж заміною з мапи; перевірка (а) без заміни дає збіги.
Тест читає сирий запис і мапу (поза git: основне дерево `temp/api-recordings`); без них пропускається (skipped ≠ зелений). Значень не друкує."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import anonymize as A, step2

RAW = 'R:/github/SMP_BankExchange/temp/api-recordings/privat/run1'
MAP = 'R:/github/SMP_BankExchange/temp/api-recordings/_anon-map/privat.json'


@unittest.skipUnless(os.path.isdir(RAW) and os.path.isfile(MAP), 'сирого запису й мапи немає: контроль не виконано')
class NumDocSweep(unittest.TestCase):
    def anonymize(self, tmp, sweep_ids):
        mp = os.path.join(tmp, 'map.json')
        shutil.copy(MAP, mp)
        out = os.path.join(tmp, 'anon' + ('1' if sweep_ids else '0'))
        orig = A.Bank.build_sweep

        def build(self):
            if not sweep_ids:
                self.ids, self.accs = (), ()
            orig(self)
        A.Bank.build_sweep = build
        try:
            A.anonymize_bank('privat', RAW, out, mp)
        finally:
            A.Bank.build_sweep = orig
        return out

    def test_check_a_is_green_with_the_sweep_and_red_without_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            with_sweep = step2.check_a('privat', RAW, self.anonymize(tmp, True))
            without = step2.check_a('privat', RAW, self.anonymize(tmp, False))
        self.assertEqual(with_sweep['hits'], 0)
        self.assertGreater(without['hits'], 0)                  # контроль уміє впасти: без заміни в NUM_DOC перевірка (а) знаходить значення ролі ID


if __name__ == '__main__':
    unittest.main()
