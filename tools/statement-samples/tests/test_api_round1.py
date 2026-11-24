# -*- coding: utf-8 -*-
"""Правила раунду 1 задачі 2: класи відмов за принципом «чи допоможе повтор», автентифікація при 200 + ERROR, порядок
фільтра статусів і дедуплікації, дублі ПриватБанку, межа довіри (D36 п. 10), перелік валют як у BSL, пояс сеансу,
сторож на згенерованому. Дані синтетичні."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import leakguard, synth as S


SCN = {(s.bank, s.sid): s for s in S.all_scenarios()}


class LeakGuard(unittest.TestCase):
    def test_clean_and_leaking(self):
        s = SCN[('privat', 'СинтСтатусы')]
        planted = s.params.account[-14:]                       # «сира» лексема, яка справді є у згенерованому
        n, bad = leakguard.scan_generated({planted}, {'Нікчемність'})
        self.assertGreater(n, 100)
        self.assertGreater(len(bad), 0)                        # контроль: сторож знаходить
        n, bad = leakguard.scan_generated({'99999999999999'}, {'Нікчемність'})
        self.assertEqual(bad, {})

    def test_control_can_fail(self):
        self.assertTrue(leakguard.control({'12345678901'}, {'Вигадане'}))
        self.assertFalse(leakguard.control(set(), set()))        # порожній лексикон: сторож нічого не вміє знаходити

    def test_allowed_words_live_in_a_separate_api_list(self):
        cfg = leakguard.api_config()
        from sslib import cfg as cfgmod
        shared = cfgmod.load()
        self.assertNotIn('ПриватБанк', shared['guard_allowed_words'])
        self.assertIn('ПриватБанк', cfg['guard_allowed_words'])


if __name__ == '__main__':
    unittest.main()
