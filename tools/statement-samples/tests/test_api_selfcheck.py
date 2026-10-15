# -*- coding: utf-8 -*-
"""Самоперевірка оракула на прикладах з документації: зелена на справжньому оракулі й червона рівно там, де оракул
зламано (контроль, що вміє падати). Ламаємо оракул у пам'яті (mock), файли не змінюються."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, expected as E, kyiv, oracle_old as O, selfcheck, synth as S


def failed():
    return {n for n, ok, _ in selfcheck.run() if not ok}


class Selfcheck(unittest.TestCase):
    def test_green_on_the_real_oracle(self):
        self.assertEqual(failed(), set())

    def test_wrong_dst_rule_is_red_on_mono_examples_only(self):
        with mock.patch.object(kyiv, 'offset_hours', lambda utc: 2):          # завжди зима
            red = failed()
        self.assertIn('check_mono_personal_example', red)
        self.assertIn('check_mono_corp_example', red)
        self.assertNotIn('check_privat_trantype_d', red)                      # у ПриватБанку пояс не бере участі

    def test_purpose_composition_mutation_is_red(self):
        real = O._mono_purpose_full
        with mock.patch.object(O, '_mono_purpose_full', lambda tx, corp: real(dict(tx, cashbackAmount=0), corp)):
            red = failed()
        self.assertIn('check_mono_personal_example', red)

    def test_nonfinal_rule_mutation_is_red(self):
        with mock.patch.object(E, 'dev2_nonfinal', lambda out, disabled, n, state, moment, ident, old: old):
            red = failed()
        self.assertTrue({'check_privat_pr_pr_legend', 'check_mono_corp_statuses', 'check_mono_personal_example'} <= red)

    def test_identifier_choice_mutation_is_red(self):
        with mock.patch.object(E, 'dev7_privat_identifier', lambda raw, p, disabled: C.to_str(raw.get('REF'))):
            red = failed()
        self.assertIn('check_privat_example_expected', red)

    def test_direction_mutation_is_red(self):
        real = E._privat_items
        def swapped(out, items, p, disabled):
            for it in items:
                it.raw = dict(it.raw, TRANTYPE={'D': 'C', 'C': 'D'}.get(it.raw.get('TRANTYPE'), it.raw.get('TRANTYPE')))
            return real(out, items, p, disabled)
        with mock.patch.object(E, '_privat_items', swapped):
            red = failed()
        self.assertTrue({'check_privat_example_expected', 'check_privat_trantype_d'} <= red)

    def test_documented_limit_mutations_are_red(self):
        with mock.patch.object(C, 'PAGE_SIZE_MONO', 600):
            self.assertIn('check_documented_limits', failed())
        with mock.patch.object(C, 'FOP_WINDOW_SECONDS', 40 * 86400):
            self.assertIn('check_documented_limits', failed())
        with mock.patch.object(E, 'MONO_PAUSE_SECONDS', 10):
            self.assertIn('check_documented_limits', failed())

    def test_completed_time_ignored_is_red(self):
        real = S.R.body_json
        # юросіб: оракул «забув» completedTime — день документа береться за time
        with mock.patch.object(E, 'dev8_local_time', lambda sec, p, disabled: kyiv.unix_to_local(1719472805)):
            self.assertIn('check_mono_corp_example', failed())


if __name__ == '__main__':
    unittest.main()
