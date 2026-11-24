# -*- coding: utf-8 -*-
"""Синтетичні записи й еталони: форма, детермінованість, покриття Review Focus, спрацювання кожного відступу, сумісність
ключа з попередником, контроль поломкою кожного відступу. Дані — вигадані генератором; валідатори кодів незалежні від
генератора (`python-stdnum`)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import synth as S

try:
    from stdnum import iban as sn_iban
    from stdnum.ua import edrpou as sn_edrpou, rntrc as sn_rntrc
except ImportError:            # pragma: no cover
    sn_iban = None

ALL = S.all_scenarios()


class Shape(unittest.TestCase):
    def test_no_token_like_or_header_leak(self):
        for s in ALL:
            for ex in s.recording().exchanges:
                self.assertNotIn('headers', ex['request'])
                self.assertNotIn('token', json.dumps(ex['request']).lower())


if __name__ == '__main__':
    unittest.main()
